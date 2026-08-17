"""Tests des seams non visuels du panneau OIC partagé."""

from frontend.components.oic_panel import should_load_on_tab_activation


def test_panel_uses_lazy_tab_activation():
    assert should_load_on_tab_activation("overview", False) is False
    assert should_load_on_tab_activation("OIC", False) is True
    assert should_load_on_tab_activation("OIC", True) is False


def test_panel_exposes_one_micro_question_for_rang_a():
    import inspect

    from frontend.components import oic_panel

    source = inspect.getsource(oic_panel.OICPanelController.render_rows)
    assert "create_rang_a_micro_session" in source
    assert "Micro-question Rang A" in source
