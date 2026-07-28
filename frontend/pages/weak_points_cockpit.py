"""weak_points_cockpit.py — Vue « Lacunes » cockpit (refonte, session 11).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
weak_points.py). Liste de cartes : point statut, titre, ligne de statut
(sévérité/récurrence/date de résolution), collège + id. Le chemin classic
(kanban 4 colonnes + drag SortableJS + propositions de lacune + filtre par
item) reste strictement inchangé.

Écarts assumés (voir Journal du CLAUDE.md de la refonte) :
  • réutilise `open_add_dialog` du classic pour « + Ajouter » (dialog déjà
    complet, non réimplémenté) et appelle directement
    `weak_points_sync_service.sync()` pour « Synchroniser Obsidian »
    (la logique de sync du classic est fine mais son handler est une
    closure couplée aux éléments UI de `weak_points_page`, non réutilisable
    telle quelle) ;
  • grammaire de la ligne de statut déduite de la seule capture
    (09-lacunes.png), le README ne détaille pas la composition exacte :
    « critique » (sévérité ≥4, prioritaire sur le statut brut, sauf
    résolue) · statut brut sinon · « récurrente Nx » si statut='récurrente'
    · « Nx » si récurrence ≥2 sur un autre statut · date de résolution si
    résolue. Une seule chaîne, casse phrase (majuscule initiale uniquement),
    conforme à la règle typographique du design system ;
  • pas de kanban/drag ici — le README §9 ne décrit qu'une liste de cartes,
    le classic garde le kanban complet accessible via « Vue classic ».
"""
from __future__ import annotations

import asyncio
import datetime

from nicegui import ui
from loguru import logger

from backend.core.reviews import local_store
from backend.core.reviews.anchors import anchor_priority, anchor_status, is_anchor_due
from backend.config.settings import settings
from frontend.components.weak_point_card import WeakPointCard, _get
from frontend.pages.weak_points import open_add_dialog

_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]

_CSS = """
.wp-wrap { max-width:none; width:100%; }
.wp-layout { display:grid; grid-template-columns:190px minmax(0,1fr); gap:28px; width:100%; }
.wp-sidebar { border-right:1px solid var(--border); padding-right:16px; min-height:460px; }
.wp-sidebar-title { font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:.08em; margin:5px 10px 10px; }
.wp-nav { display:flex; align-items:center; gap:9px; width:100%; min-height:36px; padding:0 10px; border:0; border-radius:6px; background:transparent; color:var(--text-muted); font-size:13px; text-align:left; cursor:pointer; }
.wp-nav:hover { background:var(--surface); color:var(--text); }
.wp-nav.active { background:var(--surface); color:var(--text); font-weight:600; }
.wp-nav .material-icons { font-size:16px; color:var(--text-dim); }
.wp-nav.active .material-icons { color:var(--accent); }
.wp-content { min-width:0; max-width:none; width:100%; }
.wp-content-body { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:24px; align-items:start; width:100%; }
.wp-pilotage { border:1px solid var(--border); border-radius:10px; background:var(--surface); padding:16px; position:sticky; top:16px; }
.wp-pilotage-title { font-size:13px; font-weight:600; color:var(--text); }
.wp-pilotage-subtitle { font-size:11px; color:var(--text-muted); margin-top:3px; }
.wp-pilotage-section { margin-top:18px; }
.wp-pilotage-section-title { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--text-dim); font-weight:600; margin-bottom:9px; }
.wp-kpis { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.wp-kpi { padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg); }
.wp-kpi-value { font-family:var(--font-mono); font-size:18px; font-weight:600; color:var(--text); }
.wp-kpi-label { font-size:10px; color:var(--text-muted); margin-top:2px; }
.wp-source-row { display:flex; align-items:center; gap:8px; margin-top:7px; font-size:11px; color:var(--text-muted); }
.wp-source-row span:first-child { width:58px; }
.wp-source-track { flex:1; height:6px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.wp-source-fill { height:100%; border-radius:3px; background:var(--accent); }
.wp-source-count { width:24px; text-align:right; font-family:var(--font-mono); font-size:10px; }
.wp-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
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
.wp-list { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:10px; width:100%; align-items:start; }
.wp-card { display:flex; align-items:center; gap:12px; border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
.wp-card:hover { border-color:var(--border-strong); background:var(--surface); }
.wp-card.resolved { opacity:.55; }
.wp-card.anchor { border-color:color-mix(in srgb, var(--accent) 35%, var(--border)); }
.wp-card.anchor.due { border-color:var(--danger); }
.wp-dot { width:8px; height:8px; border-radius:50%; flex:0 0 8px; }
.wp-main { flex:1 1 auto; min-width:0; }
.wp-card-title { font-size:13.5px; font-weight:500; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wp-card-sub { font-size:11.5px; color:var(--text-muted); margin-top:2px; }
.wp-meta { flex:0 0 auto; display:flex; align-items:center; gap:10px; font-size:12px; color:var(--text-muted); }
.wp-meta-id { font-family:var(--font-mono); color:var(--text-dim); }
.wp-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
@media (max-width: 760px) {
  .wp-layout { grid-template-columns:1fr; gap:16px; }
  .wp-content-body { grid-template-columns:1fr; }
  .wp-pilotage { position:static; }
  .wp-sidebar { border-right:0; border-bottom:1px solid var(--border); min-height:0; padding:0 0 10px; display:flex; gap:4px; overflow-x:auto; }
  .wp-sidebar-title { display:none; }
  .wp-nav { flex:0 0 auto; width:auto; }
}
"""

