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


from types import SimpleNamespace


def _review_task(course_id, *, days_overdue=0, priority_score=1.0, review_type="review",
                  college=None, item_number="1"):
    return SimpleNamespace(
        course_id=course_id, item_number=item_number, course_title=f"Cours {course_id}",
        best_pdf_url=None, days_overdue=days_overdue, priority_score=priority_score,
        review_type=review_type, anki=False, nb_lectures=1, qcm_done=True,
        mastery_level="à consolider" if review_type == "consolidation" else "correct",
        college=college or ["Cardiologie"], semestre=None,
    )


def test_urgent_tasks_are_never_trimmed_even_over_budget():
    urgent = [_review_task("u1", days_overdue=3)]  # ~30min via get_next_action
    plan = planning_service.plan_day(urgent, [], [], target_minutes=1)

    assert [s.course_id for s in plan.slots if s.is_urgent] == ["u1"]


def test_lecture_consumes_budget_before_consolidation_gets_any():
    today_tasks = [_review_task("t1")]  # ~30 min, review_type="review"
    consolidation_tasks = [_review_task("c1", review_type="consolidation")]

    plan = planning_service.plan_day(
        [], today_tasks, [], target_minutes=20,  # smaller than the 30min lecture task
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    assert all(s.slot_type != "consolidation" for s in plan.slots)
    assert any(getattr(s, "course_id", None) == "c1" for s in plan.skipped)


def test_consolidation_fills_the_remaining_budget():
    consolidation_tasks = [_review_task("c1", review_type="consolidation")]

    plan = planning_service.plan_day(
        [], [], [], target_minutes=120,
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    assert any(s.slot_type == "consolidation" and s.course_id == "c1" for s in plan.slots)
    assert plan.skipped == []


def test_consolidation_respects_college_diversity_cap_within_remaining_budget():
    consolidation_tasks = [
        _review_task(f"c{i}", review_type="consolidation", college=["Cardiologie"], priority_score=10 - i)
        for i in range(5)
    ]  # MAX_PER_COLLEGE_PER_DAY (2) will cap this college regardless of remaining minutes

    plan = planning_service.plan_day(
        [], [], [], target_minutes=600,
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    kept = [s for s in plan.slots if s.slot_type == "consolidation"]
    assert len(kept) == 2


def test_daily_caps_use_the_planned_day_not_the_real_today(monkeypatch):
    from backend.state.store import data_store

    monkeypatch.setitem(data_store.preferences, "weekend_light_consolidation", True)
    consolidation_tasks = [
        _review_task(f"c{i}", review_type="consolidation", college=["Cardiologie"], priority_score=10 - i)
        for i in range(5)
    ]
    saturday = datetime.date(2026, 8, 29)  # a Saturday in a future week

    plan = planning_service.plan_day(
        [], [], [], target_minutes=600,
        consolidation_tasks=consolidation_tasks, consolidation_today=saturday,
    )

    kept = [s for s in plan.slots if s.slot_type == "consolidation"]
    assert len(kept) == 1  # WEEKEND_MAX_PER_COLLEGE_PER_DAY


def test_prep_slots_are_counted_against_the_lecture_budget():
    from backend.core.planning.models import PlannedSlot

    prep = PlannedSlot(slot_type="prep", label="ITEM 187 – Préparer", subtitle="PDF",
                        duration_min=100, color="amber", icon="assignment", course_id="c187")
    consolidation_tasks = [_review_task("c1", review_type="consolidation")]

    plan = planning_service.plan_day(
        [], [], [], target_minutes=110, prep_slots=[prep],
        consolidation_tasks=consolidation_tasks, consolidation_today=datetime.date(2026, 8, 24),
    )

    assert any(s.slot_type == "prep" for s in plan.slots)
    assert all(s.slot_type != "consolidation" for s in plan.slots)  # only 10min left, task needs more
