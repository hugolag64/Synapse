"""
consolidation.py — Synapse
---------------------------
Flux de consolidation long terme : items dont le cycle J3-J30 est terminé,
ou qui ont un niveau déclaré (flou/correct/solide) sans jamais avoir été
suivis dans l'app (lus avant l'existence de Synapse).

Utilise le moteur SM-2 existant, étendu avec un review_type "consolidation"
auto-chaîné (backend.core.reviews.local_store) : l'intervalle s'étire
automatiquement avec la maîtrise plutôt que de suivre un cycle fixe.

Pas d'I/O réseau — data_store.cours est déjà chargé en mémoire.
"""
from __future__ import annotations

import datetime
from typing import Optional

from backend.core.reviews import local_store
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.mastery import get_course_mastery
from backend.core.evaluation.models import EvaluationInput
from backend.core.evaluation.service import record_evaluation
from backend.core.reviews.reentry import filter_active_review_tasks, get_study_resume_date

# Intervalle initial (jours) selon le niveau de maîtrise au moment de l'amorçage.
INITIAL_INTERVAL_BY_LEVEL: dict[str, int] = {
    "critique":          14,
    "fragile":           18,
    "en construction":   18,
    "à consolider":      24,
    "à entraîner":       24,
    "maîtrisé":          30,
}
DEFAULT_INITIAL_INTERVAL = 21

# Poids semestre : +0.15 par semestre d'écart avec la préférence semestre_actuel.
SEMESTER_GAP_WEIGHT = 0.15

# Poids niveau (multiplicatif — distinct du barème additif de reviews/service.py,
# adapté pour la formule jours_de_retard * poids_semestre * poids_niveau).
MASTERY_WEIGHT: dict[str, float] = {
    "critique":         2.5,
    "fragile":          2.0,
    "en construction":  1.6,
    "à consolider":     1.3,
    "à entraîner":      1.1,
    "maîtrisé":         1.0,
}

MAX_PER_COLLEGE_PER_DAY = 2
MAX_ITEMS_PER_DAY = 6

_HIDDEN_STATUSES = {"done", "ignored", "cancelled"}


def _due_consolidation_task_for_course(
    course,
    context: str,
    today: datetime.date,
    sessions_map: dict,
    postpone_map: dict,
    qcm_done_set: set,
    historical_ids: set,
    gate_map: dict,
    horizon_days: int = 0,
) -> Optional[ReviewTask]:
    """Build one due consolidation task without scanning sibling courses."""
    from backend.core.reviews.service import review_service

    date_ref = course.date_1ere_lecture if context == "college" else course.date_1ere_lecture_ue
    mastery = review_service._get_mastery_cached(
        course,
        context,
        sessions_map.get(course.id, []),
        postpone_map.get(course.id, 0),
        course.id in qcm_done_set,
    )
    if mastery.score is None:
        return None
    if (
        date_ref is not None
        and course.id not in historical_ids
        and not local_store.is_j_cycle_complete(course.id, context)
    ):
        return None

    due = local_store.get_consolidation_due_date(course.id, context)
    if due is None:
        bootstrap_date = _bootstrap_at_date(course, context, date_ref, today)
        initial = INITIAL_INTERVAL_BY_LEVEL.get(mastery.level, DEFAULT_INITIAL_INTERVAL)
        local_store.bootstrap_consolidation(
            course.id, context, course.title, course.item_number or "", initial, bootstrap_date,
        )
        due = local_store.get_consolidation_due_date(course.id, context)
        if due is None:
            return None

    not_before = gate_map.get(course.id)
    if not_before and today < not_before:
        return None
    effective_due = max(due, not_before) if not_before else due
    task_id = local_store.make_task_id(course.id, context, "consolidation", effective_due)
    row = local_store.get_history(task_id)
    status = row["status"] if row else "todo"
    if status in _HIDDEN_STATUSES:
        return None
    effective = (
        datetime.date.fromisoformat(row["postponed_to"])
        if status == "postponed" and row["postponed_to"]
        else effective_due
    )
    if effective > today + datetime.timedelta(days=max(0, horizon_days)):
        return None

    return ReviewTask(
        id=task_id,
        course_id=course.id,
        course_title=course.title,
        item_number=course.item_number or None,
        college=list(course.college),
        context=context,
        url_pdf=course.url_pdf,
        url_pdf_ue=course.url_pdf_ue,
        agregation_fiche_edn=course.agregation_fiche_edn,
        theoretical_due_date=effective_due,
        due_date=effective,
        review_type="consolidation",
        status=status,
        nb_lectures=course.nb_lectures if context == "college" else course.nb_lectures_ue,
        anki=getattr(course, "anki", False),
        qcm_done=getattr(course, "qcm_done", False),
        course_status=getattr(course, "course_status", "À lire"),
        days_overdue=max((today - effective).days, 0),
        mastery_score=mastery.score,
        mastery_level=mastery.level,
        mastery_reasons=mastery.reasons,
        semestre=course.semestre,
    )


