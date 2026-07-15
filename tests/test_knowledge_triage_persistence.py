"""Test de contrat — persistance utilisée par frontend/pages/triage.py.

La page de triage ne fait qu'un seul appel métier dans sa closure ``_set`` :
``knowledge_store.set_item_state(course_id, level, context="college", source="triage")``.
Ce test vérifie que cet appel exact persiste bien un état lisible via
``get_item_state``, avec la bonne source et le bon niveau déclaré. Si ce
contrat casse, la page de triage casse silencieusement (aucun retour
utilisateur visible autre qu'un bouton qui ne se met pas en surbrillance).
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


def test_set_item_state_depuis_le_triage_est_relisible_avec_sa_source():
    import backend.core.knowledge.store as ks

    ks.set_item_state("course-1", "correct", context="college", source="triage")

    st = ks.get_item_state("course-1", context="college")

    assert st is not None
    assert st.declared_level == "correct"
    assert st.source == "triage"
