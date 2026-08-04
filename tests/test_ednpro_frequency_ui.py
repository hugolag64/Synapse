import inspect

from frontend.components import ai_practice_panel


def test_item_panel_exposes_ednpro_frequency_and_direct_training():
    source = inspect.getsource(ai_practice_panel.render_ai_practice_panel)
    frequency_source = inspect.getsource(ai_practice_panel._render_ednpro_frequency)
    assert "Annales EDNpro" in frequency_source
    assert "Travailler les annales" in frequency_source
    assert "Synchroniser maintenant" in frequency_source
    assert "get_ednpro_item_frequency" in frequency_source
    assert "_render_ednpro_frequency(course, mastery_score, refresh)" in source


def test_item_panel_has_an_explicit_empty_import_state():
    source = inspect.getsource(ai_practice_panel._start_ednpro_training)
    source += inspect.getsource(ai_practice_panel._render_ednpro_frequency)
    assert "Aucune question EDNpro importée" in source
    assert "train.disable()" in source
