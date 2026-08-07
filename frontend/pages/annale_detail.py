"""Détail d'un partiel UNESS : sous-parties accessibles directement et historique des tentatives au style Linear."""

from __future__ import annotations

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness.import_service import ANNALE_TYPE_LABELS, UNIVERSITES, format_annale_title
from backend.state.store import data_store
from frontend.components.practice_session_card import open_node_qcm, render_session_actions
from frontend.components.qcm_replay import (
    open_chained_dialog,
    open_qcm_correction,
    open_qcm_session,
    replay_qcm_session,
)
from frontend.pages.qcm_cockpit import HISTORY_STATUS_OPTIONS, _format_duration
from frontend.theme import frame

_AUTRE = "Autre…"

_ANNALE_DETAIL_CSS = """
.an-wrap { width:100%; max-width:none; align-self:stretch; margin:0 auto; min-width:0; }
.an-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; border-bottom:1px solid var(--border); margin-bottom:20px; }
.an-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.an-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.an-section-title { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--text-dim); font-weight:600; margin-bottom:12px; }
.an-parts-list { display:flex; flex-direction:column; gap:10px; width:100%; margin-top:8px; }
.an-part-card { width:100%; padding:16px 18px; border:1px solid var(--border); border-radius:8px; background:var(--bg); transition:background var(--duration-fast) ease; }
.an-part-card:hover { background:var(--surface-hover); }
.an-part-title { font-size:15px; font-weight:600; color:var(--text); }
.an-part-meta { font-size:12px; color:var(--text-muted); margin-top:3px; }
.an-badge { font-size:11px; font-weight:500; padding:2px 8px; border-radius:4px; white-space:nowrap; }
.an-badge-done { background:rgba(34,197,94,0.12); color:#16a34a; }
.an-badge-todo { background:rgba(100,116,139,0.12); color:#64748b; }
.an-empty { padding:36px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
.an-history-dialog { width:540px; max-width:95vw; padding:20px; border-radius:8px; }
"""


def _load_annale_detail(annale_id: int) -> tuple[dict | None, list[dict]]:
    annale = local_store.get_uness_annale(annale_id)
    if annale is None:
        return None, []
    return annale, local_store.list_annale_sessions(annale_id)


def _open_edit_dialog(annale: dict, on_saved) -> None:
    matieres = sorted(data_store.get_colleges() or []) if data_store.is_loaded else []
    faculte_options = [*UNIVERSITES, _AUTRE] if annale["faculte"] in (*UNIVERSITES, "") else [
        annale["faculte"],
        *UNIVERSITES,
        _AUTRE,
    ]
    matiere_options = [*matieres, _AUTRE] if annale["matiere"] in (*matieres, "") else [
        annale["matiere"],
        *matieres,
        _AUTRE,
    ]

    with ui.dialog() as dialog, ui.card().classes("w-[480px] max-w-[95vw] p-5 gap-3").style("border-radius: 8px;"):
        ui.label("Modifier l'annale").classes("text-lg font-semibold")
        titre_input = ui.input("Titre", value=str(annale["titre"])).props("outlined dense").classes("w-full")
        annee_input = ui.number("Année", value=annale["annee"], format="%.0f").props("outlined dense").classes("w-full")

        faculte_select = ui.select(
            faculte_options, value=annale["faculte"] or _AUTRE, label="Université"
        ).props("outlined dense").classes("w-full")
        faculte_autre = ui.input("Université (saisie libre)", value=annale["faculte"] or "").props(
            "outlined dense"
        ).classes("w-full")
        faculte_autre.bind_visibility_from(faculte_select, "value", value=_AUTRE)

        matiere_select = ui.select(
            matiere_options, value=annale["matiere"] or _AUTRE, label="Matière"
        ).props("outlined dense").classes("w-full")
        matiere_autre = ui.input("Matière (saisie libre)", value=annale["matiere"] or "").props(
            "outlined dense"
        ).classes("w-full")
        matiere_autre.bind_visibility_from(matiere_select, "value", value=_AUTRE)

        def _save() -> None:
            faculte = str(faculte_autre.value if faculte_select.value == _AUTRE else faculte_select.value or "").strip()
            matiere = str(matiere_autre.value if matiere_select.value == _AUTRE else matiere_select.value or "").strip()
            titre_raw = str(titre_input.value or "").strip()
            annee_val = int(annee_input.value) if annee_input.value else None

            # Recompute standard title if custom title wasn't manually typed differently
            new_title = format_annale_title(matiere, faculte, annee_val, titre_raw)

            local_store.update_uness_annale(
                int(annale["id"]),
                titre=new_title,
                faculte=faculte,
                matiere=matiere,
                annee=annee_val,
            )
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat")
            ui.button("Enregistrer", on_click=_save).props("unelevated color=primary")
    dialog.open()


