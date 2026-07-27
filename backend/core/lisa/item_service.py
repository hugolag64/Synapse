"""OIC domain operations shared by all Synapse college aliases of an item."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from backend.core.reviews import local_store


def _value(row: Mapping | object, key: str, default=None):
    try:
        return row[key]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def merge_oic_rows(rows: Iterable[Mapping | object]) -> list[dict]:
    """Deduplicate historical per-course rows into canonical item OIC rows."""
    grouped: dict[str, dict] = {}
    for raw in rows:
        code = str(_value(raw, "oic_code", "") or "").strip()
        if not code:
            code = f"__row__{_value(raw, 'id', len(grouped))}"
        row = dict(raw) if isinstance(raw, Mapping) else {
            key: _value(raw, key)
            for key in (
                "id", "course_id", "oic_code", "intitule", "rang",
                "rubrique", "ordre", "mastered", "oic_level", "fetched_at",
            )
        }
        current = grouped.get(code)
        if current is None:
            current = dict(row)
            current["oic_code"] = _value(raw, "oic_code", "") or None
            current["mastered"] = _as_int(_value(raw, "mastered"))
            current["oic_level"] = _as_int(_value(raw, "oic_level"))
            current["source_ids"] = []
            current["source_course_ids"] = []
            grouped[code] = current
        source_id = _value(raw, "id")
        if source_id is not None and source_id not in current["source_ids"]:
            current["source_ids"].append(source_id)
        source_course_id = _value(raw, "course_id")
        if source_course_id and source_course_id not in current["source_course_ids"]:
            current["source_course_ids"].append(source_course_id)
        current["mastered"] = max(current["mastered"], _as_int(_value(raw, "mastered")))
        current["oic_level"] = max(current["oic_level"], _as_int(_value(raw, "oic_level")))

    def sort_key(row: dict):
        rang = str(row.get("rang") or "Z").upper()
        rang_order = {"A": 0, "B": 1}.get(rang, 2)
        return (rang_order, _as_int(row.get("ordre")), str(row.get("oic_code") or ""))

    return sorted(grouped.values(), key=sort_key)


def reconcile_oic_rows(existing_rows: Iterable[Mapping | object], incoming_rows: Iterable[Mapping | object]) -> list[dict]:
    """Merge a LiSA response while retaining identity and learning state."""
    existing = {
        str(_value(row, "oic_code", "") or ""): dict(row)
        for row in existing_rows
        if _value(row, "oic_code", "")
    }
    result: list[dict] = []
    for raw in incoming_rows:
        code = str(_value(raw, "oic_code", "") or "")
        if not code:
            continue
        row = dict(raw) if isinstance(raw, Mapping) else {}
        previous = existing.get(code, {})
        row["oic_code"] = code
        row["id"] = previous.get("id")
        row["mastered"] = max(_as_int(previous.get("mastered")), _as_int(row.get("mastered")))
        row["oic_level"] = max(_as_int(previous.get("oic_level")), _as_int(row.get("oic_level")))
        result.append(row)
    return result


def get_item_oics(course_ids: Sequence[str]) -> list[dict]:
    rows = []
    for course_id in dict.fromkeys(course_ids):
        cached = local_store.get_lisa_oic(course_id)
        if cached:
            rows.extend(cached)
    return merge_oic_rows(rows)


def set_item_oic_mastery(course_ids: Sequence[str], oic_code: str, mastered: bool) -> None:
    """Set one canonical mastery state across every matching course alias."""
    for course_id in dict.fromkeys(course_ids):
        rows = local_store.get_lisa_oic(course_id) or []
        for row in rows:
            if _value(row, "oic_code") != oic_code:
                continue
            current = bool(_value(row, "mastered", 0))
            if current != mastered:
                local_store.toggle_lisa_oic_mastery(_value(row, "id"))


def get_item_oic_attempts(course_ids: Sequence[str], oic_code: str, limit: int = 10) -> list:
    attempts = []
    for course_id in dict.fromkeys(course_ids):
        for row in local_store.get_lisa_oic(course_id) or []:
            if _value(row, "oic_code") == oic_code:
                attempts.extend(local_store.get_oic_attempts(_value(row, "id"), limit=limit))
    unique = {row["id"]: row for row in attempts}
    return sorted(unique.values(), key=lambda row: row["id"], reverse=True)[:limit]


def save_item_oic_attempt(course_ids: Sequence[str], oic_code: str, session_score: int, questions_json: str) -> int:
    """Save one attempt on a stable source row and propagate success state."""
    rows = get_item_oics(course_ids)
    target = next((row for row in rows if row.get("oic_code") == oic_code), None)
    if target is None or not target.get("source_ids"):
        raise ValueError(f"OIC introuvable pour l'item: {oic_code}")
    attempt_id = local_store.save_oic_attempt(target["source_ids"][0], session_score, questions_json)
    if session_score >= 70:
        set_item_oic_mastery(course_ids, oic_code, True)
    return attempt_id


def set_item_oic_level(course_ids: Sequence[str], oic_code: str, new_level: int) -> None:
    """Propagate the evaluator level to every alias row of the item OIC."""
    for course_id in dict.fromkeys(course_ids):
        for row in local_store.get_lisa_oic(course_id) or []:
            if _value(row, "oic_code") == oic_code:
                local_store.update_oic_level(_value(row, "id"), new_level)
