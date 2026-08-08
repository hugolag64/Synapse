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


def test_generate_daily_questions_returns_nothing_without_recent_signals():
    from backend.core.practice.flash_zero_service import FlashZeroService

    class Store:
        def get_error_signals(self, **kwargs):
            return []

    class FakeAI:
        def generate(self, *args, **kwargs):
            raise AssertionError("no AI call expected when there are no recent signals")

    result = FlashZeroService(store=Store(), ai_service=FakeAI()).generate_daily_questions(count=3)

    assert result == []


def test_generate_daily_questions_targets_priority_items_and_caps_at_their_count():
    from types import SimpleNamespace
    from backend.core.practice.flash_zero_service import FlashZeroService

    class Store:
        def get_error_signals(self, **kwargs):
            return [
                {"item_number": "221", "occurred_at": "2026-08-03", "category": "rang_a"},
                {"item_number": "340", "occurred_at": "2026-08-02", "category": "rang_a"},
            ]

        def save_flash_zero_ai_questions(self, questions):
            self.saved = questions

    class FakeAI:
        def generate(self, task, prompt, *, response_format="text", **kwargs):
            return SimpleNamespace(text=json.dumps({
                "item_title": "Titre", "question_text": "Q ?",
                "choices": ["A", "B", "C", "D"], "correct_idx": 1,
                "explanation": "Exp.", "is_zero_eliminatoire": True,
                "category": "Urgence vitale", "uncertain": False,
            }))

    result = FlashZeroService(store=Store(), ai_service=FakeAI()).generate_daily_questions(count=5)

    assert len(result) == 2
    assert {q["item_number"] for q in result} == {"ITEM 221", "ITEM 340"}
    assert all(q["review_reason"] == "" for q in result)


def test_generate_daily_questions_drops_malformed_responses_but_keeps_valid_ones():
    from types import SimpleNamespace
    from backend.core.practice.flash_zero_service import FlashZeroService

    class Store:
        def get_error_signals(self, **kwargs):
            return [
                {"item_number": "221", "occurred_at": "2026-08-03", "category": "rang_a"},
                {"item_number": "340", "occurred_at": "2026-08-02", "category": "rang_a"},
            ]

        def save_flash_zero_ai_questions(self, questions):
            self.saved = questions

    class FakeAI:
        def generate(self, task, prompt, *, response_format="text", **kwargs):
            if "ITEM 221" in prompt:
                return SimpleNamespace(text="pas du json")
            return SimpleNamespace(text=json.dumps({
                "item_title": "Titre", "question_text": "Q ?",
                "choices": ["A", "B", "C", "D"], "correct_idx": 0,
                "explanation": "Exp.", "is_zero_eliminatoire": True,
                "category": "Contre-indication", "uncertain": True,
            }))

    result = FlashZeroService(store=Store(), ai_service=FakeAI()).generate_daily_questions(count=5)

    assert len(result) == 1
    assert result[0]["item_number"] == "ITEM 340"
    assert result[0]["review_reason"] != ""


def test_ensure_daily_flash_zero_generation_calls_ai_at_most_once_per_day(monkeypatch):
    from backend.features import daily_routine
    import backend.core.practice.flash_zero_service as fz_module
    from backend.core.reviews import local_store

    monkeypatch.setattr(daily_routine, "business_today", lambda: datetime.date(2026, 8, 3))
    monkeypatch.setattr(
        daily_routine, "data_store",
        type("Store", (), {"preferences": {"timezone": "Indian/Reunion"}})(),
    )
    calls = []
    monkeypatch.setattr(
        fz_module.FlashZeroService,
        "generate_daily_questions",
        lambda self, **kwargs: calls.append(kwargs) or [],
    )

    daily_routine.ensure_daily_flash_zero_generation()
    daily_routine.ensure_daily_flash_zero_generation()

    assert len(calls) == 1
    assert calls[0] == {"count": 3}
    assert local_store.is_daily_flash_zero_ai_gen_complete(
        datetime.date(2026, 8, 3), timezone_name="Indian/Reunion",
    ) is True


def test_ensure_daily_flash_zero_generation_marks_done_even_on_failure(monkeypatch):
    from backend.features import daily_routine
    import backend.core.practice.flash_zero_service as fz_module
    from backend.core.reviews import local_store

    monkeypatch.setattr(daily_routine, "business_today", lambda: datetime.date(2026, 8, 4))
    monkeypatch.setattr(
        daily_routine, "data_store",
        type("Store", (), {"preferences": {"timezone": "Indian/Reunion"}})(),
    )

    def _raise(self, **kwargs):
        raise RuntimeError("panne réseau")

    monkeypatch.setattr(fz_module.FlashZeroService, "generate_daily_questions", _raise)

    daily_routine.ensure_daily_flash_zero_generation()

    assert local_store.is_daily_flash_zero_ai_gen_complete(
        datetime.date(2026, 8, 4), timezone_name="Indian/Reunion",
    ) is True
