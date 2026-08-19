"""Ligne UI d'une préparation de cours FAC."""

from __future__ import annotations

from nicegui import ui


_LABELS = {
    "pdf": ("Lier le PDF", "picture_as_pdf"),
    "obsidian": ("Faire la fiche Obsidian", "edit_note"),
    "resume": ("Faire le résumé", "summarize"),
    "first_read": ("Faire une première lecture", "menu_book"),
}


def course_prep_task_row(task, *, on_open, on_validate) -> None:
    label, icon = _LABELS.get(task.task_type, (task.task_type, "task"))
    with ui.card().classes("w-full p-3 border border-amber-200 bg-amber-50/40"):
        with ui.row().classes("w-full items-center gap-3"):
            ui.icon(icon).classes("text-amber-700")
            with ui.column().classes("gap-0 flex-1 min-w-0"):
                item = f"ITEM {task.item_number}" if task.item_number else "Cours FAC"
                ui.label(f"{item} · {label}").classes("font-medium text-sm")
                ui.label(task.calendar_title or "Cours à préparer").classes(
                    "text-xs text-slate-500 truncate"
                )
            ui.button("Ouvrir", icon="open_in_new", on_click=lambda: on_open(task)).props(
                "flat dense color=amber-9"
            )
            ui.button("Valider", icon="check", on_click=lambda: on_validate(task)).props(
                "unelevated dense color=amber-8"
            )
