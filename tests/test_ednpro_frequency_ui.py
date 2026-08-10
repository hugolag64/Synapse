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


def test_colleges_and_item_detail_render_ednpro_frequency_badge():
    from frontend.pages import colleges_cockpit, course_detail_cockpit

    colleges_source = inspect.getsource(colleges_cockpit)
    detail_source = inspect.getsource(course_detail_cockpit)
    assert "get_all_ednpro_item_frequencies" in colleges_source
    assert "ednpro_frequency_badge" in colleges_source
    assert "EDNpro" in colleges_source
    assert "get_all_ednpro_item_frequencies" in detail_source
    assert "ednpro_frequency_badge" in detail_source


def test_items_page_renders_frequency_badge_and_wrapped_title():
    from frontend.pages import items

    source = inspect.getsource(items)
    assert "get_all_ednpro_item_frequencies" in source
    assert "ednpro_frequency_badge" in source
    assert "EDNpro" in source
    assert "white-space:normal" in source or "white-space: normal" in source
