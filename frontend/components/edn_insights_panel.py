"""Cartes de pilotage EDN pour le Dashboard."""

from __future__ import annotations

from nicegui import ui

from backend.core.edn.external_results import import_external_results, parse_external_results
from backend.core.reviews import local_store


def edn_insights_model(status) -> dict[str, str]:
    mastery = "—" if status.average_mastery is None else f"{status.average_mastery:g} %"
    total_items = int(status.total_items or 0)
    covered_items = int(status.covered_items or 0)
    coverage_percent = min(100, covered_items / total_items * 100 if total_items else 0)
    return {
        "countdown": f"J-{status.days_remaining}",
        "target": status.target_date.strftime("%d/%m/%Y"),
        "phase": str(status.phase.value).replace("_", " ").title(),
        "coverage": f"{status.covered_items}/{status.total_items}",
        "coverage_percent": f"{coverage_percent:.1f}",
        "mastery": mastery,
        "overdue": str(status.overdue_reviews),
        "remaining": str(status.remaining_reviews),
        "focus_message": status.focus_message,
        "new_ratio": f"{int(status.recommended_new_ratio * 100)}",
        "review_ratio": f"{int(status.recommended_review_ratio * 100)}",
        "qcm_dp_ratio": f"{int(status.recommended_qcm_dp_ratio * 100)}",
        "daily_target_items": str(status.daily_target_items),
    }


def import_report_model(report) -> dict[str, object]:
    """Transforme un rapport technique en résumé lisible dans le cockpit."""
    return {
        "summary": (
            f"{report.accepted} ajouté(s) · {report.updated} mis à jour · "
            f"{report.skipped} ignoré(s)"
        ),
        "errors": [str(error.get("message", error)) for error in report.errors],
    }


def render_external_result_import(on_import=None) -> None:
    """Affiche l'import compact CSV/JSON des résultats EDNpro/Hypocampus."""
    with ui.column().classes("w-full gap-2"):
        ui.label("Résultats EDN externes").classes("text-sm font-semibold")
        ui.label(
            "Collez un export CSV ou JSON. Les doublons sont mis à jour automatiquement."
        ).classes("text-xs text-slate-500")
        fmt = ui.select({"csv": "CSV", "json": "JSON"}, value="csv", label="Format").props(
            "outlined dense"
        )
        payload = ui.textarea(
            label="Contenu de l'export",
            placeholder="source,external_id,session_date,item_number,score_percent",
        ).props("outlined autogrow").classes("w-full")
        result_label = ui.label().classes("text-xs text-slate-500")

        def _import() -> None:
            try:
                rows = parse_external_results(payload.value or "", fmt.value or "csv")
                report = import_external_results(rows, store=local_store)
                model = import_report_model(report)
                result_label.set_text(model["summary"])
                result_label.style(
                    "color:var(--danger)" if model["errors"] else "color:var(--success)"
                )
                if model["errors"]:
                    ui.notify("Import terminé avec des lignes ignorées", type="warning")
                else:
                    ui.notify("Résultats EDN importés", type="positive")
                if on_import:
                    on_import(report)
            except (TypeError, ValueError) as exc:
                result_label.set_text(f"Import impossible : {exc}")
                result_label.style("color:var(--danger)")
                ui.notify("Import EDN impossible", type="negative")

        ui.button("Importer les résultats", icon="upload_file", on_click=_import).props(
            "unelevated color=teal size=sm rounded"
        )


