"""Tests for the local five-question queue (no provider call)."""

from types import SimpleNamespace

import pytest

from backend.core.practice.daily_queue import (
    DAILY_QUEUE_MODEL,
    build_daily_question_queue,
    create_daily_queue_session,
)
from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store


@pytest.fixture()
def queue_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "queue.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _session(item_number: str, count: int = 2, *, model: str = "imported") -> int:
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM, total_questions=count,
        closed_questions=count, item_number=item_number,
        course_title=f"Item {item_number}",
    )
    return local_store.create_ai_practice_session(
        spec=spec,
        questions=[
            {
                "prompt": f"Question {item_number}-{index}",
                "kind": QuestionKind.CLOSED,
                "choices": ["A", "B"], "answer": "A", "explanation": "Correction",
            }
            for index in range(count)
        ],
        model=model,
    )


def test_queue_uses_existing_drafts_and_frequency_then_deficit(queue_db):
    _session("221", count=2)
    _session("222", count=2)
    local_store.replace_ednpro_item_frequencies([
        {"item_number": "221", "session_count": 5, "question_count": 2,
         "priority": "indispensable", "years": [], "source_url": "", "collected_at": "2026-08-16"},
        {"item_number": "222", "session_count": 1, "question_count": 2,
         "priority": "basique", "years": [], "source_url": "", "collected_at": "2026-08-16"},
    ])

    snapshots = {
        "221": SimpleNamespace(retention_score=90, retention_stability_days=30),
        "222": SimpleNamespace(retention_score=30, retention_stability_days=30),
    }
    queue = build_daily_question_queue(
        limit=5, retention_resolver=lambda item: snapshots[item]
    )

    assert len(queue) == 4
    assert queue[0]["item_number"] == "221"
    assert queue[0]["priority_factors"]["projected_retention_j7"] < 90
    assert queue[0]["priority_score"] > queue[-1]["priority_score"]


def test_queue_excludes_answered_questions_and_its_own_sessions(queue_db):
    session_id = _session("221", count=2)
    rows = local_store.get_ai_practice_session(session_id)
    local_store.record_ai_practice_attempt(
        session_id=session_id, question_id=rows[0]["id"], response="A",
        is_correct=True, score_percent=100, finalize_session=False,
    )
    _session("222", count=1, model=DAILY_QUEUE_MODEL)

    queue = build_daily_question_queue(limit=5, retention_resolver=lambda _: None)

    assert [row["item_number"] for row in queue] == ["221"]


def test_create_daily_queue_session_reuses_the_same_local_session(queue_db):
    _session("221", count=2)
    first = create_daily_queue_session(limit=2)
    second = create_daily_queue_session(limit=2)

    assert first is not None
    assert first == second
    summary = local_store.get_ai_practice_session_summary(first)
    assert summary["course_title"] == "Les 5 du jour"
    assert summary["total_questions"] == 2
