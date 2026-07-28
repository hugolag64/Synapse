"""Tests — mastery.py exploite la graine déclarée (knowledge)."""
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
from backend.core.knowledge.retention import Evidence
from backend.core.reviews.mastery import _build_retention_evidence, get_course_mastery


def _course(course_id="course-1", first_read=None, nb_lectures=0):
    """Faux cours : ancien item d'un collège validé, jamais lu dans Synapse."""
    return SimpleNamespace(
        id=course_id,
        title="Item test",
        url_pdf="http://pdf",
        url_pdf_ue=None,
        date_1ere_lecture=first_read,
        date_1ere_lecture_ue=None,
        nb_lectures=nb_lectures,
        nb_lectures_ue=0,
        anki=False,
        qcm_done=False,
        college=["Cardiovasculaire ❤️"],
    )


# ── Le verrou est levé pour un item déclaré ───────────────────────────────────

def test_item_non_declare_et_jamais_lu_reste_sans_score():
    """Non-régression : un item non déclaré garde score = None (état 'à lire')."""
    snap = get_course_mastery(_course())
    assert snap.score is None
    assert snap.level == "à lire"


def test_item_declare_et_jamais_lu_recoit_la_graine_comme_score():
    ks.set_item_state("course-1", "solide")
    snap = get_course_mastery(_course())
    assert snap.score == 70
    assert snap.level == "à consolider"
    assert snap.declared_level == "solide"


def test_les_trois_crans_donnent_trois_niveaux_distincts():
    for level, expected_score, expected_label in [
        ("solide", 70, "à consolider"),
        ("correct", 50, "fragile"),
        ("flou", 30, "critique"),
    ]:
        ks.set_item_state("course-x", level)
        snap = get_course_mastery(_course("course-x"))
        assert snap.score == expected_score
        assert snap.level == expected_label


# ── La fusion avec les preuves réelles ────────────────────────────────────────

def test_une_preuve_reelle_dilue_la_graine_de_moitie():
    import backend.core.reviews.local_store as ls

    ks.set_item_state("course-1", "solide")            # graine 70
    ls.add_study_session(course_id="course-1", activity_types=["révision"], confidence=1)

    course = _course(first_read=datetime.date.today(), nb_lectures=1)
    sessions = ls.get_sessions_by_course().get("course-1", [])
    snap = get_course_mastery(course, sessions=sessions)

    # calculé : 50 - 5 (1 lecture) - 15 (confiance basse) = 30
    # fusion  : 0.5 * 70 + 0.5 * 30 = 50
    assert snap.score == 50


def test_sans_declaration_le_score_calcule_est_inchange():
    """Non-régression : un cours normal n'est pas affecté par le nouveau code."""
    import backend.core.reviews.local_store as ls

    ls.add_study_session(course_id="course-1", activity_types=["révision"], confidence=1)
    course = _course(first_read=datetime.date.today(), nb_lectures=1)
    sessions = ls.get_sessions_by_course().get("course-1", [])
    snap = get_course_mastery(course, sessions=sessions)

    assert snap.score == 30   # 50 - 5 - 15, aucune graine
    assert snap.declared_level is None


def test_anki_sans_revision_ne_penalise_pas_la_maitrise():
    course = _course(first_read=datetime.date.today(), nb_lectures=3)
    snap = get_course_mastery(course)

    assert snap.anki_review_count == 0
    assert snap.score == 56  # lecture progress minus the QCM absence, no Anki penalty


def test_anki_presence_seule_ne_promeut_pas_le_niveau_de_preparation_edn():
    import backend.core.reviews.local_store as ls

    course = _course(first_read=datetime.date(2026, 7, 28), nb_lectures=2)
    course.item_number = "221"
    sessions = [{
        "session_date": "2026-07-28",
        "confidence": 4,
        "difficulty": "facile",
        "qcm_result": None,
    }]

    without_anki = get_course_mastery(course, sessions=sessions)

    course.anki = True
    ls.record_anki_review(
        42,
        99,
        ("221",),
        "good",
        datetime.datetime(2026, 7, 28, 8, 0, tzinfo=datetime.timezone.utc),
        7,
        "review-1",
    )
    with_anki = get_course_mastery(course, sessions=sessions)

    assert without_anki.level == "à consolider"
    assert with_anki.level == without_anki.level
    assert with_anki.qcm_done is False


