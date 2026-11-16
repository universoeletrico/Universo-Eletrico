"""Reserva segura para publicacao manual explicitamente confirmada do post 003.

Somente cria reserva local. O workflow deve persistir em Git antes de enviar
qualquer chamada para o Instagram. Nao habilita a agenda diaria.
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.publish_daily import POSTS_FILE, STATE_FILE, save_state
from src.schedule_rules import read_schedule

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/Sao_Paulo")


def reserve_manual_003(now=None):
    now = now or datetime.now(TZ)
    day = now.astimezone(TZ).date().isoformat()
    if os.environ.get("MANUAL_POST_ID") != "003":
        raise RuntimeError("Publicacao manual permitida apenas para o post 003.")
    if os.environ.get("PUBLISH_ENABLED") != "true":
        raise RuntimeError("Publicacao desativada.")
    posts = json.loads(POSTS_FILE.read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if state.get("pending"):
        raise RuntimeError("Outra publicacao esta reservada. Revisao humana necessaria.")
    if any(p.get("id") == "003" for p in state.get("published", [])):
        raise RuntimeError("Post 003 ja consta como publicado.")
    if any(p.get("id") == "003" for p in state.get("externally_scheduled", [])):
        raise RuntimeError("Post 003 agendado externamente.")
    if any(p.get("date") == day for p in state.get("externally_scheduled", [])):
        raise RuntimeError("Ja existe publicacao externa para hoje.")
    if any(p.get("local_date") == day for p in state.get("published", [])):
        raise RuntimeError("Ja existe publicacao registrada hoje.")
    if day < state.get("not_before_date", day):
        raise RuntimeError("Data de inicio da publicacao ainda nao alcancada.")
    post = next((p for p in posts if p.get("id") == "003"), None)
    if not post or post.get("approved") is not True or not post.get("caption"):
        raise RuntimeError("Post 003 nao aprovado ou sem legenda.")
    if post.get("media_type") != "IMAGE":
        raise RuntimeError("Formato nao suportado.")
    if not (ROOT / "docs/posts/003.jpg").is_file():
        raise RuntimeError("Imagem do post 003 nao encontrada.")
    if (ROOT / "docs/review/003.jpg").exists():
        raise RuntimeError("Post 003 tem imagem ainda aguardando revisao.")
    # Nao alterar a agenda. Este fluxo e manual e nao consome um horario do cron.
    state["pending"] = {"id": "003", "local_date": day,
                        "reserved_at": now.isoformat(), "source": "studio_manual"}
    save_state(state)
    print("Post 003 reservado; salvar esta reserva no GitHub antes de publicar.")


if __name__ == "__main__":
    reserve_manual_003()
