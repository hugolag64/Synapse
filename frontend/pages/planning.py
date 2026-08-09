"""
planning.py — Redirection Cockpit.
"""
from frontend.theme import frame


async def planning_page(focus: str | None = None):
    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.planning_cockpit import render_planning_cockpit
    await render_planning_cockpit(focus=focus)
    return

