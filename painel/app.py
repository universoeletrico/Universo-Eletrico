"""Universo Eletrico Studio — painel MVP para revisar a fila de artes.
Sem acesso ao Instagram: aprovacoes apenas editam o posts.json no GitHub,
quando GITHUB_WRITE_TOKEN for configurado. Nao publica nem agenda posts.
"""
from __future__ import annotations

import base64
import functools
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import requests
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("PANEL_SESSION_SECRET", "")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    MAX_CONTENT_LENGTH=1024 * 30,
)

OWNER = "universoeletrico"
REPO = "Universo-Eletrico"
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/"
ROOT = Path(__file__).resolve().parents[1]

# Reutiliza as mesmas regras da agenda que o robo executa no GitHub.
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.schedule_rules import DAYS, validate_schedule, upcoming
MEDIA = "https://universoeletrico.github.io/Universo-Eletrico/posts/"
LOGO = "https://raw.githubusercontent.com/universoeletrico/Universo-Eletrico/main/assets/logo-original.png"
_cache = {}
_lock = Lock()
_failed_logins = {}


def configured():
    return bool(app.secret_key and os.environ.get("PANEL_PASSWORD_HASH"))


def github_headers(write=False):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_WRITE_TOKEN", "").strip()
    if write and not token:
        raise RuntimeError("Aprovacao ainda nao configurada: falta GITHUB_WRITE_TOKEN na Render.")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def repo_json(path):
    with _lock:
        cached = _cache.get(path)
        if cached and time.monotonic() - cached[0] < 25:
            return cached[1]
    # Os dados do universo eletrico sao publicos e ja existem no repo.
    try:
        response = requests.get(
            f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/{path}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    with _lock:
        _cache[path] = (time.monotonic(), data)
    return data


def invalidate(*paths):
    with _lock:
        for path in paths:
            _cache.pop(path, None)


def status_of(post, state):
    pid = post["id"]
    if any(x["id"] == pid for x in state.get("published", [])):
        return ("Publicado", "published")
    if any(x["id"] == pid for x in state.get("externally_scheduled", [])):
        return ("Agendado na Meta", "scheduled")
    if state.get("pending", {}).get("id") == pid:
        return ("Reservado", "scheduled")
    if post.get("approved"):
        return ("Aprovado para fila", "approved")
    return ("Aguardando revisão", "draft")


def posts_with_status():
    posts = repo_json("content/posts.json")
    state = repo_json("content/state.json")
    rows = []
    for p in posts:
        label, state_key = status_of(p, state)
        rows.append({**p, "status_label": label, "status_key": state_key, "image_url": f"{MEDIA}{p['id']}.jpg"})
    return rows


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def validate_csrf():
    import hmac
    if not hmac.compare_digest(session.get("csrf", ""), request.form.get("csrf", "")):
        abort(400, "Falha na validacao de segurança do formulário.")


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not configured():
            return "Painel nao configurado: definir PANEL_SESSION_SECRET e PANEL_PASSWORD_HASH na Render.", 503
        if session.get("admin") is not True:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_context():
    return {"csrf": csrf_token, "logo_url": LOGO, "writable": bool(os.environ.get("GITHUB_WRITE_TOKEN"))}


@app.after_request
def secure_headers(res):
    res.headers["X-Content-Type-Options"] = "nosniff"
    res.headers["X-Frame-Options"] = "DENY"
    res.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    res.headers["Cache-Control"] = "no-store"
    res.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'none'; "
        "style-src 'self'; img-src 'self' https://universoeletrico.github.io "
        "https://raw.githubusercontent.com data:; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    return res


@app.route("/health")
def health():
    return {"ok": True, "service": "universo-eletrico-studio", "panel_configured": configured()}


@app.route("/login", methods=["GET", "POST"])
def login():
    if not configured():
        return "Painel nao configurado: procure as variaveis de ambiente na Render.", 503
    if session.get("admin"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        validate_csrf()
        remote = request.remote_addr or "unknown"
        now = time.monotonic()
        attempts = [t for t in _failed_logins.get(remote, []) if now-t < 900]
        if len(attempts) >= 8:
            abort(429, "Muitas tentativas. Aguarde alguns minutos.")
        password = request.form.get("password", "")
        if check_password_hash(os.environ["PANEL_PASSWORD_HASH"], password):
            _failed_logins.pop(remote, None)
            session.clear()
            session["admin"] = True
            session["csrf"] = secrets.token_urlsafe(24)
            return redirect(url_for("dashboard"))
        _failed_logins[remote] = attempts + [now]
        flash("Senha incorreta.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    query = request.args.get("q", "").strip().casefold()[:90]
    selected = request.args.get("status", "all")
    if selected not in {"all", "draft", "approved", "scheduled", "published"}:
        selected = "all"
    all_posts = posts_with_status()
    results = [
        p for p in all_posts
        if (selected == "all" or p["status_key"] == selected)
        and (not query or query in (p["title"] + " " + p.get("hook", "") + " " + p.get("caption", "")).casefold())
    ]
    totals = {k: sum(p["status_key"] == k for p in all_posts) for k in ("draft", "approved", "scheduled", "published")}
    return render_template("dashboard.html", posts=results, total=len(all_posts), totals=totals, q=query, selected=selected, tab="artes")


@app.route("/post/<pid>")
@login_required
def detail(pid):
    if not (pid.isdigit() and len(pid) == 3):
        abort(404)
    post = next((x for x in posts_with_status() if x["id"] == pid), None)
    if not post:
        abort(404)
    return render_template("detail.html", post=post, tab="artes")


def save_to_github(pid, caption, approved):
    """Grava apenas caption/approved do post escolhido, com SHA para evitar sobrescrever mudancas concorrentes."""
    headers = github_headers(write=True)
    url = API + "content/posts.json"
    current = requests.get(url, headers=headers, timeout=15)
    current.raise_for_status()
    data = current.json()
    posts = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
    found = next((p for p in posts if p.get("id") == pid), None)
    if not found:
        raise ValueError("Post nao encontrado.")
    state = repo_json("content/state.json")
    if any(x["id"] == pid for x in state.get("published", [])):
        raise ValueError("Post ja publicado: edição bloqueada para preservar historico.")
    if any(x["id"] == pid for x in state.get("externally_scheduled", [])):
        raise ValueError("Post agendado externamente: nao alterar pelo painel.")
    if state.get("pending", {}).get("id") == pid:
        raise ValueError("Post reservado pelo robo: nao editar.")
    found["caption"] = caption
    found["approved"] = approved
    payload = {
        "message": f"painel: revisar post {pid} ({'aprovado' if approved else 'rascunho'})",
        "content": base64.b64encode((json.dumps(posts, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii"),
        "sha": data["sha"],
        "branch": "main",
    }
    response = requests.put(url, headers=headers, json=payload, timeout=18)
    if response.status_code in (409, 422):
        raise ValueError("O arquivo mudou no GitHub. Recarregue a pagina e tente novamente.")
    response.raise_for_status()
    invalidate("content/posts.json")


@app.post("/post/<pid>/save")
@login_required
def save_post(pid):
    validate_csrf()
    if not (pid.isdigit() and len(pid) == 3):
        abort(404)
    caption = request.form.get("caption", "").strip()
    approved = request.form.get("decision") == "approve"
    if not caption or len(caption) > 2200:
        flash("A legenda deve ter de 1 a 2.200 caracteres.", "error")
        return redirect(url_for("detail", pid=pid))
    try:
        save_to_github(pid, caption, approved)
        flash("Alterações salvas no GitHub. O robô só utilizará conteúdos aprovados.", "success")
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        app.logger.warning("Erro ao salvar revisao: %s", type(exc).__name__)
        flash(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Nao foi possivel conectar ao GitHub.", "error")
    return redirect(url_for("detail", pid=pid))


def save_schedule_to_github(schedule):
    """Grava somente content/schedule.json com o SHA correto, sem alterar workflows."""
    validated = validate_schedule(schedule)
    headers = github_headers(write=True)
    url = API + "content/schedule.json"
    existing = requests.get(url, headers=headers, timeout=15)
    existing.raise_for_status()
    current = existing.json()
    contents = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
    data = {
        "message": "painel: atualizar dias e horarios de publicacao",
        "content": base64.b64encode(contents.encode("utf-8")).decode("ascii"),
        "sha": current["sha"],
        "branch": "main",
    }
    response = requests.put(url, headers=headers, json=data, timeout=20)
    if response.status_code in (409, 422):
        raise ValueError("A agenda mudou no GitHub. Recarregue a pagina e tente novamente.")
    response.raise_for_status()
    invalidate("content/schedule.json")


@app.route("/agenda", methods=["GET", "POST"])
@login_required
def agenda():
    if request.method == "POST":
        validate_csrf()
        try:
            quantidade = int(request.form.get("quantidade", "1"))
            if quantidade not in (1, 2, 3):
                raise ValueError("Escolha de 1 a 3 postagens por dia.")
            raw_days = request.form.getlist("days")
            if len(raw_days) > 7 or any(not x.isdigit() for x in raw_days):
                raise ValueError("Selecione dias validos.")
            settings = validate_schedule({
                "timezone": "America/Sao_Paulo",
                "enabled": request.form.get("enabled") == "on",
                "days": [int(x) for x in raw_days],
                "times": [request.form.get(f"time{i}", "").strip() for i in range(1, quantidade + 1)],
            })
            save_schedule_to_github(settings)
            flash("Agenda salva! O robo consultara os novos dias e horarios na proxima execucao.", "success")
        except (ValueError, RuntimeError, requests.RequestException) as exc:
            app.logger.warning("Nao foi possivel salvar a agenda: %s", type(exc).__name__)
            flash(str(exc) if isinstance(exc, (ValueError, RuntimeError))
                  else "Erro de conexao com o GitHub. Tente novamente.", "error")
        return redirect(url_for("agenda"))

    settings = validate_schedule(repo_json("content/schedule.json"))
    sugestoes = ["19:17", "12:17", "17:17"]
    exibicao = settings["times"] + [t for t in sugestoes if t not in settings["times"]]
    return render_template(
        "schedule.html", config=settings, days=list(enumerate(DAYS)), tab="agenda",
        quantidade=len(settings["times"]), horarios=exibicao[:3],
        proximos=upcoming(settings, days_ahead=14),
    )


@app.route("/planejamento")
@login_required
def planejamento():
    posts = posts_with_status()
    return render_template("planning.html", posts=posts, tab="planejamento")


@app.route("/estrutura")
@login_required
def estrutura():
    rows = posts_with_status()
    return render_template("structure.html", total=len(rows), tab="estrutura")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")), debug=False)
