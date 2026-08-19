from datetime import date

import pytest

from backend.core.prep.store import (
    cancel_pending_prep_tasks,
    get_learning_schedule,
    list_prep_tasks,
    move_pending_prep_tasks,
    save_learning_schedule,
    update_prep_task_status,
    upsert_prep_task,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "prep.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
        local_store._DB = None


def test_prep_task_is_idempotent_by_course_date_and_type():
    first = upsert_prep_task("course-1", "363", date(2026, 8, 28), "event-1", "Item 363", "pdf")
    second = upsert_prep_task("course-1", "363", date(2026, 8, 28), "event-1", "Item 363", "pdf")
    assert first.id == second.id
    assert len(list_prep_tasks(date(2026, 8, 28), ("todo",))) == 1


def test_schedule_persists_all_review_dates():
    schedule = save_learning_schedule("course-1", date(2026, 8, 28))
    assert schedule.j1_date == date(2026, 8, 29)
    assert schedule.j3_date == date(2026, 8, 31)
    assert schedule.j7_date == date(2026, 9, 4)
    assert schedule.j14_date == date(2026, 9, 11)
    assert schedule.j30_date == date(2026, 9, 27)
    assert get_learning_schedule("course-1") == schedule


def test_done_status_sets_completion_and_todo_clears_it():
    task = upsert_prep_task("course-1", "363", date(2026, 8, 28), "event-1", "Item 363", "pdf")
    done = update_prep_task_status(task.id, "done")
    assert done.status == "done"
    assert done.completed_at is not None
    reopened = update_prep_task_status(task.id, "todo")
    assert reopened.status == "todo"
    assert reopened.completed_at is None


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        update_prep_task_status(1, "wat")


def test_pending_tasks_can_move_and_cancel_without_deleting_history():
    task = upsert_prep_task("course-1", "363", date(2026, 8, 28), "event-1", "Item 363", "pdf")
    assert move_pending_prep_tasks("event-1", date(2026, 8, 29), "Item 363 déplacé") == 1
    moved = list_prep_tasks(date(2026, 8, 29), ("todo",))[0]
    assert moved.id == task.id
    assert cancel_pending_prep_tasks("event-1") == 1
    assert list_prep_tasks(date(2026, 8, 29), ("cancelled",))[0].id == task.id
