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

def test_mark_consolidation_done_croit_des_la_premiere_repetition():
    """La chaîne 'consolidation' amorce repetition_count à 2 (voir
    bootstrap_consolidation), précisément pour éviter les paliers fixes
    (3j / 7j) que compute_next_interval réserve à repetition 0 et 1 pour
    le cycle J3→J30 qui démarre "à froid". Ici, dès la première vraie
    validation, l'intervalle croît via l'ease factor à partir de
    l'intervalle mastery-seedé (initial_interval_days), au lieu de
    retomber à un palier fixe qui écraserait cet intervalle.

    Calcul (voir sm2.compute_next_interval, repetition=2 -> branche else) :
      i1 = round(21 * 2.6) = 55
      i2 = round(55 * 2.7) = 148
    """
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    i1 = ls.mark_consolidation_done(
        "course-1", "college", datetime.date(2026, 6, 22), confidence=5,
    )
    assert i1 == 55

    due2 = datetime.date(2026, 6, 22) + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due2, confidence=5)
    assert i2 == 148


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


def test_mark_consolidation_done_ne_discarde_pas_intervalle_maitrise():
    """Régression : bootstrap_consolidation seed repetition_count=2 (pas 0), pour
    que la toute première validation utilise directement la croissance SM-2
    (current_interval_days * new_ef) plutôt que les paliers fixes 3j/7j du
    cycle J. Avant le fix, un cours amorcé "maîtrisé" (30j) retombait à un
    intervalle fixe de 3 jours dès la première validation.

    Calcul attendu (voir sm2.compute_next_interval) :
      grade = confidence(5) - 1 = 4 -> réussite
      new_ef = min-clamped(2.5 + 0.1 - (4-4)*0.08) = 2.6
      repetition seedé à 2 -> branche else : round(30 * 2.6) = 78
    """
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=30, at_date=datetime.date(2026, 6, 1),
    )
    due = datetime.date(2026, 6, 1) + datetime.timedelta(days=30)
    i1 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    assert i1 == 78  # PAS 3 (l'ancien bug figeait le premier intervalle a 3j)

    row1 = ls.get_last_consolidation_state("course-1", "college")
    assert row1["repetition_count"] == 3
    assert row1["easiness_factor"] == 2.6

    # Deuxième validation : la croissance continue (pas de retour aux paliers
    # fixes 3j/7j), avec repetition qui continue de s'incrémenter.
    due2 = due + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due2, confidence=5)
    assert i2 == 211  # round(78 * 2.7)
    row2 = ls.get_last_consolidation_state("course-1", "college")
    assert row2["repetition_count"] == 4


def test_mark_consolidation_done_progresse_sur_plusieurs_occurrences():
    """Le repetition_count et l'ease factor doivent survivre d'une occurrence
    à l'autre, malgré des task_id différents à chaque fois (due date différente).
    repetition_count part de 2 (seedé par bootstrap_consolidation), donc la
    première validation l'amène à 3, la deuxième à 4."""
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    i1 = ls.mark_consolidation_done(
        "course-1", "college", datetime.date(2026, 6, 22), confidence=5,
    )
    row1 = ls.get_last_consolidation_state("course-1", "college")
    assert row1["repetition_count"] == 3

    due2 = datetime.date(2026, 6, 22) + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done(
        "course-1", "college", due2, confidence=5,
    )
    row2 = ls.get_last_consolidation_state("course-1", "college")
    assert row2["repetition_count"] == 4
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
                 item_number="1", nb_lectures=0, url_pdf="dummy.pdf"):
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
    c.url_pdf = url_pdf
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
        context="college", today=date.today() + datetime.timedelta(days=15),
    )
    assert len(tasks) == 1
    assert tasks[0].review_type == "consolidation"
    assert tasks[0].course_id == "course-1"


