import backend.config.settings as app_settings
import datetime
import json
from backend.state.store import DataStore


def test_business_time_defaults_to_paris():
    assert app_settings.APP_TIMEZONE.key == "Europe/Paris"
    assert app_settings.now_local().tzinfo == app_settings.APP_TIMEZONE
    assert app_settings.business_today() == app_settings.now_local().date()


def test_app_timezone_can_switch_between_supported_zones_and_invalid_falls_back():
    original = app_settings.get_app_timezone().key
    try:
        app_settings.set_app_timezone("Indian/Reunion")
        assert app_settings.get_app_timezone().key == "Indian/Reunion"
        assert app_settings.now_local().tzinfo == app_settings.APP_TIMEZONE

        app_settings.set_app_timezone("invalid/zone")
        assert app_settings.get_app_timezone().key == "Europe/Paris"
    finally:
        app_settings.set_app_timezone(original)


def test_datastore_timezone_preference_defaults_to_paris():
    assert DataStore().preferences["timezone"] == "Europe/Paris"


def test_datastore_edn_target_date_defaults_to_october_15():
    assert DataStore().preferences["edn_target_date"] == "2026-10-15"


def test_datastore_study_reentry_and_sprint_visibility_have_safe_defaults():
    store = DataStore()
    assert store.preferences["study_resume_date"] == "2026-08-20"
    assert store.preferences["edn_sprint_visible"] is True


def test_datastore_rejects_invalid_edn_target_date():
    store = DataStore()
    try:
        store.set_preference("edn_target_date", "not-a-date")
    except ValueError:
        pass
    else:
        raise AssertionError("An invalid EDN target date must be rejected")


def test_stale_cache_keeps_user_preferences(tmp_path, monkeypatch):
    cache_path = tmp_path / "data_cache.json"
    cache_path.write_text(
        json.dumps({
            "last_updated": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(),
            "preferences": {"dark_mode": True, "timezone": "Indian/Reunion"},
            "cours": [],
        }),
        encoding="utf-8",
    )
    store = DataStore()
    monkeypatch.setattr(store, "CACHE_FILE", str(cache_path))

    try:
        assert store.load_from_disk() is False
        assert store.preferences["dark_mode"] is True
        assert store.preferences["timezone"] == "Indian/Reunion"
        assert app_settings.get_app_timezone().key == "Indian/Reunion"
    finally:
        app_settings.set_app_timezone("Europe/Paris")