def test_anki_good_avec_intervalle_alimente_le_score_sans_remplacer_qcm():
    import backend.core.reviews.local_store as ls

    course = _course(first_read=datetime.date(2026, 7, 28), nb_lectures=1)
    course.item_number = "221"
    without_anki = get_course_mastery(course)

    ls.record_anki_review(
        42,
        99,
        ("221",),
        "good",
        datetime.datetime(2026, 7, 28, 8, 0, tzinfo=datetime.timezone.utc),
        7,
        "review-1",
    )
    with_anki = get_course_mastery(course)

    assert without_anki.qcm_done is False
    assert with_anki.anki_review_count == 1
    assert with_anki.anki_knowledge_score >= 70
    assert with_anki.qcm_done is False
    assert with_anki.score > without_anki.score


def test_manual_revision_date_changes_current_mastery():
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today, nb_lectures=1)
    old = [{"session_date": "2026-04-29", "confidence": 4, "difficulty": "facile", "qcm_result": "réussi"}]
    current = [{"session_date": "2026-07-28", "confidence": 4, "difficulty": "facile", "qcm_result": "réussi"}]

    assert get_course_mastery(course, sessions=current).score > get_course_mastery(course, sessions=old).score


def test_good_qcm_and_anki_evidence_stabilize_more_than_a_single_reading():
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today - datetime.timedelta(days=90), nb_lectures=1)
    reading = [{"session_date": "2026-04-29", "confidence": 2, "difficulty": "moyen", "qcm_result": None}]
    repeated = [
        {"session_date": "2026-04-29", "confidence": 2, "difficulty": "moyen", "qcm_result": None},
        {"session_date": "2026-05-29", "confidence": 4, "difficulty": "facile", "qcm_result": "réussi"},
        {"session_date": "2026-07-28", "confidence": 4, "difficulty": "facile", "qcm_result": "réussi"},
    ]

    assert get_course_mastery(course, sessions=repeated).score > get_course_mastery(course, sessions=reading).score


def test_invalid_session_date_falls_back_to_first_read_for_retention_evidence():
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today, nb_lectures=1)
    sessions = [{"session_date": "not-a-date", "confidence": 4, "difficulty": "facile"}]

    evidence = _build_retention_evidence(course, sessions, [])

    assert evidence == [
        Evidence(today, "manual", 0.5),
        Evidence(today, "confidence", 1.0),
    ]


def test_dp_et_kfp_utilisent_les_sources_et_qualites_attendues():
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today, nb_lectures=1)
    sessions = [
        {"session_date": "2026-07-28", "activity_types": "dp", "qcm_result": "réussi"},
        {"session_date": "2026-07-28", "activity_types": ["kfp"], "qcm_result": "raté"},
    ]

    evidence = _build_retention_evidence(course, sessions, [])

    assert evidence == [
        Evidence(today, "dp", 1.0),
        Evidence(today, "kfp", 0.15),
    ]


def test_oic_utilise_le_seuil_de_maitrise_attendu():
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today, nb_lectures=1)
    sessions = [
        {"session_date": "2026-07-28", "activity_types": '["oic"]', "perceived_mastery": 70},
        {"session_date": "2026-07-28", "activity_types": "oic", "perceived_mastery": 69},
    ]

    evidence = _build_retention_evidence(course, sessions, [])

    assert evidence == [
        Evidence(today, "oic", 1.0),
        Evidence(today, "oic", 0.15),
    ]


# ── Couverture OIC exposée dans le snapshot ───────────────────────────────────

def test_le_snapshot_expose_la_couverture_oic_et_le_badge():
    import backend.core.reviews.local_store as ls

    ks.set_item_state("course-1", "solide")
    ls.upsert_lisa_oic("course-1", [
        {"oic_code": "OIC-1", "intitule": "O1", "rang": "A", "rubrique": "Déf", "ordre": 1},
    ])
    oic_id = ls.get_lisa_oic("course-1")[0]["id"]
    ls.save_oic_attempt(oic_id, 90, "[]")

    snap = get_course_mastery(_course())
    assert snap.oic_coverage_a == 1.0
    assert snap.has_rang_a_badge is True
