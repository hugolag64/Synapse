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


def test_list_pending_uness_links_returns_matched_conferences_with_candidates(isolated_local_store):
    from backend.core.conferences import service

    _, conf = isolated_local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    annale_id = isolated_local_store.create_uness_annale(
        source_url="https://uness.example/dossier-1",
        collected_at="2026-09-01T18:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier HGE", type_annale="DP",
    )

    pending = service.list_pending_uness_links()

    assert len(pending) == 1
    assert pending[0]["conference"]["id"] == conf["id"]
    assert [c["id"] for c in pending[0]["candidates"]] == [annale_id]


def test_list_pending_uness_links_excludes_conferences_without_candidates(isolated_local_store):
    from backend.core.conferences import service

    isolated_local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )

    assert service.list_pending_uness_links() == []


def test_list_pending_uness_links_excludes_conferences_needing_validation(isolated_local_store):
    from backend.core.conferences import service

    isolated_local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="needs_validation",
        college_name=None, source_file="cal.xlsx",
    )
    isolated_local_store.create_uness_annale(
        source_url="https://uness.example/dossier-1",
        collected_at="2026-09-01T18:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier HGE", type_annale="DP",
    )

    assert service.list_pending_uness_links() == []


def test_list_pending_uness_links_excludes_already_linked_conferences(isolated_local_store):
    from backend.core.conferences import service

    _, conf = isolated_local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    annale_id = isolated_local_store.create_uness_annale(
        source_url="https://uness.example/dossier-1",
        collected_at="2026-09-01T18:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier HGE", type_annale="DP",
    )
    isolated_local_store.set_conference_uness_session(conf["id"], annale_id)

    assert service.list_pending_uness_links() == []


def test_list_pending_uness_links_gives_several_candidates_for_the_same_day(isolated_local_store):
    from backend.core.conferences import service

    isolated_local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    first_id = isolated_local_store.create_uness_annale(
        source_url="https://uness.example/dossier-1",
        collected_at="2026-09-01T17:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier A", type_annale="DP",
    )
    second_id = isolated_local_store.create_uness_annale(
        source_url="https://uness.example/dossier-2",
        collected_at="2026-09-01T19:00:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier B", type_annale="DP",
    )

    pending = service.list_pending_uness_links()

    assert len(pending) == 1
    assert [c["id"] for c in pending[0]["candidates"]] == [first_id, second_id]


def test_link_conference_to_uness_session_writes_link_and_clears_pending_list(isolated_local_store):
    from backend.core.conferences import service

    _, conf = isolated_local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    annale_id = isolated_local_store.create_uness_annale(
        source_url="https://uness.example/dossier-1",
        collected_at="2026-09-01T18:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier HGE", type_annale="DP",
    )

    updated = service.link_conference_to_uness_session(conf["id"], annale_id)

    assert updated["uness_session_id"] == annale_id
    assert service.list_pending_uness_links() == []


def test_link_conference_to_uness_session_raises_on_unknown_dossier(isolated_local_store):
    from backend.core.conferences import service

    _, conf = isolated_local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )

    with pytest.raises(ValueError):
        service.link_conference_to_uness_session(conf["id"], 9999)

    reloaded = isolated_local_store.get_conference(conf["id"])
    assert reloaded["uness_session_id"] is None