@patch('backend.state.store.data_store')
def test_pool_item_declare_il_y_a_longtemps_est_immediatement_du(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ks.set_item_state("course-old", "flou", context="college", source="triage")
    # set_item_state always stamps declared_at = today(); backdate it directly
    # to simulate a college validated 60 days before this pool-builder ever runs.
    with ls._conn() as con:
        con.execute(
            "UPDATE item_state SET declared_at = ? WHERE course_id = ? AND context = ?",
            ((date.today() - datetime.timedelta(days=60)).isoformat(), "course-old", "college"),
        )
    c = _mock_cours("course-old", "Cours ancien", ["Cardiovasculaire ❤️"], date_1ere_lecture=None)
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(context="college")
    assert len(tasks) == 1
    assert tasks[0].course_id == "course-old"


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


# ── select_daily : diversité + pondération semestre/niveau ─────────────────

def _task(course_id, college, days_overdue, mastery_level="fragile", semestre="Semestre 4"):
    from backend.core.reviews.models import ReviewTask
    return ReviewTask(
        id=f"{course_id}_task", course_id=course_id, course_title=course_id,
        college=[college],
        theoretical_due_date=date.today(), due_date=date.today(),
        review_type="consolidation", days_overdue=days_overdue,
        mastery_level=mastery_level, semestre=semestre,
    )


def test_select_daily_respecte_le_plafond_par_college():
    from backend.core.reviews import consolidation

    tasks = [
        _task("c1", "Cardiovasculaire ❤️", 10),
        _task("c2", "Cardiovasculaire ❤️", 9),
        _task("c3", "Cardiovasculaire ❤️", 8),
        _task("c4", "Pneumologie 🫁", 5),
    ]
    selected, skipped = consolidation.select_daily(tasks, max_items=6, max_per_college=2)

    cardio_selected = [t for t in selected if t.college == ["Cardiovasculaire ❤️"]]
    assert len(cardio_selected) == 2
    assert len(skipped) == 1
    assert skipped[0].course_id == "c3"  # le moins prioritaire des 3 cardio


def test_select_daily_respecte_max_items():
    from backend.core.reviews import consolidation

    tasks = [_task(f"c{i}", f"College {i}", 10 - i) for i in range(5)]
    selected, skipped = consolidation.select_daily(tasks, max_items=3, max_per_college=5)
    assert len(selected) == 3
    assert len(skipped) == 2


@patch('backend.state.store.data_store')
def test_select_daily_priorise_semestre_ancien(mock_data_store):
    from backend.core.reviews import consolidation

    mock_data_store.preferences = {"semestre_actuel": "Semestre 7"}
    old = _task("old", "A", days_overdue=5, mastery_level="à consolider", semestre="Semestre 3")
    recent = _task("recent", "B", days_overdue=5, mastery_level="à consolider", semestre="Semestre 7")

    selected, _ = consolidation.select_daily([recent, old], max_items=1, max_per_college=5)
    assert selected[0].course_id == "old"


@patch('backend.state.store.data_store')
def test_select_daily_priorise_niveau_critique(mock_data_store):
    from backend.core.reviews import consolidation

    mock_data_store.preferences = {"semestre_actuel": "Semestre 7"}
    critique = _task("crit", "A", days_overdue=5, mastery_level="critique", semestre="Semestre 7")
    maitrise = _task("mait", "B", days_overdue=5, mastery_level="maîtrisé", semestre="Semestre 7")

    selected, _ = consolidation.select_daily([maitrise, critique], max_items=1, max_per_college=5)
    assert selected[0].course_id == "crit"


# ── get_or_bootstrap_task (ajout manuel d'un cours) ─────────────────────────

@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_cree_la_chaine_si_absente(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ks.set_item_state("course-6", "correct", context="college", source="triage")
    c = _mock_cours("course-6", "Cours ajouté", ["Infectiologie 🦠"])
    mock_data_store.cours = [c]

    task = consolidation.get_or_bootstrap_task("course-6", context="college")
    assert task is not None
    assert task.course_id == "course-6"
    assert task.review_type == "consolidation"
    assert ls.get_last_consolidation_state("course-6", "college") is not None


@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_reutilise_chaine_existante(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ls.bootstrap_consolidation(
        "course-7", "college", "Déjà amorcé", "1",
        initial_interval_days=21, at_date=date(2026, 1, 1),
    )
    ks.set_item_state("course-7", "correct", context="college", source="triage")
    c = _mock_cours("course-7", "Déjà amorcé", ["Neurologie 🧠"])
    mock_data_store.cours = [c]

    task = consolidation.get_or_bootstrap_task("course-7", context="college")
    assert task.theoretical_due_date == date(2026, 1, 22)


@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_none_si_cours_introuvable(mock_data_store):
    from backend.core.reviews import consolidation

    mock_data_store.cours = []
    assert consolidation.get_or_bootstrap_task("nope", context="college") is None


@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_none_si_jamais_demarre(mock_data_store):
    from backend.core.reviews import consolidation

    c = _mock_cours("course-8", "Jamais commencé", ["Nutrition 🍔"])
    mock_data_store.cours = [c]
    assert consolidation.get_or_bootstrap_task("course-8", context="college") is None


# ── PlanningService.plan_consolidation ───────────────────────────────────────

@patch('backend.state.store.data_store')
def test_plan_consolidation_retourne_selection_et_surplus(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.planning.service import planning_service

    mock_data_store.preferences = {"semestre_actuel": "Semestre 7"}
    ks.set_item_state("course-9", "flou", context="college", source="triage")
    # Backdate declared_at to make the item immediately due for consolidation
    with ls._conn() as con:
        con.execute(
            "UPDATE item_state SET declared_at = ? WHERE course_id = ? AND context = ?",
            ((date.today() - datetime.timedelta(days=60)).isoformat(), "course-9", "college"),
        )
    c = _mock_cours("course-9", "Cours plan", ["Cardiovasculaire ❤️"])
    mock_data_store.cours = [c]

    selected, skipped = planning_service.plan_consolidation(
        max_items=6, max_per_college=2,
    )
    assert len(selected) == 1
    assert skipped == []


# ── complete_consolidation_task ──────────────────────────────────────────────

def _make_consolidation_task(
    course_id="course-1", context="college", due=datetime.date(2026, 1, 1),
):
    from backend.core.reviews.models import ReviewTask
    return ReviewTask(
        id=f"{course_id}_{context}_consolidation_{due.isoformat()}",
        course_id=course_id,
        course_title="Cardiopathies",
        item_number="234",
        college=["Cardiologie"],
        context=context,
        theoretical_due_date=due,
        due_date=due,
        review_type="consolidation",
        status="todo",
    )


def test_complete_consolidation_task_avance_la_chaine_sm2():
    from backend.core.reviews.consolidation import complete_consolidation_task
    task = _make_consolidation_task()
    complete_consolidation_task(task, confidence=4, difficulty="facile")
    state = ls.get_last_consolidation_state("course-1", "college")
    assert state is not None
    assert state["repetition_count"] == 1


def test_complete_consolidation_task_logue_une_session():
    from backend.core.reviews.consolidation import complete_consolidation_task
    task = _make_consolidation_task()
    complete_consolidation_task(
        task, activity_types=["révision", "qcm"], duration_minutes=25,
        confidence=4, difficulty="facile", qcm_result="réussi",
    )
    sessions = ls.get_recent_study_sessions(limit=5)
    assert len(sessions) == 1
    assert sessions[0]["course_id"] == "course-1"
    assert sessions[0]["duration_minutes"] == 25
    assert sessions[0]["qcm_result"] == "réussi"


def test_complete_consolidation_task_defaut_confiance_3_si_absente():
    from backend.core.reviews.consolidation import complete_consolidation_task
    task = _make_consolidation_task()
    complete_consolidation_task(task)  # aucune confidence fournie
    state = ls.get_last_consolidation_state("course-1", "college")
    assert state["repetition_count"] == 1
    sessions = ls.get_recent_study_sessions(limit=5)
    assert sessions[0]["activity_types"] == '["révision"]'
