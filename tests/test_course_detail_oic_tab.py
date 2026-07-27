"""Smoke tests for the lazy OIC tab contract."""

from frontend.components.oic_panel import should_load_on_tab_activation


def test_oic_tab_loads_only_when_activated_once():
    assert should_load_on_tab_activation("Vue d'ensemble", False) is False
    assert should_load_on_tab_activation("OIC", False) is True
    assert should_load_on_tab_activation("OIC", True) is False
