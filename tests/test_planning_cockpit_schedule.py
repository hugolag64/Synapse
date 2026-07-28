import datetime
from types import SimpleNamespace

from backend.core.planning.cockpit_schedule import tasks_for_day


def _task(due_date, days_overdue=0):
    return SimpleNamespace(due_date=due_date, days_overdue=days_overdue)


def test_past_day_does_not_render_tasks_again_as_historical_due_items():
    today = datetime.date(2026, 7, 28)
    overdue = _task(today - datetime.timedelta(days=1), days_overdue=1)

    urgent, due = tasks_for_day([overdue], today - datetime.timedelta(days=1), today)

    assert urgent == []
    assert due == []


def test_today_keeps_overdue_tasks_in_the_current_day():
    today = datetime.date(2026, 7, 28)
    overdue = _task(today - datetime.timedelta(days=1), days_overdue=1)

    urgent, due = tasks_for_day([overdue], today, today)

    assert urgent == [overdue]
    assert due == []


def test_future_day_keeps_only_tasks_due_that_day():
    today = datetime.date(2026, 7, 28)
    future = today + datetime.timedelta(days=2)
    task = _task(future)

    urgent, due = tasks_for_day([task], future, today)

    assert urgent == []
    assert due == [task]
