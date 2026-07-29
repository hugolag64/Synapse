import inspect

from frontend.components import ai_practice_panel, practice_import_panel
from frontend.pages import qcm_cockpit


def test_item_cockpit_exposes_local_dp_kfp_import():
    source = inspect.getsource(ai_practice_panel.render_ai_practice_panel)
    assert "Importer DP/KFP" in source
    assert "open_practice_import_dialog" in source


def test_qcm_cockpit_exposes_local_dp_kfp_import():
    source = inspect.getsource(qcm_cockpit._draw_topbar) if hasattr(qcm_cockpit, "_draw_topbar") else inspect.getsource(qcm_cockpit.render_qcm_cockpit)
    assert "Importer DP/KFP" in source


def test_import_dialog_is_local_upload_flow():
    source = inspect.getsource(practice_import_panel.open_practice_import_dialog)
    assert "ui.upload" in source
    assert "import_practice_batch" in source
    assert "parse_practice_discussion" in source
    assert ".txt,.md,.html" in source


def test_item_practice_panel_exposes_random_and_anchor_actions():
    source = inspect.getsource(ai_practice_panel.render_ai_practice_panel)
    assert "Tirer au hasard" in source
    assert "S'entraîner" in source
    assert "set_ai_practice_anchor" in inspect.getsource(ai_practice_panel._open_answer_dialog)
