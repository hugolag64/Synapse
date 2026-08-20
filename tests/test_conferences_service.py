import asyncio
import datetime

import pytest

from tests.conferences_xlsx_fixtures import write_minimal_xlsx


@pytest.fixture
def isolated_local_store(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "conferences.db")
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


@pytest.fixture
def fake_calendar(monkeypatch):
    from backend.core.conferences import service

    created = []

    async def _fake_create_event(*, summary, start_time_iso, duration_minutes=60,
                                  description="", color_id=None, reminders=None, all_day=False):
        event = {"id": f"evt-{len(created) + 1}", "summary": summary, "all_day": all_day}
        created.append(event)
        return event

    monkeypatch.setattr(service.calendar_service, "create_event", _fake_create_event)
    return created


def test_import_creates_conference_and_two_calendar_events(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "4", 2: "Ma", 3: "HGE"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.imported == 1
    assert summary.needs_validation == 0
    assert len(fake_calendar) == 2
    conferences = isolated_local_store.list_conferences()
    assert conferences[0]["google_event_id"] == "evt-1"
    assert conferences[0]["uness_slot_google_event_id"] == "evt-2"


def test_import_skips_thursday_only_conferences(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "6", 2: "Je", 3: "Onco"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.imported == 0
    assert isolated_local_store.list_conferences() == []


def test_import_flags_unmatched_theme_without_calendar_sync(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "1", 2: "Ma", 3: "Toussaint"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.needs_validation == 1
    assert fake_calendar == []


def test_validate_conference_assigns_college_and_syncs_calendar(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "1", 2: "Ma", 3: "Toussaint"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)
    asyncio.run(service.import_conferences_from_xlsx(path))
    pending = isolated_local_store.list_conferences(match_status="needs_validation")[0]

    updated = asyncio.run(
        service.validate_conference(
            pending["id"], college_name="Médecine légale - Santé publique ⚖️"
        )
    )

    assert updated["match_status"] == "matched"
    assert len(fake_calendar) == 2


def test_validate_conference_skip_does_not_sync_calendar(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "1", 2: "Ma", 3: "Toussaint"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)
    asyncio.run(service.import_conferences_from_xlsx(path))
    pending = isolated_local_store.list_conferences(match_status="needs_validation")[0]

    updated = asyncio.run(service.validate_conference(pending["id"], college_name=None, skip=True))

    assert updated["match_status"] == "skipped"
    assert fake_calendar == []


def test_reimport_does_not_duplicate_calendar_events(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "4", 2: "Ma", 3: "HGE"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    asyncio.run(service.import_conferences_from_xlsx(path))
    asyncio.run(service.import_conferences_from_xlsx(path))

    assert len(fake_calendar) == 2


def test_failed_calendar_sync_does_not_crash_and_stays_retryable(tmp_path, isolated_local_store, monkeypatch):
    from backend.core.conferences import service

    async def _failing_create_event(**kwargs):
        return None  # mirrors GoogleCalendarService.create_event on HttpError

    monkeypatch.setattr(service.calendar_service, "create_event", _failing_create_event)

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "4", 2: "Ma", 3: "HGE"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.imported == 1
    row = isolated_local_store.list_conferences()[0]
    assert row["google_event_id"] is None
    assert row["uness_slot_google_event_id"] is None
