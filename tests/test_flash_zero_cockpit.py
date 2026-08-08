from pathlib import Path


def test_flash_zero_card_model_exposes_morning_task_and_action():
    from frontend.components.flash_zero_cockpit import flash_zero_card_model

    model = flash_zero_card_model({"course_title": "Flash-Zero du matin", "duration_minutes": 5}, completed=False)

    assert model == {
        "title": "Flash-Zero du matin",
        "duration": "5 min",
        "status": "À faire",
        "action": "Lancer",
    }


def test_flash_zero_card_model_marks_completed_task():
    from frontend.components.flash_zero_cockpit import flash_zero_card_model

    assert flash_zero_card_model({"duration_minutes": 5}, completed=True)["status"] == "Fait"


def test_flash_zero_card_has_a_hover_dismiss_control():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert ".flash-zero-card:hover .flash-zero-dismiss" in source
    assert 'aria-label="Ignorer le Flash-Zero du jour"' in source
    assert ".flash-zero-layout" in source


def test_dismiss_control_no_longer_overlaps_the_action_button():
    """La croix était en position:absolute right:8px, c'est-à-dire sous le
    bouton « Lancer ». Elle doit vivre dans le flux, avant ce bouton."""
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert "position:absolute" not in source
    assert "top:8px !important" not in source
    assert "pointer-events:none" in source
    assert source.index("flash-zero-dismiss") < source.index('model["action"]')


def test_correction_separates_given_answer_from_expected_answer():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert ".flash-zero-answer-label" in source
    assert ".flash-zero-answer-value" in source
    assert '"Ta réponse"' in source
    assert '"Réponse attendue"' in source


def test_flash_zero_wizard_has_separate_correction_step():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert '"phase": "question"' in source
    assert "Question suivante" in source
    assert "Correction" in source
    assert "results" in source
    assert 'aria-label="Ignorer le Flash-Zero du jour"' in source


def test_sprint_card_uses_linear_layout_primitives():
    source = Path("frontend/components/edn_insights_panel.py").read_text(encoding="utf-8")

    assert ".edn-sprint-progress-track" in source
    assert ".edn-sprint-metric" in source
    assert ".edn-sprint-priority-row" in source


def test_flash_zero_wizard_shows_a_soft_badge_for_ai_flagged_questions():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert "question.review_reason" in source
    assert "Généré par IA" in source
