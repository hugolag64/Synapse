"""Tests unitaires — consolidation (SM-2 self-chaining) et pool de consolidation."""
import datetime
import pytest


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


# ── is_j_cycle_complete ──────────────────────────────────────────────────────

def test_j_cycle_incomplet_si_aucune_tache_done():
    assert ls.is_j_cycle_complete("course-1", "college") is False


def test_j_cycle_incomplet_si_3_sur_4():
    for rt in ("J3", "J7", "J14"):
        ls.mark_done(
            task_id=f"course-1_college_{rt}_2026-01-01",
            course_id="course-1", context="college", review_type=rt,
            theoretical_due_date=datetime.date(2026, 1, 1),
        )
    assert ls.is_j_cycle_complete("course-1", "college") is False


def test_j_cycle_complet_si_4_sur_4():
    for rt in ("J3", "J7", "J14", "J30"):
        ls.mark_done(
            task_id=f"course-1_college_{rt}_2026-01-01",
            course_id="course-1", context="college", review_type=rt,
            theoretical_due_date=datetime.date(2026, 1, 1),
        )
    assert ls.is_j_cycle_complete("course-1", "college") is True


def test_j_cycle_ignore_un_autre_contexte():
    for rt in ("J3", "J7", "J14", "J30"):
        ls.mark_done(
            task_id=f"course-1_ue_{rt}_2026-01-01",
            course_id="course-1", context="ue", review_type=rt,
            theoretical_due_date=datetime.date(2026, 1, 1),
        )
    assert ls.is_j_cycle_complete("course-1", "college") is False


# ── get_last_completed_date ──────────────────────────────────────────────────

def test_get_last_completed_date_absent():
    assert ls.get_last_completed_date("course-1", "college", "J30") is None


def test_get_last_completed_date_present():
    ls.mark_done(
        task_id="course-1_college_J30_2026-01-30",
        course_id="course-1", context="college", review_type="J30",
        theoretical_due_date=datetime.date(2026, 1, 30),
    )
    d = ls.get_last_completed_date("course-1", "college", "J30")
    assert d == datetime.date.today()


# ── bootstrap_consolidation ──────────────────────────────────────────────────

def test_bootstrap_consolidation_cree_une_ligne():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    row = ls.get_last_consolidation_state("course-1", "college")
    assert row is not None
    assert row["status"] == "done"
    assert row["next_interval_days"] == 21
    assert row["completed_at"][:10] == "2026-06-01"


def test_bootstrap_consolidation_idempotent():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=14, at_date=datetime.date(2026, 6, 5),
    )
    row = ls.get_last_consolidation_state("course-1", "college")
    # La 2e tentative n'a rien changé (toujours l'amorçage initial).
    assert row["next_interval_days"] == 21
    assert row["completed_at"][:10] == "2026-06-01"


# ── get_consolidation_due_date ───────────────────────────────────────────────

def test_get_consolidation_due_date_absent():
    assert ls.get_consolidation_due_date("course-1", "college") is None


def test_get_consolidation_due_date_apres_bootstrap():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    due = ls.get_consolidation_due_date("course-1", "college")
    assert due == datetime.date(2026, 6, 22)


# ── mark_consolidation_done : croissance / décroissance type Anki ──────────

def test_mark_consolidation_done_intervalles_fixes_pour_les_2_premieres_repetitions():
    """compute_next_interval (SM-2 standard) utilise des paliers fixes (3j, 7j)
    pour repetition 0 et 1, quelle que soit la confiance (>= 3/5) — la
    croissance liée à l'ease factor ne démarre qu'à partir de la 3e répétition.
    C'est un comportement existant de sm2.py, pas quelque chose à contourner."""
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    i1 = ls.mark_consolidation_done(
        "course-1", "college", datetime.date(2026, 6, 22), confidence=5,
    )
    assert i1 == 3

    due2 = datetime.date(2026, 6, 22) + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due2, confidence=5)
    assert i2 == 7


def test_mark_consolidation_done_croit_a_partir_de_la_3e_repetition():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    due = datetime.date(2026, 6, 22)
    i1 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i2)
    i3 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    assert i3 > i2  # l'ease factor entre enfin en jeu -> croissance type Anki


def test_mark_consolidation_done_echec_revient_a_un_intervalle_court():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    due = datetime.date(2026, 6, 22)
    i1 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i2)
    i3 = ls.mark_consolidation_done("course-1", "college", due, confidence=1)  # échec
    assert i3 <= 3
    assert i3 < i2


