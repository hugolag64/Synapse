from pathlib import Path


def test_settings_page_exposes_a_global_capacity_control():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert "Capacité quotidienne" in source
    assert '"planning_capacity_minutes"' in source
    assert "capacity_hours_to_minutes" in source
