"""Universo Eletrico Studio — painel MVP para revisar a fila de artes.
Sem acesso ao Instagram: aprovacoes apenas editam o posts.json no GitHub,
quando GITHUB_WRITE_TOKEN for configurado. Nao publica nem agenda posts.
"""
from __future__ import annotations

import base64
import functools
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from math import ceil
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
from painel.affiliates import (
    CATEGORIES, IDEAS, MARKETPLACES, draft_caption, marketplace_name,
    new_id, normalize_product, require_disclosure, timestamp
)
from painel.research import editorial_ideas, search_official_catalog, search_url
from painel import meli_oauth
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


def coverage_for(rows, schedule):
    """Estimativa conservadora de dias programados cobertos pela fila atual.

    Contamos apenas artes aprovadas, nao publicadas, nao agendadas.
    A previsao nao garante entrega (API, aprovacao, atrasos do GitHub).
    """
    valid = validate_schedule(schedule)
    available = sum(p["status_key"] == "approved" for p in rows)
    per_day = len(valid["times"])
    return {
        "posts": available,
        "days": ceil(available / per_day) if available else 0,
        "full_days": available // per_day,
        "partial": (available % per_day) != 0,
        "per_day": per_day,
        "active_days": len(valid["days"]),
        "enabled": valid["enabled"],
    }


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def validate_csrf():
    import hmac
    expected = session.get("csrf")
    supplied = request.form.get("csrf")
    if (not expected or not supplied or not hmac.compare_digest(expected, supplied)):
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
    # Chrome pode bloquear o redirect OAuth feito depois de POST quando
    # form-action permite somente 'self'. Liberamos o dominio oficial apenas
    # nas rotas de integracao; todo o restante do painel permanece restrito.
    form_action = (
        "form-action 'self' https://auth.mercadolivre.com.br;"
        if request.endpoint in {"meli_integration", "meli_connect"}
        else "form-action 'self';"
    )
    res.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'none'; "
        "style-src 'self'; img-src 'self' https://universoeletrico.github.io "
        "https://raw.githubusercontent.com data:; connect-src 'self'; "
        + form_action + " frame-ancestors 'none'; base-uri 'self'"
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
    coverage = coverage_for(all_posts, repo_json("content/schedule.json"))
    return render_template("dashboard.html", posts=results, total=len(all_posts), totals=totals, coverage=coverage, q=query, selected=selected, tab="artes")


@app.route("/post/<pid>")
@login_required
def detail(pid):
    if not (pid.isdigit() and len(pid) == 3):
        abort(404)
    post = next((x for x in posts_with_status() if x["id"] == pid), None)
    if not post:
        abort(404)
    return render_template("detail.html", post=post, tab="artes")


def github_file(path):
    """Carrega a versao atual do GitHub (nunca cache) para escrita com SHA."""
    response = requests.get(API + path, headers=github_headers(write=True), timeout=15)
    response.raise_for_status()
    blob = response.json()
    return json.loads(base64.b64decode(blob["content"]).decode("utf-8")), blob["sha"]


def save_bulk_approval(ids):
    """Aprova somente rascunhos escolhidos, em um commit atomico.

    Antes de editar, obtem o estado atual sem cache e protege posts
    publicados, agendados externamente ou reservados pelo robo.
    """
    if not ids or len(ids) > 30 or len(ids) != len(set(ids)):
        raise ValueError("Escolha de 1 a 30 artes, sem repetir.")
    if any(not isinstance(pid, str) or len(pid) != 3 or not pid.isdecimal() for pid in ids):
        raise ValueError("Identificador de arte invalido.")
    posts, posts_sha = github_file("content/posts.json")
    state, _ = github_file("content/state.json")
    by_id = {p.get("id"): p for p in posts}
    blocked = {p.get("id") for p in state.get("published", [])}
    blocked.update(p.get("id") for p in state.get("externally_scheduled", []))
    if state.get("pending"):
        blocked.add(state["pending"].get("id"))
    for pid in ids:
        post = by_id.get(pid)
        if (not post or pid in blocked or post.get("approved") is not False
                or not post.get("caption") or not post.get("title")):
            raise ValueError("Uma das artes foi alterada, aprovada ou reservada. Atualize a pagina.")
    for pid in ids:
        by_id[pid]["approved"] = True

    content = json.dumps(posts, indent=2, ensure_ascii=False) + "\n"
    payload = {
        "message": f"painel: aprovar {len(ids)} artes revisadas em lote",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "sha": posts_sha,
        "branch": "main",
    }
    response = requests.put(API + "content/posts.json",
                            headers=github_headers(write=True), json=payload, timeout=20)
    if response.status_code in (409, 422):
        raise ValueError("A fila foi alterada simultaneamente. Atualize a tela antes de tentar novamente.")
    response.raise_for_status()
    invalidate("content/posts.json", "content/state.json")
    return len(ids)


