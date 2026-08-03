"""
qcm.py — Redirection Cockpit.
"""
from frontend.theme import frame


def qcm_page():
    with frame("QCM"):
        # ── Vue cockpit ───────────────────────────────────────────────────────
        from frontend.pages.qcm_cockpit import render_qcm_cockpit
        render_qcm_cockpit()
        return
