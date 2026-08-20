import asyncio

import pytest


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
