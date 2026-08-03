"""Normalisation et import idempotent de résultats EDN externes."""

from __future__ import annotations

import csv
import datetime
import io
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal


@dataclass(frozen=True)
class ExternalResult:
    source: str
    external_id: str
    session_date: datetime.date
    item_number: str
    activity_type: str
    score_percent: float | None = None
    total_questions: int | None = None
    rank_a_percent: float | None = None
    rank_b_percent: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ImportReport:
    accepted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: tuple[dict, ...] = ()


_REQUIRED = ("source", "external_id", "session_date", "item_number")
_KNOWN = {
    "source", "external_id", "session_date", "item_number", "activity_type",
    "score_percent", "total_questions", "rank_a_percent", "rank_b_percent",
}


def _text(value) -> str:
    return str(value or "").strip()


def _item_number(value) -> str:
    text = _text(value)
    text = re.sub(r"^item\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _optional_float(value, field_name: str) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        result = float(text.replace(",", ".").replace("%", ""))
    except ValueError as exc:
        raise ValueError(f"{field_name} doit être numérique") from exc
    if not 0 <= result <= 100:
        raise ValueError(f"{field_name} doit être compris entre 0 et 100")
    return result


def _optional_int(value, field_name: str) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        result = int(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} doit être entier") from exc
    if result < 0:
        raise ValueError(f"{field_name} doit être positif")
    return result


def _from_mapping(raw: dict, row_number: int) -> ExternalResult:
    missing = [field_name for field_name in _REQUIRED if not _text(raw.get(field_name))]
    if missing:
        raise ValueError(f"ligne {row_number}: champs obligatoires manquants: {', '.join(missing)}")
    try:
        session_date = datetime.date.fromisoformat(_text(raw["session_date"]))
    except ValueError as exc:
        raise ValueError(f"ligne {row_number}: session_date invalide") from exc
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {key: value for key, value in raw.items() if key not in _KNOWN and _text(value)}
    return ExternalResult(
        source=_text(raw["source"]),
        external_id=_text(raw["external_id"]),
        session_date=session_date,
        item_number=_item_number(raw["item_number"]),
        activity_type=_text(raw.get("activity_type")) or "QCM",
        score_percent=_optional_float(raw.get("score_percent"), "score_percent"),
        total_questions=_optional_int(raw.get("total_questions"), "total_questions"),
        rank_a_percent=_optional_float(raw.get("rank_a_percent"), "rank_a_percent"),
        rank_b_percent=_optional_float(raw.get("rank_b_percent"), "rank_b_percent"),
        metadata=metadata,
    )


def parse_external_results(payload: str | bytes, fmt: Literal["csv", "json"]) -> list[ExternalResult]:
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    if fmt == "csv":
        rows = list(csv.DictReader(io.StringIO(text)))
    elif fmt == "json":
        decoded = json.loads(text)
        rows = decoded if isinstance(decoded, list) else [decoded]
    else:
        raise ValueError(f"format inconnu: {fmt}")
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("le fichier doit contenir une liste de résultats")
    return [_from_mapping(row, index) for index, row in enumerate(rows, start=2)]


def import_external_results(results: Iterable[ExternalResult], *, store) -> ImportReport:
    accepted = updated = skipped = 0
    errors: list[dict] = []
    for result in results:
        try:
            outcome = store.upsert_external_result(result)
        except ValueError as exc:
            errors.append({"external_id": result.external_id, "message": str(exc)})
            skipped += 1
            continue
        if outcome == "inserted":
            accepted += 1
        else:
            updated += 1
    return ImportReport(accepted, updated, skipped, tuple(errors))
