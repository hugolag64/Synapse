"""
Dashboard Synapse — Vue décisionnelle (Phase E)
------------------------------------------------
Entry point : expose `dashboard_page` pour le routeur (main.py).

Layout :
  • Bannière résumé  : N urgentes · M aujourd'hui · Xh estimé
  • Hero card (2/3)  : tâche la plus urgente
  • Focus Timer (1/3): Pomodoro compact
  • Col gauche (1/4) : Agenda + Lacune du jour
  • Col droite (3/4) : Tabs — Aujourd'hui (Urgent | Prévu) | Semaine

Architecture :
  _state.py     → DashboardState (état partagé)
  _banner.py    → context strip + stats pills
  _hero.py      → hero card
  _reviews.py   → colonnes de révision + rebuild
  _agenda.py    → agenda + lacune du jour
  _monday.py    → diagnostic lundi
  _dialogs.py   → session feedback + SR help + bilan
"""
from __future__ import annotations

from nicegui import ui
from loguru import logger


logger.info("LOADING DASHBOARD PACKAGE")


async def dashboard_page() -> None:
    logger.info("ENTERING DASHBOARD PAGE")
    try:
        # ── Vue cockpit ───────────────────────────────────────────────────────
        from ._cockpit_today import render_today_cockpit
        await render_today_cockpit()
        return

    except Exception as e:
        logger.exception("CRITICAL DASHBOARD ERROR")
        ui.label(f"Erreur Dashboard: {e}").classes("text-red-500 font-bold")
        ui.notify(f"Erreur fatale: {e}", type="negative")
