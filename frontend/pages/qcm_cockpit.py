"""qcm_cockpit.py — Vue « QCM » cockpit (refonte, session 10).

Vue principale de l'écran QCM.
qcm.py). Bandeau de stats (moyenne · taux de réussite · cours à
retravailler) + liste par cours (score, barre santé, badge « à
retravailler »). Le chemin classic (KPI cards + sparkline + stats par item
groupées par collège + assistants de saisie) reste strictement inchangé.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • réutilise `_compute_groups` / `_build_item_college_map` / `_open_add_dialog`
    du classic `qcm.py` (agrégation par cours + mapping collège + dialog de
    saisie déjà bâtis, non réimplémentés) ;
  • le README ne décrit que le rollup simple par cours — la vue détaillée
    par item EDN, les filtres période/plateforme et les assistants
    (proposer une lacune, wizard session) du classic restent inaccessibles
    depuis cette vue ;
  • badge « à retravailler » sur `avg_score` (le score affiché sur la
    ligne), pas `last_score` (métrique différente utilisée par le bandeau
    « cours à retravailler », fidèle au classic).
"""
from __future__ import annotations

from nicegui import ui

from backend.core.qcm.service import QCM_PASS_THRESHOLD
from backend.core.reviews import local_store
from backend.state.store import data_store
from frontend.components.ai_practice_panel import (
    _open_generation_dialog,
    render_dp_tutor_action,
    trusted_dossier_context,
)
from frontend.components.course_quick_actions import _open_quick_qcm_dialog
from frontend.components.ednpro_capture_panel import open_ednpro_capture_dialog
from frontend.components.mastery_indicator import _LEVEL_COLOR, _level_from_score
from frontend.components.practice_import_panel import open_practice_import_dialog
from frontend.components.practice_session_card import open_node_qcm, render_session_actions
from frontend.components.qcm_operational_dashboard import render_operational_dashboard
from frontend.components.qcm_replay import (
    open_chained_dialog,
    open_qcm_correction,
    open_qcm_session,
    replay_qcm_session,
)
from frontend.components.qcm_replay import (
    session_action_keys as _session_action_keys,  # noqa: F401 - compatibility export
)

QCM_ENTRY_LABEL = "Saisir un résultat"

def _build_item_college_map() -> dict[str, set[str]]:
    college_map: dict[str, set[str]] = {}
    for course in getattr(data_store, "cours", []) or []:
        item_number = str(getattr(course, "item_number", "") or "").strip()
        if not item_number:
            continue
        colleges = getattr(course, "college", None) or []
        college_map.setdefault(item_number, set()).update(colleges)
    return college_map


def _compute_groups(rows: list) -> list[dict]:
    groups_dict: dict[str, dict] = {}
    college_map = _build_item_college_map()

    for r in rows:
        row_dict = dict(r) if hasattr(r, "keys") or not isinstance(r, dict) else r
        c_id = row_dict["course_id"]
        title = row_dict["course_title"]
        score = row_dict["score_percent"]
        item_num = row_dict.get("item_number") or ""

        if c_id not in groups_dict:
            groups_dict[c_id] = {
                "course_id": c_id,
                "course_title": title,
                "item_number": item_num,
                "college": list(college_map.get(item_num, set())),
                "sessions": [],
                "last_score": None,
                "avg_score": None,
                "fail_count": 0,
            }

        g = groups_dict[c_id]
        g["sessions"].append(r)
        if score is not None and score < 50:
            g["fail_count"] += 1

    for g in groups_dict.values():
        g["session_count"] = len(g["sessions"])
        scores = [(s["score_percent"] if isinstance(s, dict) or hasattr(s, "__getitem__") else getattr(s, "score_percent", None)) for s in g["sessions"]]
        scores = [sc for sc in scores if sc is not None]
        if scores:
            g["last_score"] = scores[0]
            g["avg_score"] = round(sum(scores) / len(scores), 1)

    return list(groups_dict.values())


def _open_add_dialog(refresh_fn) -> None:
    courses = getattr(data_store, "cours", []) or []
    if not courses:
        ui.notify("Aucun cours disponible", type="warning")
        return
    _open_quick_qcm_dialog(courses[0], refresh_fn)

HISTORY_STATUS_OPTIONS = {
    "all": "Toutes",
    "pending": "À faire",
    "completed": "Terminées",
}


