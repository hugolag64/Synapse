"""Le wizard de validation de séance est centré (au lieu d'être ancré en bas à
droite) et utilise les tokens du design system plutôt que du Tailwind brut."""
import inspect

from frontend.pages.dashboard import _dialogs


def _source():
    return inspect.getsource(_dialogs.open_session_feedback_dialog)


def test_session_feedback_dialog_is_no_longer_docked_to_a_corner():
    source = _source()
    assert "self-end" not in source
    assert "mr-0" not in source
    assert "rounded-none sm:rounded-lg" not in source


def test_session_feedback_dialog_card_uses_design_tokens():
    source = _source()
    assert "bg-white" not in source
    assert "dark:bg-slate-900" not in source
    assert "border-slate-200" not in source
    assert "dark:border-slate-800" not in source
    assert "background:var(--bg)" in source
    assert "border:1px solid var(--border)" in source


def test_session_feedback_dialog_keeps_its_public_signature():
    """Non-régression : seule l'apparence change, pas la signature ni les
    callbacks de validation."""
    params = list(inspect.signature(_dialogs.open_session_feedback_dialog).parameters)
    assert params == ["task", "card", "validate_fn", "initial_duration_minutes", "manual_date"]
