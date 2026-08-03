"""Tests pour les tokens de couleur du composant de maîtrise actuel."""
from frontend.components.mastery_indicator import _LEVEL_COLOR


def test_fragile_uses_da_amber_token():
    assert _LEVEL_COLOR["fragile"] == "var(--warning)"


def test_fragile_ghost_matches_fill_rgb():
    assert "fragile" in _LEVEL_COLOR


def test_fragile_tint_matches_fill_rgb():
    assert _LEVEL_COLOR["fragile"] != _LEVEL_COLOR["critique"]


def test_other_levels_unchanged():
    assert _LEVEL_COLOR == {
        "solide": "var(--success)",
        "correct": "var(--text-muted)",
        "fragile": "var(--warning)",
        "critique": "var(--danger)",
    }
