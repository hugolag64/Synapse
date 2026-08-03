"""Cartes de pilotage EDN pour le Dashboard."""

from __future__ import annotations

from nicegui import ui


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


def render_edn_insights_panel(status, projections=()) -> None:
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
