"""Une seule définition de « item commencé », partagée par toutes les vues.

Trois définitions concurrentes cohabitaient : la ligne collège comptait
`date_1ere_lecture` ou une trace d'activité, le panneau de pilotage comptait
`date_1ere_lecture` ou l'existence d'une tâche, et la validation de collège
comptait `date_1ere_lecture` ou un niveau déclaré. Le même écran affichait donc
« 8 / 367 lus » à droite et 257 items lus dans ses propres lignes.

La réponse appartient à l'**item**, pas à la ligne d'où on le regarde : un item
saisi dans trois collèges dont un seul est validé est commencé dans les trois.
"""

from __future__ import annotations

from typing import Iterable


def _alias_ids(course) -> tuple[str, ...]:
    """Toutes les fiches du même item EDN, la fiche ouverte comprise."""
    course_id = str(getattr(course, "id", "") or "")
    try:
        from backend.state.store import data_store

        return tuple({course_id, *(str(value) for value in data_store.alias_ids(course_id))})
    except Exception:
        return (course_id,)


def _labels(values: Iterable | None) -> set[str]:
    return {str(value).strip() for value in (values or ()) if str(value).strip()}


_SCHEDULE_CACHE: dict[str, dict] = {}


def invalidate_schedule_cache() -> None:
    """À appeler après toute écriture de `course_learning_schedule`."""
    _SCHEDULE_CACHE.clear()


def scheduled_first_read_dates(context: str = "college") -> dict:
    """{fiche_id: date de première lecture ancrée}, lu une fois puis mémoïsé.

    La maîtrise interroge cette table pour chacun des 367 items : sans cache,
    c'est une requête par item à chaque rendu de liste.
    """
    cached = _SCHEDULE_CACHE.get(context)
    if cached is not None:
        return cached
    try:
        from backend.core.prep.store import list_learning_schedules

        dates = {
            str(schedule.course_id): schedule.first_read_date
            for schedule in list_learning_schedules(context)
            if schedule.first_read_date
        }
    except Exception:
        dates = {}
    _SCHEDULE_CACHE[context] = dates
    return dates


def scheduled_course_ids(context: str = "college") -> set[str]:
    """Fiches dont le cycle J est ancré (`course_learning_schedule`)."""
    return set(scheduled_first_read_dates(context))


def worked_course_ids() -> set[str]:
    """Fiches portant une trace de travail : activité réelle ou cycle ancré.

    `get_active_course_ids` couvre les révisions faites et les sessions d'annale.
    `course_learning_schedule` couvre les items dont la première lecture a été
    déclarée depuis une vue ou depuis une préparation FAC : le cycle J est posé,
    l'item est commencé même si aucune révision n'a encore été validée.
    """
    from backend.core.reviews.local_store import get_active_course_ids

    return set(get_active_course_ids()) | scheduled_course_ids()


def is_item_started(
    course,
    worked_ids: Iterable[str] | None = None,
    validated_colleges: Iterable[str] | None = None,
) -> bool:
    """L'item a-t-il été commencé, quel que soit le collège d'où on le regarde ?

    Trois signaux, tous portés par l'item et non par la fiche :
      - une date de première lecture sur l'une de ses fiches ;
      - une trace de travail sur l'une de ses fiches (`worked_course_ids`) ;
      - l'appartenance à un collège déclaré validé — l'ancien mode de travail,
        où la validation d'un collège vaut lecture de tous ses items.
    """
    if getattr(course, "date_1ere_lecture", None):
        return True

    worked = _labels(worked_ids)
    if worked and worked.intersection(_alias_ids(course)):
        return True

    validated = _labels(validated_colleges)
    return bool(validated and validated.intersection(_labels(getattr(course, "college", None))))


def validated_college_names(statuses: dict[str, str] | None = None) -> set[str]:
    """Collèges confirmés manuellement, source unique pour `is_item_started`."""
    if statuses is None:
        from backend.core.knowledge import store as knowledge_store

        statuses = knowledge_store.get_all_college_statuses()
    return {name for name, status in (statuses or {}).items() if status == "valide"}
