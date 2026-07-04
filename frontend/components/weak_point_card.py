"""
weak_point_card.py — Synapse
Card component for a lacune (weak point).
"""
from __future__ import annotations

import datetime
import webbrowser
from nicegui import ui
from backend.core.reviews import local_store
from backend.state.store import data_store


# Severity → left stripe color (the signature visual element)
_SEV_STRIPE = {
    1: "border-l-slate-200 dark:border-l-slate-600",
    2: "border-l-slate-300 dark:border-l-slate-500",
    3: "border-l-amber-400",
    4: "border-l-orange-500",
    5: "border-l-red-500",
}

# Status → (pill bg+text classes, icon name)
_STATUS_PILL: dict[str, tuple[str, str]] = {
    "active":     ("bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400",       "radio_button_checked"),
    "à revoir":   ("bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400",   "schedule"),
    "résolue":    ("bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400", "check_circle"),
    "récurrente": ("bg-orange-50 text-orange-600 dark:bg-orange-900/20 dark:text-orange-400", "refresh"),
}

_SRC_ICONS = {
    "qcm":      "quiz",
    "séance":   "menu_book",
    "note":     "sticky_note_2",
    "manuel":   "edit",
    "obsidian": "auto_stories",
}


def _get(row, key: str, default=None):
    try:
        v = row[key]
        return v if v is not None else default
    except (IndexError, KeyError):
        return default


