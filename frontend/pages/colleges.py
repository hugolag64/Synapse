"""
colleges.py — Vue index des collèges médicaux

Layout :
  1. En-tête : titre + stats globales + contrôles
  2. Grille des collèges : cards compactes avec jauge de maîtrise
  3. Section cours : header + filtres + grid CourseCards
"""
from __future__ import annotations

import asyncio

from nicegui import ui

from frontend.theme import frame
from frontend.components.course_card import CourseCard
from frontend.components.sortable_list import SortableList
from backend.state.store import data_store
from backend.core.notion.service import notion_service
from backend.core.reviews.mastery import get_course_mastery, PROGRESSION_COLORS
from backend.core.reviews.service import review_service


# ── Mastery color system ──────────────────────────────────────────────────────

_FILL = {
    "solide":       "#059669",
    "correct":      "#3B82F6",
    "fragile":      "#B45309",
    "non_commence": "#CBD5E1",
}
_GHOST = {
    "solide":       "rgba(5,150,105,0.12)",
    "correct":      "rgba(59,130,246,0.12)",
    "fragile":      "rgba(180,83,9,0.12)",
    "non_commence": "rgba(203,213,225,0.20)",
}
_TINT = {
    "solide":       "rgba(5,150,105,0.05)",
    "correct":      "rgba(59,130,246,0.05)",
    "fragile":      "rgba(180,83,9,0.05)",
    "non_commence": "transparent",
}
_LABEL = {
    "solide":       "Solide",
    "correct":      "Correct",
    "fragile":      "Fragile",
    "non_commence": "Non commencé",
}
_TEXT_CLS = {
    "solide":       "text-green-600 dark:text-green-400",
    "correct":      "text-blue-600 dark:text-blue-400",
    "fragile":      "text-amber-600 dark:text-amber-400",
    "non_commence": "text-slate-400 dark:text-slate-500",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _college_level(pct: float) -> str:
    if pct == 0:
        return "non_commence"
    if pct < 0.35:
        return "fragile"
    if pct < 0.75:
        return "correct"
    return "solide"


def _compute_stats(name: str) -> dict:
    courses = data_store.get_cours_for_college(name)
    total = len(courses)
    started = sum(1 for c in courses if c.date_1ere_lecture)
    pct = started / total if total > 0 else 0.0
    return {
        "total":   total,
        "started": started,
        "pct":     pct,
        "level":   _college_level(pct),
    }


# ── Page ──────────────────────────────────────────────────────────────────────

@ui.page('/colleges')
@frame('Collèges')
def colleges_page():
    if not data_store.is_loaded:
        ui.label("Chargement des données…").classes("text-slate-500")
        return

    prefs = data_store.preferences
    _s = {
        "tab":             prefs.get("college_last_tab", None),
        "sort":            prefs.get("college_sort", "newest"),
        "filter_unread":   False,
        "filter_overdue":  False,
        "filter_no_pdf":   False,
    }

    root = ui.column().classes("w-full gap-0")

    def _refresh_view():
        _show()

    # ── Main render ───────────────────────────────────────────────────────────

    def _show():
        colleges = data_store.get_colleges()
        if not colleges:
            _s["tab"] = None
        elif _s["tab"] not in colleges:
            _s["tab"] = colleges[0]
        tab = _s["tab"]

        all_stats = {name: _compute_stats(name) for name in colleges}

        root.clear()
        with root:

            # ── En-tête ───────────────────────────────────────────────────────
            n_covered   = sum(1 for s in all_stats.values() if s["started"] > 0)
            n_reinforce = sum(1 for s in all_stats.values() if s["level"] in ("fragile", "non_commence"))

            with ui.element("div").classes("w-full flex items-start justify-between gap-4 mb-5"):

                with ui.column().classes("gap-0.5"):
                    ui.label("Collèges médicaux").classes(
                        "synapse-display text-[22px] font-extrabold "
                        "text-slate-900 dark:text-slate-50 tracking-tight leading-none"
                    )
                    ui.label(
                        f"{len(colleges)} spécialités · {n_covered} couvertes · "
                        f"{n_reinforce} à renforcer"
                    ).classes("text-[13px] text-slate-500 dark:text-slate-400 font-medium mt-1")

                with ui.row().classes("items-center gap-1 shrink-0 mt-1"):

                    def open_add_dialog(_tab=tab):
                        _new_title = {"value": ""}
                        _new_item  = {"value": ""}
                        client = ui.context.client

                        async def _confirm(dialog):
                            if not _new_title["value"]:
                                with client:
                                    ui.notify("Le titre ne peut pas être vide", type="warning")
                                return
                            dialog.close()
                            with client:
                                ui.notify("Création du cours sur Notion…", type="info")
                            college_to_use = _tab if _tab and _tab != "Tout" else "Indéfini"
                            success = await notion_service.create_course_college(
                                title=_new_title["value"],
                                college=college_to_use,
                                item_number=_new_item["value"],
                            )
                            if success:
                                with client:
                                    ui.notify("Cours ajouté ! Synchronisation…", type="positive")
                                await data_store.refresh()
                                with client:
                                    _show()
                            else:
                                with client:
                                    ui.notify("Erreur lors de la création", type="negative")

                        with ui.dialog() as dlg, ui.card().classes("w-96 p-5"):
                            ui.label(f"Ajouter un cours : {_tab}").classes("text-base font-bold mb-2")
                            ui.input("Titre du cours").bind_value(_new_title, "value").classes("w-full").props("autofocus")
                            ui.input("Numéro ITEM (ex: 231)").bind_value(_new_item, "value").classes("w-full")
                            with ui.row().classes("w-full justify-end mt-4 gap-2"):
                                ui.button("Annuler", on_click=dlg.close).props("flat color=slate")
                                ui.button(
                                    "Ajouter",
                                    on_click=lambda: asyncio.create_task(_confirm(dlg)),
                                ).props("unelevated color=green")
                        dlg.open()

                    ui.button(icon="add", on_click=open_add_dialog).props(
                        "flat round dense size=sm"
                    ).classes("text-green-500").tooltip("Ajouter un cours")

                    _sync_btn = ui.button(icon="refresh").props(
                        "flat round dense size=sm"
                    ).classes("text-slate-400").tooltip("Synchroniser Notion")

                    async def _sync():
                        _sync_btn.props(add="loading")
                        try:
                            await data_store.refresh()
                            _show()
                            ui.notify("Données à jour ✓", type="positive", timeout=1500)
                        except Exception as e:
                            ui.notify(f"Erreur sync : {e}", type="negative")
                        finally:
                            _sync_btn.props(remove="loading")

                    _sync_btn.on_click(_sync)

            # ── Légende maîtrise ──────────────────────────────────────────────
            with ui.row().classes("items-center gap-4 mb-4 flex-wrap"):
                ui.label("Couverture :").classes("text-[11px] text-slate-400 dark:text-slate-500 font-medium shrink-0")
                for _lvl_key, _lvl_color, _lvl_name in [
                    ("solide",       "#059669", "Solide"),
                    ("correct",      "#3B82F6", "Correct"),
                    ("fragile",      "#D97706", "Fragile"),
                    ("non_commence", "#CBD5E1", "Non commencé"),
                ]:
                    with ui.row().classes("items-center gap-1 shrink-0"):
                        ui.element("div").style(
                            f"width:8px;height:8px;border-radius:50%;background:{_lvl_color};flex-shrink:0;"
                        )
                        ui.label(_lvl_name).classes("text-[11px] text-slate-500 dark:text-slate-400")

            # ── Grille des collèges ───────────────────────────────────────────

            def _select(name: str):
                _s["tab"] = name
                data_store.set_preference("college_last_tab", name)
                _show()

            def _handle_sort(event):
                try:
                    new_order = event.get("order")
                    if new_order and isinstance(new_order, list):
                        valid = [x for x in new_order if x]
                        data_store.update_colleges_order(valid)
                except Exception as e:
                    print(f"SortableList error: {e}")

            with SortableList(on_change=_handle_sort).classes(
                "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 w-full mb-6"
            ):
                for name in colleges:
                    s        = all_stats[name]
                    is_active = (name == tab)
                    fill_c   = _FILL[s["level"]]
                    ghost_c  = _GHOST[s["level"]]
                    tint_c   = _TINT[s["level"]]
                    txt_cls  = _TEXT_CLS[s["level"]]
                    pct_int  = int(s["pct"] * 100)

                    # Border-top : solid (actif) ou hint à 20% (passif)
                    if is_active:
                        top_style = f"border-top:3px solid {fill_c};background:{tint_c};"
                    else:
                        # hex 33 = ~20% opacity
                        top_style = f"border-top:2px solid {fill_c}33;"

                    with ui.element("div").classes(
                        "college-index-card cursor-move w-full"
                    ).style(top_style).props(
                        f'data-id="{name}"'
                    ).on("click", lambda n=name: _select(n)):

                        # Nom + count
                        with ui.column().classes("w-full px-3 pt-3 pb-1.5 gap-0.5"):
                            ui.label(name).classes("college-index-name").style(
                                "display:-webkit-box;-webkit-line-clamp:2;"
                                "-webkit-box-orient:vertical;overflow:hidden"
                            )
                            ui.label(f"{s['total']} cours").classes(
                                "text-[11px] text-slate-400 dark:text-slate-500"
                            )

                        # Stats
                        with ui.row().classes("w-full items-center justify-between px-3 pb-2"):
                            ui.label(f"{s['started']}/{s['total']}").classes(
                                f"text-[11px] font-bold tabular-nums {txt_cls}"
                            )
                            if pct_int > 0:
                                ui.label(f"{pct_int}%").classes(
                                    f"text-[11px] font-semibold tabular-nums {txt_cls}"
                                )
                            else:
                                ui.label("—").classes(
                                    "text-[11px] text-slate-300 dark:text-slate-600"
                                )

                        # Jauge de maîtrise — flush bottom
                        with ui.element("div").style(
                            f"height:5px;width:100%;background:{ghost_c};overflow:hidden;flex-shrink:0;"
                        ):
                            ui.element("div").style(
                                f"height:100%;width:{pct_int}%;background:{fill_c};"
                                "transition:width 600ms cubic-bezier(0.4,0,0.2,1);"
                            )

            # ── Section cours ─────────────────────────────────────────────────
            if not tab:
                with ui.column().classes("w-full items-center py-12 gap-2"):
                    ui.icon("school", size="4em").classes("text-slate-200 dark:text-slate-700")
                    ui.label("Sélectionne un collège pour voir ses cours").classes(
                        "text-sm text-slate-400 dark:text-slate-500"
                    )
                return

            courses = data_store.get_cours_for_college(tab)
            courses.sort(
                key=lambda x: x.created_time,
                reverse=(_s["sort"] == "newest"),
            )

            _urgent_ids = review_service.get_urgent_course_ids("college")

            def _is_urgent(c) -> bool:
                return c.id in _urgent_ids

            s_tab     = all_stats.get(tab, {})
            fill_tab  = _FILL.get(s_tab.get("level", "non_commence"), "#CBD5E1")
            level_lbl = _LABEL.get(s_tab.get("level", "non_commence"), "—")
            txt_tab   = _TEXT_CLS.get(s_tab.get("level", "non_commence"), "text-slate-400")

            # ── Règle de section ──────────────────────────────────────────────
            with ui.element("div").classes("w-full flex items-center gap-3 mb-4"):
                ui.element("div").classes("h-px flex-1 bg-slate-200 dark:bg-slate-700")
                ui.label(tab.upper()).classes(
                    "text-[11px] font-bold tracking-widest "
                    "text-slate-700 dark:text-slate-300 shrink-0 uppercase"
                )
                ui.label(
                    f"·  {s_tab.get('total', 0)} cours  ·  "
                    f"{s_tab.get('started', 0)} lus  ·  {level_lbl}"
                ).classes("text-[11px] text-slate-400 dark:text-slate-500 shrink-0")
                ui.element("div").classes("h-px flex-1 bg-slate-200 dark:bg-slate-700")

            # ── Barre de couverture + filtres + tri ───────────────────────────
            _total = s_tab.get("total", 0)
            _lus   = s_tab.get("started", 0)
            _pct   = s_tab.get("pct", 0.0)

            with ui.element("div").classes("w-full mb-4"):

                # Barre de couverture
                with ui.row().classes("w-full items-center gap-3 mb-3"):
                    ui.label(f"{_lus}/{_total} cours lus").classes(
                        f"text-[11px] font-bold shrink-0 {txt_tab}"
                    )
                    with ui.element("div").classes(
                        "flex-1 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden"
                    ):
                        ui.element("div").style(
                            f"height:100%;width:{int(_pct * 100)}%;background:{fill_tab};"
                            "border-radius:999px;transition:width 500ms ease;"
                        )
                    _not_done = _total - _lus
                    if _not_done > 0:
                        ui.label(
                            f"{_not_done} restant{'s' if _not_done > 1 else ''}"
                        ).classes("text-[11px] text-slate-400 dark:text-slate-500 shrink-0")
                    else:
                        ui.label("✓ Couvert").classes(
                            "text-[11px] text-green-500 font-semibold shrink-0"
                        )

                # Filtres + tri
                _any_filter = (
                    _s["filter_unread"] or _s["filter_overdue"] or _s["filter_no_pdf"]
                )

                def _reset():
                    _s["filter_unread"] = False
                    _s["filter_overdue"] = False
                    _s["filter_no_pdf"] = False
                    _show()

                def _toggle_unread():
                    _s["filter_unread"] = not _s["filter_unread"]
                    _show()

                def _toggle_overdue():
                    _s["filter_overdue"] = not _s["filter_overdue"]
                    _show()

                def _toggle_no_pdf():
                    _s["filter_no_pdf"] = not _s["filter_no_pdf"]
                    _show()

                with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                    ui.label("Filtres :").classes(
                        "text-[11px] font-bold text-slate-400 uppercase tracking-wide"
                    )
                    ui.button("Tout", icon="filter_list_off", on_click=_reset).props(
                        f"{'unelevated' if not _any_filter else 'outline'} rounded size=sm "
                        f"color={'slate' if not _any_filter else 'grey'}"
                    ).tooltip("Réinitialiser")
                    ui.button("Jamais lus", icon="visibility_off", on_click=_toggle_unread).props(
                        f"{'unelevated' if _s['filter_unread'] else 'outline'} rounded size=sm "
                        f"color={'blue' if _s['filter_unread'] else 'grey'}"
                    ).tooltip("Cours non lus (0 lecture)")
                    ui.button("En retard J30", icon="alarm", on_click=_toggle_overdue).props(
                        f"{'unelevated' if _s['filter_overdue'] else 'outline'} rounded size=sm "
                        f"color={'red' if _s['filter_overdue'] else 'grey'}"
                    ).tooltip("J30 dépassé de 2+ jours")
                    ui.button("Sans PDF", icon="picture_as_pdf", on_click=_toggle_no_pdf).props(
                        f"{'unelevated' if _s['filter_no_pdf'] else 'outline'} rounded size=sm "
                        f"color={'amber' if _s['filter_no_pdf'] else 'grey'}"
                    ).tooltip("Cours sans PDF lié")

                    ui.element("div").classes("flex-1")

                    ui.select(
                        options={"newest": "Plus récent", "oldest": "Plus ancien"},
                        label="Trier",
                        value=_s["sort"],
                        on_change=lambda e: (
                            _s.update({"sort": e.value}),
                            data_store.set_preference("college_sort", e.value),
                            _show(),
                        ),
                    ).classes("w-36 shrink-0")

            # Appliquer filtres
            if _s["filter_unread"]:
                courses = [c for c in courses if (c.nb_lectures or 0) == 0]
            if _s["filter_overdue"]:
                courses = [c for c in courses if _is_urgent(c)]
            if _s["filter_no_pdf"]:
                courses = [c for c in courses if not getattr(c, "url_pdf", None)]

            # État vide
            if not courses:
                with ui.column().classes("w-full items-center py-10 gap-2"):
                    ui.icon("school", size="3em").classes(
                        "text-slate-200 dark:text-slate-700 opacity-60"
                    )
                    ui.label("Aucun cours pour ce filtrage").classes(
                        "text-sm text-slate-400 dark:text-slate-500 italic"
                    )
                return

            # Grid de cours
            try:
                parent_client = ui.context.client
            except Exception:
                parent_client = None

            with ui.grid().classes("grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 w-full"):
                for cours in courses:
                    urgent   = _is_urgent(cours)
                    _mastery = get_course_mastery(cours, context="college")
                    _accent  = None if urgent else PROGRESSION_COLORS.get(_mastery.level)
                    CourseCard(
                        cours,
                        context="college",
                        refresh_fn=_refresh_view,
                        client=parent_client,
                        is_urgent=urgent,
                        accent_color=_accent,
                    )

    _show()