@app.route("/aprovacao-lote", methods=["GET", "POST"])
@login_required
def bulk_approval():
    if request.method == "POST":
        validate_csrf()
        ids = request.form.getlist("post_ids")
        if request.form.get("confirm_review") != "yes":
            flash("Confirme que revisou as artes e legendas selecionadas.", "error")
            return redirect(url_for("bulk_approval"))
        try:
            total = save_bulk_approval(ids)
            flash(f"{total} arte(s) aprovadas e enviadas para a fila. Nenhum post foi publicado agora.", "success")
            return redirect(url_for("dashboard"))
        except (ValueError, RuntimeError, requests.RequestException) as exc:
            app.logger.warning("Falha em aprovacao por lote: %s", type(exc).__name__)
            flash(str(exc) if isinstance(exc, (ValueError, RuntimeError))
                  else "Nao foi possivel concluir a aprovacao no GitHub.", "error")
            return redirect(url_for("bulk_approval"))

    drafts = [p for p in posts_with_status() if p["status_key"] == "draft"]
    return render_template("bulk_approval.html", posts=drafts, tab="lote")


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


def affiliate_catalog():
    """Busca catalogo do repositorio; nao armazena tokens nem dados bancarios."""
    catalog = repo_json("content/affiliate_products.json")
    if (not isinstance(catalog, dict) or not isinstance(catalog.get("products"), list)):
        raise ValueError("Arquivo de produtos de afiliados invalido.")
    return catalog["products"]


def save_affiliate_change(change):
    """Atualiza produtos em um unico commit GitHub, com protecao de versao (SHA)."""
    catalog, sha = github_file("content/affiliate_products.json")
    if (not isinstance(catalog, dict) or not isinstance(catalog.get("products"), list)):
        raise ValueError("Catalogo de produtos invalido.")
    result = change(catalog["products"])
    payload = {
        "message": "painel: revisar catalogo e campanhas de afiliados",
        "content": base64.b64encode(
            (json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        ).decode("ascii"),
        "sha": sha,
        "branch": "main",
    }
    response = requests.put(
        API + "content/affiliate_products.json",
        headers=github_headers(write=True), json=payload, timeout=20
    )
    if response.status_code in (409, 422):
        raise ValueError("O catalogo mudou no GitHub. Atualize a pagina e tente novamente.")
    response.raise_for_status()
    invalidate("content/affiliate_products.json")
    return result



@app.get("/radar")
@login_required
def product_radar():
    """Curadoria sem publicacao: sugestoes editoriais + catalogo oficial opcional."""
    products = affiliate_catalog()
    approved_posts = repo_json("content/posts.json")
    ideas = editorial_ideas(products, approved_posts, limit=12)
    keyword = request.args.get("q", "").strip()[:80]
    results = []
    api_configured = meli_oauth.configured()
    account_connected = False
    issue = None
    if api_configured:
        try:
            account_connected = meli_oauth.connection_status()["connected"]
        except Exception as exc:
            app.logger.warning("Status OAuth indisponivel: %s", type(exc).__name__)
            issue = "Não foi possível consultar o status do Mercado Livre. Verifique o banco da integração."
    if keyword and account_connected:
        try:
            token = meli_oauth.valid_access_token()
            results = search_official_catalog(keyword, token)
        except (ValueError, RuntimeError, requests.RequestException) as exc:
            app.logger.warning("Pesquisa em catalogo falhou: %s", type(exc).__name__)
            issue = (str(exc) if isinstance(exc, (ValueError, RuntimeError))
                     else "Não foi possível consultar a API oficial agora.")
        except Exception as exc:
            app.logger.warning("Erro na consulta OAuth: %s", type(exc).__name__)
            issue = "Conexão temporariamente indisponível. Verifique a integração."
    elif keyword and not account_connected and not issue:
        issue = "Conecte primeiro sua aplicação do Mercado Livre ao Studio."
    return render_template(
        "radar.html", tab="radar", ideas=ideas, keyword=keyword,
        catalog_results=results, api_configured=api_configured,
        account_connected=account_connected,
        catalog_error=issue, search_url=search_url
    )


@app.get("/integracoes/mercado-livre")
@login_required
def meli_integration():
    details = {"connected": False, "configured": meli_oauth.configured()}
    status_error = None
    if meli_oauth.configured():
        try:
            details = meli_oauth.connection_status()
        except Exception as exc:
            app.logger.warning("Status de integracao indisponivel: %s", type(exc).__name__)
            status_error = "Não foi possível consultar a conexão. Confira as variáveis e o banco."
    return render_template(
        "meli_integration.html", tab="integracoes",
        details=details, missing=meli_oauth.missing_settings(),
        callback_url=meli_oauth.CALLBACK_URL, status_error=status_error
    )


@app.post("/integracoes/mercado-livre/conectar")
@login_required
def meli_connect():
    validate_csrf()
    if request.form.get("confirm") != "yes":
        flash("Confirme que a aplicação e a conta autorizada são suas.", "error")
        return redirect(url_for("meli_integration"))
    try:
        request_data = meli_oauth.create_oauth_request()
        session["meli_oauth_state"] = request_data["state"]
        session["meli_pkce_verifier"] = request_data["code_verifier"]
        return redirect(request_data["url"], code=302)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("meli_integration"))


