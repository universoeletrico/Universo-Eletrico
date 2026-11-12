"""Conexao OAuth oficial com Mercado Livre para o Universo Eletrico Studio.

Os segredos da aplicacao permanecem apenas nas variaveis de ambiente da Render.
Access/refresh tokens sao criptografados e persistidos em PostgreSQL dedicado
(nunca no repositorio GitHub, no cache local ou na cookie de sessao).
A aplicacao Mercado Livre precisa de acesso de leitura e offline_access.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
CALLBACK_URL = "https://universo-eletrico-studio.onrender.com/integracoes/mercado-livre/callback"
NECESSARY = ("MELI_CLIENT_ID", "MELI_CLIENT_SECRET", "MELI_DATABASE_URL", "MELI_TOKEN_KEY")


def missing_settings():
    return [name for name in NECESSARY if not os.environ.get(name, "").strip()]


def configured():
    return not missing_settings() and len(os.environ.get("MELI_TOKEN_KEY", "")) >= 32


def create_oauth_request():
    """Prepara parametros OAuth state + PKCE, que devem ser ligados a sessao autenticada."""
    if not configured():
        raise ValueError("Integração ainda não configurada na Render.")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    url = AUTH_URL + "?" + urlencode({
        "response_type": "code", "client_id": os.environ["MELI_CLIENT_ID"],
        "redirect_uri": CALLBACK_URL,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return {"url": url, "state": state, "code_verifier": verifier}


def cipher():
    from cryptography.fernet import Fernet
    raw = os.environ.get("MELI_TOKEN_KEY", "")
    if len(raw) < 32:
        raise ValueError("MELI_TOKEN_KEY precisa de pelo menos 32 caracteres aleatórios.")
    # A chave passada pela Render pode ser qualquer texto aleatorio: Fernet usa
    # uma derivacao deterministica para nao precisar colar tokens no Studio.
    key = base64.urlsafe_b64encode(hashlib.sha256(("UniversoEletrico/MELI/v1:" + raw).encode()).digest())
    return Fernet(key)


def db():
    import psycopg
    url = os.environ.get("MELI_DATABASE_URL", "").strip()
    if not url.startswith(("postgresql://", "postgres://")):
        raise ValueError("MELI_DATABASE_URL deve apontar para PostgreSQL.")
    return psycopg.connect(url, connect_timeout=6)


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS universo_meli_tokens (
            token_id SMALLINT PRIMARY KEY CHECK (token_id = 1),
            access_encrypted TEXT NOT NULL,
            refresh_encrypted TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            account_id TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def token_exchange(code, code_verifier, http=None):
    """Troca codigo por tokens; exige refresh offline de uso unico."""
    if not code or not code_verifier:
        raise ValueError("Autorização incompleta.")
    req = http or requests
    response = req.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": os.environ["MELI_CLIENT_ID"],
        "client_secret": os.environ["MELI_CLIENT_SECRET"],
        "code": code,
        "redirect_uri": CALLBACK_URL,
        "code_verifier": code_verifier,
    }, timeout=16, headers={"Accept": "application/json"})
    if response.status_code >= 400:
        raise RuntimeError("O Mercado Livre não confirmou a autorização. Verifique o Redirect URI e as permissões.")
    data = response.json()
    validate_token_data(data)
    return data


def validate_token_data(data):
    if not isinstance(data, dict) or not data.get("access_token") or not data.get("refresh_token"):
        raise ValueError("Token incompleto. Aplique a permissão de acesso offline no DevCenter.")
    secs = data.get("expires_in")
    if not isinstance(secs, int) or secs < 60 or secs > 31_536_000:
        raise ValueError("Prazo de token inválido.")
    if not str(data.get("user_id", "")).isdigit():
        raise ValueError("Identificador da conta do Mercado Livre inválido.")


def save_tokens(data):
    validate_token_data(data)
    f = cipher()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))
    with db() as conn:
        init_db(conn)
        conn.execute("""
            INSERT INTO universo_meli_tokens
              (token_id, access_encrypted, refresh_encrypted, expires_at, account_id, updated_at)
            VALUES (1, %s, %s, %s, %s, NOW())
            ON CONFLICT (token_id) DO UPDATE SET
              access_encrypted=EXCLUDED.access_encrypted,
              refresh_encrypted=EXCLUDED.refresh_encrypted,
              expires_at=EXCLUDED.expires_at,
              account_id=EXCLUDED.account_id,
              updated_at=NOW()
        """, (
            f.encrypt(data["access_token"].encode()).decode("ascii"),
            f.encrypt(data["refresh_token"].encode()).decode("ascii"),
            expiry, str(data["user_id"])
        ))


def connection_status():
    if not configured():
        return {"connected": False, "configured": False}
    with db() as conn:
        init_db(conn)
        row = conn.execute(
            "SELECT account_id, expires_at FROM universo_meli_tokens WHERE token_id=1"
        ).fetchone()
    if not row:
        return {"connected": False, "configured": True}
    return {"connected": True, "configured": True, "account_id": row[0],
            "access_expires_at": row[1]}


def valid_access_token(http=None):
    """Renova uma unica vez sob lock de linha e persiste o refresh rotativo.

    Nao retorna tokens ao frontend. Chamado somente pelo backend para APIs
    permitidas e em sessoes de administrador.
    """
    f = cipher()
    req = http or requests
    with db() as conn:
        init_db(conn)
        row = conn.execute("""
            SELECT access_encrypted, refresh_encrypted, expires_at
            FROM universo_meli_tokens WHERE token_id=1 FOR UPDATE
        """).fetchone()
        if not row:
            raise ValueError("Conecte sua conta do Mercado Livre primeiro.")
        current_access = f.decrypt(row[0].encode()).decode()
        if row[2] > datetime.now(timezone.utc) + timedelta(minutes=3):
            return current_access
        refresh = f.decrypt(row[1].encode()).decode()
        response = req.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": os.environ["MELI_CLIENT_ID"],
            "client_secret": os.environ["MELI_CLIENT_SECRET"],
            "refresh_token": refresh,
        }, timeout=16, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            raise RuntimeError("Não foi possível renovar a autorização. Reconecte o Mercado Livre.")
        data = response.json()
        validate_token_data(data)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        conn.execute("""
            UPDATE universo_meli_tokens
            SET access_encrypted=%s, refresh_encrypted=%s,
                expires_at=%s, account_id=%s, updated_at=NOW()
            WHERE token_id=1
        """, (
            f.encrypt(data["access_token"].encode()).decode(),
            f.encrypt(data["refresh_token"].encode()).decode(),
            expiry, str(data["user_id"])
        ))
        return data["access_token"]


def disconnect():
    """Apaga nossa copia dos tokens; revogacao remota deve ser feita no Mercado Livre."""
    if not configured():
        raise ValueError("Integração não configurada.")
    with db() as conn:
        init_db(conn)
        conn.execute("DELETE FROM universo_meli_tokens WHERE token_id=1")
