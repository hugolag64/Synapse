"""Tests des seams non visuels du panneau OIC partagé."""

from frontend.components.oic_panel import should_load_on_tab_activation


def test_panel_uses_lazy_tab_activation():
    assert should_load_on_tab_activation("overview", False) is False
    assert should_load_on_tab_activation("OIC", False) is True
    assert should_load_on_tab_activation("OIC", True) is False
