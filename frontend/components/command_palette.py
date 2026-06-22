"""
command_palette.py — Synapse
----------------------------
Palette de commandes rapides accessible via Ctrl+K (ou bouton header).

Flow :
  1. Saisie libre (recherche cours ou commande textuelle)
  2. Sélection d'un cours dans les résultats
  3. Choix de l'action : Lacune / QCM / Séance / Voir fiche
  4. Formulaire contextuel

Commandes texte reconnues (en début de saisie) :
  lacune <texte>   → pré-remplit le dialogue Lacune
  qcm <texte>      → pré-remplit le dialogue QCM
  séance <texte>   → pré-remplit le dialogue Séance
"""
from __future__ import annotations

import datetime
from nicegui import ui
from loguru import logger

from backend.state.store import data_store
from backend.core.reviews import local_store


# ── Palette principale ────────────────────────────────────────────────────────

def open_command_palette() -> None:
    """Ouvre la palette de commandes globale."""

    # ── État interne ──────────────────────────────────────────────────────────
    state: dict = {
        "selected_course": None,
        "query": "",
    }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _search_courses(query: str) -> list:
        q = query.strip()
        if len(q) < 2:
            return data_store.cours[:8]
        try:
            from backend.core.search.service import search_index
            hits = search_index.search(q, limit=10, score_cutoff=50)
            return [cours for cours, _ in hits]
        except Exception:
            q_low = q.lower()
            return [
                c for c in data_store.cours
                if q_low in c.title.lower() or (c.item_number and q_low in c.item_number)
            ][:10]

    def _detect_command(query: str) -> tuple[str | None, str]:
        """Détecte lacune/qcm/séance en préfixe. Retourne (cmd, reste)."""
        q = query.strip()
        for cmd in ("lacune", "qcm", "séance", "seance"):
            if q.lower().startswith(cmd + " ") or q.lower() == cmd:
                return cmd.replace("seance", "séance"), q[len(cmd):].strip()
        return None, q

    # ── Dialog principal ──────────────────────────────────────────────────────

    with ui.dialog().props("persistent") as dlg:
        with ui.card().classes(
            "w-[580px] max-w-[95vw] p-0 rounded-2xl overflow-hidden "
            "bg-white dark:bg-slate-900 shadow-2xl"
        ).style("max-height: 80vh;"):

            # ── Barre de recherche ────────────────────────────────────────────
            with ui.element("div").classes(
                "flex items-center gap-3 px-4 py-3 "
                "border-b border-slate-100 dark:border-slate-800"
            ):
                ui.icon("search", size="sm").classes("text-slate-400 shrink-0")
                search_input = ui.input(
                    placeholder="Rechercher un cours, ou taper : lacune / qcm / séance…"
                ).props(
                    "autofocus borderless dense"
                ).classes("flex-1 text-sm text-slate-800 dark:text-slate-100")
                ui.button(icon="close", on_click=dlg.close).props(
                    "flat round dense size=sm color=grey"
                )

            # ── Corps scrollable ──────────────────────────────────────────────
            with ui.scroll_area().classes("w-full").style("max-height: 55vh"):
                body = ui.column().classes("w-full")

            # ── Footer hint ───────────────────────────────────────────────────
            with ui.element("div").classes(
                "px-4 py-2 border-t border-slate-100 dark:border-slate-800 "
                "flex items-center gap-4"
            ):
                for key, lbl in [("↵", "sélectionner"), ("Échap", "fermer"), ("Ctrl+K", "rouvrir")]:
                    with ui.row().classes("items-center gap-1"):
                        ui.element("kbd").classes(
                            "text-[11px] font-mono px-1.5 py-0.5 rounded "
                            "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
                        ).text = key
                        ui.label(lbl).classes("text-[11px] text-slate-400")

    # ── Rendu du corps ────────────────────────────────────────────────────────

    def _render_body(query: str = ""):
        body.clear()
        cmd, rest = _detect_command(query)

        with body:
            if state["selected_course"] and not query:
                _render_course_actions(state["selected_course"], dlg, body)
                return

            if cmd:
                _render_command_shortcut(cmd, rest, dlg, body)
                return

            courses = _search_courses(query)

            if not query:
                # Actions rapides
                with ui.element("div").classes("px-4 py-2"):
                    ui.label("ACTIONS RAPIDES").classes(
                        "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                    )
                with ui.element("div").classes("flex gap-2 px-4 pb-3 flex-wrap"):
                    for label, icon, color, action in [
                        ("+ Lacune",  "report_problem", "orange", lambda: _quick_action("lacune", dlg)),
                        ("+ QCM",     "quiz",           "indigo", lambda: _quick_action("qcm",    dlg)),
                        ("+ Séance",  "school",         "blue",   lambda: _quick_action("séance", dlg)),
                    ]:
                        ui.button(
                            label, icon=icon,
                            on_click=action,
                        ).props(
                            f"outline rounded size=sm color={color}"
                        ).classes("text-xs font-semibold")

                if courses:
                    with ui.element("div").classes("px-4 py-1"):
                        ui.label("COURS RÉCENTS").classes(
                            "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                        )

            # Liste des cours
            if not courses and query:
                with ui.column().classes("w-full items-center py-6 gap-2 text-slate-400"):
                    ui.icon("search_off", size="lg").classes("opacity-40")
                    ui.label(f"Aucun cours pour « {query} »").classes("text-sm")
            else:
                for course in courses:
                    item_txt = f"ITEM {course.display_item_number} — " if course.display_item_number else ""
                    college_txt = ", ".join(course.college[:2]) if course.college else ""

                    def _pick(c=course):
                        state["selected_course"] = c
                        search_input.value = ""
                        _render_body("")

                    with ui.element("div").classes(
                        "w-full px-4 py-2.5 flex items-center gap-3 cursor-pointer "
                        "hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                    ).on("click", _pick):
                        with ui.column().classes("flex-1 gap-0.5 min-w-0"):
                            ui.label(f"{item_txt}{course.title}").classes(
                                "text-sm font-semibold text-slate-800 dark:text-slate-100 truncate"
                            )
                            if college_txt:
                                ui.label(college_txt).classes(
                                    "text-[11px] text-slate-400 truncate"
                                )
                        ui.icon("chevron_right", size="xs").classes("text-slate-300 shrink-0")

    def _render_course_actions(course, dlg, body):
        """Affiche les actions disponibles pour le cours sélectionné."""
        item_txt = f"ITEM {course.display_item_number} — " if course.display_item_number else ""
        body.clear()
        with body:
            with ui.element("div").classes(
                "px-4 py-3 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.button(icon="arrow_back", on_click=lambda: _render_body("")).props(
                        "flat round dense size=xs color=grey"
                    )
                    with ui.column().classes("gap-0"):
                        ui.label(f"{item_txt}{course.title}").classes(
                            "text-sm font-bold text-slate-800 dark:text-slate-100 truncate"
                        )
                        college_txt = ", ".join(course.college[:2]) if course.college else ""
                        if college_txt:
                            ui.label(college_txt).classes("text-[11px] text-slate-400")

            with ui.element("div").classes("flex gap-2 px-4 py-4 flex-wrap"):
                for label, icon_name, color, action in [
                    ("+ Lacune",    "report_problem", "orange", lambda: _open_lacune_for_course(course, dlg)),
                    ("+ QCM",       "quiz",           "indigo", lambda: _open_qcm_for_course(course, dlg)),
                    ("+ Séance",    "school",         "blue",   lambda: _open_session_for_course(course, dlg)),
                    ("Voir fiche",  "open_in_new",    "slate",  lambda c=course: (dlg.close(), ui.navigate.to(f"/cours/{c.id}"))),
                ]:
                    ui.button(
                        label, icon=icon_name,
                        on_click=action,
                    ).props(
                        f"unelevated rounded size=sm color={color}"
                    ).classes("text-xs font-semibold")

    def _quick_action(kind: str, dlg):
        """Ouvre le formulaire de saisie rapide sans cours pré-sélectionné."""
        if kind == "lacune":
            dlg.close()
            from frontend.pages.weak_points import open_add_dialog
            open_add_dialog(lambda: None)
        elif kind == "qcm":
            dlg.close()
            ui.navigate.to("/qcm")
        elif kind == "séance":
            dlg.close()
            ui.navigate.to("/stats")

    def _open_lacune_for_course(course, dlg):
        dlg.close()
        from frontend.pages.weak_points import open_add_dialog
        # On ouvre le dialog lacune — le cours sera pré-rempli via open_add_dialog_for_course
        _open_lacune_dialog_prefilled(course)

    def _open_lacune_dialog_prefilled(course):
        """Ouvre le dialog Lacune avec le cours pré-rempli."""
        from types import SimpleNamespace
        state_lc = SimpleNamespace(
            course_id=course.id,
            course_title=course.title,
            item_number=course.item_number or "",
            category=None,
            detail="",
            severity=2,
            source_type="manuel",
        )
        _CATEGORIES = {None: "— Aucune"} | {c: c for c in local_store.WEAK_POINT_CATEGORIES}

        with ui.dialog().props("persistent") as dlg2:
            with ui.card().classes(
                "w-[520px] max-w-[92vw] rounded-3xl p-0 overflow-hidden "
                "bg-white dark:bg-slate-900 shadow-2xl"
            ).style("max-height:90vh;display:flex;flex-direction:column"):
                with ui.element("div").classes(
                    "px-6 pt-5 pb-4 border-b border-slate-100 dark:border-slate-800 shrink-0"
                ):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.column().classes("gap-0"):
                            ui.label("Ajouter une lacune").classes(
                                "text-[15px] font-bold text-slate-900 dark:text-slate-50"
                            )
                            item_txt = f"ITEM {course.display_item_number} — " if course.display_item_number else ""
                            ui.label(f"{item_txt}{course.title}").classes(
                                "text-xs text-indigo-500 font-semibold"
                            )
                        ui.button(icon="close", on_click=dlg2.close).props(
                            "flat round dense size=sm color=grey-7"
                        )

                with ui.element("div").classes(
                    "px-6 py-5 flex flex-col gap-4 flex-1 overflow-y-auto"
                ):
                    def _slbl(t):
                        ui.label(t).classes(
                            "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                        )

                    _slbl("Catégorie")
                    ui.select(options=_CATEGORIES, value=None).classes("w-full").props(
                        "outlined dense"
                    ).on_value_change(lambda e: setattr(state_lc, "category", e.value))

                    _slbl("Description")
                    ui.textarea(
                        placeholder="Décrivez la lacune, le piège EDN…"
                    ).classes("w-full").props("outlined dense autogrow").on_value_change(
                        lambda e: setattr(state_lc, "detail", e.value or "")
                    )

                    _slbl("Sévérité")
                    sev_btns: dict = {}
                    with ui.row().classes("gap-2"):
                        for sv in range(1, 6):
                            col = "positive" if sv <= 2 else "warning" if sv == 3 else "negative"
                            b = ui.button(str(sv)).props(
                                f"{'unelevated' if sv == 2 else 'outline'} round size=sm color={col}"
                            )
                            sev_btns[sv] = b
                            def _set(s=sv):
                                state_lc.severity = s
                                for sv2, bb in sev_btns.items():
                                    c2 = "positive" if sv2 <= 2 else "warning" if sv2 == 3 else "negative"
                                    bb.props(f"{'unelevated' if sv2==s else 'outline'} round size=sm color={c2}")
                            b.on_click(_set)

                with ui.element("div").classes(
                    "px-6 py-4 bg-slate-50 dark:bg-slate-800/50 "
                    "border-t border-slate-100 dark:border-slate-800 "
                    "flex justify-end gap-2 shrink-0"
                ):
                    ui.button("Annuler", on_click=dlg2.close).props("flat color=grey-8")

                    def _submit():
                        if not state_lc.detail.strip():
                            ui.notify("La description est obligatoire.", type="warning")
                            return
                        local_store.add_weak_point_full(
                            course_id=state_lc.course_id,
                            detail=state_lc.detail.strip(),
                            course_title=state_lc.course_title,
                            item_number=state_lc.item_number,
                            category=state_lc.category,
                            severity=state_lc.severity,
                            source_type=state_lc.source_type,
                        )
                        dlg2.close()
                        ui.notify("Lacune ajoutée ✓", type="positive")

                    ui.button("Ajouter ✓", on_click=_submit).props(
                        "unelevated color=indigo rounded"
                    ).classes("px-5 font-semibold")

        dlg2.open()

    def _open_qcm_for_course(course, dlg):
        dlg.close()
        ui.navigate.to("/qcm")

    def _open_session_for_course(course, dlg):
        dlg.close()
        from frontend.components.course_quick_actions import open_quick_session_dialog
        try:
            client = ui.context.client
        except Exception:
            client = None
        open_quick_session_dialog(course, lambda: None, client)

    def _render_command_shortcut(cmd: str, rest: str, dlg, body):
        """Affiche un formulaire simplifié pour la commande détectée."""
        body.clear()
        with body:
            with ui.element("div").classes("px-4 py-3 bg-slate-50 dark:bg-slate-800"):
                ui.label(f"Mode rapide : {cmd.upper()}").classes(
                    "text-xs font-bold text-slate-500 uppercase tracking-wider"
                )
            with ui.element("div").classes("px-4 py-4"):
                ui.label(f"Ouvre le formulaire « {cmd} » avec le texte pré-rempli.").classes(
                    "text-sm text-slate-600 dark:text-slate-300"
                )
                if rest:
                    ui.label(f"Texte capturé : « {rest} »").classes(
                        "text-xs text-indigo-500 mt-1 font-mono"
                    )
            with ui.element("div").classes("px-4 pb-4"):
                if cmd == "lacune":
                    def _go():
                        dlg.close()
                        from frontend.pages.weak_points import open_add_dialog
                        open_add_dialog(lambda: None)
                    ui.button("Ouvrir « Nouvelle lacune »", icon="report_problem", on_click=_go).props(
                        "unelevated color=orange rounded size=sm"
                    )
                elif cmd == "qcm":
                    def _go():
                        dlg.close()
                        ui.navigate.to("/qcm")
                    ui.button("Aller à la page QCM", icon="quiz", on_click=_go).props(
                        "unelevated color=indigo rounded size=sm"
                    )
                elif cmd == "séance":
                    def _go():
                        dlg.close()
                        ui.navigate.to("/stats")
                    ui.button("Aller à Suivi", icon="school", on_click=_go).props(
                        "unelevated color=blue rounded size=sm"
                    )

    # Mise à jour réactive sur frappe
    def _on_search_change(e):
        state["selected_course"] = None
        state["query"] = e.value or ""
        _render_body(state["query"])

    search_input.on("update:model-value", _on_search_change)

    # Affichage initial
    _render_body("")
    dlg.open()
