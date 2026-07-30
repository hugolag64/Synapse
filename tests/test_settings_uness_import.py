"""Tests for the UNESS annale-tagging dialog wired into the settings cockpit scan."""

from __future__ import annotations

import inspect

from frontend.pages import settings_cockpit


def test_settings_cockpit_opens_a_tag_dialog_when_scan_reports_pending_groups() -> None:
    source = inspect.getsource(settings_cockpit.render_settings_cockpit)

    assert "_open_tag_dialog" in source
    assert "pending_tag" in source
    assert "ANNALE_TYPE_LABELS" in source


def test_settings_cockpit_passes_chosen_tags_back_into_the_scan() -> None:
    source = inspect.getsource(settings_cockpit.render_settings_cockpit)

    assert "import_verified_directory(tags=" in source


def test_settings_cockpit_lets_the_user_skip_tagging_for_now() -> None:
    source = inspect.getsource(settings_cockpit.render_settings_cockpit)

    assert "Ignorer pour l'instant" in source
