import backend.config.settings as app_settings
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
