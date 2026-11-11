"""Publicação diária via API OFICIAL Meta (Instagram Professional com Facebook Login).

Desativado por padrão. Não usa senha do Instagram, cookies nem navegador automatizado.
"""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
POSTS_FILE = ROOT / 'content' / 'posts.json'
STATE_FILE = ROOT / 'content' / 'state.json'
TZ = ZoneInfo('America/Sao_Paulo')


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def select_next(posts, state, local_day):
    """Seleciona um único conteúdo aprovado, preservando posts agendados manualmente."""
    start = state.get('not_before_date')
    if start and local_day < start:
        return None, f'Robô só pode publicar a partir de {start}.'
    scheduled = state.get('externally_scheduled', [])
    if any(entry.get('date') == local_day for entry in scheduled):
        return None, 'Já existe publicação programada manualmente nessa data.'
    if any(entry.get('local_date') == local_day for entry in state.get('published', [])):
        return None, 'Já foi publicado um post nesta data.'
    reserved = {entry['id'] for entry in scheduled}
    published = {entry['id'] for entry in state.get('published', [])}
    for post in posts:
        if post.get('approved', False) and post['id'] not in (published | reserved):
            return post, None
    return None, 'Fila de posts aprovados vazia. Revise e aprove novas artes.'


def media_url_for(post, base_url):
    base_url = base_url.rstrip('/') + '/'
    parsed = urlsplit(base_url)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('PUBLIC_MEDIA_BASE_URL precisa ser um endereço HTTPS público válido.')
    return urljoin(base_url, f'posts/{post["id"]}.jpg')


def graph_post(session, url, token, data):
    response = session.post(url, data=data, headers={'Authorization': f'Bearer {token}'}, timeout=40)
    return json_from_response(response)


def graph_get(session, url, token, params):
    response = session.get(url, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=40)
    return json_from_response(response)


def json_from_response(response):
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f'API Meta respondeu com conteúdo inválido (HTTP {response.status_code}).') from exc
    if response.status_code >= 400 or 'error' in payload:
        err = payload.get('error', {})
        # Nunca mostrar tokens nem URLs de requisições nos logs.
        raise RuntimeError(f'API Meta recusou a solicitação (HTTP {response.status_code}): '
                           f'{err.get("message", "erro desconhecido")}; código {err.get("code", "?")}')
    return payload


def publish_image(post, url, user_id, token, version, session, *, retries=12, sleep_seconds=10):
    import time
    endpoint = f'https://graph.facebook.com/{version}'
    created = graph_post(session, f'{endpoint}/{user_id}/media', token,
                         {'image_url': url, 'caption': post['caption'],
                          'alt_text': f'Universo Elétrico: {post["hook"]} {post["body"]}'})
    container_id = created.get('id')
    if not container_id:
        raise RuntimeError('A Meta não retornou identificador do container.')
    for i in range(retries):
        status = graph_get(session, f'{endpoint}/{container_id}', token, {'fields': 'status_code'})
        code = status.get('status_code')
        if code == 'FINISHED':
            break
        if code in ('ERROR', 'EXPIRED'):
            raise RuntimeError(f'O processamento da imagem falhou com status {code}.')
        if i < retries-1:
            time.sleep(sleep_seconds)
    else:
        raise RuntimeError('A imagem não ficou pronta a tempo. Confira o container na Meta antes de tentar novamente.')
    published = graph_post(session, f'{endpoint}/{user_id}/media_publish', token,
                           {'creation_id': container_id})
    if not published.get('id'):
        raise RuntimeError('Meta não confirmou identificador da publicação: confira sua conta antes de repetir.')
    return published['id']


def run(*, publish=False, now=None, session=None):
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError('now deve conter fuso horário')
    local_day = now.astimezone(TZ).date().isoformat()
    posts = load_json(POSTS_FILE)
    state = load_json(STATE_FILE)
    post, reason = select_next(posts, state, local_day)
    if not post:
        print(reason)
        return None
    print(f'Próximo post: #{post["id"]} — {post["title"]} ({local_day}).')
    if not publish:
        print('Pré-visualização: nenhuma publicação foi enviada.')
        return post
    if os.getenv('PUBLISH_ENABLED', '').lower() != 'true':
        raise RuntimeError('Publicação desativada. Configure PUBLISH_ENABLED=true para habilitar.')
    token = os.getenv('INSTAGRAM_ACCESS_TOKEN', '').strip()
    user_id = os.getenv('INSTAGRAM_USER_ID', '').strip()
    base = os.getenv('PUBLIC_MEDIA_BASE_URL', '').strip()
    version = os.getenv('GRAPH_API_VERSION', 'v27.0').strip()
    if not (token and user_id and base):
        raise RuntimeError('Configure os secrets INSTAGRAM_ACCESS_TOKEN e INSTAGRAM_USER_ID e a variável PUBLIC_MEDIA_BASE_URL.')
    if not (version.startswith('v') and version[1:].replace('.', '').isdigit()):
        raise RuntimeError('GRAPH_API_VERSION inválida.')
    if not user_id.isdecimal():
        raise RuntimeError('INSTAGRAM_USER_ID inválido. Deve ser o ID numérico da conta profissional.')
    url = media_url_for(post, base)
    if session is None:
        import requests
        session = requests.Session()
    media_id = publish_image(post, url, user_id, token, version, session)
    state.setdefault('published', []).append({'id': post['id'], 'media_id': media_id,
                                                'local_date': local_day,
                                                'published_at': datetime.now(timezone.utc).isoformat()})
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(f'Post #{post["id"]} publicado com sucesso. ID da mídia: {media_id}')
    return post


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group()
    g.add_argument('--dry-run', action='store_true', help='Mostra qual seria a próxima publicação, sem enviar nada (padrão).')
    g.add_argument('--publish', action='store_true', help='Publica realmente, desde que autorizado por PUBLISH_ENABLED=true.')
    args=p.parse_args()
    run(publish=args.publish)
