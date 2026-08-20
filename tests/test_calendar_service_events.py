import asyncio
import datetime

import pytest

from tests.test_planning_calendar_actions import _FakeEventsMultiCalendar, _FakeServiceMultiCalendar


class _FakeEvents:
    def __init__(self):
        self.inserted_bodies = []

    def insert(self, calendarId, body):
        self.inserted_bodies.append(body)
        return self

    def execute(self):
        return {"id": "evt-1"}


class _FakeGoogleService:
    def __init__(self):
        self._events = _FakeEvents()

    def events(self):
        return self._events


@pytest.fixture
def fake_calendar_service():
    from backend.core.google.calendar_service import GoogleCalendarService

    service = GoogleCalendarService()
    service.service = _FakeGoogleService()
    return service


def test_create_event_all_day_uses_date_not_datetime(fake_calendar_service):
    result = asyncio.run(
        fake_calendar_service.create_event(
            summary="Conférence — HGE",
            start_time_iso="2026-09-01T00:00:00",
            all_day=True,
        )
    )
    body = fake_calendar_service.service._events.inserted_bodies[0]
    assert body["start"] == {"date": "2026-09-01"}
    assert body["end"] == {"date": "2026-09-02"}
    assert "dateTime" not in body["start"]
    assert result == {"id": "evt-1"}


def test_create_event_timed_slot_still_uses_datetime(fake_calendar_service):
    asyncio.run(
        fake_calendar_service.create_event(
            summary="Dossier UNESS — HGE",
            start_time_iso="2026-09-01T17:30:00",
            duration_minutes=90,
        )
    )
    body = fake_calendar_service.service._events.inserted_bodies[0]
    assert body["start"]["dateTime"].startswith("2026-09-01T17:30:00")
    assert body["end"]["dateTime"].startswith("2026-09-01T19:00:00")


def test_get_events_for_range_buckets_events_by_day(fake_calendar_service, monkeypatch):
    import backend.core.google.calendar_service as calendar_module

    events_by_cal = {
        "primary": [
            {"summary": "Lundi", "start": {"dateTime": "2026-08-24T09:00:00+02:00"},
             "end": {"dateTime": "2026-08-24T10:00:00+02:00"}},
            {"summary": "Mercredi", "start": {"dateTime": "2026-08-26T14:00:00+02:00"},
             "end": {"dateTime": "2026-08-26T15:00:00+02:00"}},
        ],
    }
    events_api = _FakeEventsMultiCalendar(events_by_cal)
    fake_calendar_service.service = _FakeServiceMultiCalendar(events_api)
    monkeypatch.setattr(
        calendar_module, "_list_calendar_sources", lambda prefs: [], raising=False,
    )

    result = asyncio.run(
        fake_calendar_service.get_events_for_range(
            datetime.date(2026, 8, 24), datetime.date(2026, 8, 30),
        )
    )

    assert [e["summary"] for e in result[datetime.date(2026, 8, 24)]] == ["Lundi"]
    assert [e["summary"] for e in result[datetime.date(2026, 8, 26)]] == ["Mercredi"]
    assert result[datetime.date(2026, 8, 25)] == []
    assert set(result.keys()) == {datetime.date(2026, 8, 24) + datetime.timedelta(days=i) for i in range(7)}
