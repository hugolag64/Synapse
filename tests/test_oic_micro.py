"""Tests de la micro-question Rang A, une session = un OIC mesuré."""

import json

import pytest

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.practice.models import PracticeKind
from backend.core.practice.oic_micro import (
    create_rang_a_micro_session,
    get_next_rang_a_oic,
)
from backend.core.practice.mastery import record_ai_practice_mastery
from backend.core.practice.service import PracticeService
from backend.core.reviews import local_store


@pytest.fixture()
def micro_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "oic_micro.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _seed_oics():
    local_store.upsert_lisa_oic(
        "course-1",
        [
            {"oic_code": "OIC-1-A1", "intitule": "A1", "rang": "A", "ordre": 1},
            {"oic_code": "OIC-1-A2", "intitule": "A2", "rang": "A", "ordre": 2},
            {"oic_code": "OIC-1-A3", "intitule": "A3", "rang": "A", "ordre": 3},
            {"oic_code": "OIC-1-B1", "intitule": "B1", "rang": "B", "ordre": 4},
        ],
    )


def test_next_micro_target_prioritizes_unattempted_rang_a_oic(micro_db):
    _seed_oics()
    first = local_store.get_lisa_oic("course-1")[0]
    local_store.save_oic_attempt(first["id"], 20, "[]")

    target = get_next_rang_a_oic(("course-1",))

    assert target is not None
    assert target["oic_code"] == "OIC-1-A2"
    assert target["rang"] == "A"
    assert target["attempt_count"] == 0


def test_micro_session_targets_one_oic_with_one_question(micro_db):
    _seed_oics()
    calls = []

    class StubAI:
        def generate(self, task, prompt, **kwargs):
            calls.append((task, prompt, kwargs))
            return AIResponse(
                text=json.dumps({
                    "questions": [{
                        "kind": "closed",
                        "prompt": "Question A2",
                        "choices": ["A", "B"],
                        "answer": "A",
                        "explanation": "Justification",
                    }]
                }),
                model=AIModel.FLASH_LITE,
            )

    session_id = create_rang_a_micro_session(
        course_id="course-1",
        course_title="Item test",
        item_number="1",
        practice_service=PracticeService(ai_service=StubAI()),
    )

    session = local_store.get_ai_practice_session_summary(session_id)
    assert session["practice_kind"] == PracticeKind.OIC.value
    assert session["objective_code"] == "OIC-1-A1"
    assert session["total_questions"] == 1
    assert session["open_questions"] == 0
    assert session["closed_questions"] == 1
    assert len(local_store.get_ai_practice_session(session_id)) == 1
    assert "OIC-1-A1" in calls[0][1]


def test_three_completed_micro_sessions_make_rang_a_conclusive(micro_db):
    _seed_oics()

    class StubAI:
        def generate(self, task, prompt, **kwargs):
            return AIResponse(
                text=json.dumps({
                    "questions": [{
                        "kind": "closed",
                        "prompt": "Question ciblée",
                        "choices": ["A", "B"],
                        "answer": "A",
                        "explanation": "Justification",
                    }]
                }),
                model=AIModel.FLASH_LITE,
            )

    service = PracticeService(ai_service=StubAI())
    objectives = []
    for _ in range(3):
        session_id = create_rang_a_micro_session(
            course_id="course-1",
            course_title="Item test",
            item_number="1",
            practice_service=service,
        )
        session = local_store.get_ai_practice_session_summary(session_id)
        objectives.append(session["objective_code"])
        question = local_store.get_ai_practice_session(session_id)[0]
        local_store.record_ai_practice_attempt(
            session_id=session_id,
            question_id=question["id"],
            response="A",
            is_correct=True,
            score_percent=100,
        )
        assert record_ai_practice_mastery(session_id) is not None

    from backend.core.knowledge.service import oic_coverage

    coverage = oic_coverage("course-1")
    assert objectives == ["OIC-1-A1", "OIC-1-A2", "OIC-1-A3"]
    assert coverage["rang_a_attempted"] == 3
    assert coverage["rang_a_conclusive"] is True
