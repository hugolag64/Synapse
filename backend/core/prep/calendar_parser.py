"""Parsing pur des événements Google Calendar de la faculté."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any


_ITEM_KEYWORD = re.compile(r"\bitems?\b", re.IGNORECASE)
_ITEM_LIST = re.compile(
    r"^\s*(?P<items>\d+(?:\s*(?:[,;/]|\bet\b)\s*\d+)*)",
    re.IGNORECASE,
)


def extract_item_numbers(summary: str) -> list[str]:
    """Extrait les numéros placés après ``Item`` ou ``Items``.

    Les occurrences sont renvoyées dans l'ordre du titre, sans doublon. Les
    nombres ailleurs dans le titre (UE, horaires, salle) sont volontairement
    ignorés.
    """
    if not isinstance(summary, str):
        return []

    result: list[str] = []
    for match in _ITEM_KEYWORD.finditer(summary):
        number_list = _ITEM_LIST.match(summary[match.end() :])
        if not number_list:
            continue
        for raw_number in re.findall(r"\d+", number_list.group("items")):
            number = str(int(raw_number))
            if number not in result:
                result.append(number)
    return result


def event_start_date(event: dict[str, Any], timezone: dt.tzinfo) -> dt.date | None:
    """Retourne la date locale de début d'un événement Google Calendar."""
    if not isinstance(event, dict):
        return None
    start = event.get("start")
    if not isinstance(start, dict):
        return None

    if isinstance(start.get("date"), str):
        try:
            return dt.date.fromisoformat(start["date"])
        except ValueError:
            return None

    raw_datetime = start.get("dateTime")
    if not isinstance(raw_datetime, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw_datetime.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone).date()


def event_is_cancelled(event: dict[str, Any]) -> bool:
    """Indique si Google Calendar signale l'événement comme annulé."""
    return isinstance(event, dict) and str(event.get("status", "")).lower() == "cancelled"