_STATUS_LABEL = {
    "active": "active",
    "à revoir": "à revoir",
    "récurrente": "récurrente",
    "résolue": "résolue",
}


def _fmt_date(d: str) -> str:
    try:
        date_obj = datetime.date.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return "—"
    base = f"{date_obj.day:02d} {_MONTHS_FR[date_obj.month - 1]}"
    return base if date_obj.year == datetime.date.today().year else f"{base} {date_obj.year}"


def _status_line(w) -> str:
    severity = int(_get(w, "severity", 2) or 2)
    status = _get(w, "status", "active") or "active"
    recurrence = int(_get(w, "recurrence_count", 0) or 0)
    critical = severity >= 4 and status != "résolue"

    parts: list[str] = []
    if status == "résolue":
        parts.append("résolue")
        resolved = _get(w, "resolved_at", None)
        if resolved:
            parts.append(_fmt_date(resolved))
    else:
        if critical:
            parts.append("critique")
        if status == "récurrente":
            parts.append(f"récurrente {recurrence}×")
        elif not critical:
            parts.append(_STATUS_LABEL.get(status, status))
            if recurrence >= 2:
                parts.append(f"{recurrence}×")
        elif recurrence >= 2:
            parts.append(f"{recurrence}×")

    line = " · ".join(parts) if parts else "active"
    return line[0].upper() + line[1:] if line else line


def _dot_color(w) -> str:
    status = _get(w, "status", "active") or "active"
    severity = int(_get(w, "severity", 2) or 2)
    if status == "résolue":
        return "var(--success)"
    if severity >= 4:
        return "var(--danger)"
    return "var(--warning)"


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


def _weak_point_summary(rows: list) -> dict:
    statuses = ("active", "à revoir", "récurrente", "résolue")
    status_counts = {status: 0 for status in statuses}
    source_counts: dict[str, int] = {}
    for row in rows:
        status = _get(row, "status", "active") or "active"
        status_counts[status] = status_counts.get(status, 0) + 1
        source = _get(row, "source_type", "manuel") or "manuel"
        source_counts[source] = source_counts.get(source, 0) + 1
    critical = sum(
        1 for row in rows
        if int(_get(row, "severity", 2) or 2) >= 4
        and _get(row, "status", "active") != "résolue"
    )
    return {
        "total": len(rows),
        "open": sum(count for status, count in status_counts.items() if status != "résolue"),
        "critical": critical,
        "status_counts": status_counts,
        "source_counts": source_counts,
    }


