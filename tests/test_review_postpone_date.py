"""Report d'une révision : la nouvelle date part toujours d'aujourd'hui
quand la tâche est déjà en retard."""
import datetime

from backend.core.reviews.service import next_postpone_date


TODAY = datetime.date(2026, 8, 7)


def test_overdue_task_is_postponed_relative_to_today():
    five_days_late = TODAY - datetime.timedelta(days=5)

    assert next_postpone_date(five_days_late, TODAY) == TODAY + datetime.timedelta(days=1)


def test_task_due_today_is_postponed_to_tomorrow():
    assert next_postpone_date(TODAY, TODAY) == TODAY + datetime.timedelta(days=1)


def test_future_task_is_postponed_relative_to_its_own_due_date():
    in_three_days = TODAY + datetime.timedelta(days=3)

    assert next_postpone_date(in_three_days, TODAY) == in_three_days + datetime.timedelta(days=1)


def test_multi_day_postpone_is_honoured():
    two_days_late = TODAY - datetime.timedelta(days=2)

    assert next_postpone_date(two_days_late, TODAY, days=7) == TODAY + datetime.timedelta(days=7)
