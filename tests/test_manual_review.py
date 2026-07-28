from __future__ import annotations

import datetime

import pytest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "manual.db")
    monkeypatch.setattr(store, "_DB", None)
    store.init_db()
    yield store
    if store._DB is not None:
        store._DB.close()
    monkeypatch.setattr(store, "_DB", None)


def test_record_manual_review_writes_history_and_session_on_selected_date(isolated_db):
    store = isolated_db
    review_date = datetime.date(2026, 8, 7)

    event_id = store.record_manual_review(
        course_id="course-1",
        course_title="Infections à VIH",
        item_number="169",
        context="college",
        review_date=review_date,
        activity_types=["révision"],
        duration_minutes=20,
        confidence=3,
        difficulty="moyen",
    )

    history = store.get_review_history_by_course("course-1")
    sessions = store.get_sessions_by_course()["course-1"]
    assert event_id.startswith("manual_course-1_")
    assert history[0]["review_type"] == "manuel"
    assert history[0]["completed_at"] == "2026-08-07"
    assert sessions[0]["session_date"] == "2026-08-07"
    assert sessions[0]["confidence"] == 3


def test_manual_review_count_is_separate_from_lecture_count(isolated_db):
    store = isolated_db
    for day in (7, 10):
        store.record_manual_review(
            "course-1", "Item", "169", "college", datetime.date(2026, 8, day),
            ["révision"], 20, 3, "moyen",
        )

    assert store.get_manual_review_count("course-1") == 2
