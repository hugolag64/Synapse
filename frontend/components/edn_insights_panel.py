"""Cartes de pilotage EDN pour le Dashboard."""

from __future__ import annotations

from nicegui import ui

from backend.core.edn.external_results import import_external_results, parse_external_results
from backend.core.reviews import local_store


def edn_insights_model(status) -> dict[str, str]:
    mastery = "—" if status.average_mastery is None else f"{status.average_mastery:g} %"
    return {
        "countdown": f"J-{status.days_remaining}",
        "target": status.target_date.strftime("%d/%m/%Y"),
        "phase": str(status.phase.value).replace("_", " ").title(),
        "coverage": f"{status.covered_items}/{status.total_items}",
        "mastery": mastery,
        "overdue": str(status.overdue_reviews),
        "remaining": str(status.remaining_reviews),
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
        fmt = ui.select(
            {"csv": "CSV", "json": "JSON"}, value="csv", label="Format"
        ).props("outlined dense")
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
.edn-sprint-panel { position:relative; border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:8px; background:var(--surface); box-shadow:var(--shadow-popover); }
.edn-sprint-title { color:var(--text); letter-spacing:-.01em; }
.edn-sprint-subtitle { color:var(--text-muted); }
.edn-sprint-stats { gap:6px; }
.edn-sprint-stats > * { padding:5px 8px; border:1px solid var(--border); border-radius:6px; background:var(--bg-alt); color:var(--text-muted); font-family:var(--font-mono); font-size:10px; }
.edn-sprint-scenarios { gap:6px; }
.edn-sprint-scenario { padding:5px 8px; border:1px solid var(--border); border-radius:6px; background:var(--bg-alt); color:var(--text-muted); font-size:11px; }
.edn-sprint-priority { color:var(--text); font-size:11px; font-family:var(--font-mono); }
"""


def render_edn_insights_panel(status, projections=(), gain_items=()) -> None:
    ui.add_head_html(f"<style>{_SPRINT_CSS}</style>", shared=True)
    model = edn_insights_model(status)
    with ui.element("div").classes("edn-sprint-panel w-full p-4 mb-4"):
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.column().classes("gap-0"):
                ui.label(f"Sprint EDN · {model['countdown']}").classes("text-sm font-semibold")
                ui.label(f"Objectif {model['target']} · phase {model['phase']}").classes("text-xs text-slate-500")
            with ui.row().classes("edn-sprint-stats"):
                ui.label(f"Items {model['coverage']}")
                ui.label(f"Maîtrise {model['mastery']}")
                ui.label(f"Retard {model['overdue']}")
                ui.label(f"Restant {model['remaining']}")
        if projections:
            with ui.row().classes("edn-sprint-scenarios mt-3 flex-wrap"):
                for projection in projections:
                    ui.label(
                        f"{projection.name.title()} · {projection.projected_coverage:g}% couverture"
                    ).classes("edn-sprint-scenario")
        if gain_items:
            ui.label("Priorités de gain relatives").classes("text-xs font-semibold mt-3")
            with ui.column().classes("w-full gap-1 mt-1"):
                for item in gain_items[:3]:
                    ui.label(
                        f"Item {item.get('item_number', '—')} · "
                        f"potentiel {item.get('potential_score', 0):g} · "
                        f"{item.get('estimated_minutes', 30):g} min"
                    ).classes("edn-sprint-priority")
