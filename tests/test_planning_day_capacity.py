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


def test_day_footer_is_clickable_and_opens_the_capacity_dialog():
    source = _source()
    assert '"pl-day-foot cursor-pointer"' in source
    assert 'foot.on("click", lambda day=d: _open_day_capacity_dialog(day))' in source


def test_day_capacity_dialog_has_fine_grained_minute_buttons():
    source = _source()
    assert "-30min" in source
    assert "+30min" in source


def test_day_capacity_dialog_allows_zero():
    source = _source()
    assert "max(0, min(MAX_CAPACITY_HOURS * 60" in source


def test_day_capacity_save_and_reset_trigger_the_cascade():
    source = _source()
    assert 'consolidation.reschedule_from("college", day)' in source
