"""Regras de frequencia do Universo Eletrico; somente configuracao local e segura.

Dias: 0=segunda ... 6=domingo.
Quantidade maxima: 3 por dia, com horarios fixos de Brasilia.
O workflow dispara nas janelas; somente dias/slots permitidos reservam um post.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import json
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_FILE = ROOT / "content" / "schedule.json"
TZ = ZoneInfo("America/Sao_Paulo")
DAYS = ("Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo")
SLOTS_BY_QUANTITY = {
    1: ("19:17",),
    2: ("12:17", "19:17"),
    3: ("12:17", "17:17", "19:17"),
}
DEFAULT = {"timezone": "America/Sao_Paulo", "days": list(range(7)), "posts_per_day": 1}


def validate_schedule(raw):
    if not isinstance(raw, dict):
        raise ValueError("Configuracao de agenda invalida.")
    if raw.get("timezone", "America/Sao_Paulo") != "America/Sao_Paulo":
        raise ValueError("Fuso horario nao permitido nesta fase.")
    days = raw.get("days")
    if not isinstance(days, list) or not days or len(days) > 7:
        raise ValueError("Selecione pelo menos um dia da semana.")
    if any(type(d) is not int or d < 0 or d > 6 for d in days):
        raise ValueError("Dia da semana invalido.")
    if len(set(days)) != len(days):
        raise ValueError("Dias repetidos.")
    amount = raw.get("posts_per_day")
    if type(amount) is not int or amount not in SLOTS_BY_QUANTITY:
        raise ValueError("Selecione entre 1 e 3 postagens por dia.")
    return {"timezone": "America/Sao_Paulo", "days": sorted(days), "posts_per_day": amount}


def read_schedule():
    if not SCHEDULE_FILE.is_file():
        return dict(DEFAULT)
    return validate_schedule(json.loads(SCHEDULE_FILE.read_text(encoding="utf-8")))


def slots_for(schedule):
    return SLOTS_BY_QUANTITY[validate_schedule(schedule)["posts_per_day"]]


def slot_allowed(schedule, now, slot):
    local = now.astimezone(TZ)
    return (local.weekday() in schedule["days"] and slot in slots_for(schedule))


def slot_window_open(now, slot):
    """Falha se uma execucao atrasada ultrapassar 100 minutos do horario configurado."""
    local = now.astimezone(TZ)
    hh, mm = map(int, slot.split(":"))
    target = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return target <= local < target + timedelta(minutes=100)


def preview_days(schedule, now=None, days_ahead=14):
    schedule = validate_schedule(schedule)
    today = (now or datetime.now(TZ)).astimezone(TZ).date()
    return [
        {"date": (today + timedelta(days=i)).isoformat(),
         "weekday": DAYS[(today + timedelta(days=i)).weekday()],
         "slots": slots_for(schedule)}
        for i in range(days_ahead)
        if (today + timedelta(days=i)).weekday() in schedule["days"]
    ]
