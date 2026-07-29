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

from backend.core.reviews import local_store
from backend.core.qcm.service import QCM_PASS_THRESHOLD
from frontend.components.mastery_indicator import _LEVEL_COLOR, _level_from_score
from frontend.components.practice_import_panel import open_practice_import_dialog
from frontend.pages.qcm import (
    _compute_groups, _build_item_college_map, _open_add_dialog, _ADD_DIALOG_CSS,
)

QCM_ENTRY_LABEL = "Saisir un résultat"

_CSS = """
.qc-wrap { max-width:1100px; width:100%; }
.qc-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
.qc-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.qc-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.qc-btn-primary { background:var(--accent); color:var(--accent-text); border-radius:6px; padding:9px 16px;
  font-size:13px; font-weight:500; cursor:pointer; white-space:nowrap; }
.qc-btn-primary:hover { background:var(--accent-hover); }
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
"""

QCM_COCKPIT_CSS = _CSS + _ADD_DIALOG_CSS


def render_qcm_cockpit() -> None:
    ui.add_head_html(f"<style>{QCM_COCKPIT_CSS}</style>", shared=True)

    college_map = _build_item_college_map()

    with ui.column().classes("qc-wrap gap-0"):
        topbar = ui.element("div").classes("qc-topbar")
        summary = ui.element("div").classes("qc-summary")
        ui.label("PAR COURS").classes("qc-label")
        head = ui.element("div").classes("qc-head")
        list_col = ui.column().classes("w-full gap-0")

    def _draw_topbar() -> None:
        topbar.clear()
        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("QCM").classes("qc-title")
                ui.label("Analytique · cours à retravailler · EDNpro & Hypocampus").classes("qc-subtitle")
            with ui.row().classes("gap-2"):
                import_btn = ui.element("div").classes("qc-btn-primary")
                with import_btn:
                    ui.label("Importer DP/KFP")
                import_btn.on("click", lambda: open_practice_import_dialog(_render))
                btn = ui.element("div").classes("qc-btn-primary")
                with btn:
                    ui.label(QCM_ENTRY_LABEL)
                btn.on("click", lambda: _open_add_dialog(_render))

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
            with ui.element("div").classes("qc-bar-cell"):
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

    def _render() -> None:
        rows = local_store.get_qcm_sessions_all(limit=300)
        groups = _compute_groups(rows)
        _draw_topbar()
        _draw_summary(rows, groups)
        _draw_head()
        _draw_list(groups)

    _render()
