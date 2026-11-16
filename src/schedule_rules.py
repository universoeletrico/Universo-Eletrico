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
    # Restricao opcional de data: garante que uma autorizacao isolada
    # nunca ative automaticamente a agenda das semanas seguintes.
    only_date = raw.get("only_date")
    if only_date is not None:
        if not isinstance(only_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", only_date):
            raise ValueError("only_date deve estar no formato AAAA-MM-DD.")
        try:
            if datetime.strptime(only_date, "%Y-%m-%d").date().isoformat() != only_date:
                raise ValueError("Data invalida.")
        except ValueError as exc:
            raise ValueError("only_date invalida.") from exc
    # Uma lista fechada de datas permite autorizar dias consecutivos sem
    # liberar a mesma segunda/terca-feira nas semanas seguintes.
    only_dates = raw.get("only_dates")
    if only_dates is not None:
        if only_date is not None:
            raise ValueError("Use only_date ou only_dates, nunca os dois.")
        if not isinstance(only_dates, list) or not 1 <= len(only_dates) <= 31:
            raise ValueError("only_dates deve conter de 1 a 31 datas.")
        if len(set(str(d) for d in only_dates)) != len(only_dates):
            raise ValueError("Datas repetidas em only_dates.")
        for day in only_dates:
            if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
                raise ValueError("Data em only_dates invalida.")
            try:
                if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
                    raise ValueError("Data invalida.")
            except ValueError as exc:
                raise ValueError("Data em only_dates invalida.") from exc
    # Horario excepcional de uma data, sem alterar a rotina diaria.
    # O painel pode continuar usando times para a agenda principal.
    date_overrides = raw.get("date_overrides", {})
    if not isinstance(date_overrides, dict) or len(date_overrides) > 31:
        raise ValueError("date_overrides invalido.")
    for day, special_times in date_overrides.items():
        if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            raise ValueError("Data excepcional invalida.")
        try:
            if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
                raise ValueError("Data excepcional invalida.")
        except ValueError as exc:
            raise ValueError("Data excepcional invalida.") from exc
        if (not isinstance(special_times, list) or len(special_times) != 1 or
                not isinstance(special_times[0], str) or
                not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", special_times[0])):
            raise ValueError("Horario excepcional invalido: apenas uma publicacao por dia.")
    result = {"timezone": "America/Sao_Paulo",
              "enabled": raw["enabled"],
              "days": sorted(days),
              "times": sorted(times)}
    if date_overrides:
        result["date_overrides"] = dict(sorted(date_overrides.items()))
    if only_date is not None:
        result["only_date"] = only_date
    if only_dates is not None:
        result["only_dates"] = sorted(only_dates)
    return result


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
    local_day = now.astimezone(TZ).date()
    if schedule.get("only_date") and local_day.isoformat() != schedule["only_date"]:
        return None
    if schedule.get("only_dates") and local_day.isoformat() not in schedule["only_dates"]:
        return None
    if not schedule["enabled"] or local_day.weekday() not in schedule["days"]:
        return None
    times = schedule.get("date_overrides", {}).get(local_day.isoformat(), schedule["times"])
    return next((t for t in times if slot_window_open(now, t)), None)


def upcoming(raw_schedule, now=None, days_ahead=14):
    schedule = validate_schedule(raw_schedule)
    now = now or datetime.now(TZ)
    day0 = now.astimezone(TZ).date()
    rows = []
    for i in range(days_ahead):
        day = day0 + timedelta(days=i)
        if (schedule["enabled"] and day.weekday() in schedule["days"]
                and (not schedule.get("only_date") or day.isoformat() == schedule["only_date"])
                and (not schedule.get("only_dates") or day.isoformat() in schedule["only_dates"])):
            rows.append({"date": day.strftime("%d/%m/%Y"),
                         "day_name": DAYS[day.weekday()],
                         "times": list(schedule.get("date_overrides", {}).get(
                             day.isoformat(), schedule["times"]))})
    return rows
