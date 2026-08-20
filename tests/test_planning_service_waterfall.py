import datetime

from backend.core.planning.service import planning_service
from backend.core.prep.models import PrepTask


def _prep_task(task_type: str, *, course_id: str = "c187", item_number: str = "187") -> PrepTask:
    return PrepTask(
        id=1, course_id=course_id, item_number=item_number,
        lecture_date=datetime.date(2026, 8, 22),
        calendar_event_id="evt-1", calendar_title="Cours HGE",
        task_type=task_type, status="todo",
        created_at="2026-08-20T10:00:00", updated_at="2026-08-20T10:00:00",
        completed_at=None,
    )


def test_slot_from_prep_tasks_aggregates_missing_subtasks():
    durations = planning_service.get_durations()
    tasks = [_prep_task("pdf"), _prep_task("first_read")]

    slot = planning_service._slot_from_prep_tasks(tasks, durations)

    assert slot.slot_type == "prep"
    assert slot.label == "ITEM 187 – Préparer"
    assert slot.subtitle == "PDF · 1ère lecture"
    assert slot.course_id == "c187"
    assert slot.item_number == "187"
    assert slot.duration_min == durations["prep_pdf"] + durations["lecture"]


def test_slot_from_prep_tasks_sums_all_four_types():
    durations = planning_service.get_durations()
    tasks = [_prep_task(t) for t in ("pdf", "obsidian", "resume", "first_read")]

    slot = planning_service._slot_from_prep_tasks(tasks, durations)

    expected = (
        durations["prep_pdf"] + durations["obsidian"]
        + durations["prep_resume"] + durations["lecture"]
    )
    assert slot.duration_min == expected
    assert slot.subtitle == "PDF · Fiche Obsidian · Résumé · 1ère lecture"
