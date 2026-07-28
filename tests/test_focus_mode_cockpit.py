from frontend.components.focus_mode_cockpit import _fmt_timer, _elapsed_minutes


def test_fmt_timer_pads_minutes_and_seconds():
    assert _fmt_timer(25 * 60) == "25:00"
    assert _fmt_timer(65) == "01:05"
    assert _fmt_timer(5) == "00:05"


def test_fmt_timer_clamps_negative_to_zero():
    assert _fmt_timer(-3) == "00:00"


def test_elapsed_minutes_none_when_timer_never_started():
    assert _elapsed_minutes(remaining=1500, total=1500) is None


def test_elapsed_minutes_rounds_down_and_floors_at_one():
    assert _elapsed_minutes(remaining=1500 - 90, total=1500) == 1
    assert _elapsed_minutes(remaining=1500 - 600, total=1500) == 10


def test_focus_dialog_uses_maximized_persistent_prop():
    source = open("frontend/components/focus_mode_cockpit.py", encoding="utf-8").read()

    assert '.props("maximized persistent")' in source
    assert "full-width full-height" not in source
