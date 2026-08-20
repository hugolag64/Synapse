import datetime

import pytest


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


def test_upsert_conference_creates_then_reports_unchanged(isolated_local_store):
    store = isolated_local_store
    outcome, row = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    assert outcome == "created"
    assert row["match_status"] == "matched"

    outcome2, row2 = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    assert outcome2 == "unchanged"
    assert row2["id"] == row["id"]


def test_upsert_conference_preserves_validated_college_when_theme_unchanged(isolated_local_store):
    store = isolated_local_store
    _, row = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="needs_validation",
        college_name=None, source_file="cal.xlsx",
    )
    store.set_conference_match(
        row["id"], match_status="matched", college_name="Hépato-Gastro-entérologie 🧻"
    )

    outcome, row2 = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="needs_validation",
        college_name=None, source_file="cal-v2.xlsx",
    )
    assert outcome == "unchanged"
    assert row2["match_status"] == "matched"
    assert row2["college_id"] == "Hépato-Gastro-entérologie 🧻"


def test_upsert_conference_resets_validation_when_theme_changes(isolated_local_store):
    store = isolated_local_store
    store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )

    outcome, row2 = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="Cardio", match_status="needs_validation",
        college_name=None, source_file="cal-v2.xlsx",
    )
    assert outcome == "updated"
    assert row2["theme_raw"] == "Cardio"
    assert row2["match_status"] == "needs_validation"
    assert row2["college_id"] is None


def test_set_conference_google_event_ids_updates_only_given_fields(isolated_local_store):
    store = isolated_local_store
    _, row = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    updated = store.set_conference_google_event_ids(row["id"], google_event_id="evt-1")
    assert updated["google_event_id"] == "evt-1"
    assert updated["uness_slot_google_event_id"] is None

    updated2 = store.set_conference_google_event_ids(row["id"], uness_slot_google_event_id="evt-2")
    assert updated2["google_event_id"] == "evt-1"
    assert updated2["uness_slot_google_event_id"] == "evt-2"


def test_list_conferences_filters_by_match_status(isolated_local_store):
    store = isolated_local_store
    store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    store.upsert_conference(
        date=datetime.date(2026, 9, 8), theme_raw="Toussaint", match_status="needs_validation",
        college_name=None, source_file="cal.xlsx",
    )
    pending = store.list_conferences(match_status="needs_validation")
    assert [row["theme_raw"] for row in pending] == ["Toussaint"]


def test_upsert_conference_rejects_invalid_match_status(isolated_local_store):
    store = isolated_local_store
    with pytest.raises(ValueError):
        store.upsert_conference(
            date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="bogus",
            college_name=None, source_file="cal.xlsx",
        )


def test_list_uness_annales_by_date_matches_calendar_day(isolated_local_store):
    store = isolated_local_store
    annale_id = store.create_uness_annale(
        source_url="https://uness.example/dossier-1",
        collected_at="2026-09-01T18:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier HGE", type_annale="DP",
    )

    same_day = store.list_uness_annales_by_date("2026-09-01")
    other_day = store.list_uness_annales_by_date("2026-09-02")

    assert [row["id"] for row in same_day] == [annale_id]
    assert other_day == []


def test_list_uness_annales_by_date_orders_by_collection_time(isolated_local_store):
    store = isolated_local_store
    later_id = store.create_uness_annale(
        source_url="https://uness.example/dossier-later",
        collected_at="2026-09-01T20:00:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier tardif", type_annale="DP",
    )
    earlier_id = store.create_uness_annale(
        source_url="https://uness.example/dossier-earlier",
        collected_at="2026-09-01T17:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="Cardio", titre="Dossier tôt", type_annale="DP",
    )

    rows = store.list_uness_annales_by_date("2026-09-01")

    assert [row["id"] for row in rows] == [earlier_id, later_id]


def test_set_conference_uness_session_writes_the_link(isolated_local_store):
    store = isolated_local_store
    _, conf = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    annale_id = store.create_uness_annale(
        source_url="https://uness.example/dossier-1",
        collected_at="2026-09-01T18:45:00+00:00",
        faculte="Fac", niveau="DFASM1", annee=2026,
        matiere="HGE", titre="Dossier HGE", type_annale="DP",
    )

    updated = store.set_conference_uness_session(conf["id"], annale_id)

    assert updated["uness_session_id"] == annale_id
    reloaded = store.get_conference(conf["id"])
    assert reloaded["uness_session_id"] == annale_id


def test_set_conference_uness_session_raises_on_unknown_conference(isolated_local_store):
    store = isolated_local_store
    with pytest.raises(ValueError):
        store.set_conference_uness_session(9999, 1)