_SPRINT_CSS = """
.edn-sprint-panel { border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:8px; background:var(--bg); box-shadow:var(--shadow-popover); }
.edn-sprint-header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.edn-sprint-title { color:var(--text); letter-spacing:-.01em; font-size:14px; font-weight:600; }
.edn-sprint-subtitle { color:var(--text-muted); font-size:11px; }
.edn-sprint-stats { display:flex; gap:16px; flex-wrap:wrap; justify-content:flex-end; }
.edn-sprint-metric { display:flex; flex-direction:column; gap:2px; min-width:54px; }
.edn-sprint-metric-label { color:var(--text-dim); font-family:var(--font-mono); font-size:9px; text-transform:uppercase; letter-spacing:.04em; }
.edn-sprint-metric-value { color:var(--text); font-family:var(--font-mono); font-size:12px; font-weight:600; }
.edn-sprint-progress-track { height:5px; border-radius:3px; background:var(--surface-hover); overflow:hidden; }
.edn-sprint-progress-fill { height:100%; border-radius:3px; background:var(--accent); }
.edn-sprint-scenarios { display:flex; gap:6px; flex-wrap:wrap; }
.edn-sprint-scenario { padding:5px 8px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--text-muted); font-size:10px; }
.edn-sprint-priority-row { display:flex; align-items:center; gap:8px; min-height:24px; color:var(--text); font-size:11px; font-family:var(--font-mono); }
.edn-sprint-priority-dot { width:5px; height:5px; flex:0 0 5px; border-radius:50%; background:var(--accent); }
.edn-sprint-priority-meta { margin-left:auto; color:var(--text-dim); }
@media (max-width: 720px) { .edn-sprint-header { flex-direction:column; } .edn-sprint-stats { justify-content:flex-start; } }
"""


def render_edn_insights_panel(status, projections=(), gain_items=()) -> None:
    ui.add_head_html(f"<style>{_SPRINT_CSS}</style>", shared=True)
    model = edn_insights_model(status)
    with ui.element("div").classes("edn-sprint-panel w-full p-4 mb-4"):
        with ui.element("div").classes("edn-sprint-header"):
            with ui.column().classes("gap-0"):
                ui.label(f"Sprint EDN · {model['countdown']}").classes("edn-sprint-title")
                ui.label(
                    f"Objectif {model['target']} · phase {model['phase']}"
                ).classes("edn-sprint-subtitle")
                ui.label(model["focus_message"]).classes("edn-sprint-subtitle")
            with ui.element("div").classes("edn-sprint-stats"):
                for label, value in (
                    ("Items", model["coverage"]),
                    ("Maîtrise", model["mastery"]),
                    ("Retard", model["overdue"]),
                    ("Restant", model["remaining"]),
                ):
                    with ui.element("div").classes("edn-sprint-metric"):
                        ui.label(label).classes("edn-sprint-metric-label")
                        ui.label(value).classes("edn-sprint-metric-value")
        with ui.element("div").classes("edn-sprint-progress-track mt-3"):
            ui.element("div").classes("edn-sprint-progress-fill").style(
                f"width:{model['coverage_percent']}%"
            )
        ui.label(
            f"Répartition recommandée : {model['new_ratio']}% nouveaux · "
            f"{model['review_ratio']}% révisions · {model['qcm_dp_ratio']}% QCM/DP · "
            f"{model['daily_target_items']} items/j visés"
        ).classes("edn-sprint-subtitle mt-2")
        if projections:
            with ui.element("div").classes("edn-sprint-scenarios mt-3"):
                for projection in projections:
                    ui.label(
                        f"{projection.name.title()} · {projection.projected_coverage:g}% couverture"
                    ).classes("edn-sprint-scenario")
        if gain_items:
            ui.label("Priorités de gain relatives").classes("text-xs font-semibold mt-3")
            with ui.column().classes("w-full gap-0 mt-1"):
                for item in gain_items[:3]:
                    with ui.element("div").classes("edn-sprint-priority-row"):
                        ui.element("span").classes("edn-sprint-priority-dot")
                        ui.label(f"Item {item.get('item_number', '—')}")
                        ui.label(
                            f"potentiel {item.get('potential_score', 0):g}"
                        ).classes("edn-sprint-priority-meta")
                        ui.label(f"{item.get('estimated_minutes', 30):g} min").classes(
                            "edn-sprint-priority-meta"
                        )