def test_mark_consolidation_done_progresse_sur_plusieurs_occurrences():
    """Le repetition_count et l'ease factor doivent survivre d'une occurrence
    à l'autre, malgré des task_id différents à chaque fois (due date différente)."""
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    i1 = ls.mark_consolidation_done(
        "course-1", "college", datetime.date(2026, 6, 22), confidence=5,
    )
    row1 = ls.get_last_consolidation_state("course-1", "college")
    assert row1["repetition_count"] == 1

    due2 = datetime.date(2026, 6, 22) + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done(
        "course-1", "college", due2, confidence=5,
    )
    row2 = ls.get_last_consolidation_state("course-1", "college")
    assert row2["repetition_count"] == 2
    assert i2 >= i1  # confiance haute répétée -> l'intervalle continue de croître ou se stabilise


# ── ReviewTask accepts review_type="consolidation" + semestre ─────────────────

def test_review_task_accepte_consolidation_et_semestre():
    from datetime import date
    from backend.core.reviews.models import ReviewTask

    t = ReviewTask(
        id="x", course_id="c1", course_title="Titre",
        theoretical_due_date=date(2026, 6, 1), due_date=date(2026, 6, 1),
        review_type="consolidation", semestre="Semestre 4",
    )
    assert t.review_type == "consolidation"
    assert t.semestre == "Semestre 4"


# ── get_due_consolidation_tasks ──────────────────────────────────────────────────

from unittest.mock import patch, MagicMock
from datetime import date
from backend.core.notion.models import Cours


def _mock_cours(id, title, college, semestre=None, date_1ere_lecture=None,
                 item_number="1", nb_lectures=0):
    c = MagicMock(spec=Cours)
    c.id = id
    c.title = title
    c.item_number = item_number
    c.college = college
    c.semestre = semestre
    c.date_1ere_lecture = date_1ere_lecture
    c.date_1ere_lecture_ue = None
    c.nb_lectures = nb_lectures
    c.nb_lectures_ue = 0
    c.url_pdf = None
    c.url_pdf_ue = None
    c.agregation_fiche_edn = None
    c.anki = False
    c.qcm_done = False
    c.course_status = "À lire"
    return c


@patch('backend.state.store.data_store')
def test_pool_inclut_item_declare_sans_lecture(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ks.set_item_state("course-1", "flou", context="college", source="triage")
    c = _mock_cours("course-1", "Cours test", ["Cardiovasculaire ❤️"], date_1ere_lecture=None)
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(
        context="college", today=date.today() + datetime.timedelta(days=1),
    )
    assert len(tasks) == 1
    assert tasks[0].review_type == "consolidation"
    assert tasks[0].course_id == "course-1"


@patch('backend.state.store.data_store')
def test_pool_exclut_item_en_cours_de_cycle_j(mock_data_store):
    from backend.core.reviews import consolidation

    ls.mark_done(
        task_id="course-2_college_J3_2026-01-01",
        course_id="course-2", context="college", review_type="J3",
        theoretical_due_date=date(2026, 1, 1),
    )
    c = _mock_cours(
        "course-2", "Cours en cycle", ["Cardiovasculaire ❤️"],
        date_1ere_lecture=date(2025, 12, 1), nb_lectures=1,
    )
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(context="college")
    assert tasks == []


@patch('backend.state.store.data_store')
def test_pool_inclut_item_ayant_fini_j30(mock_data_store):
    from backend.core.reviews import consolidation

    for rt in ("J3", "J7", "J14", "J30"):
        ls.mark_done(
            task_id=f"course-3_college_{rt}_2026-01-01",
            course_id="course-3", context="college", review_type=rt,
            theoretical_due_date=date(2026, 1, 1),
        )
    c = _mock_cours(
        "course-3", "Cours fini", ["Pneumologie 🫁"],
        date_1ere_lecture=date(2025, 12, 1), nb_lectures=4,
    )
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(
        context="college", today=date.today() + datetime.timedelta(days=40),
    )
    assert len(tasks) == 1
    assert tasks[0].course_id == "course-3"


@patch('backend.state.store.data_store')
def test_pool_exclut_item_non_demarre(mock_data_store):
    from backend.core.reviews import consolidation

    c = _mock_cours("course-4", "Jamais touché", ["Dermatologie 🧴"])
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(context="college")
    assert tasks == []


@patch('backend.state.store.data_store')
def test_pool_exclut_item_pas_encore_du(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ks.set_item_state("course-5", "solide", context="college", source="triage")
    c = _mock_cours("course-5", "Cours solide", ["Nutrition 🍔"])
    mock_data_store.cours = [c]

    # Amorcé aujourd'hui avec un intervalle initial de 30j (solide) -> pas dû aujourd'hui.
    tasks = consolidation.get_due_consolidation_tasks(context="college", today=date.today())
    assert tasks == []
