"""
Non-régression — le socle « état des connaissances » ne touche pas aux tâches JX.

Un item déclaré (ancien collège validé) devient planifiable, mais ne produit
aucune tâche J3/J7/J14/J30 : la génération JX exige une date_1ere_lecture qu'il
n'a pas. Son cycle d'entretien relève du bloc 2 (moteur de planification).
"""
import datetime
import pytest
from types import SimpleNamespace


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
from backend.core.reviews.service import ReviewService


def _course(course_id, first_read=None):
    return SimpleNamespace(
        id=course_id, title=f"Item {course_id}", item_number="230",
        college=["Cardiovasculaire ❤️"],
        url_pdf="http://pdf", url_pdf_ue=None,
        agregation_fiche_edn=None,
        date_1ere_lecture=first_read, date_1ere_lecture_ue=None,
        nb_lectures=1 if first_read else 0, nb_lectures_ue=0,
        lecture_j3_college=None, lecture_j7_college=None,
        lecture_j14_college=None, lecture_j30_college=None,
        lecture_j3_ue=None, lecture_j7_ue=None,
        lecture_j14_ue=None, lecture_j30_ue=None,
        anki=False, qcm_done=False, course_status="À lire",
    )


@pytest.fixture
def fake_store(monkeypatch):
    import backend.state.store as store_mod
    fake = SimpleNamespace(cours=[], active_stage=None, semantic_graph={})
    monkeypatch.setattr(store_mod, "data_store", fake)
    return fake


def test_item_declare_sans_premiere_lecture_ne_genere_aucune_tache_jx(fake_store):
    ks.set_college_status("Cardiovasculaire ❤️", "valide")
    ks.set_item_state("old-1", "solide")
    fake_store.cours = [_course("old-1")]

    tasks = ReviewService().generate_reviews("college")
    assert tasks == []


def test_un_cours_normal_genere_toujours_ses_taches_jx(fake_store):
    """Le comportement existant est intact."""
    fake_store.cours = [_course("new-1", first_read=datetime.date.today() - datetime.timedelta(days=10))]

    tasks = ReviewService().generate_reviews("college")
    types = {t.review_type for t in tasks}
    assert types == {"J3", "J7", "J14", "J30"}


def test_declarer_un_cours_deja_lu_ne_change_ni_ses_dates_ni_ses_types(fake_store):
    """Une déclaration peut déplacer le score, jamais les échéances."""
    first_read = datetime.date.today() - datetime.timedelta(days=10)
    fake_store.cours = [_course("new-1", first_read=first_read)]

    before = {(t.review_type, t.due_date) for t in ReviewService().generate_reviews("college")}

    ks.set_item_state("new-1", "flou")
    after = {(t.review_type, t.due_date) for t in ReviewService().generate_reviews("college")}

    assert before == after
