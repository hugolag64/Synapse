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


def render_edn_insights_panel(status, projections=(), gain_items=()) -> None:
    model = edn_insights_model(status)
    with ui.element("div").classes("w-full p-4 mb-4 rounded-lg border border-indigo-200 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/20"):
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.column().classes("gap-0"):
                ui.label(f"Sprint EDN · {model['countdown']}").classes("text-sm font-semibold")
                ui.label(f"Objectif {model['target']} · phase {model['phase']}").classes("text-xs text-slate-500")
            with ui.row().classes("gap-4 text-xs"):
                ui.label(f"Items {model['coverage']}")
                ui.label(f"Maîtrise {model['mastery']}")
                ui.label(f"Retard {model['overdue']}")
                ui.label(f"Restant {model['remaining']}")
        if projections:
            with ui.row().classes("gap-2 mt-3 flex-wrap"):
                for projection in projections:
                    ui.label(
                        f"{projection.name.title()} · {projection.projected_coverage:g}% couverture"
                    ).classes("text-[11px] px-2 py-1 rounded bg-white/70 dark:bg-slate-900/50")
        if gain_items:
            ui.label("Priorités de gain relatives").classes("text-xs font-semibold mt-3")
            with ui.column().classes("w-full gap-1 mt-1"):
                for item in gain_items[:3]:
                    ui.label(
                        f"Item {item.get('item_number', '—')} · "
                        f"potentiel {item.get('potential_score', 0):g} · "
                        f"{item.get('estimated_minutes', 30):g} min"
                    ).classes("text-[11px] text-slate-600 dark:text-slate-300")
