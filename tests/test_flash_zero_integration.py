import datetime
import json

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "flash-zero.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_flash_zero_prioritizes_repeated_recent_error_items(monkeypatch):
    from backend.core.practice import flash_zero_service as module
    from backend.core.practice.flash_zero_service import FlashZeroService

    class Store:
        def get_item_pedagogical_history(self, *args, **kwargs):
            return []

        def get_error_signals(self, **kwargs):
            return [
                {"item_number": "221", "occurred_at": "2026-08-03", "category": "rang_a"},
                {"item_number": "221", "occurred_at": "2026-08-02", "category": "rang_a"},
                {"item_number": "340", "occurred_at": "2026-08-03", "category": "oubli"},
            ]

    monkeypatch.setattr(module.random, "shuffle", lambda values: None)
    quiz = FlashZeroService(store=Store()).get_morning_quiz(count=10)

    assert quiz[0].item_number == "ITEM 221"


def test_daily_flash_zero_task_is_idempotent():
    from backend.core.reviews import local_store

    today = datetime.date(2026, 8, 3)
    first = local_store.ensure_daily_flash_zero(today, timezone_name="Indian/Reunion")
    second = local_store.ensure_daily_flash_zero(today, timezone_name="Indian/Reunion")

    assert first["id"] == second["id"]
    assert first["activity_type"] == "flash_zero"
    assert local_store.get_manual_planning_entries(today, today)[0]["activity_type"] == "flash_zero"
    assert local_store.is_daily_flash_zero_complete(today, timezone_name="Indian/Reunion") is False
    local_store.complete_daily_flash_zero(today, timezone_name="Indian/Reunion")
    assert local_store.is_daily_flash_zero_complete(today, timezone_name="Indian/Reunion") is True


def test_daily_flash_zero_can_be_dismissed_without_being_completed():
    from backend.core.reviews import local_store

    today = datetime.date(2026, 8, 3)
    local_store.ensure_daily_flash_zero(today, timezone_name="Indian/Reunion")

    assert local_store.is_daily_flash_zero_dismissed(today, timezone_name="Indian/Reunion") is False
    local_store.dismiss_daily_flash_zero(today, timezone_name="Indian/Reunion")

    assert local_store.is_daily_flash_zero_dismissed(today, timezone_name="Indian/Reunion") is True
    assert local_store.is_daily_flash_zero_complete(today, timezone_name="Indian/Reunion") is False


def test_daily_routine_uses_configured_business_timezone(monkeypatch):
    from backend.features import daily_routine

    calls = []
    monkeypatch.setattr(
        daily_routine,
        "ensure_daily_flash_zero",
        lambda day, timezone_name: calls.append((day, timezone_name)) or {"id": 1},
    )
    monkeypatch.setattr(daily_routine, "business_today", lambda: datetime.date(2026, 8, 3))
    monkeypatch.setattr(
        daily_routine,
        "data_store",
        type("Store", (), {"preferences": {"timezone": "Indian/Reunion"}})(),
    )

    assert daily_routine.ensure_morning_flash_zero()["id"] == 1
    assert calls == [(datetime.date(2026, 8, 3), "Indian/Reunion")]


def test_flash_zero_ai_questions_round_trip():
    from backend.core.reviews import local_store

    local_store.save_flash_zero_ai_questions([
        {
            "item_number": "ITEM 221", "item_title": "Méningite",
            "question_text": "Q ?", "choices": ["A", "B"], "correct_idx": 0,
            "explanation": "Exp.", "is_zero_eliminatoire": True,
            "category": "Urgence vitale", "review_reason": "",
        },
    ])

    rows = local_store.get_flash_zero_ai_questions()

    assert len(rows) == 1
    assert rows[0]["item_number"] == "ITEM 221"
    assert json.loads(rows[0]["choices_json"]) == ["A", "B"]
    assert rows[0]["correct_idx"] == 0
    assert rows[0]["is_zero_eliminatoire"] == 1
    assert rows[0]["review_reason"] == ""


def test_flash_zero_ai_gen_marker_is_idempotent_per_day():
    from backend.core.reviews import local_store

    today = datetime.date(2026, 8, 3)
    assert local_store.is_daily_flash_zero_ai_gen_complete(today, timezone_name="Indian/Reunion") is False
    local_store.complete_daily_flash_zero_ai_gen(today, timezone_name="Indian/Reunion")
    assert local_store.is_daily_flash_zero_ai_gen_complete(today, timezone_name="Indian/Reunion") is True
