"""
recommendation_service.py — Synapse
-------------------------------------
Calcule la "prochaine action recommandée" pour une ReviewTask donnée,
et estime la charge de travail journalière.

Usage :
    from backend.core.reviews.recommendation_service import get_next_action, compute_daily_load

    na = get_next_action(task)
    print(na.label, na.duration_min, na.reason)

    load = compute_daily_load(urgent_tasks, today_tasks)
    print(load['total_min'], load['is_heavy'])
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.core.reviews.models import ReviewTask


# ── Modèle ────────────────────────────────────────────────────────────────────

@dataclass
class NextAction:
    label: str           # "Réviser" | "Réviser + Anki" | "Révision urgente" …
    reason: str          # "J7 — 3j retard · niveau fragile" (peut être vide)
    icon: str            # Nom d'icône Material (menu_book, emergency, quiz, style…)
    duration_min: int    # Durée estimée en minutes
    color: str           # "red" | "orange" | "blue" | "indigo" | "slate"
    action_type: str     # "review" | "anki" | "qcm"


# ── Calcul NextAction ─────────────────────────────────────────────────────────

_CRITICAL_LEVELS = {"critique", "fragile"}
_WARN_LEVELS     = {"à consolider", "en construction"}


def get_next_action(
    task: "ReviewTask",
    *,
    last_qcm_score: float | None = None,   # % (0-100), None = inconnu
    lacune_count: int = 0,                  # lacunes actives sur ce cours
    stage_college: str | None = None,       # college du stage actif
) -> NextAction:
    """
    Retourne la NextAction recommandée pour une tâche de révision.

    Ordre de priorité :
      1. Retard critique + niveau faible     → Révision urgente (rouge)
      2. QCM récent raté (<60%)              → Réviser + QCM (orange)
      3. Retard + niveau fragile/critique    → Réviser + Anki (orange)
      4. Retard + pas d'Anki                → Réviser + créer Anki (orange)
      5. Retard simple                       → Réviser (bleu)
      6. Aujourd'hui + QCM raté (<70%)      → Réviser + QCM (indigo)
      7. Aujourd'hui + pas de QCM           → Réviser + QCM (indigo)
      8. Aujourd'hui + pas d'Anki           → Réviser + Anki (indigo)
      9. À venir, tout ok                   → Réviser (slate)
    """
    overdue = task.days_overdue
    level   = task.mastery_level or ""

    qcm_failed  = last_qcm_score is not None and last_qcm_score < 70
    qcm_poor    = last_qcm_score is not None and last_qcm_score < 60
    has_lacunes = lacune_count > 0
    in_stage    = bool(stage_college) and stage_college in (getattr(task, "college", "") or "")

    # ── Raison textuelle ──────────────────────────────────────────────────────
    parts: list[str] = []
    if overdue > 0:
        parts.append(f"{overdue}j retard")
    if level in _CRITICAL_LEVELS | _WARN_LEVELS:
        parts.append(f"niveau {level}")
    if qcm_failed:
        parts.append(f"QCM {int(last_qcm_score)}%")
    if has_lacunes:
        parts.append(f"{lacune_count} lacune{'s' if lacune_count > 1 else ''}")
    if in_stage:
        parts.append("stage actuel")
    if not task.anki:
        parts.append("Anki absent")
    reason = " · ".join(parts)

    is_critical = level in _CRITICAL_LEVELS

    # Anki est un outil de consolidation TARDIVE (après ≥3 lectures + QCMs faits)
    # On ne le suggère pas en début d'apprentissage.
    anki_eligible = (not task.anki) and (task.nb_lectures >= 3) and task.qcm_done

    # ── Sélection de l'action ─────────────────────────────────────────────────
    if overdue > 7 and is_critical:
        return NextAction(
            label="Révision urgente",
            reason=reason,
            icon="emergency",
            duration_min=35,
            color="red",
            action_type="review",
        )

    # QCM très raté récemment → priorité haute même sans retard
    if qcm_poor and overdue > 0:
        return NextAction(
            label="Réviser + refaire QCM",
            reason=reason,
            icon="quiz",
            duration_min=30,
            color="orange",
            action_type="qcm",
        )

    if overdue > 3 and is_critical:
        if anki_eligible:
            return NextAction(
                label="Réviser + créer Anki",
                reason=reason,
                icon="style",
                duration_min=30,
                color="orange",
                action_type="review",
            )
        return NextAction(
            label="Révision prioritaire",
            reason=reason,
            icon="priority_high",
            duration_min=30,
            color="orange",
            action_type="review",
        )

    if overdue > 0:
        if anki_eligible:
            return NextAction(
                label="Réviser + créer Anki",
                reason=reason,
                icon="style",
                duration_min=25,
                color="orange",
                action_type="review",
            )
        return NextAction(
            label="Réviser",
            reason=reason,
            icon="menu_book",
            duration_min=20,
            color="blue",
            action_type="review",
        )

    # Tâche prévue aujourd'hui ou dans le futur
    if qcm_failed:
        return NextAction(
            label="Réviser + refaire QCM",
            reason=reason or "QCM à améliorer",
            icon="quiz",
            duration_min=30,
            color="indigo",
            action_type="qcm",
        )

    if not task.qcm_done:
        return NextAction(
            label="Réviser + QCM",
            reason=reason or "Révision planifiée",
            icon="quiz",
            duration_min=30,
            color="indigo",
            action_type="qcm",
        )

    if anki_eligible:
        return NextAction(
            label="Réviser + créer Anki",
            reason=reason or "Consolidation mémorielle",
            icon="style",
            duration_min=20,
            color="indigo",
            action_type="review",
        )

    return NextAction(
        label="Réviser",
        reason=reason or "Révision planifiée",
        icon="menu_book",
        duration_min=15,
        color="blue",
        action_type="review",
    )


# ── Charge de travail journalière ─────────────────────────────────────────────

def compute_daily_load(
    urgent_tasks: list["ReviewTask"],
    today_tasks:  list["ReviewTask"],
) -> dict:
    """
    Estime la charge journalière (urgent + prévu aujourd'hui).

    Retourne :
        {
            "total_min"     : int,    # total estimé en minutes
            "urgent_count"  : int,
            "today_count"   : int,
            "is_heavy"      : bool,   # True si > 120 min
            "estimated_h"   : int,    # heures entières
            "estimated_m"   : int,    # minutes restantes
        }
    """
    all_tasks = urgent_tasks + today_tasks
    total_min = sum(get_next_action(t).duration_min for t in all_tasks)
    h, m = divmod(total_min, 60)

    return {
        "total_min"   : total_min,
        "urgent_count": len(urgent_tasks),
        "today_count" : len(today_tasks),
        "is_heavy"    : total_min > 120,
        "estimated_h" : h,
        "estimated_m" : m,
    }
