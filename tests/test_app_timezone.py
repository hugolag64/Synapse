from backend.config.settings import APP_TIMEZONE, business_today, now_local


def test_business_time_defaults_to_paris():
    assert APP_TIMEZONE.key == "Europe/Paris"
    assert now_local().tzinfo == APP_TIMEZONE
    assert business_today() == now_local().date()
