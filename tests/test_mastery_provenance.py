"""Le score de maîtrise doit dire d'où il vient.

Sur sept semaines de données réelles, 96 % des cours affichés « fragile » ou
« critique » le sont à cause de la décroissance d'une auto-déclaration, pas
d'un échec constaté. Rien ne le distinguait visuellement d'un score mesuré.
"""

from pathlib import Path


def test_snapshot_exposes_the_number_of_real_evidences():
    from backend.core.reviews.mastery import CourseProgressSnapshot

    assert "evidence_count" in CourseProgressSnapshot.__dataclass_fields__


def test_mastery_computation_fills_the_evidence_count():
    source = Path("backend/core/reviews/mastery.py").read_text(encoding="utf-8")

    assert '"evidence_count":   int(seed.n_evidence or 0),' in source


def test_indicator_marks_a_score_without_any_evidence():
    from frontend.components.mastery_indicator import provenance_label

    assert provenance_label(0) == "déclaré"
    assert provenance_label(1) == "mesuré"
    assert provenance_label(9) == "mesuré"


def test_indicator_explains_what_a_declared_score_means():
    from frontend.components.mastery_indicator import provenance_tooltip

    declared = provenance_tooltip(0)
    measured = provenance_tooltip(4)

    assert "aucune preuve" in declared.lower()
    assert "4" in measured


def test_semantic_text_tokens_exist_for_the_three_states():
    """--success/--warning/--danger sont calibrés pour fond sombre : utilisés
    comme couleur de texte, ils passent sous le seuil AA en thème clair."""
    source = Path("frontend/design_tokens.py").read_text(encoding="utf-8")

    for token in ("--success-text", "--danger-text", "--warning-text"):
        assert source.count(f"{token}:") == 2, f"{token} doit être défini une fois par thème"


def test_mastery_colour_code_uses_the_readable_variants():
    source = Path("frontend/components/mastery_indicator.py").read_text(encoding="utf-8")

    assert "var(--success-text)" in source
    assert "var(--warning-text)" in source
    assert "var(--danger-text)" in source
    assert "var(--success)" not in source
    assert "var(--warning)" not in source
    assert "var(--danger)" not in source
