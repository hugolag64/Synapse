from pathlib import Path


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


def test_flash_zero_wizard_persists_each_answer():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert "service.record_attempt(question, is_correct)" in source


def test_sprint_card_uses_linear_layout_primitives():
    source = Path("frontend/components/edn_insights_panel.py").read_text(encoding="utf-8")

    assert ".edn-sprint-progress-track" in source
    assert ".edn-sprint-metric" in source
    assert ".edn-sprint-priority-row" in source


def test_flash_zero_wizard_shows_a_soft_badge_for_ai_flagged_questions():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert "question.review_reason" in source
    assert "Généré par IA" in source


def test_wizard_injects_its_own_styles_now_that_the_card_is_gone():
    """Le CSS du wizard était injecté par render_flash_zero_card ; sans elle,
    open_flash_zero_quiz doit s'en charger — add_css car le dialogue s'ouvre
    sur un client déjà connecté."""
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert "render_flash_zero_card" not in source
    assert 'ui.add_head_html(f"<style>{_CSS}</style>", shared=True)' in source
    assert "ui.add_css(_CSS)" in source
