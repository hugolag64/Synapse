"""
colleges.py — Vue index des collèges médicaux

Layout :
  1. En-tête : titre + stats globales + contrôles
  2. Grille des collèges : cards compactes avec jauge de maîtrise
  3. Section cours : header + filtres + grid CourseCards
"""
from __future__ import annotations


from nicegui import ui

from frontend.theme import frame
from backend.state.store import data_store
from backend.core.knowledge import store as knowledge_store
from backend.core.knowledge import service as knowledge_service


# ── Mastery color system ──────────────────────────────────────────────────────

_FILL = {
    "solide":       "#059669",
    "correct":      "#3B82F6",
    "fragile":      "#B45309",
    "non_commence": "#CBD5E1",
}
_GHOST = {
    "solide":       "rgba(5,150,105,0.12)",
    "correct":      "rgba(59,130,246,0.12)",
    "fragile":      "rgba(180,83,9,0.12)",
    "non_commence": "rgba(203,213,225,0.20)",
}
_TINT = {
    "solide":       "rgba(5,150,105,0.05)",
    "correct":      "rgba(59,130,246,0.05)",
    "fragile":      "rgba(180,83,9,0.05)",
    "non_commence": "transparent",
}
_LABEL = {
    "solide":       "Solide",
    "correct":      "Correct",
    "fragile":      "Fragile",
    "non_commence": "Non commencé",
}
_TEXT_CLS = {
    "solide":       "text-green-600 dark:text-green-400",
    "correct":      "text-blue-600 dark:text-blue-400",
    "fragile":      "text-amber-600 dark:text-amber-400",
    "non_commence": "text-slate-400 dark:text-slate-500",
}

STATUS_LABELS = {
    "non_etudie": "Non étudié",
    "en_cours":   "En cours",
    "valide":     "Validé",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _college_level(pct: float) -> str:
    if pct == 0:
        return "non_commence"
    if pct < 0.35:
        return "fragile"
    if pct < 0.75:
        return "correct"
    return "solide"


def _compute_stats(
    name: str,
    all_college_statuses: dict[str, str] | None = None,
    all_item_states: dict | None = None,
) -> dict:
    """
    Stats d'un collège. `all_college_statuses`/`all_item_states` permettent au
    caller de pré-charger ces tables une seule fois pour tous les collèges au
    lieu d'une requête par collège (voir _show : 28 collèges → 1 lecture chacune).
    """
    courses = data_store.get_cours_for_college(name)
    total = len(courses)
    started = sum(1 for c in courses if c.date_1ere_lecture)
    pct = started / total if total > 0 else 0.0

    if all_college_statuses is None:
        status = knowledge_store.get_college_status(name)
    else:
        status = all_college_statuses.get(name, "non_etudie")

    if all_item_states is None:
        situes, n_items = knowledge_service.college_triage_progress(
            name, [c.id for c in courses]
        )
    else:
        n_items = len(courses)
        situes = sum(1 for c in courses if c.id in all_item_states)

    return {
        "total":   total,
        "started": started,
        "pct":     pct,
        "level":   _college_level(pct),
        "status":  status,             # non_etudie | en_cours | valide
        "situes":  situes,
        "n_items": n_items,
    }


# ── Page ──────────────────────────────────────────────────────────────────────

@ui.page('/colleges')
@frame('Collèges')
def colleges_page():
    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.colleges_cockpit import render_colleges_cockpit
    render_colleges_cockpit()
    return
