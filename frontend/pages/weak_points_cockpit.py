"""weak_points_cockpit.py — Vue « Lacunes » cockpit (refonte, session 11 puis
recentrage du 28/07/2026, cf. docs/superpowers/specs/2026-07-28-lacunes-cockpit-refonte-design.md).

Vue principale de l'écran Lacunes.
weak_points.py). Topbar (titre, compteurs, actions) + chips de filtre
(remplacent la sidebar interne d'origine) + colonne centrée de lignes
`weak_point_row` (tokens cockpit). Le chemin classic (kanban 4 colonnes +
drag SortableJS + carte Tailwind `weak_point_card.py`) reste strictement
inchangé.
"""
from __future__ import annotations

import asyncio

from nicegui import ui
from loguru import logger

from backend.core.reviews import local_store
from backend.core.edn.gap_suggestions import (
    accept_gap_suggestion,
    ignore_gap_suggestion,
    suggest_gap_candidates,
)
from backend.core.reviews.anchors import anchor_priority, anchor_status, is_anchor_due
from backend.config.settings import settings
from frontend.components.weak_point_card import _get
from frontend.components.weak_point_row import weak_point_row
from frontend.pages.weak_points import open_add_dialog

_CSS = """
.wp-wrap { width:860px; max-width:100%; margin:0 auto; display:flex; flex-direction:column; gap:18px; }
.wp-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 0; flex-wrap:wrap; }
.wp-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.wp-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.wp-subtitle .critical { color:var(--danger); font-weight:500; }
.wp-actions { display:flex; gap:8px; flex:0 0 auto; }
.wp-btn { display:inline-flex; align-items:center; gap:6px; height:32px; padding:0 14px; border-radius:6px;
  font-size:12.5px; font-weight:500; cursor:pointer; border:1px solid var(--border); background:var(--bg);
  color:var(--text) !important; white-space:nowrap;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard); }
.wp-btn:hover { background:var(--surface); border-color:var(--border-strong); }
.wp-btn.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-text) !important; }
.wp-btn.primary:hover { background:var(--accent-hover); }
.wp-btn.loading { opacity:.6; cursor:default; }
.wp-chips { display:flex; gap:6px; flex-wrap:wrap; }
.wp-chip { font-size:12px; font-weight:500; padding:5px 12px; border-radius:6px; cursor:pointer;
  border:1px solid var(--border); background:var(--bg); color:var(--text-muted);
  display:flex; align-items:center; gap:6px;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.wp-chip:hover { background:var(--surface); color:var(--text); }
.wp-chip.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
.wp-chip .n { font-family:var(--font-mono); font-size:10.5px; opacity:.75; }
.wp-list { display:flex; flex-direction:column; border-top:1px solid var(--border); }
.wp-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
@media (max-width: 640px) {
  .wp-topbar { flex-direction:column; }
  .wp-actions { width:100%; }
  .wp-btn { flex:1 1 auto; justify-content:center; }
}
"""


def filter_weak_points_view(rows: list, view: str) -> list:
    """Filtre les points faibles pour la navigation interne du cockpit."""
    if view == "resolved":
        return [row for row in rows if _get(row, "status", "active") == "résolue"]
    active = [row for row in rows if _get(row, "status", "active") != "résolue"]
    if view == "anchors":
        return sorted(
            [row for row in active if anchor_status(row) == "actif"],
            key=lambda row: (-anchor_priority(row), not is_anchor_due(row)),
        )
    if view == "due":
        return [row for row in active if is_anchor_due(row)]
    if view == "lacunes":
        return [row for row in active if anchor_status(row) != "actif"]
    return active


def edn_suggestion_model(row: dict) -> dict[str, object]:
    """Résumé stable d'une suggestion F6 pour l'affichage et les tests UI."""
    evidence_count = len(row.get("evidence_ids") or [])
    return {
        "title": f"Item {row.get('item_number', '—')} · {row.get('category', 'non_classé')}",
        "detail": str(row.get("detail", "")),
        "evidence": f"{evidence_count} évidence(s)",
        "id": int(row["id"]),
    }


