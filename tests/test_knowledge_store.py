"""Tests unitaires — knowledge.store (persistance SQLite)."""
import datetime
import pytest


# ── Fixture : DB temporaire isolée (même pattern que tests/test_local_store.py) ──

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


import backend.core.knowledge.store as ks


# ── college_status ────────────────────────────────────────────────────────────

def test_college_inconnu_est_non_etudie():
    assert ks.get_college_status("Cardiovasculaire ❤️") == "non_etudie"


def test_valider_un_college_le_persiste_avec_sa_date():
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    assert ks.get_college_status("Cardiovasculaire ❤️") == "valide"

    statuses = ks.get_all_college_statuses()
    assert statuses["Cardiovasculaire ❤️"] == "valide"


def test_set_college_status_refuse_un_statut_inconnu():
    with pytest.raises(ValueError):
        ks.set_college_status("Cardiovasculaire ❤️", "presque_valide")


def test_repasser_un_college_a_non_etudie_efface_validated_at():
    ks.set_college_status("Pneumologie 🫁", "valide")
    ks.set_college_status("Pneumologie 🫁", "non_etudie")
    assert ks.get_college_status("Pneumologie 🫁") == "non_etudie"


# ── item_state ────────────────────────────────────────────────────────────────

def test_item_sans_declaration_est_none():
    assert ks.get_item_state("course-1") is None


def test_declarer_un_item_le_persiste():
    ks.set_item_state("course-1", "correct", source="triage")
    st = ks.get_item_state("course-1")

    assert st.declared_level == "correct"
    assert st.source == "triage"
    assert st.declared_at == datetime.date.today()
    assert st.context == "college"


def test_redeclarer_un_item_ecrase_le_niveau_precedent():
    ks.set_item_state("course-1", "flou")
    ks.set_item_state("course-1", "solide")
    assert ks.get_item_state("course-1").declared_level == "solide"


def test_set_item_state_refuse_un_niveau_inconnu():
    with pytest.raises(ValueError):
        ks.set_item_state("course-1", "moyen")


def test_les_contextes_college_et_ue_sont_independants():
    ks.set_item_state("course-1", "solide", context="college")
    ks.set_item_state("course-1", "flou", context="ue")

    assert ks.get_item_state("course-1", "college").declared_level == "solide"
    assert ks.get_item_state("course-1", "ue").declared_level == "flou"


def test_get_all_item_states_ne_renvoie_que_le_contexte_demande():
    ks.set_item_state("course-1", "solide", context="college")
    ks.set_item_state("course-2", "flou", context="ue")

    states = ks.get_all_item_states("college")
    assert set(states.keys()) == {"course-1"}


def test_repasser_un_college_a_non_etudie_ne_detruit_pas_les_niveaux_declares():
    """Garde-fou : le statut du collège et l'état des items sont indépendants."""
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_item_state("course-1", "solide")

    ks.set_college_status("Cardiovasculaire ❤️", "non_etudie")

    assert ks.get_item_state("course-1").declared_level == "solide"
