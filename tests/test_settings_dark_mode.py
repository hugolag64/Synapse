import frontend.pages.settings_cockpit as settings_cockpit


class _FakeDarkMode:
    """Reproduit le contrat de nicegui.ui.dark_mode() utilisé par la page."""

    def __init__(self, value: bool = False) -> None:
        self.value = value

    def enable(self) -> None:
        self.value = True

    def disable(self) -> None:
        self.value = False

    def toggle(self) -> None:
        self.value = not self.value


def _patch(monkeypatch, dark: _FakeDarkMode) -> dict:
    saved: dict = {}
    monkeypatch.setattr(settings_cockpit.ui, "dark_mode", lambda: dark)
    monkeypatch.setattr(
        settings_cockpit.data_store,
        "set_preference",
        lambda key, value: saved.__setitem__(key, value),
    )
    return saved


def test_enabling_dark_mode_persists_the_preference(monkeypatch):
    saved = _patch(monkeypatch, _FakeDarkMode(False))

    assert settings_cockpit.toggle_dark_mode(True) is True
    assert saved == {"dark_mode": True}


def test_disabling_dark_mode_persists_the_preference(monkeypatch):
    saved = _patch(monkeypatch, _FakeDarkMode(True))

    assert settings_cockpit.toggle_dark_mode(False) is False
    assert saved == {"dark_mode": False}


def test_toggle_without_argument_persists_the_resolved_value(monkeypatch):
    saved = _patch(monkeypatch, _FakeDarkMode(False))

    assert settings_cockpit.toggle_dark_mode() is True
    assert saved == {"dark_mode": True}
