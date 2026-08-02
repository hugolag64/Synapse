"""
_reviews.py — Synapse
----------------------
Ne contient plus que `open_focus_mode`, point d'entrée encore utilisé
(todo_cockpit.py, course_detail_cockpit.py, dashboard/_cockpit_today.py) —
délègue entièrement à focus_mode_cockpit. Les colonnes de révision et le
rebuild complet de la vue dashboard classique (pré-cockpit) ont été
supprimés : ils n'étaient plus appelés que depuis frontend/pages/dashboard/
__init__.py, lui-même une coquille qui délègue à _cockpit_today.py.
"""
from __future__ import annotations

from nicegui import ui

from ._state import DashboardState


def open_focus_mode(state: DashboardState) -> None:
    """Dialog mode focus — une révision à la fois. Délègue à focus_mode_cockpit."""
    tasks = list(state.focus_tasks)
    if not tasks:
        ui.notify("Aucune révision à faire !", type="info")
        return

    from frontend.components.focus_mode_cockpit import open_focus_mode_cockpit

    open_focus_mode_cockpit(state)
