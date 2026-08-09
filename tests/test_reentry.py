from datetime import date
from types import SimpleNamespace

from backend.core.reviews.reentry import (
    DEFAULT_STUDY_RESUME_DATE,
    filter_active_review_tasks,
    filter_post_resume_signals,
    get_study_resume_date,
)


def test_resume_date_uses_safe_default_and_valid_preference():
    assert DEFAULT_STUDY_RESUME_DATE == date(2026, 8, 20)
    assert get_study_resume_date({}) == date(2026, 8, 20)
    assert get_study_resume_date({"study_resume_date": "2026-09-01"}) == date(2026, 9, 1)


def test_invalid_resume_date_falls_back_to_default():
    assert get_study_resume_date({"study_resume_date": "not-a-date"}) == date(2026, 8, 20)


def test_active_task_filter_keeps_resume_date_and_later():
    tasks = [
        SimpleNamespace(due_date=date(2026, 8, 19)),
        SimpleNamespace(due_date=date(2026, 8, 20)),
        SimpleNamespace(due_date=date(2026, 8, 21)),
    ]

    assert filter_active_review_tasks(tasks) == tasks[1:]


def test_signal_filter_does_not_mutate_input():
    signals = [
        {"item_number": "1", "occurred_at": "2026-08-19"},
        {"item_number": "2", "occurred_at": "2026-08-20"},
    ]

    result = filter_post_resume_signals(signals)

    assert result == [signals[1]]
    assert signals[0]["occurred_at"] == "2026-08-19"
