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
) -> list[ReviewTask]:
    """
    Construit les ReviewTask virtuelles 'consolidation' dues aujourd'hui ou
    en retard, pour tous les cours éligibles. Amorce (bootstrap) au passage
    les items nouvellement éligibles qui n'ont pas encore de chaîne SM-2.
    """
    from backend.state.store import data_store

    today = today or datetime.date.today()
    tasks: list[ReviewTask] = []

    for c in data_store.cours:
        date_ref = c.date_1ere_lecture if context == "college" else c.date_1ere_lecture_ue

        mastery = get_course_mastery(c, context=context)
        if mastery.score is None:
            continue

        if date_ref is not None and not local_store.is_j_cycle_complete(c.id, context):
            continue  # encore en cours de cycle J3-J30 normal

        due = local_store.get_consolidation_due_date(c.id, context)
        if due is None:
            bootstrap_date = _bootstrap_at_date(c, context, date_ref, today)
            initial = INITIAL_INTERVAL_BY_LEVEL.get(mastery.level, DEFAULT_INITIAL_INTERVAL)
            local_store.bootstrap_consolidation(
                c.id, context, c.title, c.item_number or "", initial, bootstrap_date,
            )
            due = local_store.get_consolidation_due_date(c.id, context)
            if due is None:
                continue

        task_id = local_store.make_task_id(c.id, context, "consolidation", due)
        row = local_store.get_history(task_id)
        status = row["status"] if row else "todo"
        if status in _HIDDEN_STATUSES:
            continue

        if status == "postponed" and row["postponed_to"]:
            effective = datetime.date.fromisoformat(row["postponed_to"])
        else:
            effective = due

        if effective > today:
            continue

        days_overdue = (today - effective).days

        tasks.append(ReviewTask(
            id=task_id,
            course_id=c.id,
            course_title=c.title,
            item_number=c.item_number or None,
            college=list(c.college),
            context=context,
            url_pdf=c.url_pdf,
            url_pdf_ue=c.url_pdf_ue,
            agregation_fiche_edn=c.agregation_fiche_edn,
            theoretical_due_date=due,
            due_date=effective,
            review_type="consolidation",
            status=status,
            nb_lectures=c.nb_lectures if context == "college" else c.nb_lectures_ue,
            anki=getattr(c, "anki", False),
            qcm_done=getattr(c, "qcm_done", False),
            course_status=getattr(c, "course_status", "À lire"),
            days_overdue=max(days_overdue, 0),
            mastery_score=mastery.score,
            mastery_level=mastery.level,
            mastery_reasons=mastery.reasons,
            semestre=c.semestre,
        ))

    return tasks


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
