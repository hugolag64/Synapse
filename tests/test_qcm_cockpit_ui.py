import inspect

from frontend.pages import qcm as qcm_page
from frontend.pages import qcm_cockpit


def test_qcm_cockpit_entry_uses_a_plain_action_label():
    assert qcm_cockpit.QCM_ENTRY_LABEL == "Saisir un résultat"
    assert "+" not in qcm_cockpit.QCM_ENTRY_LABEL


def test_qcm_cockpit_exposes_ai_generation_entry():
    import inspect

    source = inspect.getsource(qcm_cockpit.render_qcm_cockpit)
    assert "Générer avec IA" in source
    assert "_open_ai_generation_picker" in source


def test_qcm_cockpit_keeps_generated_sessions_visible_before_scoring():
    pending = qcm_cockpit._pending_ai_sessions([
        {"id": 1, "score_percent": None},
        {"id": 2, "score_percent": 82},
    ])

    assert [row["id"] for row in pending] == [1]


def test_qcm_cockpit_renders_a_start_action_for_pending_ai_sessions():
    source = inspect.getsource(qcm_cockpit.render_qcm_cockpit)

    assert "get_ai_practice_sessions" in source
    assert "SESSIONS À FAIRE" in source
    assert "Commencer" in source
    assert "_open_answer_dialog" in source


def test_ai_generation_opens_the_session_and_defaults_to_closed_questions():
    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._open_generation_dialog)

    assert 'value=0' in source
    assert '_open_answer_dialog(session_id, refresh)' in source


def test_ai_history_exposes_the_session_difficulty():
    from frontend.components import ai_practice_panel

    source = inspect.getsource(ai_practice_panel._render_history)
    assert "difficulty_labels" in source
    assert "difficulty_label" in source


def test_item_picker_filters_and_limits_results():
    courses = [
        ("118", type("Course", (), {"title": "Évaluation fonctionnelle"})()),
        ("119", type("Course", (), {"title": "Soins chroniques"})()),
        ("220", type("Course", (), {"title": "Cardiologie"})()),
    ]

    matches = qcm_cockpit._filter_item_picker_options(courses, "cardio", limit=1)

    assert matches == [("220", courses[2][1])]


def test_qcm_cockpit_uses_compact_picker_and_single_action_menu():
    source = inspect.getsource(qcm_cockpit._open_ai_generation_picker)
    topbar_source = inspect.getsource(qcm_cockpit.render_qcm_cockpit)

    assert "ui.select" not in source
    assert "Rechercher un ITEM" in source
    assert "max-h-[280px]" in source
    assert "ui.menu" in topbar_source
    assert "Nouvelle session" in topbar_source


def test_qcm_cockpit_is_full_width_with_handoff_content_bound():
    assert "max-width:1200px" in qcm_cockpit.QCM_COCKPIT_CSS
    assert "align-self:stretch" in qcm_cockpit.QCM_COCKPIT_CSS


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
