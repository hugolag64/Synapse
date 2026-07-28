import datetime

import pytest


@pytest.fixture
def isolated_local_store(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "planning.db")
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


def test_manual_planning_entry_round_trip_and_delete(isolated_local_store):
    store = isolated_local_store
    created = store.create_manual_planning_entry(
        datetime.date(2026, 7, 28), "course-1", "Syphilis", "162", "qcm", 30
    )
    rows = store.get_manual_planning_entries(
        datetime.date(2026, 7, 28), datetime.date(2026, 7, 28)
    )
    assert rows[0]["id"] == created["id"]
    assert rows[0]["activity_type"] == "qcm"
    assert rows[0]["duration_minutes"] == 30
    assert store.delete_manual_planning_entry(created["id"])
    assert store.get_manual_planning_entries(
        datetime.date(2026, 7, 28), datetime.date(2026, 7, 28)
    ) == []


def test_manual_planning_range_includes_both_endpoints(isolated_local_store):
    store = isolated_local_store
    for day in (datetime.date(2026, 7, 28), datetime.date(2026, 7, 30)):
        store.create_manual_planning_entry(day, "course-1", "Cours", "1", "revision", 20)
    rows = store.get_manual_planning_entries(
        datetime.date(2026, 7, 28), datetime.date(2026, 7, 30)
    )
    assert [row["entry_date"] for row in rows] == ["2026-07-28", "2026-07-30"]


def test_manual_planning_rejects_invalid_activity_or_duration(isolated_local_store):
    store = isolated_local_store
    with pytest.raises(ValueError):
        store.create_manual_planning_entry(
            datetime.date(2026, 7, 28), "course-1", "Cours", "1", "unknown", 20
        )
    with pytest.raises(ValueError):
        store.create_manual_planning_entry(
            datetime.date(2026, 7, 28), "course-1", "Cours", "1", "revision", 0
        )
