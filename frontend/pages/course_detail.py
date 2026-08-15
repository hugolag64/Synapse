"""
course_detail.py — Synapse — Fiche Course Intelligence
-------------------------------------------------------
Route : /cours/{course_id}

Délègue entièrement à la vue cockpit (frontend/pages/course_detail_cockpit.py).
"""
from __future__ import annotations

from frontend.theme import frame


def course_detail_page(course_id: str, college: str | None = None) -> None:
    with frame("Fiche cours"):
        from frontend.pages.course_detail_cockpit import render_item_cockpit
        # Legacy contract retained in the source: render_item_cockpit(course_id)
        render_item_cockpit(course_id, college=college)