def _bootstrap_at_date(
    course, context: str, date_ref: Optional[datetime.date], today: datetime.date
) -> datetime.date:
    """Date d'ancrage pour l'amorçage : date de déclaration (item pré-app) ou
    date de complétion du J30 (item ayant fini son cycle)."""
    if date_ref is None:
        from backend.core.knowledge import store as ks
        item_state = ks.get_item_state(course.id, context)
        return item_state.declared_at if item_state else today
    return local_store.get_last_completed_date(course.id, context, "J30") or today


def get_due_consolidation_tasks(
    context: str = "college",
    today: Optional[datetime.date] = None,
    horizon_days: int = 0,
) -> list[ReviewTask]:
    """
    Construit les ReviewTask virtuelles 'consolidation' dues aujourd'hui ou
    en retard, pour tous les cours éligibles. Amorce (bootstrap) au passage
    les items nouvellement éligibles qui n'ont pas encore de chaîne SM-2.
    """
    from backend.state.store import data_store
    from backend.core.reviews.service import review_service
    from backend.core.reviews.local_store import (
        get_sessions_by_course, get_postpone_counts, get_qcm_done_course_ids,
    )
    from backend.core.knowledge.service import get_historically_completed_course_ids

    today = today or datetime.date.today()
    tasks: list[ReviewTask] = []

    # Précalculées une seule fois (au lieu d'une requête SQLite par cours) et
    # passées à _get_mastery_cached avec les mêmes arguments que generate_reviews,
    # pour rester cohérent avec le cache déjà chaud si celui-ci a tourné avant.
    sessions_map = get_sessions_by_course()
    postpone_map = get_postpone_counts()
    qcm_done_set = get_qcm_done_course_ids()
    historical_ids = get_historically_completed_course_ids(data_store.cours, context)
    gate_map = local_store.get_consolidation_not_before_map(context)

    for c in data_store.cours:
        task = _due_consolidation_task_for_course(
            c, context, today, sessions_map, postpone_map, qcm_done_set,
            historical_ids, gate_map, horizon_days,
        )
        if task is not None:
            tasks.append(task)

    active_tasks = filter_active_review_tasks(
        tasks,
        get_study_resume_date(data_store.preferences),
    )
    return active_tasks


def get_due_consolidation_task_for_course(
    course_id: str,
    context: str = "college",
    today: Optional[datetime.date] = None,
) -> Optional[ReviewTask]:
    """Return one due consolidation task without generating the daily batch."""
    from backend.state.store import data_store
    from backend.core.knowledge.service import get_historically_completed_course_ids
    from backend.core.reviews.local_store import (
        get_qcm_done_course_ids, get_sessions_by_course, get_postpone_counts,
    )

    course = next((candidate for candidate in data_store.cours if candidate.id == course_id), None)
    if course is None:
        return None
    today = today or datetime.date.today()
    return _due_consolidation_task_for_course(
        course,
        context,
        today,
        get_sessions_by_course(),
        get_postpone_counts(),
        get_qcm_done_course_ids(),
        get_historically_completed_course_ids(data_store.cours, context),
        local_store.get_consolidation_not_before_map(context),
    )


def _semestre_num(semestre: Optional[str]) -> Optional[int]:
    if not semestre:
        return None
    digits = "".join(ch for ch in semestre if ch.isdigit())
    return int(digits) if digits else None


def _priority_score(task: ReviewTask) -> float:
    from backend.state.store import data_store

    actuel = _semestre_num(data_store.preferences.get("semestre_actuel")) or 7
    item_sem = _semestre_num(task.semestre)
    gap = max(0, actuel - item_sem) if item_sem is not None else 0
    poids_semestre = 1 + gap * SEMESTER_GAP_WEIGHT
    poids_niveau = MASTERY_WEIGHT.get(task.mastery_level or "", 1.0)
    return max(task.days_overdue, 1) * poids_semestre * poids_niveau