def render_weak_points_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    state = {"view": "overview"}
    with ui.element("div").classes("wp-wrap"):
        topbar = ui.element("div").classes("wp-topbar")
        chips_row = ui.element("div").classes("wp-chips")
        suggestions_col = ui.element("div")
        list_col = ui.element("div").classes("wp-list")

    def _select_view(view: str) -> None:
        state["view"] = view
        _render()

    def _draw_chips(rows: list) -> None:
        chips_row.clear()
        counts = {
            "overview": len(filter_weak_points_view(rows, "overview")),
            "lacunes": len(filter_weak_points_view(rows, "lacunes")),
            "anchors": len(filter_weak_points_view(rows, "anchors")),
            "due": len(filter_weak_points_view(rows, "due")),
            "resolved": len(filter_weak_points_view(rows, "resolved")),
        }
        with chips_row:
            for key, label in (
                ("overview", "Toutes"),
                ("lacunes", "Lacunes"),
                ("anchors", "Ancrages"),
                ("due", "À revoir"),
                ("resolved", "Résolues"),
            ):
                chip = ui.element("div").classes(
                    "wp-chip active" if state["view"] == key else "wp-chip"
                )
                with chip:
                    ui.label(label)
                    ui.label(str(counts[key])).classes("n")
                chip.on("click", lambda key=key: _select_view(key))

    def _draw_topbar(rows: list) -> None:
        topbar.clear()
        n_critical = sum(
            1 for w in rows
            if int(_get(w, "severity", 2) or 2) >= 4
            and _get(w, "status", "active") != "résolue"
        )
        n_active = len(filter_weak_points_view(rows, "overview"))
        n_anchors = len(filter_weak_points_view(rows, "anchors"))
        n_resolved = len(filter_weak_points_view(rows, "resolved"))

        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Points faibles").classes("wp-title")
                with ui.element("div").classes("wp-subtitle"):
                    ui.label(f"{n_critical} critique{'s' if n_critical != 1 else ''}").classes("critical")
                    ui.label(
                        f" · {n_active} actif{'s' if n_active != 1 else ''}"
                        f" · {n_anchors} ancrage{'s' if n_anchors != 1 else ''}"
                        f" · {n_resolved} résolue{'s' if n_resolved != 1 else ''}"
                    )

            with ui.element("div").classes("wp-actions"):
                vault_ok = bool(settings.obsidian_vault_path)
                sync_btn = ui.element("div").classes(
                    "wp-btn" + ("" if vault_ok else " loading")
                )
                with sync_btn:
                    ui.label("Synchroniser Obsidian")
                if not vault_ok:
                    sync_btn.tooltip("Configurez OBSIDIAN_VAULT_PATH dans les paramètres")
                else:
                    sync_btn.on("click", lambda: asyncio.create_task(_run_sync(sync_btn)))

                add_btn = ui.element("div").classes("wp-btn primary")
                with add_btn:
                    ui.label("Créer une lacune")
                add_btn.on("click", lambda: open_add_dialog(_render))

    async def _run_sync(btn) -> None:
        btn.classes(add="loading")
        try:
            from backend.core.obsidian.weak_points_sync import weak_points_sync_service
            result = await asyncio.to_thread(weak_points_sync_service.sync)
            ui.notify(result.summary(), type="positive" if not result.errors else "warning")
            if result.errors:
                for err in result.errors:
                    logger.error(f"Sync lacune : {err}")
            _render()
        except Exception as exc:
            logger.exception("Erreur sync Obsidian lacunes")
            ui.notify(f"Erreur : {exc}", type="negative")
        finally:
            btn.classes(remove="loading")

    def _draw_list(rows: list) -> None:
        list_col.clear()
        with list_col:
            if not rows:
                with ui.element("div").classes("wp-empty"):
                    ui.label("Aucun point faible dans cette vue.")
                return
            for w in rows:
                weak_point_row(w, on_refresh=_render)

    def _draw_suggestions(rows: list[dict]) -> None:
        suggestions_col.clear()
        if not rows:
            return
        with suggestions_col:
            ui.label("Suggestions EDN · erreurs répétées").classes("text-sm font-semibold")
            ui.label(
                "Ces propositions sont explicables et restent à valider par vous."
            ).classes("text-xs text-slate-500 mb-2")
            with ui.column().classes("w-full gap-2"):
                for row in rows:
                    model = edn_suggestion_model(row)
                    with ui.element("div").classes("w-full p-3 rounded-lg border border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/20"):
                        with ui.row().classes("w-full items-center justify-between gap-2"):
                            with ui.column().classes("gap-0"):
                                ui.label(model["title"]).classes("text-sm font-semibold")
                                ui.label(model["detail"]).classes("text-xs text-slate-500")
                                ui.label(model["evidence"]).classes("text-[11px] text-slate-500")
                            with ui.row().classes("gap-1"):
                                ui.button(
                                    "Créer",
                                    on_click=lambda suggestion_id=model["id"]: _accept_suggestion(suggestion_id),
                                ).props("unelevated color=teal size=sm rounded")
                                ui.button(
                                    "Ignorer",
                                    on_click=lambda suggestion_id=model["id"]: _ignore_suggestion(suggestion_id),
                                ).props("flat color=grey size=sm")

    def _accept_suggestion(suggestion_id: int) -> None:
        try:
            accept_gap_suggestion(suggestion_id, store=local_store)
            ui.notify("Lacune créée", type="positive")
            _render()
        except Exception as exc:
            ui.notify(f"Impossible de créer la lacune : {exc}", type="negative")

    def _ignore_suggestion(suggestion_id: int) -> None:
        try:
            ignore_gap_suggestion(suggestion_id, store=local_store)
            ui.notify("Suggestion ignorée", type="info")
            _render()
        except Exception as exc:
            ui.notify(f"Impossible d'ignorer la suggestion : {exc}", type="negative")

    def _render() -> None:
        rows = local_store.get_all_weak_points_table(limit=300)
        try:
            suggest_gap_candidates(days=30, store=local_store)
            suggestions = local_store.get_edn_recommendations(status="proposée")
        except Exception as exc:
            logger.warning(f"Suggestions F6 indisponibles : {exc}")
            suggestions = []
        _draw_topbar(rows)
        _draw_chips(rows)
        _draw_suggestions(suggestions)
        _draw_list(filter_weak_points_view(rows, state["view"]))

    _render()
