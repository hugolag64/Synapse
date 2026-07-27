from frontend.pages.dashboard._cockpit_today import _RESIZER_JS, _clamp_panel_width


def test_panel_width_is_clamped_to_safe_range():
    assert _clamp_panel_width(100, 1440) == 220
    assert _clamp_panel_width(700, 1440) == 520


def test_panel_width_respects_small_viewport():
    assert _clamp_panel_width(400, 700) == 340


def test_resizer_script_binds_pointer_drag_after_layout_mount():
    assert "querySelector('.ct-resizer')" in _RESIZER_JS
    assert "pointermove" in _RESIZER_JS
    assert "localStorage.setItem" in _RESIZER_JS
