import asyncio
import datetime

import pytest

import backend.config.settings as app_settings
from backend.core.google.calendar_service import GoogleCalendarService
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


def test_google_calendar_uses_selected_app_timezone():
    class FakeEvents:
        def __init__(self):
            self.list_kwargs = None

        def list(self, **kwargs):
            self.list_kwargs = kwargs
            return self

        def execute(self):
            return {"items": []}

    class FakeService:
        def __init__(self):
            self.events_api = FakeEvents()

        def events(self):
            return self.events_api

    service = GoogleCalendarService()
    fake = FakeService()
    service.service = fake
    try:
        app_settings.set_app_timezone("Europe/Paris")
        asyncio.run(service.get_events_for_day(datetime.date(2026, 7, 28)))
        assert fake.events_api.list_kwargs["timeMin"].endswith("+02:00")
    finally:
        app_settings.set_app_timezone("Europe/Paris")
