import datetime

from backend.core.reviews.anchors import (
    anchor_priority,
    anchor_status,
    anchor_interval_days,
    is_anchor_due,
)


def test_recurrent_or_severe_weak_point_becomes_anchor():
    row = {"status": "récurrente", "severity": 3, "recurrence_count": 2}
    assert anchor_status(row) == "actif"


def test_simple_active_weak_point_is_not_an_anchor():
    row = {"status": "active", "severity": 2, "recurrence_count": 0}
    assert anchor_status(row) == "inactif"


def test_repeated_anchor_gets_shorter_interval_after_failure():
    assert anchor_interval_days({"recurrence_count": 1}) == 3
    assert anchor_interval_days({"recurrence_count": 3}) == 7
    assert anchor_interval_days({"recurrence_count": 6}) == 14


def test_priority_combines_severity_and_recurrence():
    low = {"status": "récurrente", "severity": 2, "recurrence_count": 2}
    high = {"status": "récurrente", "severity": 5, "recurrence_count": 4}
    assert anchor_priority(high) > anchor_priority(low)


def test_anchor_is_due_after_its_interval():
    today = datetime.date(2026, 7, 28)
    row = {
        "status": "récurrente",
        "severity": 3,
        "recurrence_count": 2,
        "last_reviewed_at": "2026-07-21T08:00:00",
    }
    assert is_anchor_due(row, today) is True
