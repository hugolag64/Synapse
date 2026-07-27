"""Compatibility dialog wrapper for the shared inline OIC panel."""
from __future__ import annotations

from nicegui import ui

from frontend.components.oic_panel import render_oic_panel


def open_lisa_dialog(course, refresh_fn=None) -> None:
    """Open the legacy LiSA dialog while sharing the cockpit OIC renderer."""
    item_number = str(getattr(course, "display_item_number", "") or "")
    with ui.dialog() as dialog, ui.card().classes(
        "w-[680px] max-w-[95vw] p-0 overflow-hidden rounded-2xl shadow-2xl"
    ):
        with ui.element("div").style(
            "background:linear-gradient(135deg,#4c1d95 0%,#1e293b 100%);padding:1.1rem 1.25rem 1rem;"
        ):
            with ui.row().classes("items-start justify-between w-full gap-3"):
                with ui.column().classes("gap-0.5 flex-1 min-w-0"):
                    if item_number:
                        ui.label(f"ITEM {item_number}").classes("text-[9px] font-bold uppercase tracking-widest text-violet-300 opacity-80")
                    ui.label(course.title or "").classes("text-[15px] font-bold text-white leading-snug").style("word-break:break-word")
                    ui.label("Objectifs intermédiaires de connaissance · LiSA").classes("text-[10px] text-slate-400 mt-0.5")
                ui.button(icon="close", on_click=dialog.close).props("flat dense round size=sm").classes("text-slate-400 hover:text-white")

        progress_area = ui.element("div").classes(
            "px-5 py-3 flex items-center gap-6 flex-wrap border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60"
        )
        content_area = ui.element("div").classes("overflow-y-auto w-full").style("max-height:56vh")

    controller = render_oic_panel(course, content_area, progress_area, refresh_fn=refresh_fn)
    ui.button(icon="refresh", on_click=lambda: __import__("asyncio").ensure_future(controller.load(True))).props(
        "flat dense round size=sm"
    ).style("position:absolute;top:12px;right:48px;z-index:2").tooltip("Recharger depuis LiSA")
    if refresh_fn:
        dialog.on("hide", refresh_fn)
    dialog.open()
