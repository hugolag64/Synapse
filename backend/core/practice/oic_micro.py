"""File et sessions d'une micro-question ciblée sur un OIC Rang A."""

from __future__ import annotations

from collections.abc import Sequence

from backend.core.lisa import item_service

from .models import PracticeDifficulty, PracticeKind, PracticeSessionSpec
from .service import PracticeService


def _normalized_course_ids(course_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in course_ids if str(value).strip()))


def get_next_rang_a_oic(course_ids: Sequence[str]) -> dict | None:
    """Sélectionne le prochain OIC A à mesurer, de façon stable et explicable.

    Les objectifs non maîtrisés passent avant ceux déjà validés, puis le nombre
    de tentatives croissant garantit que les trois premières micro-sessions
    couvrent trois OIC distincts quand le cache LiSA les fournit.
    """
    normalized_ids = _normalized_course_ids(course_ids)
    if not normalized_ids:
        return None

    candidates: list[dict] = []
    for row in item_service.get_item_oics(normalized_ids):
        if str(row.get("rang") or "").strip().upper() != "A":
            continue
        code = str(row.get("oic_code") or "").strip()
        if not code:
            continue
        attempts = item_service.get_item_oic_attempts(normalized_ids, code, limit=10_000)
        candidate = dict(row)
        candidate["attempt_count"] = len({int(attempt["id"]) for attempt in attempts})
        candidates.append(candidate)

    if not candidates:
        return None

    def sort_key(row: dict) -> tuple[int, int, int, str]:
        try:
            order = int(row.get("ordre") or 0)
        except (TypeError, ValueError):
            order = 0
        return (
            1 if bool(row.get("mastered")) else 0,
            int(row.get("attempt_count") or 0),
            order,
            str(row.get("oic_code") or ""),
        )

    return min(candidates, key=sort_key)


def create_rang_a_micro_session(
    *,
    course_id: str,
    course_title: str,
    item_number: str,
    course_ids: Sequence[str] | None = None,
    target_code: str | None = None,
    practice_service: PracticeService | None = None,
) -> int:
    """Génère et persiste une session OIC composée d'une seule question fermée."""
    normalized_ids = _normalized_course_ids(course_ids or (course_id,))
    target = get_next_rang_a_oic(normalized_ids)
    if target_code:
        wanted = str(target_code).strip()
        target = next(
            (
                row for row in (item_service.get_item_oics(normalized_ids) or [])
                if str(row.get("oic_code") or "").strip() == wanted
                and str(row.get("rang") or "").strip().upper() == "A"
            ),
            None,
        )
        if target is not None:
            target = dict(target)
            target["attempt_count"] = len(
                item_service.get_item_oic_attempts(normalized_ids, wanted, limit=10_000)
            )
    if target is None:
        raise ValueError("Aucun OIC de rang A disponible pour cet item")

    objective_code = str(target.get("oic_code") or "").strip()
    objective_title = str(target.get("intitule") or "").strip()
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.OIC,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        item_number=str(item_number or ""),
        course_id=str(course_id or ""),
        course_title=str(course_title or ""),
        objective_code=objective_code,
        difficulty=PracticeDifficulty.EDN,
    )
    context = (
        f"MICRO-QUESTION OIC CIBLE : {objective_code} — {objective_title}.\n"
        "La question doit mesurer uniquement cet objectif, sans dériver vers un autre OIC."
    )
    service = practice_service or PracticeService()
    return service.create_new_session(spec, context, max_attempts=2)
