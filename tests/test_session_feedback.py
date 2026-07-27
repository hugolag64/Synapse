import asyncio
import datetime

import pytest

from backend.core.reviews import local_store
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.validation import complete_review
from frontend.components.session_feedback import submit_session_feedback


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    previous_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(previous_loop)
    db_path = tmp_path / "reviews.db"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)
    asyncio.set_event_loop(previous_loop)


def _task():
    due = datetime.date(2026, 7, 27)
    return ReviewTask(
        id="task-1",
        course_id="course-1",
        course_title="Cardiologie",
        item_number="75",
        context="college",
        theoretical_due_date=due,
        due_date=due,
        review_type="J7",
    )


def _sessions(course_id):
    with local_store._conn() as con:
        return con.execute(
            "SELECT * FROM study_sessions WHERE course_id = ?", (course_id,)
        ).fetchall()


def test_submit_session_feedback_forwards_full_wizard_result():
    received = {}

    async def on_done(task, card, **feedback):
        received["task"] = task
        received["card"] = card
        received.update(feedback)

    task = object()
    card = object()
    asyncio.run(
        submit_session_feedback(
            on_done,
            task,
            card,
            activity_types=["révision", "qcm"],
            duration_minutes=25,
            confidence=2,
            difficulty="difficile",
            qcm_result="raté",
            weak_category="raisonnement",
            weak_detail="Oubli du diagnostic différentiel",
        )
    )

    assert received == {
        "task": task,
        "card": card,
        "activity_types": ["révision", "qcm"],
        "duration_minutes": 25,
        "confidence": 2,
        "difficulty": "difficile",
        "qcm_result": "raté",
        "weak_category": "raisonnement",
        "weak_detail": "Oubli du diagnostic différentiel",
    }


def test_focus_feedback_reaches_review_completion_without_immediate_weak_point():
    task = _task()

    async def on_done(task, card, **feedback):
        complete_review(task, **feedback)

    asyncio.run(
        submit_session_feedback(
            on_done,
            task,
            object(),
            activity_types=["qcm"],
            duration_minutes=15,
            confidence=2,
            difficulty="difficile",
            qcm_result="raté",
            weak_category="raisonnement",
            weak_detail="Confusion de prise en charge",
        )
    )

    assert _sessions("course-1")[0]["weak_detail"] == "Confusion de prise en charge"
    assert local_store.get_pending_proposals() == []