def render_weak_points_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    state = {"view": "overview"}
    with ui.element("div").classes("wp-wrap"):
        with ui.element("div").classes("wp-layout"):
            sidebar = ui.element("nav").classes("wp-sidebar")
            with ui.element("main").classes("wp-content"):
                topbar = ui.element("div").classes("wp-topbar")
                with ui.element("div").classes("wp-content-body"):
                    list_col = ui.element("div").classes("wp-list")
                    pilotage = ui.element("aside").classes("wp-pilotage")

    def _draw_sidebar(rows: list) -> None:
        sidebar.clear()
        counts = {
            "overview": len(filter_weak_points_view(rows, "overview")),
            "lacunes": len(filter_weak_points_view(rows, "lacunes")),
            "anchors": len(filter_weak_points_view(rows, "anchors")),
            "due": len(filter_weak_points_view(rows, "due")),
            "resolved": len(filter_weak_points_view(rows, "resolved")),
        }
        with sidebar:
            ui.label("Points faibles").classes("wp-sidebar-title")
            for key, icon, label in (
                ("overview", "dashboard", "Vue d’ensemble"),
                ("lacunes", "report_problem", "Lacunes"),
                ("anchors", "anchor", "Ancrages"),
                ("due", "schedule", "À revoir"),
                ("resolved", "check_circle", "Résolues"),
            ):
                nav = ui.element("button").classes(
                    "wp-nav" + (" active" if state["view"] == key else "")
                )
                with nav:
                    ui.icon(icon)
                    ui.label(f"{label} · {counts[key]}")
                nav.on("click", lambda key=key: _select_view(key))

    def _select_view(view: str) -> None:
        state["view"] = view
        _render()

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
                _draw_card(w)

    def _draw_card(w) -> None:
        WeakPointCard(w, on_refresh=_render)

    def _draw_pilotage(rows: list) -> None:
        pilotage.clear()
        summary = _weak_point_summary(rows)
        with pilotage:
            ui.label("Pilotage des lacunes").classes("wp-pilotage-title")
            ui.label("Les points à traiter en priorité").classes("wp-pilotage-subtitle")

            with ui.element("div").classes("wp-kpis wp-pilotage-section"):
                for value, label in [
                    (summary["critical"], "critiques"),
                    (summary["open"], "ouvertes"),
                    (summary["status_counts"]["à revoir"], "à revoir"),
                    (summary["status_counts"]["résolue"], "résolues"),
                ]:
                    with ui.element("div").classes("wp-kpi"):
                        ui.label(str(value)).classes("wp-kpi-value")
                        ui.label(label).classes("wp-kpi-label")

            with ui.element("div").classes("wp-pilotage-section"):
                ui.label("Sources").classes("wp-pilotage-section-title")
                source_items = sorted(
                    summary["source_counts"].items(), key=lambda item: (-item[1], item[0])
                )
                maximum = max((count for _, count in source_items), default=0)
                for source, count in source_items:
                    with ui.element("div").classes("wp-source-row"):
                        ui.label(source.capitalize())
                        with ui.element("div").classes("wp-source-track"):
                            ui.element("div").classes("wp-source-fill").style(
                                f"width:{int(count / maximum * 100) if maximum else 0}%"
                            )
                        ui.label(str(count)).classes("wp-source-count")

    def _render() -> None:
        rows = local_store.get_all_weak_points_table(limit=300)
        _draw_sidebar(rows)
        _draw_topbar(rows)
        _draw_pilotage(rows)
        _draw_list(filter_weak_points_view(rows, state["view"]))

    _render()
