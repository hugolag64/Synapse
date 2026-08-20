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