def WeakPointCard(wp, on_refresh=None):
    sev     = int(wp["severity"] or 2)
    status  = wp["status"] or "active"
    cat     = wp["category"] or ""
    detail  = wp["detail"] or ""
    title   = wp["course_title"] or ""
    item_nb = wp["item_number"] or ""
    src_t   = wp["source_type"] or "manuel"
    rec_c   = int(wp["recurrence_count"] or 0)
    created = (wp["created_at"] or "")[:10]
    wp_id   = wp["id"]

    obs_path    = _get(wp, "obsidian_path", "")
    obs_uri     = _get(wp, "obsidian_uri",  "")
    obs_title   = _get(wp, "obsidian_title", "")
    college     = _get(wp, "college", "")
    is_obsidian = bool(obs_path)

    display_detail = obs_title or detail

    stripe       = _SEV_STRIPE.get(sev, _SEV_STRIPE[2])
    pill_cls, pill_icon = _STATUS_PILL.get(status, ("bg-slate-50 text-slate-500", "help"))

    def _refresh():
        if on_refresh:
            on_refresh()

    with ui.card().props(f'data-id="{wp_id}"').classes(
        f"lacune-card w-full p-0 rounded-xl overflow-hidden "
        f"border border-slate-100 dark:border-slate-700/60 "
        f"border-l-4 {stripe} "
        f"shadow-sm hover:shadow-md transition-all bg-white dark:bg-slate-900"
    ):
        with ui.element("div").classes("px-4 py-3 flex flex-col gap-2"):

            # ── Row 1: context meta + status pill ─────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-2"):
                # Left: item / course / category
                with ui.row().classes("items-center gap-1.5 min-w-0 flex-1 flex-wrap"):
                    if item_nb:
                        ui.label(f"ITEM {item_nb}").classes(
                            "text-[11px] font-bold tracking-wide "
                            "text-indigo-600 dark:text-indigo-400 shrink-0"
                        )
                    elif title and title != "—":
                        ui.label(title[:28]).classes(
                            "text-[11px] font-medium text-slate-500 dark:text-slate-400 truncate"
                        )
                    elif college:
                        ui.label(college[:22]).classes(
                            "text-[11px] text-slate-400 dark:text-slate-500 truncate"
                        )

                    if cat and (item_nb or title or college):
                        ui.label("·").classes("text-slate-200 dark:text-slate-700 shrink-0")
                    if cat:
                        ui.label(cat).classes(
                            "text-[11px] text-slate-400 dark:text-slate-500 truncate"
                        )

                    if rec_c > 0:
                        ui.label(f"↺ {rec_c}×").classes(
                            "text-[11px] font-semibold text-orange-500 dark:text-orange-400 shrink-0"
                        )

                # Right: status pill
                with ui.row().classes(
                    f"items-center gap-1 px-2 py-0.5 rounded-full shrink-0 {pill_cls}"
                ):
                    ui.icon(pill_icon, size="xs")
                    ui.label(status).classes("text-[11px] font-medium leading-none")

            # ── Course title (when item_nb is known and title adds context) ─────
            if item_nb and title and title != "—":
                ui.label(title).classes(
                    "text-[11px] text-slate-400 dark:text-slate-500 truncate w-full -mt-1"
                )

            # ── Description: the visual hero ──────────────────────────────────
            ui.label(display_detail or detail).classes(
                "text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug w-full"
            ).style(
                "display:-webkit-box;-webkit-line-clamp:2;"
                "-webkit-box-orient:vertical;overflow:hidden;word-break:break-word"
            )

            # ── Bottom row: source + date (left) / actions (right) ─────────────
            with ui.row().classes(
                "w-full items-center gap-1 pt-2 border-t "
                "border-slate-50 dark:border-slate-800/60"
            ):
                # Source + date
                with ui.row().classes("items-center gap-1 flex-1 min-w-0"):
                    src_icon = _SRC_ICONS.get(src_t, "help_outline")
                    ui.icon(src_icon, size="xs").classes("text-slate-300 dark:text-slate-600")
                    ui.label(created).classes("text-[11px] text-slate-300 dark:text-slate-600")

                # Action icons
                with ui.row().classes("items-center gap-0 shrink-0"):

                    if is_obsidian:
                        def _on_open_obsidian(uri=obs_uri, path=obs_path):
                            target = uri or path
                            if not target:
                                ui.notify("Chemin Obsidian indisponible", type="warning")
                                return
                            try:
                                webbrowser.open(target)
                            except Exception as exc:
                                try:
                                    import os
                                    os.startfile(path.replace("/", "\\"))
                                except Exception:
                                    ui.notify(f"Impossible d'ouvrir : {exc}", type="negative")

                        ui.button(icon="auto_stories", on_click=_on_open_obsidian).props(
                            "flat round dense size=sm color=indigo"
                        ).tooltip("Ouvrir dans Obsidian")

                    if status != "résolue":
                        def _on_revoir(wid=wp_id, cid=wp["course_id"], opath=obs_path):
                            local_store.mark_weak_point_reviewed(wid)
                            if opath:
                                from backend.core.obsidian.weak_points_sync import write_obsidian_reviewed_at
                                write_obsidian_reviewed_at(
                                    opath.replace("/", "\\"),
                                    datetime.date.today().isoformat(),
                                )
                            c = next((x for x in data_store.cours if x.id == cid), None)
                            if c and (c.url_pdf or c.url_pdf_ue):
                                ui.navigate.to(f"/pdf/{cid}", new_tab=True)
                            else:
                                ui.notify("Lacune marquée comme revue", type="info")
                            _refresh()

                        ui.button(icon="menu_book", on_click=_on_revoir).props(
                            "flat round dense size=sm color=indigo"
                        ).tooltip("Revoir le cours")

                    if status != "résolue":
                        def _on_resolve(wid=wp_id, opath=obs_path):
                            local_store.update_weak_point_status(wid, "résolue")
                            if opath:
                                from backend.core.obsidian.weak_points_sync import (
                                    write_obsidian_lacune_status, move_obsidian_lacune_file,
                                )
                                new_path = move_obsidian_lacune_file(opath, "résolue")
                                write_obsidian_lacune_status(
                                    new_path.replace("/", "\\"),
                                    "résolue",
                                    resolved_at=datetime.date.today().isoformat(),
                                )
                                if new_path != opath:
                                    local_store.update_weak_point_obsidian_path(wid, new_path)
                            ui.notify("Lacune résolue ✓", type="positive")
                            _refresh()

                        ui.button(icon="check_circle", on_click=_on_resolve).props(
                            "flat round dense size=sm color=positive"
                        ).tooltip("Marquer résolue")

                    # Context menu: less-frequent actions
                    with ui.button(icon="more_horiz").props(
                        "flat round dense size=sm"
                    ).classes("text-slate-300 dark:text-slate-600"):
                        with ui.menu().classes("text-sm"):
                            if status != "récurrente":
                                def _on_recur(wid=wp_id, opath=obs_path):
                                    local_store.increment_recurrence(wid)
                                    if opath:
                                        from backend.core.obsidian.weak_points_sync import (
                                            write_obsidian_lacune_status, move_obsidian_lacune_file,
                                        )
                                        new_path = move_obsidian_lacune_file(opath, "récurrente")
                                        write_obsidian_lacune_status(new_path.replace("/", "\\"), "récurrente")
                                        if new_path != opath:
                                            local_store.update_weak_point_obsidian_path(wid, new_path)
                                    ui.notify("Lacune marquée récurrente ↺", type="warning")
                                    _refresh()
                                ui.menu_item("Rendre récurrente", on_click=_on_recur).classes("text-xs")

                            if status != "à revoir":
                                def _on_to_review(wid=wp_id, opath=obs_path):
                                    local_store.update_weak_point_status(wid, "à revoir")
                                    if opath:
                                        from backend.core.obsidian.weak_points_sync import (
                                            write_obsidian_lacune_status, move_obsidian_lacune_file,
                                        )
                                        new_path = move_obsidian_lacune_file(opath, "à revoir")
                                        write_obsidian_lacune_status(new_path.replace("/", "\\"), "à revoir")
                                        if new_path != opath:
                                            local_store.update_weak_point_obsidian_path(wid, new_path)
                                    ui.notify("Lacune marquée à revoir", type="info")
                                    _refresh()
                                ui.menu_item("Marquer à revoir", on_click=_on_to_review).classes("text-xs")

                            if status == "résolue":
                                def _on_reopen(wid=wp_id, opath=obs_path):
                                    local_store.update_weak_point_status(wid, "active")
                                    if opath:
                                        from backend.core.obsidian.weak_points_sync import (
                                            write_obsidian_lacune_status, move_obsidian_lacune_file,
                                        )
                                        new_path = move_obsidian_lacune_file(opath, "active")
                                        write_obsidian_lacune_status(new_path.replace("/", "\\"), "active")
                                        if new_path != opath:
                                            local_store.update_weak_point_obsidian_path(wid, new_path)
                                    ui.notify("Lacune réactivée", type="warning")
                                    _refresh()
                                ui.menu_item("Réactiver", on_click=_on_reopen).classes("text-xs")

                            ui.separator()
                            ui.menu_item("Sévérité").classes(
                                "text-[11px] text-slate-400 font-bold uppercase pointer-events-none"
                            )
                            with ui.row().classes("px-3 pb-2 gap-1"):
                                for sv in range(1, 6):
                                    def _set_sev(s=sv, wid=wp_id):
                                        local_store.update_weak_point_severity(wid, s)
                                        _refresh()
                                    ui.button(str(sv)).props(
                                        f"{'unelevated' if sv == sev else 'outline'} round dense size=xs "
                                        f"color={'positive' if sv <= 2 else 'warning' if sv == 3 else 'negative'}"
                                    ).on_click(_set_sev)

                            ui.separator()
                            def _on_delete(wid=wp_id, obs=obs_path):
                                if obs:
                                    try:
                                        from backend.core.obsidian.weak_points_sync import delete_obsidian_lacune_file
                                        delete_obsidian_lacune_file(obs)
                                    except Exception:
                                        pass
                                local_store.delete_weak_point(wid)
                                ui.notify("Lacune supprimée", type="warning")
                                _refresh()
                            ui.menu_item("Supprimer", on_click=_on_delete).classes(
                                "text-xs text-red-400"
                            )
