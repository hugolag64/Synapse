"""Contrats C4 : banque versionnée, erreurs IA et répétition espacée."""

import datetime
import json
from pathlib import Path

import pytest

from backend.core.practice.flash_zero_service import FlashZeroService
from backend.core.practice.models import PracticeKind, PracticeSessionSpec, QuestionKind
from backend.core.reviews import local_store


BANK_PATH = Path("data/flash_zero_bank.json")


@pytest.fixture()
def flash_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "flash-zero.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_flash_zero_bank_is_external_and_versioned():
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    source = Path("backend/core/practice/flash_zero_service.py").read_text(encoding="utf-8")

    assert len(bank) == 10
    assert all(str(row.get("source") or "").strip() for row in bank)
    assert all(str(row.get("revised_at") or "").strip() for row in bank)
    assert "canonical_flash_bank: list[FlashZeroQuestion]" not in source


def test_flash_zero_uses_ai_practice_errors_when_error_signals_are_empty():
    class Store:
        def get_item_pedagogical_history(self, *args, **kwargs):
            return []

        def get_error_signals(self, **kwargs):
            return []

        def get_ai_practice_error_signals(self, **kwargs):
            return [
                {"item_number": "340", "occurred_at": "2026-08-21"},
                {"item_number": "340", "occurred_at": "2026-08-20"},
            ]

        def get_flash_zero_ai_questions(self, **kwargs):
            return []

        def get_flash_zero_attempts(self, **kwargs):
            return []

    quiz = FlashZeroService(store=Store()).get_morning_quiz(
        count=1, quiz_date=datetime.date(2026, 8, 21)
    )

    assert quiz[0].item_number == "ITEM 340"


def test_flash_zero_does_not_repeat_a_recently_correct_question_if_another_is_available():
    class Store:
        def get_item_pedagogical_history(self, *args, **kwargs):
            return []

        def get_error_signals(self, **kwargs):
            return []

        def get_ai_practice_error_signals(self, **kwargs):
            return [{"item_number": "999", "occurred_at": "2026-08-21"}]

        def get_flash_zero_ai_questions(self, **kwargs):
            return [{
                "id": 1, "item_number": "ITEM 999", "item_title": "Titre IA",
                "question_text": "Q IA ?", "choices_json": json.dumps(["A", "B"]),
                "correct_idx": 0, "explanation": "Exp.", "is_zero_eliminatoire": 1,
                "category": "Contre-indication", "review_reason": "",
            }]

        def get_flash_zero_attempts(self, **kwargs):
            return [{
                "question_id": "fz-001", "is_correct": 1,
                "answered_at": "2026-08-20T08:00:00",
            }]

    quiz = FlashZeroService(store=Store()).get_morning_quiz(
        count=1, quiz_date=datetime.date(2026, 8, 21)
    )

    assert quiz[0].id == "fz-ai-1"


def test_flash_zero_attempts_are_persisted_and_ai_errors_are_queryable(flash_db):
    local_store.record_flash_zero_attempt(
        question_id="fz-001", item_number="ITEM 340", source="canonical", is_correct=False
    )
    attempts = local_store.get_flash_zero_attempts()

    assert attempts[0]["question_id"] == "fz-001"
    assert attempts[0]["is_correct"] == 0

    session_id = local_store.create_ai_practice_session(
        spec=PracticeSessionSpec(
            practice_kind=PracticeKind.QCM,
            total_questions=1,
            open_questions=0,
            closed_questions=1,
            item_number="340",
            course_title="Item 340",
        ),
        questions=[{
            "prompt": "Question",
            "kind": QuestionKind.CLOSED,
            "choices": ["A", "B"],
            "answer": "A",
            "explanation": "Explication",
        }],
        model="test",
    )
    question = local_store.get_ai_practice_session(session_id)[0]
    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question["id"],
        response="B",
        is_correct=False,
        score_percent=0,
    )

    signals = local_store.get_ai_practice_error_signals(days=30)
    assert signals and signals[0]["item_number"] == "340"
