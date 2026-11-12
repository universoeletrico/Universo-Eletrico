"""Publicador do Universo Eletrico via API oficial Meta.

Seguranca: reserva e persiste um post ANTES de enviar qualquer chamada de
publicacao para a Meta. Se houver falha, a reserva bloqueia novos posts ate
revisao humana; nunca tenta publicar novamente automaticamente.
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


def save_state(state):
    tmp = STATE_FILE.with_name(STATE_FILE.name + '.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(STATE_FILE)


def select_next(posts, state, local_day):
    """Retorna proximo post; nunca pula reservas ou posts agendados."""
    if state.get('pending'):
        return None, ('Existe uma publicacao reservada, ainda sem confirmacao. '
                      'Revise o Instagram e o historico antes de continuar.')
    start = state.get('not_before_date')
    if start and local_day < start:
        return None, f'Robo so pode publicar a partir de {start}.'
    scheduled = state.get('externally_scheduled', [])
    if any(entry.get('date') == local_day for entry in scheduled):
        return None, 'Ja existe publicacao programada manualmente nessa data.'
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
        raise ValueError('PUBLIC_MEDIA_BASE_URL precisa ser um endereco HTTPS publico valido.')
    return urljoin(base_url, f'posts/{post["id"]}.jpg')


def json_from_response(response):
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f'API Meta respondeu com conteudo invalido (HTTP {response.status_code}).') from exc
    if response.status_code >= 400 or 'error' in payload:
        err = payload.get('error', {})
        raise RuntimeError(f'API Meta recusou a solicitacao (HTTP {response.status_code}): '
                           f'{err.get("message", "erro desconhecido")}; codigo {err.get("code", "?")}')
    return payload


def graph_post(session, url, token, data):
    response = session.post(url, data=data, headers={'Authorization': f'Bearer {token}'}, timeout=40)
    return json_from_response(response)


def graph_get(session, url, token, params):
    response = session.get(url, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=40)
    return json_from_response(response)


def publish_image(post, url, user_id, token, version, session, *, retries=12, sleep_seconds=10):
    import time
    endpoint = f'https://graph.facebook.com/{version}'
    created = graph_post(session, f'{endpoint}/{user_id}/media', token,
                         {'image_url': url, 'caption': post['caption'],
                          'alt_text': f'Universo Eletrico: {post["hook"]} {post["body"]}'})
    container_id = created.get('id')
    if not container_id:
        raise RuntimeError('A Meta nao retornou identificador do container.')
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
        raise RuntimeError('Imagem nao ficou pronta. Confira a Meta antes de tentar novamente.')
    published = graph_post(session, f'{endpoint}/{user_id}/media_publish', token,
                           {'creation_id': container_id})
    if not published.get('id'):
        raise RuntimeError('Meta nao confirmou a publicacao; confira Instagram antes de repetir.')
    return published['id']


def manual_early_test_allowed(day, post_id):
    """Excecao unica, estritamente para o teste manual aprovado do post 002 em 11/11."""
    return (
        os.getenv('MANUAL_TEST_POST_ID', '') == '002'
        and day == '2026-11-11'
        and post_id == '002'
    )


def reserve_for_day(now):
    day = now.astimezone(TZ).date().isoformat()
    posts, state = load_json(POSTS_FILE), load_json(STATE_FILE)
    # A regra geral de inicio permanece 13/11. Apenas o fluxo manual de 11/11
    # pode reservar o post 002 antes da data. Agendamentos e duplicacoes seguem protegidos.
    selection_state = dict(state)
    if manual_early_test_allowed(day, '002'):
        selection_state['not_before_date'] = day
    post, reason = select_next(posts, selection_state, day)
    if post and os.getenv('MANUAL_TEST_POST_ID') and post['id'] != os.getenv('MANUAL_TEST_POST_ID'):
        raise RuntimeError('Post reservado nao corresponde ao teste manual autorizado.')
    if not post:
        print(reason)
        return None
    if os.getenv('PUBLISH_ENABLED', '').lower() != 'true':
        raise RuntimeError('Reserva recusada: PUBLISH_ENABLED nao esta true.')
    state['pending'] = {
        'id': post['id'], 'local_date': day,
        'reserved_at': datetime.now(timezone.utc).isoformat()
    }
    save_state(state)
    print(f'Post #{post["id"]} reservado. O historico DEVE ser enviado ao GitHub antes de publicar.')
    return post


def run(*, publish=False, reserve=False, now=None, session=None):
    if publish and reserve:
        raise ValueError('Nao e possivel reservar e publicar ao mesmo tempo.')
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError('now deve conter fuso horario')
    local_day = now.astimezone(TZ).date().isoformat()
    if reserve:
        return reserve_for_day(now)
    posts, state = load_json(POSTS_FILE), load_json(STATE_FILE)
    if not publish:
        post, reason = select_next(posts, state, local_day)
        if post:
            print(f'Simulacao: post #{post["id"]} - {post["title"]} ({local_day}). Nenhuma publicacao enviada.')
        else:
            print(f'Simulacao: {reason} Nenhuma publicacao enviada.')
        return post

    # Somente uma reserva que ja tenha sido salva e enviada ao GitHub pode ser publicada.
    if os.getenv('PUBLISH_ENABLED', '').lower() != 'true':
        raise RuntimeError('Publicacao desativada: PUBLISH_ENABLED != true.')
    pending = state.get('pending')
    if not pending:
        print('Nenhum post reservado. Nada sera publicado.')
        return None
    if pending.get('local_date') != local_day:
        raise RuntimeError('Reserva de outra data: revise manualmente antes de continuar.')
    post = next((p for p in posts if p['id'] == pending.get('id') and p.get('approved')), None)
    if not post:
        raise RuntimeError('Post reservado nao encontrado ou perdeu aprovacao.')
    start = state.get('not_before_date')
    if start and local_day < start and not manual_early_test_allowed(local_day, post['id']):
        raise RuntimeError(f'Publicacao antes de {start} proibida.')
    if any(e.get('date') == local_day for e in state.get('externally_scheduled', [])):
        raise RuntimeError('Data reservada para publicacao manual.')
    if any(e.get('local_date') == local_day or e.get('id') == post['id']
           for e in state.get('published', [])):
        raise RuntimeError('Post ou dia ja foi registrado como publicado.')

    token = os.getenv('INSTAGRAM_ACCESS_TOKEN', '').strip()
    user_id = os.getenv('INSTAGRAM_USER_ID', '').strip()
    base = os.getenv('PUBLIC_MEDIA_BASE_URL', '').strip()
    version = os.getenv('GRAPH_API_VERSION', 'v27.0').strip()
    if not token or not user_id.isdecimal() or not base:
        raise RuntimeError('Credenciais ou PUBLIC_MEDIA_BASE_URL ausentes/invalidas.')
    if not (version.startswith('v') and version[1:].replace('.', '').isdigit()):
        raise RuntimeError('GRAPH_API_VERSION invalida.')
    url = media_url_for(post, base)
    if session is None:
        import requests
        session = requests.Session()
    # Se a chamada da Meta falhar, preservamos pending e BLOQUEAMOS proximas execucoes.
    # Nao repetir automaticamente, pois uma publicacao pode ter acontecido sem retorno.
    media_id = publish_image(post, url, user_id, token, version, session)
    state.setdefault('published', []).append({
        'id': post['id'], 'media_id': media_id, 'local_date': local_day,
        'published_at': datetime.now(timezone.utc).isoformat()
    })
    del state['pending']
    save_state(state)
    print(f'Publicacao confirmada para o post #{post["id"]}.')
    return post


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument('--dry-run', action='store_true', help='Apenas simula (padrao).')
    g.add_argument('--reserve', action='store_true', help='Reserva no historico; workflow deve gravar antes de publicar.')
    g.add_argument('--publish', action='store_true', help='Publica somente uma reserva ja salva no GitHub.')
    args = p.parse_args()
    run(publish=args.publish, reserve=args.reserve)