@app.get("/integracoes/mercado-livre/callback")
@login_required
def meli_callback():
    """URL fixa declarada no DevCenter; state e PKCE protegem o fluxo."""
    expected = session.pop("meli_oauth_state", None)
    verifier = session.pop("meli_pkce_verifier", None)
    state = request.args.get("state", "")
    if not expected or not verifier or not state or not hmac.compare_digest(expected, state):
        abort(400, "Autorização inválida ou expirada. Inicie novamente pelo Studio.")
    if request.args.get("error"):
        flash("A autorização foi cancelada ou recusada no Mercado Livre.", "error")
        return redirect(url_for("meli_integration"))
    code = request.args.get("code", "")
    if not code or len(code) > 2048:
        abort(400, "Código de autorização inválido.")
    try:
        token_data = meli_oauth.token_exchange(code, verifier)
        meli_oauth.save_tokens(token_data)
        flash("Conta Mercado Livre conectada! Os tokens são protegidos no banco da integração.", "success")
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        app.logger.warning("OAuth recusado: %s", type(exc).__name__)
        flash(str(exc) if isinstance(exc, (ValueError, RuntimeError))
              else "Falha ao contatar a API do Mercado Livre.", "error")
    except Exception as exc:
        app.logger.warning("Erro ao salvar OAuth: %s", type(exc).__name__)
        flash("Autorização não concluída: confira o armazenamento da integração.", "error")
    return redirect(url_for("meli_integration"))


@app.post("/integracoes/mercado-livre/desconectar")
@login_required
def meli_disconnect():
    validate_csrf()
    if request.form.get("confirm") != "disconnect":
        flash("Confirme a desconexão no formulário.", "error")
        return redirect(url_for("meli_integration"))
    try:
        meli_oauth.disconnect()
        flash("Tokens apagados do Studio. Para revogar o acesso no Mercado Livre, faça isso também no DevCenter.", "success")
    except Exception as exc:
        app.logger.warning("Falha de desconexao OAuth: %s", type(exc).__name__)
        flash("Não foi possível limpar os tokens. Verifique a integração.", "error")
    return redirect(url_for("meli_integration"))


