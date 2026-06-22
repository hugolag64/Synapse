"""
weak_points.py — Synapse — Page Lacunes (Phase D + Phase H)
------------------------------------------------------------
Affiche et gère les lacunes (points faibles) :
  🔴 Très critiques  (sévérité ≥ 4, actives)
  🟡 À revoir        (status = 'à revoir')
  🟠 Actives         (sévérité < 4, actives)
  ↺  Récurrentes     (status = 'récurrente')
  🔗 Non reliées     (Obsidian sans cours Synapse)
  ✓  Résolues récemment (collapsed)

Phase H : bouton "Synchroniser Obsidian" en haut de page.
"""

from nicegui import ui
from loguru import logger

from frontend.theme import frame
from backend.core.reviews import local_store
from backend.state.store import data_store
from backend.config.settings import settings
from frontend.components.weak_point_card import WeakPointCard, _get


# ── Catégories et options ──────────────────────────────────────────────────────

_CATEGORIES = {None: "— Aucune"} | {c: c for c in local_store.WEAK_POINT_CATEGORIES}
_SOURCE_OPTS = {"manuel": "Manuel", "qcm": "QCM", "séance": "Séance", "note": "Note"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_unlinked_obsidian(w) -> bool:
    """Lacune venant d'Obsidian mais sans cours Synapse associé."""
    try:
        return bool(w["obsidian_path"]) and not (w["course_id"] or "").strip()
    except (IndexError, KeyError):
        return False


# ── Page principale ───────────────────────────────────────────────────────────

def weak_points_page(item_filter: str | None = None):
    _state = {"item": item_filter}

    with frame("Lacunes"):
        logger.info("ENTERING WEAK POINTS PAGE")
        try:
            with ui.column().classes("w-full gap-6 max-w-5xl mx-auto"):

                # ── Header ────────────────────────────────────────────────────
                with ui.row().classes("w-full items-center justify-between flex-wrap gap-3"):
                    ui.label("Lacunes").classes(
                        "text-3xl font-extrabold text-slate-900 dark:text-slate-50 tracking-tight"
                    )
                    with ui.row().classes("items-center gap-2"):
                        # ── Bouton sync Obsidian ───────────────────────────────
                        vault_ok = bool(settings.obsidian_vault_path)
                        sync_btn = ui.button(
                            "Synchroniser Obsidian",
                            icon="sync",
                        ).props(
                            f"unelevated color={'indigo' if vault_ok else 'grey'} rounded"
                        ).classes("text-sm font-semibold")
                        if not vault_ok:
                            sync_btn.tooltip("Configurez OBSIDIAN_VAULT_PATH dans les paramètres")

                        ui.button(
                            "+ Ajouter une lacune",
                            icon="add",
                            on_click=lambda: open_add_dialog(_rebuild),
                        ).props("unelevated color=indigo rounded").classes("text-sm font-semibold")

                # ── Résultat de sync (masqué par défaut) ──────────────────────
                sync_result_row = ui.row().classes("items-center gap-2 w-full")
                with sync_result_row:
                    sync_icon  = ui.icon("info", size="xs").classes("text-slate-400")
                    sync_label = ui.label("").classes("text-sm text-slate-500")
                sync_result_row.set_visibility(False)

                # ── Bandeau filtre item (visible uniquement si filtrage actif) ─
                filter_banner = ui.element("div").classes("w-full")

                # ── Conteneur principal (rebuildable) ─────────────────────────
                main_col = ui.column().classes("w-full gap-6")

                def _clear_filter():
                    _state["item"] = None
                    _rebuild()

                def _rebuild():
                    filter_banner.clear()
                    if _state["item"]:
                        with filter_banner:
                            _render_item_filter_banner(_state["item"], _clear_filter)
                    main_col.clear()
                    _render_all(main_col, _rebuild, item_filter=_state["item"])

                _rebuild()

                # ── Handler sync async ─────────────────────────────────────────
                async def _run_obsidian_sync():
                    if not vault_ok:
                        ui.notify(
                            "Vault Obsidian non configuré (Paramètres → Obsidian)",
                            type="warning",
                        )
                        return

                    sync_btn.props("loading")
                    sync_result_row.set_visibility(True)
                    sync_icon.props("name=sync color=blue")
                    sync_label.set_text("Synchronisation en cours…")

                    try:
                        import asyncio
                        from backend.core.obsidian.weak_points_sync import weak_points_sync_service
                        result = await asyncio.to_thread(weak_points_sync_service.sync)

                        # Affichage résultat
                        sync_icon.props("name=check_circle color=positive")
                        sync_label.set_text(result.summary())
                        sync_label.classes(
                            remove="text-red-500 text-slate-500",
                            add="text-green-600 dark:text-green-400",
                        )

                        if result.unmatched:
                            logger.warning(
                                f"Lacunes Obsidian non reliées : {result.unmatched}"
                            )
                        if result.errors:
                            for err in result.errors:
                                logger.error(f"Sync lacune: {err}")

                        _rebuild()

                    except Exception as exc:
                        logger.exception("Erreur sync Obsidian lacunes")
                        sync_icon.props("name=error color=negative")
                        sync_label.set_text(f"Erreur : {exc}")
                        sync_label.classes(add="text-red-500")
                    finally:
                        sync_btn.props(remove="loading")

                sync_btn.on_click(_run_obsidian_sync)

        except Exception as e:
            logger.exception("WEAK POINTS PAGE ERROR")
            ui.label(f"Erreur : {e}").classes("text-red-500 font-bold")


# ── Render sections ───────────────────────────────────────────────────────────

def _render_item_filter_banner(item_number: str, clear_fn) -> None:
    with ui.row().classes(
        "w-full items-center gap-3 px-4 py-2.5 rounded-xl "
        "bg-indigo-50 dark:bg-indigo-900/20 "
        "border border-indigo-200 dark:border-indigo-800"
    ):
        ui.icon("filter_alt", size="xs").classes("text-indigo-500 shrink-0")
        ui.label(f"Filtré sur l'item {item_number}").classes(
            "text-sm font-semibold text-indigo-800 dark:text-indigo-200 flex-1"
        )
        ui.button(
            "Voir toutes les lacunes",
            icon="close",
            on_click=clear_fn,
        ).props("flat dense size=xs color=indigo").classes("text-xs font-semibold shrink-0")


def _render_all(container, refresh_fn, item_filter: str | None = None):
    """Charge et affiche toutes les sections."""
    # Sprint 2 : expire les vieilles propositions avant d'afficher
    local_store.expire_old_gap_proposals()
    pending_proposals = local_store.get_pending_proposals()

    all_wps = local_store.get_all_weak_points_table(limit=300)

    # Filtre par item si demandé (depuis la page QCM)
    if item_filter:
        all_wps = [
            w for w in all_wps
            if str(w["item_number"] or "").strip() == str(item_filter).strip()
        ]
        # Les propositions ne sont pas filtrées par item dans ce contexte
        pending_proposals = []

    # Séparer les non-reliées Obsidian des lacunes normales
    unlinked_obs = [w for w in all_wps if _is_unlinked_obsidian(w)]
    regular_wps  = [w for w in all_wps if not _is_unlinked_obsidian(w)]

    critical  = [w for w in regular_wps if w["status"] == "active"     and int(w["severity"] or 0) >= 4]
    to_review = [w for w in regular_wps if w["status"] == "à revoir"]
    active    = [w for w in regular_wps if w["status"] == "active"     and int(w["severity"] or 0) < 4]
    recurring = [w for w in regular_wps if w["status"] == "récurrente"]
    resolved  = [w for w in regular_wps if w["status"] == "résolue"][:15]

    total_open = len(critical) + len(to_review) + len(active) + len(recurring) + len(unlinked_obs)

    with container:

        # ── Résumé rapide ──────────────────────────────────────────────────
        with ui.row().classes("items-center gap-3 flex-wrap"):
            if pending_proposals:
                _stat_pill(
                    f"{len(pending_proposals)} à valider",
                    "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
                )
            _stat_pill(f"{len(critical)} critiques",      "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400")
            _stat_pill(f"{len(to_review)} à revoir",      "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400")
            _stat_pill(f"{len(active)} actives",          "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400")
            _stat_pill(f"{len(recurring)} récurrentes",   "bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400")
            if unlinked_obs:
                _stat_pill(f"{len(unlinked_obs)} non reliées", "bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400")
            _stat_pill(f"{len(resolved)} résolues",       "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400")

        # ── Propositions récurrentes (Sprint 2) ────────────────────────────
        if pending_proposals:
            _render_proposals_section(pending_proposals, refresh_fn)

        # ── Sections ──────────────────────────────────────────────────────
        if critical:
            _render_section(
                "🔴 Très critiques", critical, refresh_fn,
                border="border-red-200 dark:border-red-800",
                bg="bg-red-50/30 dark:bg-red-900/5",
            )

        if to_review:
            _render_section(
                "🟡 À revoir", to_review, refresh_fn,
                border="border-amber-200 dark:border-amber-800",
                bg="bg-amber-50/30 dark:bg-amber-900/5",
            )

        if active:
            _render_section(
                "🟠 Actives", active, refresh_fn,
                border="border-slate-200 dark:border-slate-700",
                bg="bg-slate-50/30 dark:bg-slate-800/20",
            )

        if recurring:
            _render_section(
                "↺ Récurrentes", recurring, refresh_fn,
                border="border-orange-200 dark:border-orange-800",
                bg="bg-orange-50/20 dark:bg-orange-900/5",
            )

        # ── Non reliées Obsidian ───────────────────────────────────────────
        if unlinked_obs:
            _render_section(
                "🔗 Non reliées à un cours", unlinked_obs, refresh_fn,
                border="border-purple-200 dark:border-purple-800",
                bg="bg-purple-50/20 dark:bg-purple-900/5",
                subtitle="Lacunes Obsidian importées sans correspondance de cours Synapse.",
            )

        if not total_open:
            with ui.column().classes("w-full items-center py-16 gap-3 text-slate-400"):
                if item_filter:
                    ui.icon("search_off", size="xl").classes("opacity-50")
                    ui.label(f"Aucune lacune pour l'item {item_filter}.").classes(
                        "text-lg font-semibold text-slate-500"
                    )
                    ui.label("Cet item n'a pas encore de lacune enregistrée.").classes(
                        "text-sm text-slate-400"
                    )
                else:
                    ui.icon("emoji_events", size="xl").classes("opacity-50")
                    ui.label("Aucune lacune active. Bon travail !").classes(
                        "text-lg font-semibold text-slate-500"
                    )

        # ── Résolues récemment (collapsé par défaut) ─────────────────────
        if resolved:
            _render_section(
                "✓ Résolues récemment", resolved, refresh_fn,
                border="border-green-200 dark:border-green-800",
                bg="bg-green-50/20 dark:bg-green-900/5",
                collapsed=True,
            )


def _stat_pill(text: str, classes: str):
    with ui.element("div").classes(
        f"flex items-center px-3 py-1.5 rounded-full text-sm font-semibold {classes}"
    ):
        ui.label(text)


# ── Sprint 2 — Propositions de lacunes récurrentes ───────────────────────────

_ET_COLORS_WP: dict[str, str] = {
    "connaissance":  "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
    "raisonnement":  "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
    "inattention":   "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    "stratégie EDN": "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
}
_ET_FALLBACK_WP = "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300"


def _render_proposal_card(p, refresh_fn) -> None:
    pid         = p["id"]
    item_number = p["item_number"]
    error_type  = p["error_type"]
    course_title = p["course_title"] or ""
    count       = p["occurrence_count"]
    et_cls      = _ET_COLORS_WP.get(error_type, _ET_FALLBACK_WP)

    with ui.element("div").classes(
        "flex items-start gap-3 p-3.5 rounded-xl "
        "bg-white dark:bg-slate-900 "
        "border border-amber-100 dark:border-amber-900/40"
    ):
        with ui.column().classes("flex-1 gap-1.5 min-w-0"):
            with ui.row().classes("items-center gap-2 flex-wrap"):
                if item_number:
                    ui.label(f"ITEM {item_number}").classes(
                        "text-[11px] font-bold text-indigo-600 dark:text-indigo-400"
                    )
                ui.label(error_type).classes(
                    f"text-[11px] font-bold px-2 py-0.5 rounded-full {et_cls}"
                )
            if course_title:
                ui.label(course_title).classes(
                    "text-xs text-slate-600 dark:text-slate-300 truncate"
                ).tooltip(course_title)
            ui.label(
                f"{count} session{'s' if count > 1 else ''} avec cette erreur"
            ).classes("text-[11px] text-slate-400")

        with ui.row().classes("shrink-0 gap-1.5 items-center"):
            def _dismiss(p_id=pid):
                local_store.dismiss_gap_proposal(p_id)
                ui.notify("Proposition ignorée", type="info", timeout=2000)
                refresh_fn()

            def _accept(p_id=pid):
                try:
                    wp_id = local_store.accept_gap_proposal(p_id)
                    ui.notify(
                        f"Lacune récurrente créée ✓",
                        type="positive", icon="repeat",
                    )
                    refresh_fn()
                except Exception as _exc:
                    ui.notify(f"Erreur : {_exc}", type="negative")

            ui.button("Ignorer", on_click=_dismiss).props(
                "flat dense rounded size=xs color=grey-7"
            ).classes("text-[11px]")
            ui.button(
                "Créer la lacune", icon="add", on_click=_accept,
            ).props(
                "unelevated dense rounded size=xs color=amber"
            ).classes("text-[11px] font-semibold")


def _render_proposals_section(proposals: list, refresh_fn) -> None:
    with ui.expansion(value=True).classes(
        "w-full rounded-2xl shadow-sm "
        "border border-amber-200 dark:border-amber-800 "
        "bg-amber-50/20 dark:bg-amber-900/5"
    ) as exp:
        with exp.add_slot("header"):
            with ui.row().classes("items-center gap-2 px-4 py-3 w-full"):
                ui.icon("repeat", size="xs").classes("text-amber-500 shrink-0")
                ui.label("Lacunes récurrentes à valider").classes(
                    "font-bold text-slate-800 dark:text-slate-100 text-base flex-1"
                )
                ui.badge(str(len(proposals)), color="amber").classes("text-xs")

        with ui.element("div").classes("px-4 pb-4 flex flex-col gap-3"):
            ui.label(
                "Ces types d'erreur sont réapparus plusieurs fois sur le même item EDN. "
                "Crée une lacune pour le signaler ou ignore pour le supprimer."
            ).classes("text-xs text-slate-500 dark:text-slate-400 italic mt-1 mb-1")
            for p in proposals:
                _render_proposal_card(p, refresh_fn)


def _render_section(
    title: str,
    items: list,
    refresh_fn,
    border: str = "",
    bg: str = "",
    collapsed: bool = False,
    subtitle: str = "",
):
    """Affiche une section de lacunes (expansion + grille de cartes)."""
    with ui.expansion(
        value=not collapsed,
    ).classes(
        f"w-full rounded-2xl shadow-sm border {border} {bg}"
    ) as exp:
        with exp.add_slot("header"):
            with ui.row().classes("items-center gap-2 px-4 py-3 w-full"):
                ui.label(title).classes(
                    "font-bold text-slate-800 dark:text-slate-100 text-base flex-1"
                )
                ui.badge(str(len(items)), color="slate").classes("text-xs")

        if subtitle:
            with ui.element("div").classes("px-4 pt-1 pb-0"):
                ui.label(subtitle).classes("text-xs text-slate-400 italic")

        with ui.element("div").classes(
            "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 px-4 pb-4"
        ):
            for wp in items:
                WeakPointCard(wp, on_refresh=refresh_fn)


# ── Dialog : Ajouter une lacune ───────────────────────────────────────────────

def open_add_dialog(refresh_fn):
    """Ouvre le formulaire d'ajout de lacune."""
    from types import SimpleNamespace

    state = SimpleNamespace(
        course_id="",
        course_title="",
        item_number="",
        category=None,
        detail="",
        severity=2,
        source_type="manuel",
    )

    with ui.dialog().props("persistent") as dialog:
        with ui.card().classes(
            "w-[540px] max-w-[92vw] rounded-3xl p-0 overflow-hidden "
            "bg-white dark:bg-slate-900 shadow-2xl"
        ).style("max-height:90vh;display:flex;flex-direction:column"):

            # Header
            with ui.element("div").classes(
                "px-6 pt-5 pb-4 border-b border-slate-100 dark:border-slate-800 shrink-0"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Ajouter une lacune").classes(
                        "text-[15px] font-bold text-slate-900 dark:text-slate-50"
                    )
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense size=sm color=grey-7"
                    )

            # Body
            with ui.element("div").classes(
                "px-6 py-5 flex flex-col gap-4 flex-1 overflow-y-auto"
            ):

                def _section_lbl(text):
                    ui.label(text).classes(
                        "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                    )

                # ── Cours ─────────────────────────────────────────────────
                _section_lbl("Cours associé")
                course_display = ui.label("Aucun cours sélectionné").classes(
                    "text-xs text-slate-400 italic"
                )

                def _open_course_picker():
                    with ui.dialog() as picker_dlg:
                        with ui.card().classes("w-[480px] max-w-[90vw] rounded-2xl p-4 gap-3"):
                            ui.label("Sélectionner un cours").classes("font-bold text-slate-800 dark:text-slate-100")
                            result_col = ui.column().classes("w-full gap-1")

                            def _do_search(q: str):
                                result_col.clear()
                                q_l = q.lower().strip()
                                if len(q_l) < 2:
                                    return
                                matches = [
                                    c for c in data_store.cours
                                    if q_l in c.title.lower()
                                    or (c.item_number and q_l in c.item_number.lower())
                                ][:12]
                                with result_col:
                                    for c in matches:
                                        itxt = f"ITEM {c.item_number} — " if c.item_number else ""
                                        def _pick(course=c):
                                            state.course_id    = course.id
                                            state.course_title = course.title
                                            state.item_number  = course.item_number or ""
                                            course_display.set_text(
                                                f"ITEM {course.item_number} — {course.title}"
                                                if course.item_number else course.title
                                            )
                                            course_display.classes(remove="text-slate-400 italic")
                                            picker_dlg.close()
                                        with ui.item(on_click=_pick).classes(
                                            "cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 "
                                            "rounded px-3 py-2 w-full"
                                        ):
                                            ui.label(f"{itxt}{c.title}").classes(
                                                "text-sm font-medium text-slate-800 dark:text-slate-100"
                                            )

                            with ui.scroll_area().classes("w-full").style("max-height:280px"):
                                ui.column().classes("w-full")
                            ui.input(
                                "Rechercher un cours…",
                                on_change=lambda e: _do_search(e.value),
                            ).props("autofocus outlined dense").classes("w-full mt-2")

                    picker_dlg.open()

                ui.button("Choisir un cours…", icon="search", on_click=_open_course_picker).props(
                    "outline dense rounded color=indigo"
                ).classes("text-xs self-start")

                # ── Catégorie ─────────────────────────────────────────────
                _section_lbl("Catégorie")
                ui.select(
                    options=_CATEGORIES,
                    value=None,
                    label="Catégorie",
                ).classes("w-full").props("outlined dense").on_value_change(
                    lambda e: setattr(state, "category", e.value)
                )

                # ── Détail ────────────────────────────────────────────────
                _section_lbl("Description de la lacune")
                ui.textarea(
                    placeholder="Ex : oubli antibioprophylaxie post-splénectomie, piège du syndrome de Li-Fraumeni…",
                ).classes("w-full").props("outlined dense autogrow").on_value_change(
                    lambda e: setattr(state, "detail", e.value or "")
                )

                # ── Sévérité ──────────────────────────────────────────────
                _section_lbl("Sévérité (1 = mineur · 5 = critique)")
                sev_btns: dict[int, ui.button] = {}
                with ui.row().classes("gap-2"):
                    for sv in range(1, 6):
                        col = "positive" if sv <= 2 else "warning" if sv == 3 else "negative"
                        b = ui.button(str(sv)).props(
                            f"{'unelevated' if sv == state.severity else 'outline'} "
                            f"round size=sm color={col}"
                        )
                        sev_btns[sv] = b

                        def _set_sev(s=sv):
                            state.severity = s
                            for sv2, btn2 in sev_btns.items():
                                col2 = "positive" if sv2 <= 2 else "warning" if sv2 == 3 else "negative"
                                if sv2 == s:
                                    btn2.props(f"unelevated round size=sm color={col2}")
                                else:
                                    btn2.props(f"outline round size=sm color={col2}")

                        b.on_click(_set_sev)

                # ── Source ────────────────────────────────────────────────
                _section_lbl("Source")
                src_btns: dict[str, ui.button] = {}
                with ui.row().classes("gap-2 flex-wrap"):
                    for src_id, src_lbl in _SOURCE_OPTS.items():
                        b = ui.button(src_lbl).props(
                            f"{'unelevated' if src_id == state.source_type else 'outline'} "
                            "rounded size=sm color=indigo"
                        )
                        src_btns[src_id] = b

                        def _set_src(s=src_id):
                            state.source_type = s
                            for si, sb in src_btns.items():
                                if si == s:
                                    sb.props("unelevated rounded size=sm color=indigo")
                                else:
                                    sb.props("outline rounded size=sm color=indigo")

                        b.on_click(_set_src)

            # Footer
            with ui.element("div").classes(
                "px-6 py-4 bg-slate-50 dark:bg-slate-800/50 "
                "border-t border-slate-100 dark:border-slate-800 "
                "flex justify-end gap-2 shrink-0"
            ):
                ui.button("Annuler", on_click=dialog.close).props("flat color=grey-8")

                def _submit():
                    detail = state.detail.strip()
                    if not detail:
                        ui.notify("La description est obligatoire.", type="warning", icon="warning")
                        return

                    wp_id = local_store.add_weak_point_full(
                        course_id=state.course_id or "—",
                        detail=detail,
                        course_title=state.course_title,
                        item_number=state.item_number,
                        category=state.category,
                        severity=state.severity,
                        source_type=state.source_type,
                    )

                    # Créer la note Obsidian si le vault est configuré
                    if settings.obsidian_vault_path:
                        try:
                            from backend.core.obsidian.weak_points_sync import create_obsidian_lacune_note
                            college = ""
                            if state.course_id:
                                c = next((x for x in data_store.cours if x.id == state.course_id), None)
                                if c and c.college:
                                    college = c.college[0] if isinstance(c.college, list) else str(c.college)
                            ok, obs_path, obs_uri = create_obsidian_lacune_note(
                                title=detail,
                                college=college,
                                severity=state.severity,
                                course_title=state.course_title,
                                item_number=state.item_number,
                                synapse_id=str(wp_id),
                                source=state.source_type,
                                status="active",
                            )
                            if ok:
                                local_store.update_weak_point_obsidian(wp_id, obs_path, obs_uri)
                        except Exception as _exc:
                            from loguru import logger
                            logger.warning(f"Création note Obsidian lacune échouée (non bloquant): {_exc}")

                    dialog.close()
                    ui.notify("Lacune ajoutée ✓", type="positive")
                    refresh_fn()

                ui.button(
                    "Ajouter ✓", on_click=_submit
                ).props("unelevated color=indigo rounded").classes("px-5 font-semibold")

    dialog.open()
