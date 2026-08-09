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


_CSS = """
.oic-panel { width:100%; color:var(--text); }
.oic-panel-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding:14px 20px 12px; border-bottom:1px solid var(--border); }
.oic-panel-title { font-size:13px; font-weight:600; letter-spacing:-.01em; color:var(--text); }
.oic-panel-meta { margin-top:2px; font-size:11px; color:var(--text-muted); }
.oic-panel-summary { display:grid; grid-template-columns:1.1fr 1fr 1fr 1fr; gap:1px;
  margin:0 20px; border:1px solid var(--border); border-radius:8px; overflow:hidden;
  background:var(--border); }
.oic-summary-cell { min-width:0; padding:11px 12px; background:var(--bg); }
.oic-summary-label { font-size:10px; color:var(--text-dim); text-transform:uppercase;
  letter-spacing:.07em; font-weight:600; }
.oic-summary-value { margin-top:4px; font:600 15px var(--font-mono, ui-monospace); color:var(--text); }
.oic-summary-detail { margin-top:3px; font:11px var(--font-mono, ui-monospace); color:var(--text-muted); }
.oic-summary-track { display:flex; gap:3px; margin-top:7px; }
.oic-summary-segment { height:5px; flex:1; min-width:3px; border-radius:2px; background:var(--surface-hover); }
.oic-summary-segment.done { background:var(--accent); }
.oic-panel-list { padding:18px 20px 24px; display:flex; flex-direction:column; gap:20px; }
.oic-rank-header { display:flex; align-items:center; gap:10px; margin-bottom:7px; }
.oic-rank-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.1em; color:var(--text-muted); }
.oic-rank-count { font:11px var(--font-mono, ui-monospace); color:var(--text-dim); }
.oic-rank-rule { flex:1; height:1px; background:var(--border); }
.oic-list { border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.oic-row { display:grid; grid-template-columns:110px minmax(0,1fr) 132px; align-items:center; gap:12px; min-height:58px; padding:9px 10px 9px 12px;
  background:var(--bg); border-bottom:1px solid var(--border); transition:background 140ms ease-out; }
.oic-row > * { min-width:0; box-sizing:border-box; }
.oic-row:last-child { border-bottom:0; }
.oic-row:hover { background:var(--surface-hover); }
.oic-row-mastered { opacity:.62; }
.oic-row-code { width:100%; font:10px var(--font-mono, ui-monospace); color:var(--text-dim); }
.oic-row-main { flex:1; min-width:0; }
.oic-row-title { font-size:12.5px; line-height:1.45; color:var(--text); }
.oic-row-mastered .oic-row-title { color:var(--text-muted); }
.oic-row-meta { margin-top:3px; font-size:10.5px; color:var(--text-dim); }
.oic-row-status { display:flex; align-items:center; justify-content:flex-end; gap:8px; width:100%; min-width:0; }
.oic-level { font:10px var(--font-mono, ui-monospace); color:var(--text-muted); white-space:nowrap; }
.oic-row-action { color:var(--text-muted); }
@media (max-width:640px) {
  .oic-panel-toolbar, .oic-panel-list { padding-left:14px; padding-right:14px; }
  .oic-panel-summary { margin-left:14px; margin-right:14px; grid-template-columns:1fr 1fr; }
  .oic-row { grid-template-columns:78px minmax(0,1fr) 108px; gap:8px; }
  .oic-row-title { font-size:12px; }
}
"""


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
            total = len(rows)
            mastered_total = sum(bool(row.get("mastered")) for row in rows)
            with ui.element("div").classes("oic-panel-toolbar"):
                with ui.column().classes("gap-0"):
                    ui.label("Objectifs d’apprentissage").classes("oic-panel-title")
                    ui.label(f"{total} objectif{'s' if total != 1 else ''} · cache LiSA").classes("oic-panel-meta")
                ui.button("Actualiser", icon="refresh",
                           on_click=lambda: asyncio.ensure_future(self.load(True))).props(
                    "flat dense no-caps"
                ).classes("text-[11px] text-slate-500")
            with ui.element("div").classes("oic-panel-summary"):
                self._summary_cell("Total", str(total), "LiSA")
                for label, rang in (("Rang A", "A"), ("Rang B", "B")):
                    subset = [row for row in rows if row.get("rang") == rang]
                    done = sum(bool(row.get("mastered")) for row in subset)
                    self._summary_cell(label, f"{done}/{len(subset)}", "maîtrisés", done, len(subset))
                self._summary_cell("Maîtrisés", str(mastered_total), f"sur {total}")

    def _summary_cell(self, label: str, value: str, detail: str,
                      done: int | None = None, total: int | None = None) -> None:
        with ui.element("div").classes("oic-summary-cell"):
            ui.label(label).classes("oic-summary-label")
            ui.label(value).classes("oic-summary-value")
            ui.label(detail).classes("oic-summary-detail")
            if done is not None and total:
                with ui.element("div").classes("oic-summary-track"):
                    for index in range(total):
                        ui.element("div").classes(
                            "oic-summary-segment" + (" done" if index < done else "")
                        )

    def render_rows(self, rows: list[dict]) -> None:
        self.rows = rows
        self.render_progress(rows)
        self.content_area.clear()
        with self.content_area:
            with ui.column().classes("oic-panel w-full"):
                if not rows:
                    with ui.column().classes("items-center py-12 gap-2 w-full"):
                        ui.icon("search_off").classes("text-4xl text-slate-300")
                        ui.label("Aucun objectif trouvé sur LiSA pour cet item.").classes("text-sm text-slate-400 italic text-center")
                    return

                with ui.column().classes("oic-panel-list"):
                    for rang_label, rang in (("Rang A", "A"), ("Rang B", "B")):
                        rang_rows = [row for row in rows if row.get("rang") == rang]
                        if not rang_rows:
                            continue
                        with ui.row().classes("oic-rank-header w-full"):
                            ui.label(rang_label).classes("oic-rank-label")
                            ui.label(f"{len(rang_rows)} objectifs").classes("oic-rank-count")
                            ui.element("div").classes("oic-rank-rule")
                        with ui.element("div").classes("oic-list"):
                            for oic in rang_rows:
                                mastered = bool(oic.get("mastered"))
                                code = oic.get("oic_code") or ""
                                icon_name = "check_circle" if mastered else "radio_button_unchecked"
                                row_cls = "oic-row oic-row-mastered" if mastered else "oic-row"

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

                                with ui.element("div").classes(row_cls):
                                    ui.label(code).classes("oic-row-code")
                                    with ui.column().classes("oic-row-main gap-0"):
                                        ui.label(oic.get("intitule", "")).classes("oic-row-title")
                                        if oic.get("rubrique"):
                                            ui.label(oic["rubrique"]).classes("oic-row-meta")
                                    with ui.row().classes("oic-row-status"):
                                        level = int(oic.get("oic_level") or 0)
                                        if level > 0:
                                            _, level_text = _level_badge(level)
                                            ui.label(level_text).classes("oic-level")
                                        ui.button(icon=icon_name).props("flat dense round size=sm").classes(
                                            "oic-row-action"
                                        ).on("click", lambda t=_toggle: asyncio.ensure_future(t())).tooltip(
                                            "Basculer la maîtrise"
                                        )
                                        ui.button(icon="school").props("flat dense round size=sm").classes(
                                            "oic-row-action"
                                        ).on(
                                            "click",
                                            lambda row=oic: open_oic_eval_dialog(
                                                row, self.course,
                                                refresh_fn=lambda: asyncio.ensure_future(_refresh_after_eval()),
                                                course_ids=self.course_ids,
                                            ),
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


def render_oic_panel(
    course,
    content_area,
    progress_area,
    refresh_fn=None,
    course_ids: Sequence[str] | None = None,
    auto_load: bool = True,
) -> OICPanelController:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
    controller = OICPanelController(
        course=course,
        course_ids=tuple(course_ids or [course.id]),
        item_number=str(getattr(course, "display_item_number", "") or ""),
        content_area=content_area,
        progress_area=progress_area,
        refresh_fn=refresh_fn,
    )
    if auto_load:
        asyncio.ensure_future(controller.load())
    return controller
