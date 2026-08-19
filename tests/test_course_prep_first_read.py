import datetime as dt

import pytest

from backend.core.prep.service import validate_prep_task
from backend.core.prep.store import get_learning_schedule, upsert_prep_task
from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prep-first-read.sqlite3"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    local_store._DB = None
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


def test_validating_first_read_anchors_all_local_review_dates_to_lecture_day():
    task = upsert_prep_task(
        "course-363", "363", dt.date(2026, 8, 28), "event-1", "Item 363", "first_read"
    )

    validated = validate_prep_task(task.id)
    schedule = get_learning_schedule("course-363")

    assert validated.status == "done"
    assert schedule is not None
    assert schedule.first_read_date == dt.date(2026, 8, 28)
    assert schedule.j1_date == dt.date(2026, 8, 29)
    assert schedule.j3_date == dt.date(2026, 8, 31)
    assert schedule.j7_date == dt.date(2026, 9, 4)
    assert schedule.j14_date == dt.date(2026, 9, 11)
    assert schedule.j30_date == dt.date(2026, 9, 27)


def test_cancelled_first_read_cannot_be_validated():
    task = upsert_prep_task(
        "course-363", "363", dt.date(2026, 8, 28), "event-1", "Item 363", "first_read"
    )
    from backend.core.prep.store import update_prep_task_status

    update_prep_task_status(task.id, "cancelled")
    with pytest.raises(ValueError, match="annulée"):
        validate_prep_task(task.id)
