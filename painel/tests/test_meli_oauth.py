"""Autenticação e renovação de tokens Mercado Livre, inteiramente offline."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PANEL_SESSION_SECRET", "segredo-apenas-testes")
os.environ.setdefault("PANEL_PASSWORD_HASH", "hash-apenas-testes")

import app as studio
from painel import meli_oauth


class TestMercadoLivreOAuth(unittest.TestCase):
    def setUp(self):
        studio.app.config["TESTING"] = True
        studio.app.secret_key = "chave-exclusivamente-para-testes"
        self.client = studio.app.test_client()
        self.env = {
            "MELI_CLIENT_ID": "123456789",
            "MELI_CLIENT_SECRET": "client-secret-privado",
            "MELI_DATABASE_URL": "postgresql://usuario:senha@localhost:5432/teste",
            "MELI_TOKEN_KEY": "chave-aleatoria-para-testes-de-oauth-mercado-livre-2026",
        }
        self.payload = {
            "access_token": "access-token-de-teste",
            "refresh_token": "refresh-token-rotativo-de-teste",
            "expires_in": 21600,
            "user_id": 123456789,
        }

    def authorize(self):
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["csrf"] = "csrf-teste"

    def test_integration_page_requires_login(self):
        self.assertEqual(self.client.get("/integracoes/mercado-livre").status_code, 302)
        self.assertIn("/login", self.client.get("/integracoes/mercado-livre").location)

    def test_page_without_credentials_does_not_contact_api(self):
        self.authorize()
        with patch.dict(os.environ, {key: "" for key in meli_oauth.NECESSARY}), \
             patch.object(meli_oauth, "connection_status") as status:
            r = self.client.get("/integracoes/mercado-livre")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"MELI_CLIENT_ID", r.data)
        self.assertIn(b"Conectar", r.data)
        status.assert_not_called()

    def test_require_full_config(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.assertTrue(meli_oauth.configured())
            with patch.dict(os.environ, {"MELI_TOKEN_KEY": "123"}):
                self.assertFalse(meli_oauth.configured())
            with patch.dict(os.environ, {"MELI_CLIENT_SECRET": ""}):
                self.assertFalse(meli_oauth.configured())

    def test_start_requires_post_and_csrf(self):
        self.authorize()
        self.assertEqual(self.client.get("/integracoes/mercado-livre/conectar").status_code, 405)
        r = self.client.post("/integracoes/mercado-livre/conectar",
                             data={"csrf": "errado", "confirm": "yes"})
        self.assertEqual(r.status_code, 400)

    def test_start_oauth_pkce_state(self):
        self.authorize()
        with patch.dict(os.environ, self.env):
            r = self.client.post("/integracoes/mercado-livre/conectar",
                                 data={"csrf": "csrf-teste", "confirm": "yes"})
        self.assertEqual(r.status_code, 302)
        parsed = urlsplit(r.location)
        self.assertEqual(parsed.hostname, "auth.mercadolivre.com.br")
        query = parse_qs(parsed.query)
        self.assertEqual(query["client_id"], ["123456789"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], [meli_oauth.CALLBACK_URL])
        self.assertNotIn("client-secret-privado", r.location)
        with self.client.session_transaction() as s:
            self.assertEqual(s["meli_oauth_state"], query["state"][0])
            self.assertGreater(len(s["meli_pkce_verifier"]), 40)

    def test_callback_wrong_state_does_not_exchange(self):
        self.authorize()
        with self.client.session_transaction() as s:
            s["meli_oauth_state"] = "esperado"
            s["meli_pkce_verifier"] = "verifier-local"
        with patch.object(meli_oauth, "token_exchange") as exchange:
            r = self.client.get("/integracoes/mercado-livre/callback?code=abc&state=errado")
        self.assertEqual(r.status_code, 400)
        exchange.assert_not_called()

    def test_callback_valid_saves_tokens(self):
        self.authorize()
        with self.client.session_transaction() as s:
            s["meli_oauth_state"] = "state-teste"
            s["meli_pkce_verifier"] = "verifier-teste"
        with patch.object(meli_oauth, "token_exchange", return_value=self.payload) as exchange, \
             patch.object(meli_oauth, "save_tokens") as save:
            r = self.client.get("/integracoes/mercado-livre/callback?code=abc&state=state-teste")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/integracoes/mercado-livre", r.location)
        exchange.assert_called_once_with("abc", "verifier-teste")
        save.assert_called_once_with(self.payload)
        with self.client.session_transaction() as s:
            self.assertNotIn("meli_oauth_state", s)
            self.assertNotIn("meli_pkce_verifier", s)

    def test_cannot_replay_callback(self):
        self.authorize()
        self.assertEqual(self.client.get(
            "/integracoes/mercado-livre/callback?code=abc&state=state-teste"
        ).status_code, 400)

    def test_token_exchange_sends_secret_server_side(self):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = self.payload
        http = MagicMock()
        http.post.return_value = r
        with patch.dict(os.environ, self.env):
            result = meli_oauth.token_exchange("codigo", "verificador", http=http)
        self.assertEqual(result["access_token"], "access-token-de-teste")
        request = http.post.call_args
        self.assertEqual(request.args[0], meli_oauth.TOKEN_URL)
        self.assertEqual(request.kwargs["data"]["code_verifier"], "verificador")
        self.assertEqual(request.kwargs["data"]["client_secret"], "client-secret-privado")
        self.assertEqual(request.kwargs["timeout"], 16)

    def test_fernet_encrypt_decrypt(self):
        with patch.dict(os.environ, self.env):
            crypto = meli_oauth.cipher()
            encrypted = crypto.encrypt(b"acesso-privado")
            self.assertNotIn(b"acesso-privado", encrypted)
            self.assertEqual(crypto.decrypt(encrypted), b"acesso-privado")

    def test_refuses_token_without_offline_refresh(self):
        with self.assertRaisesRegex(ValueError, "offline"):
            meli_oauth.validate_token_data({"access_token": "abc", "expires_in": 21600, "user_id": 1})

    def test_valid_access_skips_refresh_when_not_expired(self):
        with patch.dict(os.environ, self.env):
            crypto = meli_oauth.cipher()
            conn = MagicMock()
            conn.__enter__.return_value = conn
            conn.execute.return_value.fetchone.return_value = (
                crypto.encrypt(b"token-antigo").decode(),
                crypto.encrypt(b"refresh-antigo").decode(),
                datetime.now(timezone.utc) + timedelta(hours=2)
            )
            with patch.object(meli_oauth, "db", return_value=conn), \
                 patch.object(meli_oauth, "init_db"), \
                 patch.object(meli_oauth.requests, "post") as post:
                result = meli_oauth.valid_access_token()
            self.assertEqual(result, "token-antigo")
            post.assert_not_called()

    def test_expired_access_rotates_refresh_under_lock(self):
        with patch.dict(os.environ, self.env):
            crypto = meli_oauth.cipher()
            conn = MagicMock()
            conn.__enter__.return_value = conn
            conn.execute.return_value.fetchone.return_value = (
                crypto.encrypt(b"token-vencido").decode(),
                crypto.encrypt(b"refresh-antigo").decode(),
                datetime.now(timezone.utc) - timedelta(minutes=1)
            )
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = self.payload
            req = MagicMock()
            req.post.return_value = resp
            with patch.object(meli_oauth, "db", return_value=conn), \
                 patch.object(meli_oauth, "init_db"):
                token = meli_oauth.valid_access_token(http=req)
        self.assertEqual(token, "access-token-de-teste")
        self.assertEqual(req.post.call_args.kwargs["data"]["refresh_token"], "refresh-antigo")
        self.assertEqual(conn.execute.call_count, 2)
        self.assertIn("FOR UPDATE", conn.execute.call_args_list[0].args[0])
        self.assertIn("UPDATE universo_meli_tokens", conn.execute.call_args_list[1].args[0])
        params = conn.execute.call_args_list[1].args[1]
        with patch.dict(os.environ, self.env):
            crypto = meli_oauth.cipher()
            self.assertEqual(crypto.decrypt(params[1].encode()), b"refresh-token-rotativo-de-teste")

    def test_connection_status_only_id_no_secrets(self):
        self.authorize()
        with patch.object(meli_oauth, "configured", return_value=True), \
             patch.object(meli_oauth, "missing_settings", return_value=[]), \
             patch.object(meli_oauth, "connection_status", return_value={
                 "connected": True, "configured": True, "account_id": "123456789"
             }):
            r = self.client.get("/integracoes/mercado-livre")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Conta conectada", r.data)
        self.assertNotIn(b"client-secret-privado", r.data)

    def test_disconnect_requires_confirm(self):
        self.authorize()
        with patch.object(meli_oauth, "disconnect") as disconnect:
            r = self.client.post("/integracoes/mercado-livre/desconectar", data={
                "csrf": "csrf-teste", "confirm": "no"
            })
        self.assertEqual(r.status_code, 302)
        disconnect.assert_not_called()

    def test_disconnect_requires_csrf(self):
        self.authorize()
        with patch.object(meli_oauth, "disconnect") as disconnect:
            r = self.client.post("/integracoes/mercado-livre/desconectar", data={
                "csrf": "errado", "confirm": "disconnect"
            })
        self.assertEqual(r.status_code, 400)
        disconnect.assert_not_called()

if __name__ == "__main__":
    unittest.main()