@app.route("/afiliados", methods=["GET", "POST"])
@login_required
def affiliates_page():
    if request.method == "POST":
        validate_csrf()
        try:
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            raw = normalize_product({
                "name": name,
                "category": category,
                "marketplace": request.form.get("marketplace", ""),
                "affiliate_url": request.form.get("affiliate_url", ""),
                "description": request.form.get("description", ""),
                "caption": draft_caption(name, category),
            })
            def add(products):
                if len(products) >= 300:
                    raise ValueError("Limite de 300 produtos atingido.")
                pid = new_id(products)
                products.append({
                    "id": pid, **raw, "status": "draft",
                    "created_at": timestamp(), "updated_at": timestamp()
                })
                return pid
            pid = save_affiliate_change(add)
            flash("Produto cadastrado! Revise a legenda e aprove antes de divulgar.", "success")
            return redirect(url_for("affiliate_detail", pid=pid))
        except (ValueError, RuntimeError, requests.RequestException) as exc:
            app.logger.warning("Cadastro de afiliados falhou: %s", type(exc).__name__)
            flash(str(exc) if isinstance(exc, (ValueError, RuntimeError))
                  else "Falha na conexao com o GitHub.", "error")
            return redirect(url_for("affiliates_page"))

    products = affiliate_catalog()
    stats = {
        "total": len(products),
        "draft": sum(x.get("status") == "draft" for x in products),
        "approved": sum(x.get("status") == "approved" for x in products),
        "rejected": sum(x.get("status") == "rejected" for x in products)
    }
    initial_name = request.args.get("name", "").strip()[:150]
    initial_category = request.args.get("category", "").strip()[:90]
    if initial_category not in CATEGORIES:
        initial_category = CATEGORIES[0]
    return render_template(
        "affiliates.html", tab="afiliados", products=products,
        stats=stats, marketplaces=MARKETPLACES,
        categories=CATEGORIES, ideas=IDEAS,
        prefill_name=initial_name, prefill_category=initial_category,
        marketplace_name=marketplace_name
    )


@app.route("/afiliados/<pid>", methods=["GET", "POST"])
@login_required
def affiliate_detail(pid):
    if not (len(pid) in range(4, 7) and pid.startswith("A") and pid[1:].isdigit()):
        abort(404)
    if request.method == "POST":
        validate_csrf()
        action = request.form.get("action", "")
        if action not in {"save", "approve", "reject", "draft", "regenerate"}:
            abort(400)
        if action == "approve" and request.form.get("reviewed") != "yes":
            flash("Confirme que revisou o produto, o anuncio e o texto comercial.", "error")
            return redirect(url_for("affiliate_detail", pid=pid))
        try:
            def update(products):
                found = next((p for p in products if p.get("id") == pid), None)
                if found is None:
                    raise ValueError("Produto nao encontrado.")
                if action in ("save", "regenerate"):
                    fields = {
                        "name": request.form.get("name", ""),
                        "category": request.form.get("category", ""),
                        "marketplace": request.form.get("marketplace", ""),
                        "affiliate_url": request.form.get("affiliate_url", ""),
                        "description": request.form.get("description", ""),
                        "caption": request.form.get("caption", ""),
                    }
                    if action == "regenerate":
                        fields["caption"] = draft_caption(fields["name"], fields["category"])
                    approved = found.get("status") == "approved"
                    found.update(normalize_product(fields))
                    # Toda edicao comercial exige nova revisao antes de exibir na vitrine.
                    found["status"] = "draft"
                elif action == "approve":
                    require_disclosure(found.get("caption", ""))
                    normalize_product(found)
                    found["status"] = "approved"
                else:
                    found["status"] = "rejected" if action == "reject" else "draft"
                found["updated_at"] = timestamp()
                return found["id"]
            save_affiliate_change(update)
            messages = {
                "save": "Rascunho salvo. Aprovacao necessaria antes da divulgacao.",
                "regenerate": "Legenda-modelo recriada. Confira o conteudo antes de aprovar.",
                "approve": "Produto aprovado! Ele agora aparece na vitrine publica.",
                "reject": "Produto retirado da vitrine e marcado como rejeitado.",
                "draft": "Produto retornou para revisao."
            }
            flash(messages[action], "success")
        except (ValueError, RuntimeError, requests.RequestException) as exc:
            app.logger.warning("Erro ao revisar afiliado: %s", type(exc).__name__)
            flash(str(exc) if isinstance(exc, (ValueError, RuntimeError))
                  else "Nao foi possivel salvar no GitHub.", "error")
        return redirect(url_for("affiliate_detail", pid=pid))

    product = next((p for p in affiliate_catalog() if p.get("id") == pid), None)
    if product is None:
        abort(404)
    return render_template(
        "affiliate_detail.html", product=product, tab="afiliados",
        marketplaces=MARKETPLACES, categories=CATEGORIES,
        marketplace_name=marketplace_name
    )


@app.get("/vitrine")
def affiliate_storefront():
    """Pagina publica somente de produtos explicitamente aprovados."""
    products = [p for p in affiliate_catalog() if p.get("status") == "approved"]
    response = render_template("vitrine.html", products=products,
                               marketplace_name=marketplace_name)
    return response


@app.route("/estrutura")
@login_required
def estrutura():
    rows = posts_with_status()
    return render_template("structure.html", total=len(rows), tab="estrutura")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")), debug=False)
