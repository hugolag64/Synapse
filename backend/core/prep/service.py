"""Orchestration de la génération des préparations de cours FAC."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

from backend.config.settings import get_app_timezone
from backend.core.prep.calendar_parser import event_is_cancelled, event_start_date, extract_item_numbers
from backend.core.prep.store import (
    get_prep_task,
    list_prep_tasks,
    move_pending_prep_tasks,
    save_learning_schedule,
    update_prep_task_status,
    upsert_prep_task,
)
from backend.state.catalog_repository import CatalogRepository


@dataclass(frozen=True)
class CoursePrepState:
    """État local nécessaire pour décider quelles préparations manquent."""

    course_id: str
    item_number: str
    pdf_link: str = ""
    obsidian_uri: str = ""
    resume_done: bool = False
    first_read_date: dt.date | None = None


@dataclass
class PrepSyncReport:
    events_seen: int = 0
    events_processed: int = 0
    tasks_created: int = 0
    tasks_existing: int = 0
    events_cancelled: int = 0
    events_moved: int = 0
    unresolved_items: list[str] | None = None

    def __post_init__(self) -> None:
        if self.unresolved_items is None:
            self.unresolved_items = []


def _parse_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def default_course_resolver(item_number: str) -> CoursePrepState | None:
    """Résout une fiche collège depuis le catalogue SQLite local."""
    repository = CatalogRepository()
    item = repository.get_item_by_number(int(item_number))
    if item is None:
        return None

    for fiche in repository.list_fiches(item.id):
        payload = repository.get_fiche_payload(fiche.id)
        colleges = payload.get("college") or repository.get_fiche_colleges(fiche.id)
        if not colleges:
            continue
        return CoursePrepState(
            course_id=str(fiche.id),
            item_number=str(item.item_number),
            pdf_link=str(payload.get("url_pdf") or "").strip(),
            obsidian_uri=str(payload.get("obsidian_uri") or "").strip(),
            resume_done=bool(payload.get("resume_done")),
            first_read_date=_parse_date(payload.get("date_1ere_lecture")),
        )
    return None


def _missing_task_types(course: CoursePrepState) -> tuple[str, ...]:
    missing: list[str] = []
    if not course.pdf_link:
        missing.append("pdf")
    if not course.obsidian_uri:
        missing.append("obsidian")
    if not course.resume_done:
        missing.append("resume")
    if course.first_read_date is None:
        missing.append("first_read")
    return tuple(missing)


def sync_fac_events(
    events: list[dict[str, Any]],
    run_date: dt.date,
    *,
    course_resolver: Callable[[str], CoursePrepState | None] = default_course_resolver,
    timezone: dt.tzinfo | None = None,
    source_calendar_id: str | None = None,
) -> PrepSyncReport:
    """Génère les tâches des cours à J+1 et J+2, de manière idempotente."""
    timezone = timezone or get_app_timezone()
    report = PrepSyncReport(events_seen=len(events))
    accepted_dates = {run_date + dt.timedelta(days=1), run_date + dt.timedelta(days=2)}

    for event in events:
        if source_calendar_id and event.get("_synapse_calendar_id") != source_calendar_id:
            continue
        if event_is_cancelled(event):
            event_id = str(event.get("id") or "").strip()
            if event_id:
                from backend.core.prep.store import cancel_pending_prep_tasks

                if cancel_pending_prep_tasks(event_id):
                    report.events_cancelled += 1
            continue

        lecture_date = event_start_date(event, timezone)
        if lecture_date not in accepted_dates:
            continue

        event_id = str(event.get("id") or "").strip()
        title = str(event.get("summary") or "").strip()
        item_numbers = extract_item_numbers(title)
        if not item_numbers:
            continue

        report.events_processed += 1
        if event_id:
            report.events_moved += move_pending_prep_tasks(event_id, lecture_date, title)
        for item_number in item_numbers:
            course = course_resolver(item_number)
            if course is None:
                report.unresolved_items.append(item_number)
                logger.warning("Cours FAC ignoré : item {} absent du catalogue local", item_number)
                continue

            existing = {
                task.task_type
                for task in list_prep_tasks(
                    lecture_date,
                    statuses=("todo", "done", "cancelled"),
                )
                if task.course_id == course.course_id
            }
            for task_type in _missing_task_types(course):
                task = upsert_prep_task(
                    course_id=course.course_id,
                    item_number=course.item_number,
                    lecture_date=lecture_date,
                    calendar_event_id=event_id,
                    calendar_title=title,
                    task_type=task_type,
                )
                if task_type in existing:
                    report.tasks_existing += 1
                else:
                    report.tasks_created += 1

    return report


def anchor_first_read(
    course_id: str,
    first_read_date: dt.date | None = None,
    context: str = "college",
) -> Any:
    """Ancre le cycle J1→J30 d'un item depuis une vue, sans passer par Notion.

    Le moteur de révisions n'entre en jeu que si l'item porte une date de
    référence. Elle n'existait que par deux chemins : l'écriture Notion
    « Démarrer le suivi » (qui exige un PDF lié, absent sur 256 items, et
    dépend d'une resynchronisation) et le calendrier FAC. Résultat mesuré :
    1 seule fiche sur 582 franchissait ce filtre, donc 0 révision planifiée.

    Cette fonction est le chemin local : elle pose les cinq échéances et
    invalide le cache du moteur pour que la vue suivante les voie.
    """
    if not str(course_id or "").strip():
        raise ValueError("course_id obligatoire")
    day = first_read_date or dt.date.today()
    schedule = save_learning_schedule(str(course_id), day, context=context)
    try:
        from backend.core.knowledge.item_progress import invalidate_schedule_cache
        from backend.core.reviews.service import review_service

        invalidate_schedule_cache()
        review_service.invalidate_cache()
    except Exception as exc:  # pragma: no cover - cache best effort
        logger.warning(f"cache de révisions non invalidé pour {course_id}: {exc}")
    return schedule


def validate_prep_task(task_id: int) -> Any:
    """Valide manuellement une préparation et ancre le cycle si nécessaire."""
    task = get_prep_task(task_id)
    if task is None:
        raise KeyError(f"Tâche de préparation introuvable: {task_id}")
    if task.status == "cancelled":
        raise ValueError("Une tâche annulée ne peut pas être validée")

    if task.task_type == "first_read":
        anchor_first_read(task.course_id, task.lecture_date, context="college")
    return update_prep_task_status(task.id, "done")
