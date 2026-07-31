"""Détail d'un partiel UNESS : ses sous-parties, jouées via le lecteur Node existant."""

from __future__ import annotations

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness.import_service import ANNALE_TYPE_LABELS
from frontend.components.practice_session_card import open_node_qcm, render_session_actions
from frontend.components.qcm_replay import open_qcm_correction, open_qcm_session, replay_qcm_session
from frontend.theme import frame


def _load_annale_detail(annale_id: int) -> tuple[dict | None, list[dict]]:
    annale = local_store.get_uness_annale(annale_id)
    if annale is None:
        return None, []
    return annale, local_store.list_annale_sessions(annale_id)


@ui.page("/annales/{annale_id}")
def annale_detail_page(annale_id: str) -> None:
    with frame("Annale"):
        try:
            parsed_id = int(annale_id)
        except ValueError:
            ui.label("Identifiant d'annale invalide.").classes("text-sm text-negative")
            return

        annale, sessions = _load_annale_detail(parsed_id)
        if annale is None:
            ui.label("Annale introuvable.").classes("text-sm text-negative")
            ui.button("Retour", icon="arrow_back", on_click=lambda: ui.navigate.to("/annales")).props("flat")
            return

        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-1"):
                ui.label(str(annale["titre"])).classes("text-xl font-semibold")
                ui.label(
                    f"{annale['matiere'] or '—'} · {annale['faculte'] or '—'} · {annale['annee'] or '—'} · "
                    f"{ANNALE_TYPE_LABELS.get(annale['type_annale'], annale['type_annale'])}"
                ).classes("text-sm text-slate-500")
            ui.button("Retour", icon="arrow_back", on_click=lambda: ui.navigate.to("/annales")).props("flat")

        def _show_session(session_id: int) -> None:
            if open_node_qcm(session_id):
                return
            open_qcm_session(session_id, on_complete=lambda _sid: None, on_back=lambda: None)

        def _show_correction(session_id: int) -> None:
            if open_node_qcm(session_id):
                return
            open_qcm_correction(session_id, on_back=lambda: None, on_replay=lambda _sid: None)

        def _replay(session_id: int) -> None:
            replay_qcm_session(session_id)

        with ui.column().classes("w-full gap-3 mt-6"):
            if not sessions:
                ui.label("Aucune sous-partie importée pour cette annale.").classes("text-sm text-slate-500")
            for session in sessions:
                score = session.get("score_percent")
                score_label = "—" if score is None else f"{float(score):.0f} %"
                status_label = "Terminée" if session["status"] == "completed" else "À faire"
                with ui.card().classes("w-full p-4"):
                    ui.label(str(session.get("course_title") or "Sous-partie")).classes("font-semibold")
                    ui.label(f"{session['total_questions']} questions · {status_label} · Score : {score_label}").classes(
                        "text-xs text-slate-500"
                    )
                    render_session_actions(
                        session,
                        on_resume=_show_session,
                        on_correction=_show_correction,
                        on_replay=_replay,
                    )
