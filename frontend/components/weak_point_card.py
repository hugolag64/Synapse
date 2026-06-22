"""
weak_point_card.py — Synapse
------------------------------
Composant carte pour une lacune (weak_point).

Supporte les lacunes :
  - Synapse natif (créées manuellement ou depuis une séance)
  - Obsidian (synapse_id = "obsidian_*", obsidian_path non null)

Usage :
    from frontend.components.weak_point_card import WeakPointCard

    WeakPointCard(wp_row, on_refresh=_rebuild)
"""
from __future__ import annotations

import datetime
import webbrowser
from nicegui import ui
from backend.core.reviews import local_store
from backend.state.store import data_store


# ── Couleurs sévérité ─────────────────────────────────────────────────────────

_SEV_COLORS = {
    1: ("bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300", "text-slate-400"),
    2: ("bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300", "text-slate-400"),
    3: ("bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300", "text-amber-400"),
    4: ("bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",       "text-red-500"),
    5: ("bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",      "text-red-600"),
}

_STATUS_BADGE_COLORS = {
    "active":     "blue",
    "à revoir":   "amber",
    "résolue":    "green",
    "récurrente": "red",
}

_STATUS_ICONS = {
    "active":     "radio_button_checked",
    "à revoir":   "schedule",
    "résolue":    "check_circle",
    "récurrente": "refresh",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(row, key: str, default=None):
    """Lecture sécurisée d'un sqlite3.Row (gère colonnes absentes)."""
    try:
        v = row[key]
        return v if v is not None else default
    except (IndexError, KeyError):
        return default


# ── Composant ─────────────────────────────────────────────────────────────────

def WeakPointCard(wp, on_refresh=None):
    """
    Affiche une carte de lacune.

    wp : sqlite3.Row (ou dict-like) issu de get_all_weak_points_table()
    on_refresh : callable() appelé après toute action
    """
    sev     = int(wp["severity"] or 2)
    status  = wp["status"] or "active"
    cat     = wp["category"] or ""
    detail  = wp["detail"] or ""
    title   = wp["course_title"] or "—"
    item_nb = wp["item_number"] or ""
    src_t   = wp["source_type"] or "manuel"
    rec_c   = int(wp["recurrence_count"] or 0)
    created = (wp["created_at"] or "")[:10]
    wp_id   = wp["id"]

    # ── Champs Obsidian (Phase H) ─────────────────────────────────────────────
    obs_path   = _get(wp, "obsidian_path", "")   # chemin absolu (slashes)
    obs_uri    = _get(wp, "obsidian_uri",  "")   # obsidian:// URI
    obs_title  = _get(wp, "obsidian_title", "")  # titre H1 de la note
    college    = _get(wp, "college", "")         # collège Obsidian
    is_obsidian = bool(obs_path)

    # Titre affiché : pour les lacunes Obsidian, le 'detail' IS le titre
    display_detail = obs_title or detail

    sev_classes, _dot_cls = _SEV_COLORS.get(sev, _SEV_COLORS[2])
    status_color  = _STATUS_BADGE_COLORS.get(status, "slate")

    def _refresh():
        if on_refresh:
            on_refresh()

    with ui.card().classes(
        "w-full p-3 rounded-xl border border-slate-100 dark:border-slate-700 "
        "shadow-sm hover:shadow-md transition-all"
    ):
        with ui.column().classes("w-full gap-2 min-w-0"):

            # ── Ligne 1 : badges ──────────────────────────────────────────────
            with ui.row().classes("items-center gap-1.5 flex-wrap"):
                # Sévérité
                ui.badge(f"{'●' * sev}{'○' * (5 - sev)}  {sev}/5").classes(
                    f"text-[11px] font-bold px-2 py-0.5 shrink-0 {sev_classes} rounded-full"
                )
                # Catégorie
                if cat:
                    ui.badge(cat, color="slate").classes("text-[11px] px-1.5 py-0.5 shrink-0")
                # Cours
                item_lbl = f"ITEM {item_nb}" if item_nb else (title[:20] if title != "—" else "")
                if item_lbl:
                    ui.badge(item_lbl, color="indigo").classes("text-[11px] px-1.5 py-0.5 shrink-0")
                # Collège (si fourni par Obsidian et pas de cours lié)
                if college and not item_nb:
                    ui.badge(college[:18], color="slate").classes(
                        "text-[11px] px-1.5 py-0.5 shrink-0"
                    )
                # Statut
                ui.badge(status, color=status_color).classes("text-[11px] px-1.5 py-0.5 shrink-0")
                # Récurrence
                if rec_c > 0:
                    ui.badge(f"↺ {rec_c}×", color="red").classes("text-[11px] px-1.5 py-0.5 shrink-0")
                # Badge Obsidian
                if is_obsidian:
                    tooltip_txt = obs_uri or obs_path
                    ui.badge("⟁ Obsidian", color="indigo").classes(
                        "text-[11px] px-1.5 py-0.5 shrink-0"
                    ).tooltip(tooltip_txt or "Note Obsidian liée")

            # ── Titre du cours (si lié) ───────────────────────────────────────
            if title and title != "—":
                ui.label(title).classes(
                    "text-[11px] text-slate-400 font-medium truncate"
                )
            elif college:
                ui.label(f"Collège : {college}").classes(
                    "text-[11px] text-slate-400 font-medium truncate"
                )

            # ── Détail / titre de la lacune ───────────────────────────────────
            ui.label(display_detail or detail).classes(
                "text-sm font-semibold text-slate-900 dark:text-slate-100 leading-snug w-full"
            ).style(
                "display:-webkit-box;-webkit-line-clamp:3;"
                "-webkit-box-orient:vertical;overflow:hidden;word-break:break-word"
            )

            # ── Sous-info : source + date ──────────────────────────────────────
            src_icon = {
                "qcm": "quiz", "séance": "menu_book",
                "note": "sticky_note_2", "manuel": "edit",
                "obsidian": "auto_stories",
            }.get(src_t, "help_outline")
            with ui.row().classes("items-center gap-1 text-slate-400"):
                ui.icon(src_icon, size="xs")
                ui.label(f"{src_t} · {created}").classes("text-[11px]")

            # ── Actions ───────────────────────────────────────────────────────
            with ui.row().classes(
                "w-full items-center gap-1 pt-1.5 border-t border-slate-100 dark:border-slate-700"
            ):
                # Bouton "Ouvrir dans Obsidian"
                if is_obsidian:
                    def _on_open_obsidian(uri=obs_uri, path=obs_path):
                        target = uri or path
                        if not target:
                            ui.notify("Chemin Obsidian indisponible", type="warning")
                            return
                        try:
                            webbrowser.open(target)
                        except Exception as exc:
                            # Fallback : ouvrir le fichier directement
                            try:
                                import os
                                os.startfile(path.replace("/", "\\"))
                            except Exception:
                                ui.notify(f"Impossible d'ouvrir : {exc}", type="negative")

                    ui.button("Obsidian", icon="auto_stories", on_click=_on_open_obsidian).props(
                        "unelevated dense size=sm color=purple rounded"
                    ).classes("text-xs")

                # Revoir
                if status != "résolue":
                    def _on_revoir(wid=wp_id, cid=wp["course_id"], opath=obs_path):
                        local_store.mark_weak_point_reviewed(wid)
                        # Écriture dans Obsidian si applicable
                        if opath:
                            from backend.core.obsidian.weak_points_sync import write_obsidian_reviewed_at
                            write_obsidian_reviewed_at(
                                opath.replace("/", "\\"),
                                datetime.date.today().isoformat(),
                            )
                        # Ouvrir le PDF si disponible
                        c = next((x for x in data_store.cours if x.id == cid), None)
                        if c and (c.url_pdf or c.url_pdf_ue):
                            ui.navigate.to(f"/pdf/{cid}", new_tab=True)
                        else:
                            ui.notify("Lacune marquée comme revue", type="info")
                        _refresh()

                    ui.button("Revoir", icon="menu_book", on_click=_on_revoir).props(
                        "unelevated dense size=sm color=indigo rounded"
                    ).classes("text-xs")

                # Marquer résolue
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
                        ui.notify("Lacune marquée résolue ✓", type="positive")
                        _refresh()

                    ui.button(icon="check_circle", on_click=_on_resolve).props(
                        "flat round dense size=sm color=positive"
                    ).tooltip("Marquer résolue")

                ui.element("div").classes("flex-1")

                # Menu ⋯
                with ui.button(icon="more_horiz").props(
                    "flat round dense size=sm"
                ).classes("text-slate-400").tooltip("Plus d'actions"):
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
                            ui.menu_item("↺  Rendre récurrente", on_click=_on_recur).classes("text-xs")

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
                            ui.menu_item("📋  Marquer à revoir", on_click=_on_to_review).classes("text-xs")

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
                            ui.menu_item("🔄  Réactiver", on_click=_on_reopen).classes("text-xs")

                        # Sévérité
                        ui.separator()
                        ui.menu_item("Sévérité").classes("text-[11px] text-slate-400 font-bold uppercase")
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
                        def _on_delete(wid=wp_id):
                            local_store.delete_weak_point(wid)
                            ui.notify("Lacune supprimée", type="warning")
                            _refresh()
                        ui.menu_item("🗑  Supprimer", on_click=_on_delete).classes("text-xs text-red-400")
