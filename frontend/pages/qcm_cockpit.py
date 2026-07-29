"""qcm_cockpit.py — Vue « QCM » cockpit (refonte, session 10).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
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
    depuis le cockpit (bascule « Vue classic » pour y accéder) ;
  • badge « à retravailler » sur `avg_score` (le score affiché sur la
    ligne), pas `last_score` (métrique différente utilisée par le bandeau
    « cours à retravailler », fidèle au classic).
"""
from __future__ import annotations

from nicegui import ui

from backend.core.qcm.service import QCM_PASS_THRESHOLD
from backend.core.reviews import local_store
from backend.state.store import data_store
from frontend.components.ai_practice_panel import _open_answer_dialog, _open_generation_dialog
from frontend.components.mastery_indicator import _LEVEL_COLOR, _level_from_score
from frontend.components.practice_import_panel import open_practice_import_dialog
from frontend.pages.qcm import (
    _ADD_DIALOG_CSS,
    _build_item_college_map,
    _compute_groups,
    _open_add_dialog,
)

QCM_ENTRY_LABEL = "Saisir un résultat"


def _pending_ai_sessions(rows: list) -> list:
    """Retourne les sessions IA encore à faire, avant leur premier score."""
    return [row for row in rows if row["score_percent"] is None]


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

        def _select_item(item_number: str) -> None:
            selected["item"] = item_number
            _render_options(search.value or "")

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
            course = by_item.get(str(selected["item"]))
            if course is None:
                ui.notify("Sélectionne un ITEM", type="warning")
                return
            picker.close()
            _open_generation_dialog(course, refresh)

        with ui.row().classes("justify-end gap-2 mt-5"):
            ui.button("Annuler", on_click=picker.close).props("flat")
            ui.button("Continuer", on_click=_continue).props("color=primary unelevated")
    picker.open()

_CSS = """
.qc-wrap { width:100%; max-width:1200px; align-self:stretch; margin:0 auto; min-width:0; }
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
.qc-head { display:flex; align-items:center; gap:14px; padding:0 10px 8px; font-size:10px;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-dim); font-weight:600;
  border-bottom:1px solid var(--border); }
.qc-h-id { flex:0 0 46px; }
.qc-h-main { flex:1 1 auto; }
.qc-h-bar { flex:1 1 200px; }
.qc-h-score { flex:0 0 100px; text-align:right; }
.qc-row { display:flex; align-items:center; gap:14px; min-height:44px; padding:9px 10px;
  border-bottom:1px solid var(--border); }
.qc-row:last-child { border-bottom:none; }
.qc-id { font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); flex:0 0 46px; }
.qc-main { flex:1 1 auto; min-width:0; }
.qc-course-title { font-size:13.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.qc-course-sub { font-size:11.5px; color:var(--text-dim); margin-top:2px; }
.qc-bar-cell { flex:1 1 200px; }
.qc-bar-track { height:5px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.qc-bar-fill { height:100%; border-radius:3px; transition: width var(--duration-base) var(--ease-standard); }
.qc-score-cell { flex:0 0 100px; display:flex; align-items:center; justify-content:flex-end; gap:8px; }
.qc-score { font-family:var(--font-mono); font-size:13px; font-weight:600; }
.qc-badge { font-size:10.5px; font-weight:500; padding:2px 7px; border-radius:4px;
  background:rgba(229,72,77,0.1); color:var(--danger); white-space:nowrap; }
.qc-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
.qc-pending { margin-top:24px; }
.qc-pending-action { flex:0 0 auto; }
.qc-pending-state { flex:0 0 auto; font-size:11px; color:var(--warning); }
"""

QCM_COCKPIT_CSS = _CSS + _ADD_DIALOG_CSS


def render_qcm_cockpit() -> None:
    ui.add_head_html(f"<style>{QCM_COCKPIT_CSS}</style>", shared=True)

    college_map = _build_item_college_map()

    with ui.column().classes("qc-wrap gap-0").style("flex:1 1 auto;"):
        topbar = ui.element("div").classes("qc-topbar")
        summary = ui.element("div").classes("qc-summary")
        ui.label("PAR COURS").classes("qc-label")
        head = ui.element("div").classes("qc-head")
        list_col = ui.column().classes("w-full gap-0")
        pending_col = ui.column().classes("w-full gap-0 qc-pending")

    # Handoff action model: one primary entry point, secondary flows in a menu.
    def _draw_topbar() -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("QCM").classes("qc-title")
                ui.label("Analytique · cours à retravailler · EDNpro & Hypocampus").classes("qc-subtitle")
            with ui.button("Nouvelle session", icon="add").props(
                "unelevated color=primary"
            ).classes("qc-action-primary"), ui.menu().classes("qc-session-menu text-sm"):
                ui.menu_item("Générer avec IA", on_click=lambda: _open_ai_generation_picker(_render))
                ui.menu_item("Importer QCM / DP / KFP", on_click=lambda: open_practice_import_dialog(_render))
                ui.separator()
                ui.menu_item(QCM_ENTRY_LABEL, on_click=lambda: _open_add_dialog(_render))

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
        college = college_map.get(g["item_number"], "")
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
                        on_click=lambda _e=None, sid=session["id"]: _open_answer_dialog(sid, _render),
                    ).props("flat dense color=primary").classes("qc-pending-action")

    def _render() -> None:
        rows = local_store.get_qcm_sessions_all(limit=300)
        pending = _pending_ai_sessions(local_store.get_ai_practice_sessions(limit=100))
        groups = _compute_groups(rows)
        _draw_topbar()
        _draw_summary(rows, groups)
        _draw_head()
        _draw_list(groups)
        _draw_pending(pending)

    _render()
