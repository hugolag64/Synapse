"""Test de contrat — comportement de knowledge_service.oic_coverage() pour
un item sans OIC vs. avec au moins un OIC de rang A.

Historiquement, ce test reprenait la condition de gating utilisée par le bloc
« Niveau déclaré » de la fiche cours (rang_a_total or rang_b_total) pour
décider d'afficher une ligne de couverture OIC. Ce bloc a été retiré du
cockpit au chantier C2 (2026-08-08) : la couverture OIC est affichée en
détail dans l'onglet OIC dédié (render_oic_panel), pas en résumé dans
l'onglet Vue d'ensemble. Le test reste utile comme contrat sur la forme des
comptes retournés par oic_coverage().
"""
import pytest


# ── Fixture : DB temporaire isolée (même pattern que tests/test_knowledge_oic.py) ──

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


def test_aucun_oic_ne_declenche_pas_l_affichage_de_la_couverture():
    """Un item sans aucun OIC (rang A ou B) doit signaler « rien à afficher »."""
    from backend.core.knowledge import service as knowledge_service

    cov = knowledge_service.oic_coverage("course-sans-oic")

    assert cov["rang_a_total"] == 0
    assert cov["rang_b_total"] == 0
    # C'est exactement la garde utilisée par _render_knowledge_block.
    assert not (cov["rang_a_total"] or cov["rang_b_total"])


def test_un_seul_oic_de_rang_a_declenche_l_affichage_de_la_couverture():
    """Dès qu'un OIC (même unique, même de rang A seul) existe, la ligne s'affiche."""
    import backend.core.reviews.local_store as ls
    from backend.core.knowledge import service as knowledge_service

    ls.upsert_lisa_oic("course-avec-oic", [
        {"oic_code": "OIC-001", "intitule": "Objectif test", "rang": "A",
         "rubrique": "Définition", "ordre": 1},
    ])

    cov = knowledge_service.oic_coverage("course-avec-oic")

    assert cov["rang_a_total"] == 1
    assert cov["rang_b_total"] == 0
    assert cov["rang_a_total"] or cov["rang_b_total"]