def select_daily(
    tasks: list[ReviewTask],
    max_items: int = MAX_ITEMS_PER_DAY,
    max_per_college: int = MAX_PER_COLLEGE_PER_DAY,
) -> tuple[list[ReviewTask], list[ReviewTask]]:
    """
    Trie les tâches par priorité (ancienneté x semestre x niveau) et
    sélectionne les N premières en plafonnant le nombre par collège, pour
    éviter qu'une seule journée soit monopolisée par un seul collège.
    Le surplus est retourné dans `skipped` (repasse le(s) jour(s) suivant(s),
    sa date d'échéance SM-2 ne changeant pas tant qu'il n'est pas validé).
    """
    scored = sorted(tasks, key=_priority_score, reverse=True)
    selected: list[ReviewTask] = []
    skipped: list[ReviewTask] = []
    college_count: dict[str, int] = {}

    for t in scored:
        primary = t.college[0] if t.college else "?"
        if len(selected) < max_items and college_count.get(primary, 0) < max_per_college:
            selected.append(t)
            college_count[primary] = college_count.get(primary, 0) + 1
        else:
            skipped.append(t)

    return selected, skipped


def get_or_bootstrap_task(course_id: str, context: str = "college") -> Optional[ReviewTask]:
    """
    Retourne la ReviewTask 'consolidation' d'un cours choisi manuellement
    ("j'ai travaillé ce cours aujourd'hui"), en amorçant sa chaîne SM-2 si
    elle n'existe pas encore. due_date est forcée à aujourd'hui — l'utilisateur
    choisit de le traiter maintenant, indépendamment de sa vraie échéance.
    Retourne None si le cours est introuvable ou jamais démarré (mastery.score is None).
    """
    from backend.state.store import data_store

    course = next((c for c in data_store.cours if c.id == course_id), None)
    if course is None:
        return None

    mastery = get_course_mastery(course, context=context)
    if mastery.score is None:
        return None

    today = datetime.date.today()
    due = local_store.get_consolidation_due_date(course.id, context)
    if due is None:
        date_ref = course.date_1ere_lecture if context == "college" else course.date_1ere_lecture_ue
        at_date = _bootstrap_at_date(course, context, date_ref, today)
        initial = INITIAL_INTERVAL_BY_LEVEL.get(mastery.level, DEFAULT_INITIAL_INTERVAL)
        local_store.bootstrap_consolidation(
            course.id, context, course.title, course.item_number or "", initial, at_date,
        )
        due = local_store.get_consolidation_due_date(course.id, context) or today

    task_id = local_store.make_task_id(course.id, context, "consolidation", due)
    return ReviewTask(
        id=task_id,
        course_id=course.id,
        course_title=course.title,
        item_number=course.item_number or None,
        college=list(course.college),
        context=context,
        url_pdf=course.url_pdf,
        url_pdf_ue=course.url_pdf_ue,
        agregation_fiche_edn=course.agregation_fiche_edn,
        theoretical_due_date=due,
        due_date=today,
        review_type="consolidation",
        status="todo",
        nb_lectures=course.nb_lectures if context == "college" else course.nb_lectures_ue,
        anki=getattr(course, "anki", False),
        qcm_done=getattr(course, "qcm_done", False),
        course_status=getattr(course, "course_status", "À lire"),
        days_overdue=0,
        mastery_score=mastery.score,
        mastery_level=mastery.level,
        mastery_reasons=mastery.reasons,
        semestre=course.semestre,
    )


def complete_consolidation_task(
    task: ReviewTask,
    activity_types: Optional[list] = None,
    duration_minutes: Optional[int] = None,
    confidence: Optional[int] = None,
    difficulty: Optional[str] = None,
    qcm_result: Optional[str] = None,
    weak_category: Optional[str] = None,
    weak_detail: Optional[str] = None,
) -> None:
    """
    Valide une occurrence 'consolidation' : avance la chaîne SM-2 et logue la
    séance de travail associée. Point d'entrée unique utilisé par le dashboard
    et par planning.py — évite de dupliquer ces deux appels local_store à deux
    endroits.
    """
    local_store.mark_consolidation_done(
        course_id=task.course_id,
        context=task.context,
        theoretical_due_date=task.theoretical_due_date,
        course_title=task.course_title,
        item_number=task.item_number or "",
        confidence=confidence or 3,
        difficulty=difficulty,
    )
    record_evaluation(EvaluationInput(
        source="auto_eval",
        course_id=task.course_id,
        course_title=task.course_title,
        item_number=task.item_number or "",
        context=task.context,
        activity_types=tuple(activity_types or ["révision"]),
        duration_minutes=duration_minutes,
        confidence=confidence,
        difficulty=difficulty,
        qcm_result=qcm_result,
        error_types=(weak_category,) if weak_category else (),
        detail=weak_detail,
    ))
