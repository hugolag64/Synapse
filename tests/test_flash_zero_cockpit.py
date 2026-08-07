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
    assert "top:8px !important" in source


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