def _pending_ai_sessions(rows: list) -> list:
    """Retourne les sessions IA encore à faire, avant leur premier score."""
    pending = []
    for row in rows:
        values = dict(row)
        if values["score_percent"] is None and values.get("completed_at") is None:
            pending.append(values)
    return pending


def _filter_item_picker_options(courses, query: str = "", limit: int = 8):
    """Retourne une courte liste d'ITEMs correspondant à la recherche."""
    normalized = (query or "").strip().casefold()
    matches = []
    for item_number, course in courses:
        title = str(getattr(course, "title", "") or "")
        if not normalized or normalized in f"{item_number} {title}".casefold():
            matches.append((item_number, course))
        if len(matches) >= limit:
            break
    return matches


def _format_duration(duration_seconds: int | None) -> str:
    if duration_seconds is None:
        return ""
    minutes, seconds = divmod(max(0, int(duration_seconds)), 60)
    if minutes and seconds:
        return f"{minutes} min {seconds} s"
    if minutes:
        return f"{minutes} min"
    return f"{seconds} s"


def _history_metadata(session: dict) -> str:
    parts = [
        f"ITEM {session.get('item_number') or '—'}",
        str(session.get("practice_kind") or "QCM").upper(),
        f"{session.get('answered_count', 0)}/{session.get('total_questions', 0)} répondues",
    ]
    score = session.get("score_percent")
    if score is not None:
        parts.append(f"Score {float(score):g} %")
    duration = _format_duration(session.get("duration_seconds"))
    if duration:
        parts.append(duration)
    return " · ".join(parts)


def _get_replayable_history(
    *, limit: int = 100, query: str = "", status: str = "all"
) -> list[dict]:
    return [
        session
        for session in local_store.get_ai_practice_sessions_history(
            limit=limit,
            query=query,
            status=status,
            exclude_uness=True,
        )
        if session.get("has_questions")
    ]


def _filter_replayable_history(sessions: list[dict], practice_kind: str) -> list[dict]:
    """Return only replayable sessions for the selected QCM or DP view."""
    selected = str(practice_kind or "QCM").strip().casefold()
    return [
        session
        for session in sessions
        if str(session.get("practice_kind") or "QCM").strip().casefold() == selected
    ]


def _open_ai_generation_picker(refresh) -> None:
    """Choisit un ITEM avant d'ouvrir le réglage de session IA partagé."""
    courses = []
    seen = set()
    for course in getattr(data_store, "cours", []) or []:
        item_number = str(getattr(course, "item_number", "") or "").strip()
        if not item_number or item_number in seen:
            continue
        seen.add(item_number)
        courses.append((item_number, course))
    courses.sort(key=lambda row: int(row[0]) if row[0].isdigit() else row[0])
    if not courses:
        ui.notify("Aucun ITEM disponible pour générer une session", type="warning")
        return

    by_item = {item_number: course for item_number, course in courses}
    page_slot = ui.context.slot
    with ui.dialog() as picker, ui.card().classes("w-[560px] max-w-[95vw] p-5").style(
        "border-radius: 8px;"
    ):
        ui.label("Générer avec IA").classes("text-lg font-semibold")
        ui.label("Choisis l’ITEM qui servira de contexte à la session.").classes(
            "text-xs text-slate-500 mb-4"
        )
        selected = {"item": courses[0][0]}
        search = ui.input(placeholder="Rechercher un ITEM ou un titre…").props(
            "outlined dense autofocus"
        ).classes("w-full")
        results = ui.column().classes("w-full max-h-[280px] overflow-auto mt-3 gap-1")

        def _open_selected_item(item_number: str) -> None:
            course = by_item.get(str(item_number))
            if course is None:
                ui.notify("Sélectionne un ITEM", type="warning")
                return
            picker.close()
            # Fermer d'abord le picker avant de monter le second overlay.
            def _open_generation() -> None:
                with page_slot:
                    _open_generation_dialog(course, refresh)

            ui.timer(0.01, _open_generation, once=True)

        def _select_item(item_number: str) -> None:
            selected["item"] = item_number
            _open_selected_item(item_number)

        def _render_options(query: str = "") -> None:
            results.clear()
            matches = _filter_item_picker_options(courses, query)
            with results:
                for item_number, course in matches:
                    title = getattr(course, "title", "") or "Cours sans titre"
                    row = ui.button(
                        on_click=lambda _e=None, _item=item_number: _select_item(_item)
                    ).props("flat no-caps align=left").classes(
                        "w-full justify-start px-3 py-2 text-left"
                    )
                    if item_number == selected["item"]:
                        row.props("color=primary")
                    with row:
                        ui.label(f"ITEM {item_number}").classes("font-mono text-xs shrink-0")
                        ui.label(title).classes("text-sm truncate ml-3")

        search.on_value_change(lambda event: _render_options(event.value or ""))
        _render_options()

        def _continue() -> None:
            _open_selected_item(selected["item"])

        with ui.row().classes("justify-end gap-2 mt-5"):
            ui.button("Annuler", on_click=picker.close).props("flat")
            ui.button("Continuer", on_click=_continue).props("color=primary unelevated")
    picker.open()

