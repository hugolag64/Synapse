from pathlib import Path


def test_weekend_light_toggle_triggers_the_cascade():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert 'consolidation.reschedule_from("college", date.today())' in source
