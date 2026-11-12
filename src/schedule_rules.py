"""Agenda do Universo Eletrico editavel pelo painel web.
Os horarios sao locais de Sao Paulo. Acoes agendadas do GitHub apenas
verificam os horarios; o arquivo JSON e a fonte unica de configuracao.
"""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_FILE = ROOT / "content" / "schedule.json"
TZ = ZoneInfo("America/Sao_Paulo")
DAYS = ("Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo")
DEFAULT = {
    "timezone": "America/Sao_Paulo",
    "enabled": True,
    "days": list(range(7)),
    "times": ["19:17"],
}


def validate_schedule(raw):
    if not isinstance(raw, dict):
        raise ValueError("A configuracao precisa ser um objeto.")
    if raw.get("timezone") != "America/Sao_Paulo":
        raise ValueError("A agenda usa o fuso de Sao Paulo.")
    if type(raw.get("enabled")) is not bool:
        raise ValueError("O estado de ativacao e invalido.")
    days = raw.get("days")
    if not isinstance(days, list) or len(days) > 7:
        raise ValueError("Selecione dias da semana validos.")
    if any(type(day) is not int or day not in range(7) for day in days):
        raise ValueError("Dia da semana invalido.")
    if len(set(days)) != len(days):
        raise ValueError("Dias da semana repetidos.")
    if raw["enabled"] and not days:
        raise ValueError("Ative ao menos um dia para publicar.")
    times = raw.get("times")
    if not isinstance(times, list) or not 1 <= len(times) <= 3:
        raise ValueError("Escolha de 1 a 3 horarios diarios.")
    for t in times:
        if not isinstance(t, str) or not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", t):
            raise ValueError("Use horarios no formato HH:MM.")
        if int(t[:2]) > 23:
            raise ValueError("Hora nao pode ser maior que 23.")
    if len(times) != len(set(times)):
        raise ValueError("Horarios duplicados.")
    minutes = sorted(int(t[:2]) * 60 + int(t[3:]) for t in times)
    if any(b - a < 60 for a, b in zip(minutes, minutes[1:])):
        raise ValueError("Mantenha pelo menos uma hora entre as publicacoes.")
    return {"timezone": "America/Sao_Paulo",
            "enabled": raw["enabled"],
            "days": sorted(days),
            "times": sorted(times)}


def read_schedule():
    if not SCHEDULE_FILE.exists():
        return dict(DEFAULT)
    return validate_schedule(json.loads(SCHEDULE_FILE.read_text(encoding="utf-8")))


def slot_window_open(now, slot):
    local = now.astimezone(TZ)
    hour, minute = map(int, slot.split(":"))
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # GitHub Actions pode iniciar depois do cron: janelinha de tolerancia.
    return start <= local < start + timedelta(minutes=45)


def due_slot(raw_schedule, now):
    schedule = validate_schedule(raw_schedule)
    if not schedule["enabled"] or now.astimezone(TZ).weekday() not in schedule["days"]:
        return None
    return next((t for t in schedule["times"] if slot_window_open(now, t)), None)


def upcoming(raw_schedule, now=None, days_ahead=14):
    schedule = validate_schedule(raw_schedule)
    now = now or datetime.now(TZ)
    day0 = now.astimezone(TZ).date()
    rows = []
    for i in range(days_ahead):
        day = day0 + timedelta(days=i)
        if schedule["enabled"] and day.weekday() in schedule["days"]:
            rows.append({"date": day.strftime("%d/%m/%Y"),
                         "day_name": DAYS[day.weekday()],
                         "times": list(schedule["times"])})
    return rows