def _confirm_delete(annale: dict, on_deleted) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[420px] max-w-[95vw] p-5 gap-3").style("border-radius: 8px;"):
        ui.label("Supprimer cette annale ?").classes("text-lg font-semibold")
        ui.label(
            f"« {annale['titre']} » et toutes ses sous-parties importées seront supprimées "
            "définitivement. Cette action est irréversible."
        ).classes("text-sm text-slate-500")

        def _delete() -> None:
            local_store.delete_uness_annale(int(annale["id"]))
            dialog.close()
            on_deleted()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat")
            ui.button("Supprimer", on_click=_delete).props("unelevated color=negative")
    dialog.open()


def _session_history_metadata(session: dict) -> str:
    parts = [
        f"ITEM {session.get('item_number') or '—'}",
        str(session.get("practice_kind") or "QCM").upper(),
        f"{session.get('answered_count', 0)}/{session.get('total_questions', 0)} répondues",
    ]
    score = session.get("score_percent")
    if score is not None:
        score_20 = round(float(score) / 5.0, 1)
        score_20_str = f"{score_20:g}".replace(".", ",")
        parts.append(f"Note {score_20_str}/20 ({float(score):g} %)")
    duration = _format_duration(session.get("duration_seconds"))
    if duration:
        parts.append(duration)
    return " · ".join(parts)


def _open_history_dialog(page_slot, sessions: list[dict], refresh_parent) -> None:
    with ui.dialog() as dialog, ui.card().classes("an-history-dialog gap-3"):
        ui.label("Historique des tentatives").classes("text-lg font-semibold")
        ui.label("Sessions passées pour ce partiel.").classes("text-xs text-slate-500 mb-1")

        search = ui.input(placeholder="Rechercher une sous-partie…").props("outlined dense clearable").classes("w-full")
        status_toggle = ui.toggle(HISTORY_STATUS_OPTIONS, value="all").props(
            "spread no-caps unelevated dense"
        ).classes("w-full")
        history_list = ui.column().classes("w-full gap-2 max-h-[360px] overflow-y-auto mt-2")

        def _render_dialog_list() -> None:
            history_list.clear()
            query = str(search.value or "").strip().casefold()
            status_val = str(status_toggle.value or "all")
            filtered = []
            for s in sessions:
                if status_val == "pending" and (s.get("score_percent") is not None or s.get("status") == "completed"):
                    continue
                if status_val == "completed" and s.get("status") != "completed" and s.get("score_percent") is None:
                    continue
                title = str(s.get("course_title") or "").casefold()
                if query and query not in title:
                    continue
                filtered.append(s)

            with history_list:
                if not filtered:
                    ui.label("Aucune tentative trouvée.").classes("text-sm text-slate-400 py-4 text-center")
                    return
                for s in filtered:
                    sid = int(s["id"])
                    with ui.card().classes("w-full p-3").style(
                        "border:1px solid var(--border); border-radius:var(--radius-md);"
                    ):
                        with ui.row().classes("w-full items-center justify-between gap-2"):
                            with ui.column().classes("gap-0 min-w-0 flex-1"):
                                ui.label(s.get("course_title") or "Sous-partie").classes("font-semibold text-sm truncate")
                                ui.label(_session_history_metadata(s)).classes("text-xs text-slate-500")
                            with ui.row().classes("gap-1 items-center shrink-0"):
                                ui.button(
                                    icon="delete_outline",
                                    on_click=lambda _e=None, _sid=sid, t=s.get("course_title"): _confirm_delete_session(_sid, t),
                                ).props("flat dense round color=negative").tooltip("Supprimer cette session")

        def _confirm_delete_session(session_id: int, course_title: str) -> None:
            with ui.dialog() as sub_dialog, ui.card().classes("p-5 w-[400px] max-w-[95vw]").style("border-radius: 8px;"):
                ui.label("Supprimer cette session ?").classes("text-lg font-semibold")
                ui.label(f'« {course_title or "Sous-partie"} » sera supprimée.').classes("text-sm text-slate-500 mt-1")

                def _delete() -> None:
                    local_store.delete_ai_practice_session(session_id)
                    sub_dialog.close()
                    _render_dialog_list()
                    refresh_parent()

                with ui.row().classes("justify-end gap-2 mt-4"):
                    ui.button("Annuler", on_click=sub_dialog.close).props("flat")
                    ui.button("Supprimer", on_click=_delete).props("color=negative unelevated")
            sub_dialog.open()

        search.on_value_change(lambda _e=None: _render_dialog_list())
        status_toggle.on_value_change(lambda _e=None: _render_dialog_list())
        _render_dialog_list()

        with ui.row().classes("w-full justify-end mt-2"):
            ui.button("Fermer", on_click=dialog.close).props("flat")
    dialog.open()


