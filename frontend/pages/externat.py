"""
externat.py — Redirection Cockpit.
"""
from frontend.theme import frame


def externat_page():
    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.externat_cockpit import render_externat_cockpit
    render_externat_cockpit()
    return
