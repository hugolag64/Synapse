"""ensure_schedule() étale le backlog de consolidation sur les jours suivants,
de façon stable entre deux appels tant que rien ne change — remplace le
comportement où tout le backlog s'empilait sur « aujourd'hui »."""
import datetime
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.knowledge.store as ks
    import backend.core.reviews.local_store as ls

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls  # noqa: E402
from backend.core.reviews import consolidation  # noqa: E402
from backend.state.store import data_store  # noqa: E402

_TODAY = datetime.date(2026, 8, 21)


@pytest.fixture(autouse=True)
def _empty_preferences(monkeypatch):
    monkeypatch.setattr(data_store, "preferences", {})


def _tasks(n: int, *, prefix: str = "course", due_date=_TODAY, days_overdue=5):
    return [
        SimpleNamespace(
            course_id=f"{prefix}-{i}", days_overdue=days_overdue, semestre=None,
            mastery_level="à consolider", college=[f"college-{i}"], due_date=due_date,
        )
        for i in range(n)
    ]


def test_spreads_a_large_backlog_across_several_days(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(14))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    by_day: dict[datetime.date, int] = {}
    for day in schedule.values():
        by_day[day] = by_day.get(day, 0) + 1
    assert by_day[_TODAY] == 6
    assert by_day[_TODAY + datetime.timedelta(days=1)] == 6
    assert by_day[_TODAY + datetime.timedelta(days=2)] == 2


def test_is_stable_across_two_calls_with_no_change(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(10))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    first = consolidation.ensure_schedule("college", today=_TODAY)
    second = consolidation.ensure_schedule("college", today=_TODAY)

    assert first == second


def test_a_day_that_has_passed_reassigns_its_items_forward(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(12))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)
    tomorrow = _TODAY + datetime.timedelta(days=1)

    schedule = consolidation.ensure_schedule("college", today=tomorrow)

    assert all(day >= tomorrow for day in schedule.values())
    by_day: dict[datetime.date, int] = {}
    for day in schedule.values():
        by_day[day] = by_day.get(day, 0) + 1
    assert by_day[tomorrow] == 6


def test_a_manual_postpone_invalidates_a_stale_earlier_assignment(monkeypatch):
    tasks = _tasks(3)
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: tasks)
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)

    postponed_to = _TODAY + datetime.timedelta(days=5)
    tasks[0] = SimpleNamespace(
        course_id="course-0", days_overdue=0, semestre=None,
        mastery_level="à consolider", college=["college-0"], due_date=postponed_to,
    )

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    assert schedule["course-0"] >= postponed_to


def test_zero_capacity_day_is_skipped(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(2))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))
    data_store.preferences = {
        "planning_targets": {_TODAY.isoformat(): {"mode": "minutes", "value": 0}}
    }

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    assert _TODAY not in schedule.values()
    assert all(day == _TODAY + datetime.timedelta(days=1) for day in schedule.values())


def test_todays_cap_shrinks_by_dismissals_without_backfilling_the_freed_slot(monkeypatch):
    tasks = _tasks(6)
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: tasks)
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)  # course-0..5 all land on _TODAY

    ls.postpone(
        task_id=f"course-0_college_consolidation_{_TODAY.isoformat()}",
        course_id="course-0", context="college", review_type="consolidation",
        theoretical_due_date=_TODAY, postponed_to=_TODAY + datetime.timedelta(days=7),
    )
    # course-0 drops out of the due backlog (postponed, like real filtering would do);
    # a brand new item enters at the same time — without the shrink it would fill the freed slot.
    tasks[:] = _tasks(6)[1:] + [SimpleNamespace(
        course_id="course-new", days_overdue=5, semestre=None,
        mastery_level="à consolider", college=["college-new"], due_date=_TODAY,
    )]

    schedule = consolidation.ensure_schedule("college", today=_TODAY)

    assert sum(1 for day in schedule.values() if day == _TODAY) == 5
    assert schedule.get("course-new") != _TODAY


def test_reschedule_from_cascades_the_surplus_to_later_days(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(6))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)  # all 6 land on _TODAY

    data_store.preferences = {
        "planning_targets": {_TODAY.isoformat(): {"mode": "minutes", "value": 90}}
    }
    schedule = consolidation.reschedule_from("college", _TODAY, today=_TODAY)

    by_day: dict[datetime.date, int] = {}
    for day in schedule.values():
        by_day[day] = by_day.get(day, 0) + 1
    assert by_day[_TODAY] == 6  # target_for_day > 0 (90min) still lets the item-count cap (6) decide

    # capacity reduced to 0 instead: everything must move off _TODAY
    data_store.preferences = {
        "planning_targets": {_TODAY.isoformat(): {"mode": "minutes", "value": 0}}
    }
    schedule = consolidation.reschedule_from("college", _TODAY, today=_TODAY)
    assert _TODAY not in schedule.values()


def test_reschedule_from_does_not_touch_days_before_it(monkeypatch):
    monkeypatch.setattr(consolidation, "get_due_consolidation_tasks", lambda *a, **k: _tasks(12))
    monkeypatch.setattr(consolidation, "daily_caps", lambda **_: (6, 6))

    consolidation.ensure_schedule("college", today=_TODAY)  # 6 on _TODAY, 6 on _TODAY+1
    tomorrow = _TODAY + datetime.timedelta(days=1)

    data_store.preferences = {
        "planning_targets": {tomorrow.isoformat(): {"mode": "minutes", "value": 0}}
    }
    schedule = consolidation.reschedule_from("college", tomorrow, today=_TODAY)

    assert sum(1 for day in schedule.values() if day == _TODAY) == 6  # untouched
    assert tomorrow not in schedule.values()
