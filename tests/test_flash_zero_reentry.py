import json
from types import SimpleNamespace

from backend.core.practice.flash_zero_service import FlashZeroService


def test_flash_zero_priority_ignores_signals_before_resume(monkeypatch):
    prompts = []

    class FakeAI:
        def generate(self, _task, prompt, response_format="json"):
            assert response_format == "json"
            prompts.append(prompt)
            return SimpleNamespace(text=json.dumps({
                "item_title": "Item test",
                "question_text": "Question test",
                "choices": ["A", "B"],
                "correct_idx": 0,
                "explanation": "Règle test",
                "is_zero_eliminatoire": True,
                "category": "Rang A",
            }))

    monkeypatch.setattr(
        "backend.core.practice.flash_zero_service.signals_since",
        lambda **_kwargs: [
            {"item_number": "1", "occurred_at": "2026-08-18"},
            {"item_number": "1", "occurred_at": "2026-08-19"},
            {"item_number": "2", "occurred_at": "2026-08-20"},
        ],
    )
    store = SimpleNamespace(save_flash_zero_ai_questions=lambda _rows: None)

    FlashZeroService(store=store, ai_service=FakeAI()).generate_daily_questions(count=1)

    assert prompts and "ITEM 2" in prompts[0]
