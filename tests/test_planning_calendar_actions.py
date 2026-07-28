import datetime

import pytest

from backend.core.planning.calendar_actions import event_duration_minutes


def test_event_duration_minutes_returns_positive_duration():
    start = datetime.datetime(2026, 7, 28, 9, 0)
    end = datetime.datetime(2026, 7, 28, 10, 30)

    assert event_duration_minutes(start, end) == 90


@pytest.mark.parametrize("end_offset", [datetime.timedelta(0), datetime.timedelta(minutes=-5)])
def test_event_duration_minutes_rejects_non_positive_ranges(end_offset):
    start = datetime.datetime(2026, 7, 28, 9, 0)

    with pytest.raises(ValueError):
        event_duration_minutes(start, start + end_offset)
