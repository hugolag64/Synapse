"""Ancrages de lacunes : rappels persistants pour les erreurs récurrentes."""
from __future__ import annotations

import datetime


ANCHOR_STATUS_ACTIVE = "actif"
ANCHOR_STATUS_INACTIVE = "inactif"


def anchor_status(row) -> str:
    """Retourne l'état d'ancrage d'une ligne weak_points."""
    status = str(_get(row, "status", "") or "").strip().lower()
    if status == "résolue":
        return ANCHOR_STATUS_INACTIVE

    severity = _int(_get(row, "severity", 0))
    recurrence_count = _int(_get(row, "recurrence_count", 0))
    if status == "récurrente" or recurrence_count >= 2 or severity >= 4:
        return ANCHOR_STATUS_ACTIVE
    return ANCHOR_STATUS_INACTIVE


def anchor_interval_days(row) -> int:
    """Intervalle de rappel selon le nombre de réapparitions."""
    recurrence_count = _int(_get(row, "recurrence_count", 0))
    if recurrence_count <= 1:
        return 3
    if recurrence_count <= 3:
        return 7
    return 14


def anchor_priority(row) -> int:
    """Priorité stable pour trier les ancrages dans l'interface."""
    severity = max(1, min(5, _int(_get(row, "severity", 1))))
    recurrence_count = max(0, _int(_get(row, "recurrence_count", 0)))
    recurrent_bonus = 5 if str(_get(row, "status", "")) == "récurrente" else 0
    return severity * 10 + min(recurrence_count, 10) * 5 + recurrent_bonus


def is_anchor_due(row, today: datetime.date | None = None) -> bool:
    """Indique si un ancrage actif doit réapparaître aujourd'hui."""
    if anchor_status(row) != ANCHOR_STATUS_ACTIVE:
        return False
    today = today or datetime.date.today()
    raw = _get(row, "last_reviewed_at") or _get(row, "created_at")
    reviewed = _coerce_date(raw)
    if reviewed is None:
        return True
    return (today - reviewed).days >= anchor_interval_days(row)


def _get(row, key: str, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_date(value) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.date.fromisoformat(text[:10])
        except ValueError:
            return None
