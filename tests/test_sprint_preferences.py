import pytest

from backend.state.store import DataStore


def test_sprint_and_reentry_preferences_have_safe_defaults():
    store = DataStore()
    assert store.preferences["edn_target_date"] == "2026-10-15"
    assert store.preferences["study_resume_date"] == "2026-08-20"
    assert store.preferences["edn_sprint_visible"] is True


def test_set_preferences_validates_dates_and_writes_values(tmp_path):
    store = DataStore()
    store.CACHE_FILE = str(tmp_path / "cache.json")
    store.set_preferences({
        "edn_target_date": "2026-11-01",
        "study_resume_date": "2026-08-20",
        "edn_sprint_visible": False,
    })

    reloaded = DataStore()
    reloaded.CACHE_FILE = store.CACHE_FILE
    assert reloaded.load_from_disk(force=True) is True
    assert reloaded.preferences["edn_target_date"] == "2026-11-01"
    assert reloaded.preferences["study_resume_date"] == "2026-08-20"
    assert reloaded.preferences["edn_sprint_visible"] is False


def test_invalid_reentry_date_is_rejected():
    store = DataStore()
    with pytest.raises(ValueError):
        store.set_preferences({"study_resume_date": "not-a-date"})