_CSS = """
.qc-wrap { width:100%; max-width:none; align-self:stretch; margin:0 auto; min-width:0; }
.qc-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
.qc-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.qc-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.qc-btn-primary { background:var(--accent); color:var(--accent-text); border-radius:6px; padding:9px 16px;
  font-size:13px; font-weight:500; cursor:pointer; white-space:nowrap; }
.qc-btn-primary:hover { background:var(--accent-hover); }
.qc-session-menu { min-width:230px; }
.qc-summary { display:flex; align-items:center; gap:24px; padding:14px 0; border-top:1px solid var(--border);
  border-bottom:1px solid var(--border); margin-bottom:18px; flex-wrap:wrap; }
.qc-metric { display:flex; flex-direction:column; gap:2px; }
.qc-metric-val { font-size:24px; font-weight:700; line-height:1; }
.qc-metric-sub { font-size:11.5px; color:var(--text-muted); }
.qc-vsep { width:1px; height:34px; background:var(--border); }
.qc-label { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600; margin-bottom:8px; }
.qc-section { width:100%; min-width:0; border:1px solid var(--border); border-radius:8px; background:var(--bg); overflow:hidden; }
.qc-section > .qc-label { padding:14px 14px 0; margin-bottom:10px; }
.qc-head, .qc-row { display:grid; grid-template-columns:46px minmax(220px, 1.2fr) minmax(180px, .8fr) 120px; column-gap:14px; align-items:center; }
.qc-head, .qc-row { width:100%; box-sizing:border-box; }
.qc-row > * { min-width:0; box-sizing:border-box; }
.qc-head { padding:0 14px 8px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); }
.qc-h-id { flex:0 0 46px; }
.qc-h-main { flex:1 1 auto; }
.qc-h-bar { flex:1 1 200px; }
.qc-h-score { flex:0 0 100px; text-align:right; }
.qc-row { min-height:50px; padding:9px 14px; border-bottom:1px solid var(--border); }
.qc-row:last-child { border-bottom:none; }
.qc-id { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); min-width:0; }
.qc-main { flex:1 1 auto; min-width:0; }
.qc-course-title { font-size:13.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.qc-course-sub { font-size:11.5px; color:var(--text-dim); margin-top:2px; }
.qc-bar-cell { min-width:0; }
.qc-bar-track { height:5px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.qc-bar-fill { height:100%; border-radius:3px; transition: width var(--duration-base) var(--ease-standard); }
.qc-score-cell { min-width:0; display:flex; align-items:center; justify-content:flex-end; gap:8px; }
.qc-score { font-family:var(--font-mono); font-size:13px; font-weight:600; }
.qc-badge { font-size:10.5px; font-weight:500; padding:2px 7px; border-radius:4px;
  background:rgba(229,72,77,0.1); color:var(--danger-text); white-space:nowrap; }
.qc-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
.qc-pending { margin-top:24px; }
.qc-pending .qc-row { align-items:flex-start; }
.qc-pending .qc-course-title { white-space:normal; overflow:visible; text-overflow:clip; overflow-wrap:anywhere; line-height:1.4; }
.qc-pending-state { flex:0 0 64px; padding-top:2px; font-size:11px; color:var(--warning-text); }
.qc-pending-action { flex:0 0 110px; justify-content:flex-start; padding-left:0; padding-right:0; }
.qc-workspace { display:grid; grid-template-columns:minmax(0, 1.1fr) minmax(320px, .9fr); gap:20px; width:100%; margin:24px 0 8px; align-items:stretch; }
.qc-history { min-width:0; max-height:620px; overflow-x:hidden; overflow-y:auto; padding:14px; border:1px solid var(--border); border-radius:8px; background:var(--bg); }
.qc-history-list { margin-top:10px; }
.qc-history-entry { width:100%; min-width:0; flex-wrap:nowrap; align-items:center; gap:4px; border-radius:6px; }
.qc-history-entry.qc-history-row-active { background:var(--surface-hover); }
.qc-history-row { flex:1 1 auto; width:auto; min-width:0; min-height:64px; flex-direction:column; align-items:flex-start; justify-content:center; text-align:left; padding:12px 14px; border-radius:6px; gap:4px; background:transparent; }
.qc-history-row .q-btn__content { min-width:0; width:100%; flex-direction:column; align-items:flex-start; justify-content:center; gap:4px; }
.qc-history-row .qc-course-title { display:block; max-width:100%; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.qc-history-row + .q-btn { flex:0 0 40px; width:40px; }
.qc-history-row .qc-course-title { line-height:1.25; }
.qc-history-meta { font-size:11px; color:var(--text-dim); margin-top:0; line-height:1.25; }
.qc-history-dp-action { flex:0 0 auto; white-space:nowrap; }
.qc-selected { min-width:0; width:100%; padding:18px; border:1px solid var(--border); border-radius:8px; background:var(--bg); }
.qc-selected-title { font-size:17px; font-weight:600; color:var(--text); }
.qc-selected-meta { font-size:12px; color:var(--text-muted); margin-top:4px; }
.qc-pending { width:100%; }
.qc-pending .qc-row { display:grid; grid-template-columns:46px minmax(0, 1fr) 64px 130px 40px; align-items:center; width:100%; }
.qc-pending-state { width:64px; }
.qc-pending-action { width:130px; }
@media (max-width:760px) {
  .qc-workspace { grid-template-columns:1fr; }
  .qc-history { max-height:360px; }
  .qc-head, .qc-row { grid-template-columns:42px minmax(0, 1fr) 36px; column-gap:10px; }
  .qc-head .qc-h-bar, .qc-row .qc-bar-cell { display:none; }
  .qc-head .qc-h-score, .qc-row .qc-score-cell { grid-column:3; }
  .qc-pending .qc-row { grid-template-columns:42px minmax(0, 1fr) 36px; }
  .qc-pending-state, .qc-pending-action { grid-column:2; width:auto; }
}
"""

