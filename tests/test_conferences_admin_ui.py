from pathlib import Path


def test_conferences_admin_component_contains_import_and_validation_actions():
    source = Path("frontend/components/conferences_admin.py").read_text(encoding="utf-8")

    assert "PLANNING CONFÉRENCES — IMPORT" in source
    assert "Importer le planning" in source
    assert "Valider" in source
    assert "Non applicable" in source


def test_settings_mounts_conferences_admin_panel():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert "render_conferences_admin" in source
    assert "PLANNING CONFÉRENCES" in source
