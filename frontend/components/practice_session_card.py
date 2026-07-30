"""Shared session-action rendering reused by the QCM cockpit and the annale detail page."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from nicegui import ui

from frontend.components.qcm_replay import session_action_keys

QCM_NODE_DIST = Path(__file__).parents[2] / "qcm_app" / "dist" / "index.html"


def open_node_qcm(session_id: int) -> bool:
    """Open the approved Node reader when its production bundle is available."""
    if not QCM_NODE_DIST.exists():
        return False
    ui.navigate.to(f"/qcm-app/?session={int(session_id)}")
    return True


def render_session_actions(
    session: dict,
    *,
    on_resume: Callable[[int], None],
    on_correction: Callable[[int], None],
    on_replay: Callable[[int], None],
) -> None:
    """Render the resume/correction/replay buttons valid for this session's current state."""
    session_id = int(session["id"])
    with ui.row().classes("gap-2 flex-wrap mt-2"):
        actions = session_action_keys(session)
        if "resume" in actions:
            ui.button(
                "Reprendre",
                icon="play_arrow",
                on_click=lambda: on_resume(session_id),
            ).props("flat color=primary")
        if "correction" in actions:
            ui.button(
                "Voir la correction",
                icon="fact_check",
                on_click=lambda: on_correction(session_id),
            ).props("flat color=primary")
        if "replay" in actions:
            ui.button(
                "Rejouer",
                icon="replay",
                on_click=lambda: on_replay(session_id),
            ).props("flat")