@ui.page("/annales/{annale_id}")
def annale_detail_page(annale_id: str) -> None:
    page_slot = ui.context.slot
    ui.add_head_html(f"<style>{_ANNALE_DETAIL_CSS}</style>", shared=True)

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

        with ui.column().classes("an-wrap gap-0").style("flex:1 1 auto;"):
            with ui.element("div").classes("an-topbar"):
                with ui.column().classes("gap-0"):
                    ui.label(str(annale["titre"])).classes("an-title")
                    ui.label(
                        f"{annale['matiere'] or '—'} · {annale['faculte'] or '—'} · {annale['annee'] or '—'} · "
                        f"{ANNALE_TYPE_LABELS.get(annale['type_annale'], annale['type_annale'])}"
                    ).classes("an-subtitle")
                with ui.row().classes("gap-2 items-center"):
                    ui.button(
                        "Historique",
                        icon="history",
                        on_click=lambda: _open_history_dialog(page_slot, sessions, _render),
                    ).props("flat color=primary size=sm")
                    ui.button(
                        "Éditer",
                        icon="edit",
                        on_click=lambda: _open_edit_dialog(
                            annale, on_saved=lambda: ui.navigate.to(f"/annales/{parsed_id}")
                        ),
                    ).props("flat color=primary size=sm")
                    ui.button(
                        "Supprimer",
                        icon="delete",
                        on_click=lambda: _confirm_delete(
                            annale, on_deleted=lambda: ui.navigate.to("/annales")
                        ),
                    ).props("flat color=negative size=sm")
                    ui.button("Retour", icon="arrow_back", on_click=lambda: ui.navigate.to("/annales")).props("flat size=sm")

            ui.label("SOUS-PARTIES / DOSSIERS DU PARTIEL").classes("an-section-title")
            parts_container = ui.column().classes("an-parts-list")

        def _show_session(session_id: int) -> None:
            if open_node_qcm(session_id):
                return
            open_qcm_session(
                session_id,
                on_complete=_after_completion,
                on_back=lambda: open_chained_dialog(page_slot, _render),
            )

        def _show_correction(session_id: int) -> None:
            if open_node_qcm(session_id):
                return
            open_qcm_correction(
                session_id,
                on_back=lambda: open_chained_dialog(page_slot, _render),
                on_replay=_select_replayed,
            )

        def _after_completion(session_id: int) -> None:
            open_chained_dialog(
                page_slot,
                lambda: _show_correction(session_id),
                refresh=_render,
            )

        def _select_replayed(session_id: int) -> None:
            open_chained_dialog(
                page_slot,
                lambda: _show_session(session_id),
                refresh=_render,
            )

        def _replay_session(session_id: int) -> None:
            new_id = replay_qcm_session(session_id)
            if new_id is None:
                return
            _select_replayed(new_id)

        def _render_parts() -> None:
            parts_container.clear()
            with parts_container:
                if not sessions:
                    ui.label("Aucune sous-partie importée pour cette annale.").classes("an-empty")
                    return

                for s in sessions:
                    sid = int(s["id"])
                    score = s.get("score_percent")
                    is_completed = s.get("status") == "completed" or score is not None
                    score_label = f"{float(score):.0f} %" if score is not None else "pas encore de score"
                    is_exam_mode = bool(data_store.preferences.get("exam_mode", False))
                    badge_class = "an-badge-todo" if is_exam_mode else ("an-badge-done" if is_completed else "an-badge-todo")
                    badge_text = "Épreuve Neutre" if is_exam_mode else (f"Terminée ({score_label})" if is_completed else "À faire")

                    with ui.element("div").classes("an-part-card"):
                        with ui.row().classes("w-full items-center justify-between gap-4"):
                            with ui.column().classes("gap-0 min-w-0 flex-1"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(s.get("course_title") or "Sous-partie").classes("an-part-title truncate")
                                    ui.label(badge_text).classes(f"an-badge {badge_class}")
                                ui.label(
                                    f"ITEM {s.get('item_number') or '—'} · {s.get('total_questions', 0)} questions"
                                ).classes("an-part-meta")
                            with ui.row().classes("gap-2 items-center shrink-0"):
                                if is_exam_mode:
                                    ui.button(
                                        "LANCER ÉPREUVE",
                                        icon="play_arrow",
                                        on_click=lambda _sid=sid, _comp=is_completed: (_replay_session(_sid) if _comp else open_chained_dialog(page_slot, lambda: _show_session(_sid))),
                                    ).props("unelevated color=primary")
                                else:
                                    render_session_actions(
                                        s,
                                        on_resume=lambda _sid=sid: open_chained_dialog(page_slot, lambda: _show_session(_sid)),
                                        on_correction=lambda _sid=sid: open_chained_dialog(page_slot, lambda: _show_correction(_sid)),
                                        on_replay=lambda _sid=sid: _replay_session(_sid),
                                    )

        def _render() -> None:
            nonlocal annale, sessions
            loaded_annale, loaded_sessions = _load_annale_detail(parsed_id)
            if loaded_annale:
                annale, sessions = loaded_annale, loaded_sessions
            _render_parts()

        _render()


