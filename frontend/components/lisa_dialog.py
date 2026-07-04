"""
lisa_dialog.py — Synapse
--------------------------
Dialog OIC LiSA : header violet, liste par rang, progression segmentée,
toggle maîtrise par clic sur la ligne entière.
"""
from __future__ import annotations

import asyncio
from nicegui import ui

from backend.core.reviews import local_store as ls
from backend.core.lisa.scraper import scrape_oic, LisaFetchError
from frontend.components.oic_eval_dialog import open_oic_eval_dialog


def open_lisa_dialog(course) -> None:
    """Ouvre la dialog OIC pour un cours. Scrappe LiSA si pas encore en cache."""
    course_id    = course.id
    course_title = course.title or ""
    item_number  = str(getattr(course, "display_item_number", "") or "")

    with ui.dialog() as dialog, ui.card().classes(
        "w-[680px] max-w-[95vw] p-0 overflow-hidden rounded-2xl shadow-2xl"
    ):
        # ── Header dégradé ────────────────────────────────────────────────────
        with ui.element("div").style(
            "background:linear-gradient(135deg,#4c1d95 0%,#1e293b 100%);"
            "padding:1.1rem 1.25rem 1rem 1.25rem;"
        ):
            with ui.row().classes("items-start justify-between w-full gap-3"):
                with ui.column().classes("gap-0.5 flex-1 min-w-0"):
                    if item_number:
                        ui.label(f"ITEM {item_number}").classes(
                            "text-[9px] font-bold uppercase tracking-widest "
                            "text-violet-300 opacity-80"
                        )
                    ui.label(course_title).classes(
                        "text-[15px] font-bold text-white leading-snug"
                    ).style("word-break:break-word")
                    ui.label("Objectifs intermédiaires de connaissance · LiSA").classes(
                        "text-[10px] text-slate-400 mt-0.5"
                    )

                with ui.row().classes("items-center gap-0.5 shrink-0 -mt-1 -mr-1"):
                    ui.button(
                        icon="refresh",
                        on_click=lambda: asyncio.ensure_future(_reload()),
                    ).props("flat dense round size=sm").classes(
                        "text-slate-400 hover:text-white transition-colors"
                    ).tooltip("Recharger depuis LiSA")
                    ui.button(
                        icon="close",
                        on_click=dialog.close,
                    ).props("flat dense round size=sm").classes(
                        "text-slate-400 hover:text-white transition-colors"
                    )

        # ── Progression segmentée ─────────────────────────────────────────────
        progress_area = ui.element("div").classes(
            "px-5 py-3 flex items-center gap-6 flex-wrap "
            "border-b border-slate-100 dark:border-slate-800 "
            "bg-slate-50 dark:bg-slate-900/60"
        )

        # ── Zone de contenu scrollable ────────────────────────────────────────
        content_area = ui.element("div").classes(
            "overflow-y-auto w-full"
        ).style("max-height:56vh")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _seg_html(mastered: int, total: int, color_on: str) -> str:
        blocks = "".join(
            f'<div style="width:8px;height:8px;border-radius:2px;flex-shrink:0;'
            f'background:{"" + color_on if i < mastered else "#cbd5e1"}"></div>'
            for i in range(total)
        )
        return f'<div style="display:flex;gap:3px;align-items:center">{blocks}</div>'

    # ── Rendu progression ─────────────────────────────────────────────────────

    def _render_progress(oics: list) -> None:
        progress_area.clear()
        rang_a = [o for o in oics if o["rang"] == "A"]
        rang_b = [o for o in oics if o["rang"] == "B"]
        ma, ta = sum(1 for o in rang_a if o["mastered"]), len(rang_a)
        mb, tb = sum(1 for o in rang_b if o["mastered"]), len(rang_b)

        with progress_area:
            for label, m, t, seg_color, label_cls in (
                ("Rang A", ma, ta, "#7c3aed", "text-violet-600 dark:text-violet-400"),
                ("Rang B", mb, tb, "#0ea5e9",  "text-sky-600 dark:text-sky-400"),
            ):
                if t == 0:
                    continue
                with ui.row().classes("items-center gap-2"):
                    ui.label(label).classes(
                        f"text-[10px] font-bold uppercase tracking-wider {label_cls} w-12 shrink-0"
                    )
                    ui.html(_seg_html(m, t, seg_color))
                    done_cls = "text-emerald-600 font-semibold" if m == t else "text-slate-500"
                    ui.label(f"{m}/{t}").classes(f"text-[11px] tabular-nums {done_cls}")

    # ── Rendu liste OIC ───────────────────────────────────────────────────────

    def _level_badge(level: int) -> tuple[str, str]:
        if level >= 5:
            return (
                "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
                "★ Maîtrisé",
            )
        if level >= 3:
            return "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300", f"Lvl {level}"
        return "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300", f"Lvl {level}"

    def _render_oics(oics: list) -> None:
        _render_progress(oics)
        content_area.clear()
        with content_area:
            with ui.column().classes("px-4 py-4 gap-5 w-full"):

                if not oics:
                    with ui.column().classes("items-center py-12 gap-2 w-full"):
                        ui.icon("search_off").classes("text-4xl text-slate-300")
                        ui.label("Aucun objectif trouvé sur LiSA pour ce cours.").classes(
                            "text-sm text-slate-400 italic text-center"
                        )
                    return

                rang_a = [o for o in oics if o["rang"] == "A"]
                rang_b = [o for o in oics if o["rang"] == "B"]

                for rang_label, rang_oics, accent, hover_cls, label_cls in (
                    (
                        "RANG A", rang_a, "#7c3aed",
                        "hover:bg-violet-50 dark:hover:bg-violet-900/20",
                        "text-violet-600 dark:text-violet-400",
                    ),
                    (
                        "RANG B", rang_b, "#0ea5e9",
                        "hover:bg-sky-50 dark:hover:bg-sky-900/20",
                        "text-sky-600 dark:text-sky-400",
                    ),
                ):
                    if not rang_oics:
                        continue

                    # En-tête de section
                    with ui.row().classes("items-center gap-3 w-full"):
                        ui.label(rang_label).classes(
                            f"text-[9px] font-bold uppercase tracking-widest {label_cls} shrink-0"
                        )
                        ui.element("div").classes(
                            "flex-1 h-px bg-slate-200 dark:bg-slate-700"
                        )

                    # Lignes OIC
                    with ui.column().classes("gap-1.5 w-full"):
                        for oic in rang_oics:
                            oic_id      = oic["id"]
                            is_mastered = bool(oic["mastered"])
                            oic_code    = oic["oic_code"] or ""

                            border = "#10b981" if is_mastered else accent
                            row_bg = (
                                "bg-emerald-50/70 dark:bg-emerald-900/10"
                                if is_mastered else
                                "bg-white dark:bg-slate-800/30"
                            )
                            icon_name = "check_circle" if is_mastered else "radio_button_unchecked"
                            icon_cls  = (
                                "text-emerald-500" if is_mastered
                                else "text-slate-300 dark:text-slate-600"
                            )
                            text_cls  = (
                                "text-slate-400 dark:text-slate-500"
                                if is_mastered else
                                "text-slate-700 dark:text-slate-200"
                            )

                            async def _toggle(oid=oic_id):
                                await asyncio.to_thread(ls.toggle_lisa_oic_mastery, oid)
                                updated = (await asyncio.to_thread(ls.get_lisa_oic, course_id)) or []
                                _render_oics(updated)

                            async def _refresh_after_eval(cid=course_id):
                                updated = (await asyncio.to_thread(ls.get_lisa_oic, cid)) or []
                                _render_oics(updated)

                            with ui.element("div").classes(
                                f"flex items-stretch gap-0 rounded-xl overflow-hidden "
                                f"border border-slate-100 dark:border-slate-700/50 "
                                f"{row_bg} {hover_cls} cursor-pointer "
                                "transition-colors duration-150 w-full"
                            ).on("click", lambda t=_toggle: asyncio.ensure_future(t())):
                                # Bordure gauche colorée
                                ui.element("div").style(
                                    f"width:4px;flex-shrink:0;background:{border}"
                                )
                                # Contenu
                                with ui.row().classes(
                                    "flex-1 items-start gap-3 px-3 py-2.5 min-w-0"
                                ):
                                    with ui.column().classes("flex-1 gap-0.5 min-w-0"):
                                        if oic_code:
                                            ui.label(oic_code).classes(
                                                "text-[9px] font-mono uppercase tracking-wider "
                                                "text-slate-400 dark:text-slate-500"
                                            )
                                        ui.label(oic["intitule"]).classes(
                                            f"text-[13px] leading-snug {text_cls}"
                                        )
                                    with ui.column().classes("items-end gap-1 shrink-0"):
                                        ui.icon(icon_name).classes(f"text-[20px] mt-0.5 {icon_cls}")
                                        level = oic["oic_level"] or 0
                                        if level > 0:
                                            level_cls, level_text = _level_badge(level)
                                            ui.label(level_text).classes(
                                                f"text-[8px] font-bold px-1.5 py-0.5 rounded {level_cls}"
                                            )
                                        ui.button(icon="school").props(
                                            "flat dense round size=xs"
                                        ).classes(
                                            "text-violet-400 hover:text-violet-600"
                                        ).on(
                                            "click.stop",
                                            lambda o=oic: open_oic_eval_dialog(
                                                o, course,
                                                refresh_fn=lambda: asyncio.ensure_future(_refresh_after_eval()),
                                            ),
                                        ).tooltip("Évaluer cet OIC")

    # ── Chargement async ──────────────────────────────────────────────────────

    async def _load(force: bool = False) -> None:
        cached = ls.get_lisa_oic(course_id)

        if cached is not None and not force:
            _render_oics(cached)
            return

        content_area.clear()
        with content_area:
            with ui.column().classes("items-center py-14 gap-3 w-full"):
                ui.spinner(size="lg").classes("text-violet-600")
                ui.label("Chargement depuis LiSA…").classes(
                    "text-sm text-slate-500"
                )

        try:
            oics = await asyncio.to_thread(scrape_oic, course_title, item_number)
            ls.upsert_lisa_oic(course_id, oics)
            fresh = (await asyncio.to_thread(ls.get_lisa_oic, course_id)) or []
            _render_oics(fresh)
        except LisaFetchError as exc:
            err_str = str(exc)
            is_auth = any(k in err_str.lower() for k in ("permission", "login", "read permission", "not logged"))
            content_area.clear()
            with content_area:
                with ui.column().classes("items-center py-10 gap-3 w-full"):
                    ui.icon("lock" if is_auth else "wifi_off").classes(
                        f"text-4xl {'text-amber-400' if is_auth else 'text-red-400'}"
                    )
                    ui.label(
                        "Cookie LiSA expiré" if is_auth else "LiSA inaccessible"
                    ).classes("text-sm font-semibold text-slate-700 dark:text-slate-300")
                    ui.label(
                        "Ta session LiSA a expiré. Copie le cookie depuis DevTools et mets-le à jour dans Paramètres → LiSA."
                        if is_auth else err_str
                    ).classes("text-xs text-slate-400 text-center px-6")
                    with ui.row().classes("gap-2"):
                        if is_auth:
                            ui.button(
                                "Paramètres",
                                icon="settings",
                                on_click=lambda: ui.navigate.to("/settings"),
                            ).props("unelevated color=amber size=sm rounded")
                        ui.button(
                            "Réessayer",
                            icon="refresh",
                            on_click=lambda: asyncio.ensure_future(_load(True)),
                        ).props("unelevated color=violet size=sm rounded")

    async def _reload() -> None:
        await _load(force=True)

    ui.timer(0.05, lambda: asyncio.ensure_future(_load()), once=True)
    dialog.open()
