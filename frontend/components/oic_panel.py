"""Shared inline OIC renderer used by the classic dialog and item cockpit."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from collections.abc import Sequence

from nicegui import ui

from backend.config.settings import settings
from backend.core.lisa import item_service
from backend.core.lisa.scraper import LisaFetchError, scrape_oic
from backend.core.reviews import local_store
from frontend.components.oic_eval_dialog import open_oic_eval_dialog


def should_load_on_tab_activation(active_tab: str, loaded: bool) -> bool:
    return active_tab == "OIC" and not loaded


def _level_badge(level: int) -> tuple[str, str]:
    if level >= 5:
        return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300", "★ Maîtrisé"
    if level >= 3:
        return "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300", f"Lvl {level}"
    return "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300", f"Lvl {level}"


@dataclass
class OICPanelController:
    course: object
    course_ids: Sequence[str]
    item_number: str
    content_area: object
    progress_area: object
    refresh_fn: object = None
    loaded: bool = False
    rows: list[dict] | None = None

    def _segment(self, mastered: int, total: int, color: str) -> str:
        blocks = "".join(
            f'<div style="width:8px;height:8px;border-radius:2px;flex-shrink:0;background:{color if i < mastered else "#cbd5e1"}"></div>'
            for i in range(total)
        )
        return f'<div style="display:flex;gap:3px;align-items:center">{blocks}</div>'

    def render_progress(self, rows: list[dict]) -> None:
        self.progress_area.clear()
        with self.progress_area:
            for label, rang, color, label_cls in (
                ("Rang A", "A", "#7c3aed", "text-violet-600 dark:text-violet-400"),
                ("Rang B", "B", "#0ea5e9", "text-sky-600 dark:text-sky-400"),
            ):
                subset = [row for row in rows if row.get("rang") == rang]
                mastered = sum(bool(row.get("mastered")) for row in subset)
                if not subset:
                    continue
                with ui.row().classes("items-center gap-2"):
                    ui.label(label).classes(f"text-[10px] font-bold uppercase tracking-wider {label_cls} w-12 shrink-0")
                    ui.html(self._segment(mastered, len(subset), color), sanitize=False)
                    done_cls = "text-emerald-600 font-semibold" if mastered == len(subset) else "text-slate-500"
                    ui.label(f"{mastered}/{len(subset)}").classes(f"text-[11px] tabular-nums {done_cls}")

    def render_rows(self, rows: list[dict]) -> None:
        self.rows = rows
        self.render_progress(rows)
        self.content_area.clear()
        with self.content_area:
            with ui.column().classes("px-4 py-4 gap-5 w-full"):
                if not rows:
                    with ui.column().classes("items-center py-12 gap-2 w-full"):
                        ui.icon("search_off").classes("text-4xl text-slate-300")
                        ui.label("Aucun objectif trouvé sur LiSA pour cet item.").classes("text-sm text-slate-400 italic text-center")
                    return

                for rang_label, rang, accent, hover_cls, label_cls in (
                    ("RANG A", "A", "#7c3aed", "hover:bg-violet-50 dark:hover:bg-violet-900/20", "text-violet-600 dark:text-violet-400"),
                    ("RANG B", "B", "#0ea5e9", "hover:bg-sky-50 dark:hover:bg-sky-900/20", "text-sky-600 dark:text-sky-400"),
                ):
                    rang_rows = [row for row in rows if row.get("rang") == rang]
                    if not rang_rows:
                        continue
                    with ui.row().classes("items-center gap-3 w-full"):
                        ui.label(rang_label).classes(f"text-[9px] font-bold uppercase tracking-widest {label_cls} shrink-0")
                        ui.element("div").classes("flex-1 h-px bg-slate-200 dark:bg-slate-700")
                    with ui.column().classes("gap-1.5 w-full"):
                        for oic in rang_rows:
                            mastered = bool(oic.get("mastered"))
                            code = oic.get("oic_code") or ""
                            border = "#10b981" if mastered else accent
                            row_bg = "bg-emerald-50/70 dark:bg-emerald-900/10" if mastered else "bg-white dark:bg-slate-800/30"
                            icon_name = "check_circle" if mastered else "radio_button_unchecked"
                            icon_cls = "text-emerald-500" if mastered else "text-slate-300 dark:text-slate-600"
                            text_cls = "text-slate-400 dark:text-slate-500" if mastered else "text-slate-700 dark:text-slate-200"

                            async def _toggle(row=oic):
                                await asyncio.to_thread(
                                    item_service.set_item_oic_mastery,
                                    self.course_ids, row.get("oic_code"), not bool(row.get("mastered")),
                                )
                                await self.load_cached()

                            async def _refresh_after_eval():
                                await self.load_cached()
                                if self.refresh_fn:
                                    self.refresh_fn()

                            with ui.element("div").classes(
                                f"flex items-stretch gap-0 rounded-xl overflow-hidden border border-slate-100 dark:border-slate-700/50 {row_bg} {hover_cls} cursor-pointer transition-colors duration-150 w-full"
                            ).on("click", lambda t=_toggle: asyncio.ensure_future(t())):
                                ui.element("div").style(f"width:4px;flex-shrink:0;background:{border}")
                                with ui.row().classes("flex-1 items-start gap-3 px-3 py-2.5 min-w-0"):
                                    with ui.column().classes("flex-1 gap-0.5 min-w-0"):
                                        if code:
                                            ui.label(code).classes("text-[9px] font-mono uppercase tracking-wider text-slate-400 dark:text-slate-500")
                                        ui.label(oic.get("intitule", "")).classes(f"text-[13px] leading-snug {text_cls}")
                                    with ui.column().classes("items-end gap-1 shrink-0"):
                                        ui.icon(icon_name).classes(f"text-[20px] mt-0.5 {icon_cls}")
                                        level = int(oic.get("oic_level") or 0)
                                        if level > 0:
                                            level_cls, level_text = _level_badge(level)
                                            ui.label(level_text).classes(f"text-[8px] font-bold px-1.5 py-0.5 rounded {level_cls}")
                                        ui.button(icon="school").props("flat dense round size=xs").classes("text-violet-400 hover:text-violet-600").on(
                                            "click.stop",
                                            lambda row=oic: open_oic_eval_dialog(row, self.course, refresh_fn=lambda: asyncio.ensure_future(_refresh_after_eval())),
                                        ).tooltip("Évaluer cet OIC")

    async def load_cached(self) -> None:
        rows = await asyncio.to_thread(item_service.get_item_oics, self.course_ids)
        self.loaded = True
        self.render_rows(rows)

    async def load(self, force: bool = False) -> None:
        if not force:
            await self.load_cached()
            has_cache = any(local_store.get_lisa_oic(course_id) is not None for course_id in self.course_ids)
            if has_cache:
                return

        self.content_area.clear()
        with self.content_area:
            with ui.column().classes("items-center py-14 gap-3 w-full"):
                ui.spinner(size="lg").classes("text-violet-600")
                ui.label("Chargement depuis LiSA…").classes("text-sm text-slate-500")
        try:
            oics = await asyncio.to_thread(scrape_oic, self.course.title or "", self.item_number)
            await asyncio.to_thread(local_store.upsert_lisa_oic, self.course_ids[0], oics)
            await self.load_cached()
        except LisaFetchError as exc:
            self.content_area.clear()
            with self.content_area:
                with ui.column().classes("items-center py-10 gap-3 w-full"):
                    ui.icon("wifi_off").classes("text-4xl text-red-400")
                    ui.label("LiSA inaccessible").classes("text-sm font-semibold text-slate-700 dark:text-slate-300")
                    ui.label(str(exc)).classes("text-xs text-slate-400 text-center px-6")
                    ui.button("Réessayer", icon="refresh", on_click=lambda: asyncio.ensure_future(self.load(True))).props("unelevated color=violet size=sm rounded")


def render_oic_panel(course, content_area, progress_area, refresh_fn=None, course_ids: Sequence[str] | None = None) -> OICPanelController:
    controller = OICPanelController(
        course=course,
        course_ids=tuple(course_ids or [course.id]),
        item_number=str(getattr(course, "display_item_number", "") or ""),
        content_area=content_area,
        progress_area=progress_area,
        refresh_fn=refresh_fn,
    )
    asyncio.ensure_future(controller.load())
    return controller
