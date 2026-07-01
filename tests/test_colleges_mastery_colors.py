"""Tests pour les tokens de couleur de mastery du switch collèges."""
from frontend.pages.colleges import _FILL, _GHOST, _TINT


def test_fragile_uses_da_amber_token():
    assert _FILL["fragile"] == "#B45309"


def test_fragile_ghost_matches_fill_rgb():
    assert _GHOST["fragile"] == "rgba(180,83,9,0.12)"


def test_fragile_tint_matches_fill_rgb():
    assert _TINT["fragile"] == "rgba(180,83,9,0.05)"


def test_other_levels_unchanged():
    assert _FILL["solide"] == "#059669"
    assert _FILL["correct"] == "#3B82F6"
    assert _FILL["non_commence"] == "#CBD5E1"
    assert _GHOST["solide"] == "rgba(5,150,105,0.12)"
    assert _TINT["non_commence"] == "transparent"
