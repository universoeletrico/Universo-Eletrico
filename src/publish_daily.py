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
CAMPAIGNS_FILE = ROOT / 'content' / 'commercial_campaigns.json'
STATE_FILE = ROOT / 'content' / 'state.json'
TZ = ZoneInfo('America/Sao_Paulo')

try:
    from src.schedule_rules import read_schedule, due_slot
except ModuleNotFoundError:
    from schedule_rules import read_schedule, due_slot



def ready_commercial_posts():
    """Obtém somente campanhas autorizadas, com link e arte disponível.

    O arquivo de campanhas é separado para não modificar a fila educativa,
    e a leitura não acrescenta chamadas ao helper load_json nos testes.
    """
    if not CAMPAIGNS_FILE.exists():
        return []
    from painel.affiliates import validate_affiliate_url, require_disclosure
    document = json.loads(CAMPAIGNS_FILE.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or not isinstance(document.get('campaigns'), list):
        raise ValueError('Arquivo de campanhas comerciais inválido.')
    posts = []
    seen = set()
    for entry in document['campaigns']:
        if entry.get('status') != 'queued':
            continue
        pid = str(entry.get('id', ''))
        if not (len(pid) == 4 and pid.startswith('C') and pid[1:].isdigit()) or pid in seen:
            raise ValueError('Identificador de campanha inválido ou duplicado.')
        seen.add(pid)
        link = validate_affiliate_url(entry.get('affiliate_url', ''), 'mercadolivre')
        caption = entry.get('caption', '')
        require_disclosure(caption)
        # Evita publicar uma campanha se o JPEG ainda não foi gerado.
        if not (ROOT / 'docs' / 'posts' / f'{pid}.jpg').exists():
            continue
        posts.append({
            'id': pid, 'kind': 'commercial', 'approved': True,
            'title': entry['name'], 'hook': entry['hook'],
            'body': entry['body'], 'caption': caption,
            'affiliate_url': link,
        })
    return posts


def load_json(path: Path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if path == POSTS_FILE:
        if not isinstance(data, list):
            raise ValueError('Fila de posts educativos inválida.')
        return data + ready_commercial_posts()
    return data


def save_state(state):
    tmp = STATE_FILE.with_name(STATE_FILE.name + '.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(STATE_FILE)


def select_next(posts, state, local_day, max_per_day=1, slot=None):
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
    today_posts = [p for p in state.get('published', []) if p.get('local_date') == local_day]
    if len(today_posts) >= max_per_day:
        return None, 'Já foi publicado o limite de posts nesta data.'
    if slot is not None and any(p.get('slot') in (None, slot) for p in today_posts):
        return None, 'Já foi publicado neste horario, ou existe uma publicacao sem horario registrado.'
    reserved = {entry['id'] for entry in scheduled}
    published = {entry['id'] for entry in state.get('published', [])}
    eligible = [post for post in posts
                if post.get('approved', False) and post['id'] not in (published | reserved)]
    educational = [post for post in eligible if post.get('kind') != 'commercial']
    commercial = [post for post in eligible if post.get('kind') == 'commercial']

    if educational and commercial:
        # Alterna sem alterar a programação: um post educativo, depois
        # uma indicação comercial. Reserva, histórico e limites permanecem.
        last_id = next((str(entry.get('id', '')) for entry in reversed(state.get('published', []))
                        if entry.get('id')), '')
        next_group = commercial if not last_id.startswith('C') else educational
        return next_group[0], None
    if educational:
        return educational[0], None
    if commercial:
        return commercial[0], None
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
    agenda = read_schedule()
    event = os.getenv('GITHUB_EVENT_NAME', '')
    slot = None
    if event == 'schedule':
        slot = due_slot(agenda, now)
        if slot is None:
            print('Agenda pausada ou horario nao corresponde: nao reservar.')
            return None
    elif event == 'workflow_dispatch' and os.getenv('MANUAL_TEST_POST_ID') != '002':
        print('O robo diario nao publica por acionamento manual; use o teste separado.')
        return None
    # A regra geral de inicio permanece 13/11. Apenas o fluxo manual de 11/11
    # pode reservar o post 002 antes da data. Agendamentos e duplicacoes seguem protegidos.
    selection_state = dict(state)
    if manual_early_test_allowed(day, '002'):
        selection_state['not_before_date'] = day
    post, reason = select_next(
        posts, selection_state, day,
        max_per_day=len(agenda['times']), slot=slot
    )
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
    if slot:
        state['pending']['slot'] = slot
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
    if pending.get('slot'):
        agenda = read_schedule()
        expected_slot = due_slot(agenda, now)
        if expected_slot != pending['slot']:
            raise RuntimeError('Agenda alterada ou horario expirou; revisar reserva antes de publicar.')
    post = next((p for p in posts if p['id'] == pending.get('id') and p.get('approved')), None)
    if not post:
        raise RuntimeError('Post reservado nao encontrado ou perdeu aprovacao.')
    start = state.get('not_before_date')
    if start and local_day < start and not manual_early_test_allowed(local_day, post['id']):
        raise RuntimeError(f'Publicacao antes de {start} proibida.')
    if any(e.get('date') == local_day for e in state.get('externally_scheduled', [])):
        raise RuntimeError('Data reservada para publicacao manual.')
    if any(e.get('id') == post['id'] for e in state.get('published', [])):
        raise RuntimeError('Post ja foi registrado como publicado.')
    today_posts = [e for e in state.get('published', []) if e.get('local_date') == local_day]
    max_count = len(read_schedule()['times'])
    if len(today_posts) >= max_count:
        raise RuntimeError('Limite de posts por dia atingido.')
    if pending.get('slot') and any(e.get('slot') in (None, pending['slot']) for e in today_posts):
        raise RuntimeError('Ja houve publicacao neste horario, ou sem horario cadastrado.')
    if not pending.get('slot') and today_posts:
        raise RuntimeError('Publicacao manual adicional no mesmo dia bloqueada.')

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
    record = {
        'id': post['id'], 'media_id': media_id, 'local_date': local_day,
        'published_at': datetime.now(timezone.utc).isoformat()
    }
    if pending.get('slot'):
        record['slot'] = pending['slot']
    state.setdefault('published', []).append(record)
    del state['pending']
    save_state(state)
    print(f'Publicacao confirmada para o post #{post["id"]}.')
    return post


def check_schedule(now=None):
    """Pre-verificacao sem credenciais e sem escrita. GitHub Actions usa para pular execucoes fora da agenda."""
    now = now or datetime.now(TZ)
    agenda = read_schedule()
    slot = due_slot(agenda, now)
    if slot:
        posts, state = load_json(POSTS_FILE), load_json(STATE_FILE)
        today = now.astimezone(TZ).date().isoformat()
        post, reason = select_next(posts, state, today, max_per_day=len(agenda['times']), slot=slot)
        if post:
            output = os.getenv('GITHUB_OUTPUT')
            if output:
                with open(output, 'a', encoding='utf-8') as handle:
                    handle.write(f'ready=true\nslot={slot}\n')
            print(f'Agenda liberou post #{post["id"]} no horario {slot}.')
            return slot
        print(f'Sem post elegivel: {reason}')
    else:
        print('Fora dos horarios de postagem ou agenda pausada.')
    return None


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument('--dry-run', action='store_true', help='Apenas simula (padrao).')
    g.add_argument('--reserve', action='store_true', help='Reserva no historico; workflow deve gravar antes de publicar.')
    g.add_argument('--publish', action='store_true', help='Publica somente uma reserva ja salva no GitHub.')
    g.add_argument('--check-schedule', action='store_true', help='Verifica agenda sem acessar a Meta.')
    args = p.parse_args()
    if args.check_schedule:
        check_schedule()
    else:
        run(publish=args.publish, reserve=args.reserve)
