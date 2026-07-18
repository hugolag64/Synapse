"""
lacune_adapter.py — Synapse
----------------------------
Convertit une ligne de la table weak_points en ReviewTask, pour que les
lacunes actives puissent traverser le même pipeline carte/assistant que
les révisions et la consolidation (Dashboard RETARD/AUJOURD'HUI, To Do).

Pas d'écriture Notion, pas de nouvelle table — pur adaptateur en mémoire.
"""
from __future__ import annotations

import datetime

from backend.core.reviews.models import ReviewTask


def weak_point_to_task(row) -> ReviewTask:
    """
    Construit une ReviewTask virtuelle (review_type="lacune") à partir d'une
    ligne weak_points (dict ou sqlite3.Row — accès par clé dans les deux cas).

    Le libellé affiché est le texte de la lacune (row["detail"]), pas le
    titre du cours : c'est ce qui doit apparaître en premier sur la carte.
    """
    from backend.state.store import data_store

    course = next((c for c in data_store.cours if c.id == row["course_id"]), None)
    college = list(course.college) if course is not None else []

    today = datetime.date.today()
    return ReviewTask(
        id=f"lacune_{row['id']}",
        course_id=row["course_id"],
        course_title=row["detail"],
        item_number=row["item_number"] or None,
        college=college,
        context="college",
        theoretical_due_date=today,
        due_date=today,
        review_type="lacune",
        status="todo",
    )
