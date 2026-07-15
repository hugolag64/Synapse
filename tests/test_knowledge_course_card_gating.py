"""Test de contrat — badge « à situer » sur la CourseCard.

``frontend/components/course_card.py`` affiche un badge « À situer » sur la
première ligne de la carte uniquement quand
``knowledge.service.is_to_situate(course.id, list(course.college or []), context)``
est vrai. ``course_card()`` est une fonction de rendu NiceGUI complète —
non testable unitairement de façon pratique — donc ce test vérifie
uniquement la condition de gating sous-jacente, avec l'exacte forme d'appel
utilisée par le badge, y compris le cas défensif ``course.college is None``
(un cours dont l'attribut Notion `college` n'a jamais été renseigné) que la
suite de tests de Task 4 (``test_knowledge_service.py``) ne couvre pas.
"""
import pytest


# ── Fixture : DB temporaire isolée (même pattern que tests/test_knowledge_store.py) ──

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


def test_badge_visible_college_valide_non_declare():
    """Collège validé + aucun état déclaré → le badge doit s'afficher."""
    import backend.core.knowledge.store as ks
    import backend.core.knowledge.service as ksv

    ks.set_college_status("Cardiovasculaire ❤️", "valide")

    course_college = ["Cardiovasculaire ❤️"]
    assert ksv.is_to_situate("course-1", list(course_college or []), "college") is True


def test_badge_disparait_apres_declaration():
    """Une fois un niveau déclaré, le gate se ferme et le badge disparaît."""
    import backend.core.knowledge.store as ks
    import backend.core.knowledge.service as ksv

    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_item_state("course-1", "correct", context="college")

    course_college = ["Cardiovasculaire ❤️"]
    assert ksv.is_to_situate("course-1", list(course_college or []), "college") is False


def test_badge_masque_college_non_valide():
    """Collège non validé (ou inconnu) → jamais « à situer »."""
    import backend.core.knowledge.service as ksv

    course_college = ["Pas encore validé"]
    assert ksv.is_to_situate("course-1", list(course_college or []), "college") is False


def test_college_none_ne_casse_pas_le_gate_defensif():
    """course.college peut être None (attribut Notion jamais renseigné) —
    le badge utilise `list(course.college or [])` pour s'en protéger ;
    ce test vérifie que ce garde-fou tient réellement avec is_to_situate."""
    import backend.core.knowledge.service as ksv

    course_college = None
    assert ksv.is_to_situate("course-1", list(course_college or []), "college") is False


def test_college_liste_vide_ne_casse_pas_le_gate():
    """course.college peut aussi être une liste vide plutôt que None."""
    import backend.core.knowledge.service as ksv

    course_college = []
    assert ksv.is_to_situate("course-1", list(course_college or []), "college") is False
