from pathlib import Path


SOURCE = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")


def test_settings_exposes_explicit_planning_save_and_reentry_date():
    assert "Date de reprise" in SOURCE
    assert "Enregistrer la planification" in SOURCE
    assert "study_resume_date" in SOURCE
    assert "set_preferences" in SOURCE


def test_settings_exposes_sprint_visibility_control():
    assert "edn_sprint_visible" in SOURCE
    assert "Masquer le Sprint" in SOURCE
    assert "Réafficher le Sprint" in SOURCE
