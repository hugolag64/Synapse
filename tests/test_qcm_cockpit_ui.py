import inspect

from frontend.pages import qcm as qcm_page
from frontend.pages import qcm_cockpit


def test_qcm_cockpit_entry_uses_a_plain_action_label():
    assert qcm_cockpit.QCM_ENTRY_LABEL == "Saisir un résultat"
    assert "+" not in qcm_cockpit.QCM_ENTRY_LABEL


def test_qcm_add_dialog_has_cockpit_scoped_linear_tokens():
    assert ".qcm-add-dialog-card" in qcm_page._ADD_DIALOG_CSS
    assert "var(--accent)" in qcm_page._ADD_DIALOG_CSS
    assert "var(--border)" in qcm_page._ADD_DIALOG_CSS
    assert "@media" in qcm_page._ADD_DIALOG_CSS
    assert ".qcm-add-dialog-card" in qcm_cockpit.QCM_COCKPIT_CSS


def test_qcm_add_dialog_does_not_render_all_college_chips_up_front():
    source = inspect.getsource(qcm_page._open_add_dialog)
    assert "all_colleges" not in source
    assert "_render_course_search" in source
    assert "Rechercher un item, un cours ou une matière" in inspect.getsource(qcm_page._open_add_dialog)