QCM_COCKPIT_CSS = _CSS


def render_qcm_cockpit() -> None:
    page_slot = ui.context.slot
    ui.add_head_html(f"<style>{QCM_COCKPIT_CSS}</style>", shared=True)

    college_map = _build_item_college_map()

    with ui.column().classes("qc-wrap gap-0").style("flex:1 1 auto;"):
        topbar = ui.element("div").classes("qc-topbar")
        summary = ui.element("div").classes("qc-summary")
        with ui.element("section").classes("qc-section"):
            ui.label("PAR COURS").classes("qc-label")
            head = ui.element("div").classes("qc-head")
            list_col = ui.column().classes("w-full gap-0")
        operational_dashboard = ui.element("section").classes(
            "qc-section mt-5 p-4"
        )
        pending_col = ui.column().classes("w-full gap-0 qc-pending")
        with ui.element("div").classes("qc-workspace"):
            with ui.element("section").classes("qc-history"):
                ui.label("HISTORIQUE REJOUABLE").classes("qc-label")
                history_search = ui.input(placeholder="Rechercher une session").props("outlined dense clearable")
                history_kind = ui.toggle({"QCM": "QCM", "DP": "DP"}, value="QCM").props(
                    "spread no-caps unelevated dense"
                ).classes("w-full mt-2")
                history_col = ui.column().classes("w-full gap-1 qc-history-list")
            selected_col = ui.column().classes("qc-selected gap-3")

    selected_session = {"id": None}

    # Handoff action model: one primary entry point, secondary flows in a menu.
    def _draw_topbar() -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("QCM").classes("qc-title")
                ui.label("Analytique · cours à retravailler · EDNpro & Hypocampus").classes("qc-subtitle")
            with ui.button("Lancer un entraînement", icon="add").props(
                "unelevated color=primary"
            ).classes("qc-action-primary"), ui.menu().classes("qc-session-menu text-sm"):
                ui.menu_item("Générer avec IA", on_click=lambda: _open_ai_generation_picker(_render))
                ui.menu_item("Importer QCM / DP / KFP", on_click=lambda: open_practice_import_dialog(_render))
                ui.separator()
                ui.menu_item(QCM_ENTRY_LABEL, on_click=lambda: _open_add_dialog(_render))
                ui.menu_item(
                    "Capturer une session EDNpro",
                    on_click=lambda: open_ednpro_capture_dialog(_render),
                )

    def _draw_summary(rows: list, groups: list) -> None:
        summary.clear()
        scores = [r["score_percent"] for r in rows if r["score_percent"] is not None]
        total = len(rows)
        avg = round(sum(scores) / len(scores), 1) if scores else None
        passed = sum(1 for s in scores if s >= QCM_PASS_THRESHOLD)
        pass_rate = round(passed / len(scores) * 100) if scores else None
        to_review = sum(
            1 for g in groups
            if g["last_score"] is not None and g["last_score"] < QCM_PASS_THRESHOLD
        )

        with summary:
            avg_color = _LEVEL_COLOR.get(_level_from_score(avg), "var(--text-muted)") if avg is not None else "var(--text-dim)"
            with ui.element("div").classes("qc-metric"):
                ui.label(f"{avg}%" if avg is not None else "—").classes("qc-metric-val").style(f"color:{avg_color}")
                ui.label(f"moyenne · {total} session{'s' if total != 1 else ''}").classes("qc-metric-sub")

            ui.element("div").classes("qc-vsep")

            pr_color = _LEVEL_COLOR.get(_level_from_score(pass_rate), "var(--text-muted)") if pass_rate is not None else "var(--text-dim)"
            with ui.element("div").classes("qc-metric"):
                ui.label(f"{pass_rate}%" if pass_rate is not None else "—").classes("qc-metric-val").style(f"color:{pr_color}")
                ui.label("taux de réussite ≥ 70 %").classes("qc-metric-sub")

            ui.element("div").classes("qc-vsep")

            rev_color = "var(--warning)" if to_review > 0 else "var(--success)"
            with ui.element("div").classes("qc-metric"):
                ui.label(str(to_review) if rows else "—").classes("qc-metric-val").style(f"color:{rev_color}")
                ui.label("cours à retravailler").classes("qc-metric-sub")

    def _draw_head() -> None:
        head.clear()
        with head:
            ui.label("").classes("qc-h-id")
            ui.label("COURS").classes("qc-h-main")
            ui.label("").classes("qc-h-bar")
            ui.label("SCORE").classes("qc-h-score")

    def _draw_row(g: dict) -> None:
        avg = g["avg_score"]
        pct = int(round(avg)) if avg is not None else 0
        color = _LEVEL_COLOR.get(_level_from_score(avg if avg is not None else None), "var(--text-muted)")
        raw_college = college_map.get(g["item_number"], "")
        college = " · ".join(sorted(raw_college)) if isinstance(raw_college, (set, list)) else str(raw_college or "")
        sub = " · ".join(x for x in [college, f"{g['session_count']} session{'s' if g['session_count'] != 1 else ''}"] if x)

        with ui.element("div").classes("qc-row"):
            ui.label(g["item_number"] or "—").classes("qc-id")
            with ui.element("div").classes("qc-main"):
                ui.label(g["course_title"]).classes("qc-course-title")
                ui.label(sub).classes("qc-course-sub")
            with ui.element("div").classes("qc-bar-cell"):  # noqa: SIM117 - the track must remain nested
                with ui.element("div").classes("qc-bar-track"):
                    ui.element("div").classes("qc-bar-fill").style(f"width:{pct}%; background:{color}")
            with ui.element("div").classes("qc-score-cell"):
                ui.label(f"{pct}%" if avg is not None else "—").classes("qc-score").style(f"color:{color}")
                if avg is not None and avg < QCM_PASS_THRESHOLD:
                    ui.label("à retravailler").classes("qc-badge")

    def _draw_list(groups: list) -> None:
        list_col.clear()
        with list_col:
            if not groups:
                with ui.element("div").classes("qc-empty"):
                    ui.label("Aucune session QCM enregistrée.")
                return
            for g in groups:
                _draw_row(g)

    def _show_session(session_id: int) -> None:
        if open_node_qcm(session_id):
            return
        open_qcm_session(
            session_id,
            on_complete=_after_session_completion,
            on_back=lambda: open_chained_dialog(page_slot, _render),
        )

    def _show_correction(session_id: int) -> None:
        if open_node_qcm(session_id, correction=True):
            return
        open_qcm_correction(
            session_id,
            on_back=lambda: open_chained_dialog(page_slot, _render),
            on_replay=_select_replayed_session,
        )

    def _open_selected_session(session_id: int) -> None:
        selected_session["id"] = session_id
        open_chained_dialog(page_slot, lambda: _show_session(session_id))

    def _after_session_completion(session_id: int) -> None:
        selected_session["id"] = session_id
        open_chained_dialog(
            page_slot,
            lambda: _show_correction(session_id),
            refresh=_render,
        )

    def _open_selected_correction(session_id: int) -> None:
        selected_session["id"] = session_id
        open_chained_dialog(page_slot, lambda: _show_correction(session_id))

    def _select_replayed_session(session_id: int) -> None:
        selected_session["id"] = session_id
        open_chained_dialog(
            page_slot,
            lambda: _show_session(session_id),
            refresh=_render,
        )

    def _replay_selected_session(session_id: int) -> None:
        new_id = replay_qcm_session(session_id)
        if new_id is None:
            return
        _select_replayed_session(new_id)

    def _select_history_session(session_id: int) -> None:
        selected_session["id"] = session_id
        _render_workspace()

    def _confirm_delete_history(session_id: int, course_title: str) -> None:
        with ui.dialog() as dialog, ui.card().classes("p-5").style(
            "width: 420px; max-width: calc(100vw - 32px); border-radius: 8px;"
        ):
            ui.label("Supprimer cette session de l’historique ?").classes("text-lg font-semibold")
            ui.label(
                f'« {course_title or "Session IA"} » et sa correction seront supprimées.'
            ).classes("text-sm text-slate-500 mt-2")

            def _delete() -> None:
                deleted = local_store.delete_ai_practice_session(session_id)
                dialog.close()
                if deleted:
                    if selected_session["id"] == session_id:
                        selected_session["id"] = None
                    ui.notify("Session supprimée", type="positive")
                    _render()
                else:
                    ui.notify("Cette session n'est plus disponible", type="warning")

            with ui.row().classes("justify-end gap-2 mt-5"):
                ui.button("Annuler", on_click=dialog.close).props("flat")
                ui.button("Supprimer", on_click=_delete).props("color=negative unelevated")
        dialog.open()

    def _open_dp_tutor(session: dict) -> None:
        questions = local_store.get_ai_practice_session(int(session["id"]))
        dossier_context = trusted_dossier_context(session, questions)
        render_dp_tutor_action(
            item_number=str(session.get("item_number") or ""),
            dp_session={**session, "dossier_context": dossier_context},
            errors=[],
            gap_details=[],
            refresh=_render,
        )

    def _render_history(sessions: list[dict]) -> None:
        history_col.clear()
        with history_col:
            if not sessions:
                ui.label("Aucune session dans cette vue.").classes("qc-empty")
                return
            for session in sessions:
                session_id = int(session["id"])
                active_class = " qc-history-row-active" if session_id == selected_session["id"] else ""
                is_dp = str(session.get("practice_kind") or "QCM").strip().casefold() == "dp"
                with ui.row().classes(f"qc-history-entry{active_class}"):
                    with ui.button(
                        on_click=lambda _e=None, sid=session_id: _select_history_session(sid)
                    ).props("flat no-caps align=left").classes("qc-history-row"):
                        ui.label(session["course_title"] or "Session IA").classes("qc-course-title")
                        ui.label(_history_metadata(session)).classes("qc-history-meta")
                    if is_dp:
                        ui.button(
                            "Tuteur DP",
                            icon="psychology",
                            on_click=lambda _e=None, current=session: _open_dp_tutor(current),
                        ).props("flat dense color=primary").classes("qc-history-dp-action")
                    ui.button(
                        icon="delete_outline",
                        on_click=lambda _e=None, sid=session_id, title=session["course_title"]: _confirm_delete_history(sid, title),
                    ).props("flat dense round color=negative").tooltip("Supprimer cette session")

    def _render_selected_session(sessions: list[dict]) -> None:
        selected_col.clear()
        selected = next((row for row in sessions if row["id"] == selected_session["id"]), None)
        with selected_col:
            if selected is None:
                ui.label("Sélectionnez une session").classes("qc-selected-title")
                ui.label("Les sessions IA avec questions conservées apparaissent ici.").classes("qc-selected-meta")
                return
            ui.label(selected["course_title"] or "Session IA").classes("qc-selected-title")
            ui.label(
                f"ITEM {selected['item_number'] or '—'} · {str(selected['practice_kind'] or 'QCM').upper()} · "
                f"{selected['total_questions']} questions"
            ).classes("qc-selected-meta")
            score = selected.get("score_percent")
            status = "Terminée" if selected["status"] == "completed" else "À faire"
            ui.label(f"{status} · {f'{score}%' if score is not None else 'pas encore de score'}").classes(
                "qc-selected-meta"
            )
            if str(selected.get("practice_kind") or "QCM").strip().casefold() == "dp":
                ui.button(
                    "Ouvrir le Tuteur DP",
                    icon="psychology",
                    on_click=lambda current=selected: _open_dp_tutor(current),
                ).props("flat color=primary")
            render_session_actions(
                selected,
                on_resume=_open_selected_session,
                on_correction=_open_selected_correction,
                on_replay=_replay_selected_session,
            )

    def _replayable_history() -> list[dict]:
        sessions = _get_replayable_history(
            limit=100,
            query=str(history_search.value or ""),
            status="all",
        )
        return _filter_replayable_history(sessions, str(history_kind.value or "QCM"))

    def _confirm_delete_pending(session_id: int, course_title: str) -> None:
        with ui.dialog() as dialog, ui.card().classes("p-5").style(
            "width: 420px; max-width: calc(100vw - 32px); border-radius: 8px;"
        ):
            ui.label("Supprimer cette session ?").classes("text-lg font-semibold")
            ui.label(
                f'« {course_title or "Session IA"} » sera retirée de la liste des sessions à faire.'
            ).classes("text-sm text-slate-500 mt-2")

            def _delete() -> None:
                deleted = local_store.delete_pending_ai_practice_session(session_id)
                dialog.close()
                if deleted:
                    ui.notify("Session supprimée", type="positive")
                    _render()
                else:
                    ui.notify("Cette session n'est plus disponible", type="warning")

            with ui.row().classes("justify-end gap-2 mt-5"):
                ui.button("Annuler", on_click=dialog.close).props("flat")
                ui.button("Confirmer la suppression", on_click=_delete).props(
                    "color=negative unelevated"
                )
        dialog.open()

    def _render_workspace() -> None:
        sessions = _replayable_history()
        session_ids = {session["id"] for session in sessions}
        if selected_session["id"] not in session_ids:
            selected_session["id"] = sessions[0]["id"] if sessions else None
        _render_history(sessions)
        _render_selected_session(sessions)

    def _draw_pending(sessions: list) -> None:
        pending_col.clear()
        if not sessions:
            return
        with pending_col:
            ui.label("SESSIONS À FAIRE").classes("qc-label")
            for session in sessions:
                item_number = session["item_number"] or "—"
                course_title = session["course_title"] or "Session IA"
                kind = str(session["practice_kind"] or "QCM").upper()
                total = session["total_questions"] or 0
                with ui.element("div").classes("qc-row"):
                    ui.label(item_number).classes("qc-id")
                    with ui.element("div").classes("qc-main"):
                        ui.label(course_title).classes("qc-course-title")
                        ui.label(f"{kind} · {total} question{'s' if total != 1 else ''}").classes(
                            "qc-course-sub"
                        )
                    ui.label("à faire").classes("qc-pending-state")
                    ui.button(
                        "Commencer",
                        on_click=lambda _e=None, sid=session["id"]: _open_selected_session(sid),
                    ).props("flat dense color=primary").classes("qc-pending-action")
                    ui.button(
                        icon="delete_outline",
                        on_click=lambda _e=None, sid=session["id"], title=course_title: _confirm_delete_pending(sid, title),
                    ).props("flat dense round color=negative").tooltip("Supprimer cette session")

    def _render() -> None:
        rows = local_store.get_qcm_sessions_all(limit=300)
        groups = _compute_groups(rows)
        _draw_topbar()
        _draw_summary(rows, groups)
        _draw_head()
        _draw_list(groups)
        render_operational_dashboard(operational_dashboard)
        _render_workspace()

    history_search.on_value_change(lambda _event: _render_workspace())
    history_kind.on_value_change(lambda _event: _render_workspace())
    _render()
