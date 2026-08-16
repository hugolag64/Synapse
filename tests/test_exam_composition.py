import pytest

from backend.core.practice.models import PracticeKind, PracticeSessionSpec


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "exam-composition.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _spec(total_questions: int) -> PracticeSessionSpec:
    return PracticeSessionSpec(
        practice_kind=PracticeKind.DP,
        total_questions=total_questions,
        open_questions=0,
        closed_questions=total_questions,
        course_id="exam-blanc",
        course_title="Concours blanc",
        item_number="",
    )


def _question(label: str) -> dict:
    return {
        "prompt": f"Question {label}",
        "choices": ["A", "B"],
        "answer": '["A"]',
        "explanation": "Correction officielle.",
        "kind": "closed",
        "item_numbers": ("230",),
        "import_metadata": {"uness": {"provenance": {"source": "UNESS"}}},
    }


def test_exam_session_persists_mode_duration_and_composition(isolated_db):
    session_id = isolated_db.create_ai_practice_session(
        spec=_spec(2),
        questions=[_question("q1"), _question("q2")],
        model="exam-composer-v1",
        exam_mode=True,
        exam_format="series",
        exam_seed="seed-1",
        duration_seconds=5400,
    )
    rows = isolated_db.get_ai_practice_session(session_id)
    question_ids = [int(row["id"]) for row in rows]
    isolated_db.save_exam_composition(
        session_id,
        format="series",
        seed="seed-1",
        duration_seconds=5400,
        question_ids=question_ids,
    )

    session = isolated_db.get_ai_practice_session_summary(session_id)
    composition = isolated_db.get_exam_composition(session_id)
    assert session["exam_mode"] == 1
    assert session["duration_seconds"] == 5400
    assert composition["seed"] == "seed-1"
    assert composition["question_ids"] == question_ids


def test_exam_session_rejects_out_of_order_attempts(isolated_db):
    session_id = isolated_db.create_ai_practice_session(
        spec=_spec(2),
        questions=[_question("q1"), _question("q2")],
        model="exam-composer-v1",
        exam_mode=True,
        exam_format="series",
        exam_seed="seed-1",
        duration_seconds=5400,
    )
    question_ids = [int(row["id"]) for row in isolated_db.get_ai_practice_session(session_id)]

    with pytest.raises(ValueError, match="ordre"):
        isolated_db.record_ai_practice_attempt(
            session_id=session_id,
            question_id=question_ids[1],
            response='["A"]',
            score_percent=0,
            is_correct=False,
        )

    isolated_db.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_ids[0],
        response='["A"]',
        score_percent=100,
        is_correct=True,
    )

    isolated_db.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_ids[1],
        response="",
        score_percent=0,
        is_correct=False,
        score_mode="timed_out",
    )
