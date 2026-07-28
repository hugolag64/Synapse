from frontend.pages.dashboard._cockpit_today import _CSS, _RESIZER_JS, _clamp_panel_width


def test_panel_width_is_clamped_to_safe_range():
    assert _clamp_panel_width(100, 1440) == 220
    assert _clamp_panel_width(700, 1440) == 520


def test_panel_width_respects_small_viewport():
    assert _clamp_panel_width(400, 700) == 340


def test_resizer_script_binds_pointer_drag_after_layout_mount():
    assert "querySelector('.ct-resizer')" in _RESIZER_JS
    assert "pointermove" in _RESIZER_JS
    assert "localStorage.setItem" in _RESIZER_JS


def test_resizer_uses_the_dashboard_container_not_the_browser_width():
    assert "getBoundingClientRect()" in _RESIZER_JS
    assert "layoutRect.right" in _RESIZER_JS
    assert "innerWidth - moveEvent.clientX" not in _RESIZER_JS


def test_dashboard_columns_include_panel_spacing_in_the_declared_width():
    assert "box-sizing:border-box" in _CSS
