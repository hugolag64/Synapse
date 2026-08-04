"""Normalisation et calculs locaux pour les statistiques EDNpro."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

PRIORITIES = ("indispensable", "important", "basique", "jamais_tombe")
_ITEM_RE = re.compile(r"(?:item\s*#?\s*)?(\d{1,3})(?:\b|$)", re.IGNORECASE)


def _value(row: dict, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def _item_number(value: Any) -> str:
    match = _ITEM_RE.search(str(value or "").strip())
    return match.group(1) if match else ""


def _integer(value: Any) -> int:
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _years(value: Any) -> list[int]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result = set()
    for raw in values:
        match = re.search(r"\b(20\d{2})\b", str(raw or ""))
        if match:
            result.add(int(match.group(1)))
    return sorted(result)


def _priority(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", normalized)
        if unicodedata.category(char) != "Mn"
    )
    aliases = {
        "indispensable": "indispensable",
        "essential": "indispensable",
        "important": "important",
        "basique": "basique",
        "basic": "basique",
        "jamais_tombe": "jamais_tombe",
        "jamais": "jamais_tombe",
        "never": "jamais_tombe",
    }
    return aliases.get(normalized, "basique")


def _looks_like_item_row(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return any(key in value for key in (
        "item", "item_number", "itemNumber", "numero_item", "item_id", "numero", "number"
    ))


def _walk_rows(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        rows = [payload] if _looks_like_item_row(payload) else []
        for value in payload.values():
            rows.extend(_walk_rows(value))
        return rows
    if isinstance(payload, list):
        rows: list[dict] = []
        for value in payload:
            rows.extend(_walk_rows(value))
        return rows
    return []


def normalize_training_payload(
    payload: object, *, source_url: str, collected_at: str, raw_payload_json: str | None = None
) -> list[dict]:
    """Convert EDNpro's changing card/API shapes into one stable item snapshot."""
    del raw_payload_json  # Kept in the public signature for callers retaining the raw artifact.
    merged: dict[str, dict] = {}
    for row in _walk_rows(payload):
        item_number = _item_number(_value(
            row, "item_number", "itemNumber", "item", "numero_item", "item_id", "numero", "number"
        ))
        if not item_number:
            continue
        candidate = {
            "item_number": item_number,
            "priority": _priority(_value(row, "priority", "category", "status", "priorite", "importance", "priority_category")),
            "session_count": _integer(_value(
                row, "session_count", "sessions", "sessions_count", "nb_sessions", "appearances", "occurrences", "annales", "frequency"
            )),
            "question_count": _integer(_value(
                row, "question_count", "questions", "nb_questions", "qcm_count", "qcm", "question_total"
            )),
            "years": _years(_value(
                row, "years", "annees", "passages", "sessions_years", "years_seen", "annees_passage", default=[]
            )),
            "source_url": source_url,
            "collected_at": collected_at,
        }
        current = merged.get(item_number)
        if current is None:
            merged[item_number] = candidate
            continue
        current["session_count"] = max(current["session_count"], candidate["session_count"])
        current["question_count"] = max(current["question_count"], candidate["question_count"])
        current["years"] = sorted(set(current["years"]) | set(candidate["years"]))
        if PRIORITIES.index(candidate["priority"]) < PRIORITIES.index(current["priority"]):
            current["priority"] = candidate["priority"]
    return [merged[key] for key in sorted(merged, key=lambda value: (len(value), value))]


def is_frequency_sync_due(
    collected_at: str | None, *, now: datetime | None = None, interval_days: int = 90
) -> bool:
    if not collected_at:
        return True
    try:
        stamp = datetime.fromisoformat(str(collected_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    current = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current - stamp >= timedelta(days=max(1, int(interval_days)))


def calculate_gain_priority(
    *, session_count: int, mastery: float | None, question_count: int, imported_question_count: int
) -> float:
    """Return a deterministic relative potential; it is not a rank prediction."""
    frequency = max(0, int(session_count or 0))
    gap = max(0.0, min(100.0, 100.0 - float(mastery if mastery is not None else 0.0)))
    expected = max(0, int(question_count or 0))
    available = max(0, int(imported_question_count or 0))
    availability = 0.0 if available <= 0 else (1.0 if expected <= 0 else min(1.0, available / expected))
    return round(frequency * gap * availability, 1)
