import datetime

from backend.core.practice.flash_zero_service import FlashZeroService


def test_flash_zero_fallback_order_changes_between_days_but_is_stable_same_day():
    class Store:
        def get_item_pedagogical_history(self, *args, **kwargs):
            return []

        def get_error_signals(self, **kwargs):
            return []

        def get_flash_zero_ai_questions(self, **kwargs):
            return []

    service = FlashZeroService(store=Store())
    first = service.get_morning_quiz(count=10, quiz_date=datetime.date(2026, 8, 20))
    same_day = service.get_morning_quiz(count=10, quiz_date=datetime.date(2026, 8, 20))
    next_day = service.get_morning_quiz(count=10, quiz_date=datetime.date(2026, 8, 21))

    assert [q.id for q in first] == [q.id for q in same_day]
    assert [q.id for q in first] != [q.id for q in next_day]
    assert {q.id for q in first} == {q.id for q in next_day}
