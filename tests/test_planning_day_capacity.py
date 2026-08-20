from pathlib import Path


def _source() -> str:
    return Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")


def test_day_actions_menu_offers_a_capacity_override():
    assert "Ajuster la capacité de ce jour" in _source()


def test_day_capacity_dialog_writes_planning_targets():
    source = _source()
    assert '"mode": "minutes"' in source
    assert 'data_store.set_preference("planning_targets", targets)' in source


def test_day_capacity_dialog_can_reset_to_the_global_default():
    assert "targets.pop(day.isoformat(), None)" in _source()
