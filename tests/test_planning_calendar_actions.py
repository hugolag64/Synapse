import asyncio
import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.config.settings as app_settings
from backend.core.google.calendar_service import GoogleCalendarAuthError, GoogleCalendarService
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


def test_google_calendar_uses_configured_secrets_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_SECRETS_DIR", str(tmp_path))

    service = GoogleCalendarService()

    assert Path(service.credentials_path) == tmp_path / "credentials.json"
    assert Path(service.token_path) == tmp_path / "token.json"


def test_google_calendar_surfaces_authentication_failure(monkeypatch):
    service = GoogleCalendarService()

    def fail_authentication():
        raise RuntimeError("OAuth indisponible")

    monkeypatch.setattr(service, "authenticate", fail_authentication)

    with pytest.raises(GoogleCalendarAuthError, match="OAuth indisponible"):
        asyncio.run(service.get_events_for_day(datetime.date(2026, 7, 28)))


def test_google_calendar_create_event_surfaces_authentication_failure(monkeypatch):
    service = GoogleCalendarService()

    def fail_authentication():
        raise RuntimeError("OAuth indisponible")

    monkeypatch.setattr(service, "authenticate", fail_authentication)

    with pytest.raises(GoogleCalendarAuthError, match="OAuth indisponible"):
        asyncio.run(service.create_event("Révision", "2026-08-07T09:00:00"))


class _FakeEventsMultiCalendar:
    def __init__(self, items_by_cal: dict):
        self.items_by_cal = items_by_cal
        self.calls: list[str] = []
        self._current = None

    def list(self, **kwargs):
        self._current = kwargs["calendarId"]
        self.calls.append(self._current)
        return self

    def execute(self):
        return {"items": self.items_by_cal.get(self._current, [])}


class _FakeServiceMultiCalendar:
    def __init__(self, events_api):
        self.events_api = events_api

    def events(self):
        return self.events_api


def _event(summary: str) -> dict:
    return {
        "summary": summary,
        "start": {"dateTime": "2026-08-10T09:00:00+02:00"},
        "end": {"dateTime": "2026-08-10T10:00:00+02:00"},
    }


@patch("backend.state.store.data_store")
def test_get_events_for_day_queries_preference_calendar_ids(mock_data_store):
    mock_data_store.preferences = {
        "planning_calendar_sources": [{"id": "fac@x.com", "label": "Fac"}]
    }
    events_api = _FakeEventsMultiCalendar({"fac@x.com": [_event("Sémio")], "primary": []})
    service = GoogleCalendarService()
    service.service = _FakeServiceMultiCalendar(events_api)

    events = asyncio.run(service.get_events_for_day(datetime.date(2026, 8, 10)))

    assert "fac@x.com" in events_api.calls
    assert events[0]["_synapse_source_label"] == "Fac"


@patch("backend.state.store.data_store")
def test_get_events_for_day_deduplicates_id_present_in_env_and_preferences(mock_data_store, monkeypatch):
    mock_data_store.preferences = {
        "planning_calendar_sources": [{"id": "fac@x.com", "label": "Fac"}]
    }
    monkeypatch.setattr(app_settings.settings, "google_calendar_ids", "fac@x.com")
    events_api = _FakeEventsMultiCalendar({"fac@x.com": [], "primary": []})
    service = GoogleCalendarService()
    service.service = _FakeServiceMultiCalendar(events_api)

    asyncio.run(service.get_events_for_day(datetime.date(2026, 8, 10)))

    assert events_api.calls.count("fac@x.com") == 1
    monkeypatch.setattr(app_settings.settings, "google_calendar_ids", "")


@patch("backend.state.store.data_store")
def test_get_events_for_day_leaves_unlabeled_events_with_empty_source_label(mock_data_store):
    mock_data_store.preferences = {}
    events_api = _FakeEventsMultiCalendar({"primary": [_event("Perso")]})
    service = GoogleCalendarService()
    service.service = _FakeServiceMultiCalendar(events_api)

    events = asyncio.run(service.get_events_for_day(datetime.date(2026, 8, 10)))

    assert events[0]["_synapse_source_label"] == ""
