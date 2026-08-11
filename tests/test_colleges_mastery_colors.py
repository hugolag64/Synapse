"""Tests pour les tokens de couleur du composant de maîtrise actuel.

Le code couleur utilise les variantes `-text` des tokens sémantiques :
`--success`, `--warning` et `--danger` sont déclarés « stables clair & sombre »
dans `design_tokens.py` et calibrés pour un fond sombre. Employés comme couleur
de texte, ils tombent sous le seuil WCAG AA en thème clair — mesuré à 2,57 pour
`--success` et ~2,2 pour `--warning`. Or c'est précisément ici que la couleur
porte l'information la plus urgente à lire.
"""
from frontend.components.mastery_indicator import _LEVEL_COLOR


def test_fragile_uses_the_readable_amber_token():
    assert _LEVEL_COLOR["fragile"] == "var(--warning-text)"


def test_fragile_ghost_matches_fill_rgb():
    assert "fragile" in _LEVEL_COLOR


def test_fragile_tint_matches_fill_rgb():
    assert _LEVEL_COLOR["fragile"] != _LEVEL_COLOR["critique"]


def test_other_levels_unchanged():
    assert _LEVEL_COLOR == {
        "solide": "var(--success-text)",
        "correct": "var(--text-muted)",
        "fragile": "var(--warning-text)",
        "critique": "var(--danger-text)",
    }
