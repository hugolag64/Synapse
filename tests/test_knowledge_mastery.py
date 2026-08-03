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
    assert snap.retention_stability_days == 0.0
    assert snap.retention_last_evidence is None


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


def test_mastery_supports_clean_checkout_without_anki_evidence_api(monkeypatch):
    import backend.core.reviews.local_store as ls

    course = _course(first_read=datetime.date.today(), nb_lectures=1)
    course.item_number = "221"
    monkeypatch.delattr(ls, "get_anki_review_evidence", raising=False)

    snapshot = get_course_mastery(course)

    assert snapshot.anki_review_count == 0
    assert snapshot.score is not None


def test_anki_presence_seule_ne_promeut_pas_le_niveau_de_preparation_edn():
    import backend.core.reviews.local_store as ls

    if not callable(getattr(ls, "record_anki_review", None)):
        pytest.skip("AnkiConnect evidence store unavailable in this checkout")

    today = datetime.date.today()
    course = _course(first_read=today, nb_lectures=2)
    course.item_number = "221"
    sessions = [{
        "session_date": today.isoformat(),
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
        datetime.datetime.now(datetime.timezone.utc),
        7,
        "review-1",
    )
    with_anki = get_course_mastery(course, sessions=sessions)

    assert without_anki.level == "à consolider"
    assert with_anki.level == without_anki.level
    assert with_anki.qcm_done is False


def test_anki_good_avec_intervalle_alimente_le_score_sans_remplacer_qcm():
    import backend.core.reviews.local_store as ls

    if not callable(getattr(ls, "record_anki_review", None)):
        pytest.skip("AnkiConnect evidence store unavailable in this checkout")

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


def test_first_read_without_study_session_is_dated_retention_evidence():
    today = datetime.date.today()
    course = _course(first_read=today - datetime.timedelta(days=90), nb_lectures=1)

    snapshot = get_course_mastery(course)

    assert snapshot.retention_stability_days > 0.0
    assert snapshot.retention_last_evidence == course.date_1ere_lecture
    assert snapshot.score < 45


def test_canonical_qcm_evidence_improves_retention_stability_and_score():
    import backend.core.reviews.local_store as ls

    today = datetime.date.today()
    course = _course(first_read=today - datetime.timedelta(days=90), nb_lectures=1)
    baseline = get_course_mastery(course)
    ls.add_qcm_session_full(
        platform="EDNpro",
        session_date=today.isoformat(),
        course_id=course.id,
        session_type="DP",
        score_raw="18/20",
        score_percent=90,
    )

    refreshed = get_course_mastery(course)

    assert refreshed.retention_stability_days > baseline.retention_stability_days
    assert refreshed.score > baseline.score
    assert refreshed.retention_last_evidence == today


def test_canonical_oic_attempt_improves_retention_stability_and_score():
    import backend.core.reviews.local_store as ls

    today = datetime.date.today()
    course = _course(first_read=today - datetime.timedelta(days=90), nb_lectures=1)
    baseline = get_course_mastery(course)
    ls.upsert_lisa_oic(course.id, [
        {"oic_code": "OIC-1", "intitule": "O1", "rang": "A", "rubrique": "Def", "ordre": 1},
    ])
    oic_id = ls.get_lisa_oic(course.id)[0]["id"]
    attempt_id = ls.save_oic_attempt(oic_id, 90, "[]")
    with ls._conn() as con:
        con.execute(
            "UPDATE oic_attempts SET attempted_at = ? WHERE id = ?",
            (today.isoformat(), attempt_id),
        )

    refreshed = get_course_mastery(course)

    assert refreshed.retention_stability_days > baseline.retention_stability_days
    assert refreshed.score > baseline.score
    assert refreshed.retention_last_evidence == today


def test_canonical_qcm_does_not_duplicate_study_session_evidence():
    import backend.core.reviews.local_store as ls

    today = datetime.date.today()
    course = _course(first_read=today - datetime.timedelta(days=90), nb_lectures=1)
    ls.add_study_session(
        course_id=course.id,
        course_title=course.title,
        activity_types=["qcm"],
        qcm_result="r\u00e9ussi",
    )
    sessions = ls.get_sessions_by_course()[course.id]
    ls.add_qcm_session_full(
        platform="EDNpro",
        session_date=today.isoformat(),
        course_id=course.id,
        session_type="QCM",
        score_raw="18/20",
        score_percent=90,
    )

    snapshot = get_course_mastery(course, sessions=sessions)

    assert snapshot.retention_stability_days == 63.0


def test_snapshot_exposes_retention_stability_and_last_evidence_for_started_items():
    today = datetime.date(2026, 7, 28)
    course = _course(first_read=today - datetime.timedelta(days=90), nb_lectures=1)
    sessions = [
        {"session_date": "2026-04-29", "confidence": 2, "difficulty": "moyen", "qcm_result": None},
        {"session_date": "2026-06-29", "activity_types": ["qcm"], "confidence": 4, "difficulty": "facile", "qcm_result": "réussi"},
        {"session_date": "2026-07-28", "activity_types": ["oic"], "confidence": 4, "difficulty": "facile", "qcm_result": None, "perceived_mastery": 80},
    ]

    snap = get_course_mastery(course, sessions=sessions)

    assert snap.retention_stability_days > 0.0
    assert snap.retention_last_evidence == today


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


def test_lecture_ue_sans_session_alimente_la_retention():
    first_read = datetime.date(2026, 4, 29)
    course = _course(first_read=None, nb_lectures=1)
    course.url_pdf = None
    course.url_pdf_ue = "http://ue-pdf"
    course.date_1ere_lecture_ue = first_read
    course.nb_lectures_ue = 1

    evidence = _build_retention_evidence(course, "ue", [], [])

    assert evidence == [Evidence(first_read, "lecture", 0.5)]


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


def test_same_day_qcm_results_contribute_one_retention_evidence():
    import backend.core.reviews.local_store as ls

    today = datetime.date.today().isoformat()
    for score in (20, 95):
        ls.add_qcm_session_full(
            platform="Synapse", session_date=today, course_id="course-1",
            session_type="QCM", score_percent=score, total_questions=20,
        )

    evidence = _build_retention_evidence(_course(), "college", [], [])

    assert [row for row in evidence if row.source == "qcm"] == [Evidence(datetime.date.today(), "qcm", 0.2)]


def test_recent_low_qcm_prioritizes_error_correction():
    import backend.core.reviews.local_store as ls

    ls.add_qcm_session_full(
        platform="Synapse", session_date=datetime.date.today().isoformat(),
        course_id="course-1", session_type="QCM", score_percent=25,
        total_questions=20,
    )

    snapshot = get_course_mastery(
        _course(first_read=datetime.date.today(), nb_lectures=3), qcm_done_local=True,
    )

    assert "QCM récent faible (25% sur 20 questions)" in snapshot.reasons
    assert snapshot.next_action == "Corriger les erreurs"
