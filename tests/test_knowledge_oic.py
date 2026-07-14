"""Tests — une évaluation OIC réussie marque l'OIC comme maîtrisé."""
import pytest

from backend.core.knowledge.models import OIC_SUCCESS_SCORE


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


import backend.core.reviews.local_store as ls


def _seed_one_oic(course_id: str = "course-1", rang: str = "A") -> int:
    """Insère un OIC et renvoie son id."""
    ls.upsert_lisa_oic(course_id, [
        {"oic_code": "OIC-001", "intitule": "Objectif test", "rang": rang,
         "rubrique": "Définition", "ordre": 1},
    ])
    oics = ls.get_lisa_oic(course_id)
    return oics[0]["id"]


def _mastered(oic_id: int) -> int:
    with ls._conn() as con:
        return con.execute(
            "SELECT mastered FROM lisa_oic WHERE id = ?", (oic_id,)
        ).fetchone()["mastered"]


def test_une_tentative_reussie_passe_mastered_a_1():
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, OIC_SUCCESS_SCORE, "[]")
    assert _mastered(oic_id) == 1


def test_une_tentative_ratee_ne_passe_pas_mastered():
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, OIC_SUCCESS_SCORE - 1, "[]")
    assert _mastered(oic_id) == 0


def test_une_tentative_ratee_ne_demastere_pas_un_oic_deja_acquis():
    """Un échec ponctuel ne doit pas effacer une réussite antérieure."""
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, 90, "[]")
    ls.save_oic_attempt(oic_id, 20, "[]")
    assert _mastered(oic_id) == 1


def test_la_tentative_est_bien_enregistree():
    oic_id = _seed_one_oic()
    ls.save_oic_attempt(oic_id, 85, "[]")
    attempts = ls.get_oic_attempts(oic_id)
    assert len(attempts) == 1
    assert attempts[0]["session_score"] == 85
