import datetime as dt

import pytest

from backend.core.prep.service import CoursePrepState, sync_fac_events
from backend.core.prep.store import list_prep_tasks
from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prep-service.sqlite3"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    local_store._DB = None
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


def _event(summary: str, event_id: str = "event-1", day: str = "2026-08-28") -> dict:
    return {
        "id": event_id,
        "summary": summary,
        "start": {"date": day},
        "end": {"date": day},
    }


def _resolver(states: dict[str, CoursePrepState]):
    return lambda item_number: states.get(item_number)


def test_sync_creates_only_missing_college_preparations():
    states = {
        "363": CoursePrepState("course-363", "363", pdf_link="pdf", first_read_date=dt.date(2026, 8, 20)),
        "362": CoursePrepState("course-362", "362", obsidian_uri="obsidian", resume_done=True),
    }
    report = sync_fac_events(
        [_event("UE7 Orthopédie - items 363, 362")],
        dt.date(2026, 8, 26),
        course_resolver=_resolver(states),
    )

    tasks = list_prep_tasks(dt.date(2026, 8, 28))
    assert {task.course_id + ":" + task.task_type for task in tasks} == {
        "course-363:obsidian",
        "course-363:resume",
        "course-362:pdf",
        "course-362:first_read",
    }
    assert report.tasks_created == 4


def test_sync_is_idempotent_between_j_minus_2_and_catchup_j_minus_1():
    states = {"363": CoursePrepState("course-363", "363")}
    event = _event("Cours - Item 363")
    resolver = _resolver(states)

    first = sync_fac_events([event], dt.date(2026, 8, 26), course_resolver=resolver)
    second = sync_fac_events([event], dt.date(2026, 8, 27), course_resolver=resolver)
    repeated = sync_fac_events([event], dt.date(2026, 8, 26), course_resolver=resolver)

    assert first.tasks_created == 4
    assert second.tasks_created == 0
    assert repeated.tasks_created == 0
    assert len(list_prep_tasks(dt.date(2026, 8, 28))) == 4


def test_sync_ignores_unresolved_items_without_creating_fake_tasks():
    report = sync_fac_events(
        [_event("Cours - Items 363, 999")],
        dt.date(2026, 8, 26),
        course_resolver=_resolver({"363": CoursePrepState("course-363", "363")}),
    )

    assert report.unresolved_items == ["999"]
    assert len(list_prep_tasks(dt.date(2026, 8, 28))) == 4


def test_sync_cancels_existing_pending_event_tasks():
    states = {"363": CoursePrepState("course-363", "363")}
    event = _event("Cours - Item 363")
    sync_fac_events([event], dt.date(2026, 8, 26), course_resolver=_resolver(states))
    cancelled = dict(event, status="cancelled")

    report = sync_fac_events([cancelled], dt.date(2026, 8, 26), course_resolver=_resolver(states))

    assert report.events_cancelled == 1
    assert list_prep_tasks(dt.date(2026, 8, 28)) == []
    assert len(local_store._conn().execute("SELECT * FROM course_prep_tasks WHERE status = 'cancelled'").fetchall()) == 4
