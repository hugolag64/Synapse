"""OIC domain operations shared by all Synapse college aliases of an item."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Callable

from loguru import logger

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


def scrape_all_items(
    courses: Iterable,
    on_progress: Callable[[int, int, str], None] | None = None,
    delay_seconds: float = 0.4,
) -> dict:
    """Rafraîchit les OIC LiSA pour tous les items distincts couverts par `courses`.

    Un seul scrape par item_number (pas par cours) ; le résultat est ensuite
    upserté sur CHAQUE cours partageant cet item (collège + UE + autres alias),
    exactement comme `get_item_oics` les regroupe déjà à la lecture. Reconciliation
    (mastered/niveau préservés) déjà assurée par `local_store.upsert_lisa_oic`,
    donc rappelable à volonté pour détecter des ajouts/retraits côté LiSA.

    `on_progress(done, total, item_number)` est appelé (depuis le thread appelant,
    généralement via asyncio.to_thread) après chaque item traité — à l'appelant
    de le rendre thread-safe pour l'UI.
    """
    from backend.core.lisa.scraper import LisaFetchError, scrape_oic

    groups: dict[str, list] = {}
    for c in courses:
        item_key = str(getattr(c, "display_item_number", "") or getattr(c, "item_number", "") or "").strip()
        if not item_key:
            continue
        groups.setdefault(item_key, []).append(c)

    def _sort_key(item_key: str) -> tuple[int, str]:
        try:
            return (0, f"{int(float(item_key.replace(',', '.'))):06d}")
        except (TypeError, ValueError):
            return (1, item_key)

    ordered_items = sorted(groups.items(), key=lambda kv: _sort_key(kv[0]))
    total = len(ordered_items)
    ok = 0
    errors: list[dict] = []

    for index, (item_key, group_courses) in enumerate(ordered_items, start=1):
        title = group_courses[0].title if group_courses else ""
        try:
            oics = scrape_oic(title, item_key)
            for course in group_courses:
                local_store.upsert_lisa_oic(course.id, oics)
            ok += 1
        except LisaFetchError as exc:
            errors.append({"item_number": item_key, "error": str(exc)})
            logger.warning(f"scrape_all_items: item {item_key} échoué : {exc}")
        except Exception as exc:
            errors.append({"item_number": item_key, "error": str(exc)})
            logger.error(f"scrape_all_items: erreur inattendue sur l'item {item_key} : {exc}")

        if on_progress:
            try:
                on_progress(index, total, item_key)
            except Exception:
                pass

        if index < total:
            time.sleep(delay_seconds)

    return {"items_total": total, "items_ok": ok, "items_failed": len(errors), "errors": errors}
