from backend.config.settings import Settings


def test_gemini_routing_defaults_are_economic():
    settings = Settings(_env_file=None)

    assert settings.gemini_lite_model == "gemini-3.1-flash-lite"
    assert settings.gemini_flash_model == "gemini-3-flash-preview"
    assert settings.gemini_timeout_seconds == 60
