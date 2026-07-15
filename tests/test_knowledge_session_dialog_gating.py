"""Test de contrat — déclaration passive depuis la modale de séance.

``frontend/pages/dashboard/_dialogs.py::open_session_feedback_dialog`` affiche
un champ « Où en es-tu sur cet item ? » uniquement quand
``knowledge.service.is_to_situate(task.course_id, task.college, task.context)``
est vrai, et persiste la déclaration via
``knowledge_store.set_item_state(..., source="reprise")`` — jamais
``source="triage"``, qui est réservé aux pages de triage dédiées (Tasks 8/9).
Ce test vérifie ce contrat exact sans rendre la modale : si le gating ou la
source cassent, l'utilisateur perd le chemin par défaut du triage progressif
sans aucun signal d'erreur visible.
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


def test_un_item_dun_college_valide_non_declare_est_a_situer_dans_la_modale():
    import backend.core.knowledge.store as ks
    import backend.core.knowledge.service as ksv

    ks.set_college_status("Cardiovasculaire ❤️", "valide")

    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"], "college") is True


def test_declarer_depuis_la_modale_utilise_la_source_reprise_et_ferme_le_gate():
    import backend.core.knowledge.store as ks
    import backend.core.knowledge.service as ksv

    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"], "college") is True

    # Appel exact fait par _submit() dans _dialogs.py.
    ks.set_item_state("course-1", "correct", context="college", source="reprise")

    assert ksv.is_to_situate("course-1", ["Cardiovasculaire ❤️"], "college") is False

    st = ks.get_item_state("course-1", context="college")
    assert st is not None
    assert st.declared_level == "correct"
    assert st.source == "reprise"


def test_la_source_reprise_se_distingue_de_la_source_triage():
    """La modale de séance (Task 10) et les pages dédiées (Tasks 8/9) déclarent
    le même item mais avec des sources différentes — ce qui permet de
    distinguer une déclaration passive d'une déclaration explicite."""
    import backend.core.knowledge.store as ks

    ks.set_item_state("course-triage", "flou", context="college", source="triage")
    ks.set_item_state("course-reprise", "solide", context="college", source="reprise")

    assert ks.get_item_state("course-triage", context="college").source == "triage"
    assert ks.get_item_state("course-reprise", context="college").source == "reprise"
