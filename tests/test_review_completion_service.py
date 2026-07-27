import datetime

import pytest

from backend.core.reviews import local_store
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.validation import complete_review


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "reviews.db"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _task(review_type="J7", task_id="task-1"):
    due = datetime.date(2026, 7, 27)
    return ReviewTask(
        id=task_id,
        course_id="course-1",
        course_title="Cardiologie",
        item_number="75",
        context="college",
        theoretical_due_date=due,
        due_date=due,
        review_type=review_type,
    )


def _sessions(course_id):
    with local_store._conn() as con:
        return con.execute(
            "SELECT * FROM study_sessions WHERE course_id = ?", (course_id,)
        ).fetchall()


def test_complete_review_records_history_and_session_with_feedback():
    result = complete_review(
        _task(),
        activity_types=["révision", "qcm"],
        duration_minutes=25,
        confidence=4,
        difficulty="moyen",
        qcm_result="réussi",
        weak_category="aucune",
    )

    history = local_store.get_history("task-1")
    sessions = _sessions("course-1")

    assert result.review_type == "J7"
    assert history["status"] == "done"
    assert history["confidence"] == 4
    assert len(sessions) == 1
    assert sessions[0]["qcm_result"] == "réussi"


def test_complete_review_records_feedback_without_creating_immediate_weak_point():
    complete_review(
        _task(),
        qcm_result="raté",
        weak_category="raisonnement",
        weak_detail="Oubli du diagnostic différentiel",
    )

    with local_store._conn() as con:
        weak_points = con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]
    session = _sessions("course-1")[0]

    assert session["qcm_result"] == "raté"
    assert session["weak_category"] == "raisonnement"
    assert session["weak_detail"] == "Oubli du diagnostic différentiel"
    assert weak_points == 0


def test_complete_consolidation_uses_consolidation_state_and_session():
    result = complete_review(
        _task("consolidation", "course-1_college_consolidation_2026-07-27"),
        confidence=3,
        activity_types=["révision"],
    )

    history = local_store.get_history(result.id)
    assert history["status"] == "done"
    assert history["review_type"] == "consolidation"
    assert len(_sessions("course-1")) == 1


def test_complete_lacune_resolves_point_and_records_session():
    weak_id = local_store.add_weak_point("course-1", "Revoir le traitement", item_number="75")
    task = _task("lacune", f"lacune_{weak_id}")

    complete_review(task, weak_detail="Revoir le traitement", confidence=2)

    with local_store._conn() as con:
        status = con.execute("SELECT status FROM weak_points WHERE id = ?", (weak_id,)).fetchone()[0]
    assert status == "résolue"
    sessions = _sessions("course-1")
    assert len(sessions) == 1
    assert sessions[0]["confidence"] == 2
