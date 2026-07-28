"""
CourseCard v4.

REST  : ITEM badge · titre · statut lecture · dot maîtrise · menu ⋯
BAR   : rail gauche coloré + barre d'actions permanente
        (Notion · OIC LiSA · +Lecture · QCM · [CTA] Séance)

Menu ⋯ (dans le header, à côté du dot de maîtrise) :
  PDF (ouvrir/chercher)
  ─────
  Suivi J3/J7/J14/J30
  ─────
  Fiche LISA · Fiche EDN · Lier note Obsidian
  ─────
  COMPLÉTION  [Résumé ✓/○] [ChatGPT ✓/○] [Anki ✓/○]
"""
from __future__ import annotations

import asyncio
from nicegui import ui

from frontend.components.course_quick_actions import (
    quick_mark_course_action,
    open_quick_session_dialog,
    open_start_tracking_dialog,
    _open_quick_qcm_dialog,
    _open_obsidian_note_action,
    _create_obsidian_note_action,
    _open_link_note_dialog,
    open_pdf_wizard,
    _delete_course_action,
)
from frontend.components.lisa_dialog import open_lisa_dialog
from backend.core.obsidian.service import obsidian_service
from backend.core.reviews import local_store as _ls
from backend.config.settings import settings as _settings
from backend.core.knowledge import service as knowledge_service


_ACCENT_HEX: dict[str, str] = {
    "gray":   "#94A3B8",
    "blue":   "#3B82F6",
    "teal":   "#0D9488",
    "cyan":   "#06B6D4",
    "indigo": "#4F46E5",
    "violet": "#7C3AED",
    "orange": "#EA580C",
    "amber":  "#D97706",
    "red":    "#DC2626",
    "green":  "#059669",
    "slate":  "#64748B",
}


def CourseCard(
    course,
    context: str = "college",
    refresh_fn=None,
    client=None,
    accent_color: str | None = None,
    is_urgent: bool = False,
) -> None:
    if client is None:
        try:
            client = ui.context.client
        except Exception:
            client = None

    # ── Données ───────────────────────────────────────────────────────────────
    if context == "college":
        has_pdf   = bool(getattr(course, "url_pdf", None))
        nb_lec    = getattr(course, "nb_lectures", 0) or 0
        date_1ere = getattr(course, "date_1ere_lecture", None)
    else:
        has_pdf   = bool(getattr(course, "url_pdf_ue", None))
        nb_lec    = getattr(course, "nb_lectures_ue", 0) or 0
        date_1ere = getattr(course, "date_1ere_lecture_ue", None)

    anki_done    = getattr(course, "anki", False)
    qcm_done     = getattr(course, "qcm_done", False)
    resume_done  = getattr(course, "resume_done", False)
    chatgpt_done = getattr(course, "chatgpt_done", False)
    item_lbl     = (
        f"ITEM {course.display_item_number}"
        if getattr(course, "display_item_number", None) else None
    )

    accent_hex = "#DC2626" if is_urgent else _ACCENT_HEX.get(accent_color or "", "#94A3B8")

    date_str = None
    if date_1ere:
        date_str = (
            date_1ere.strftime("%d/%m")
            if hasattr(date_1ere, "strftime") else str(date_1ere)
        )

    def _run(action_key: str):
        return lambda: asyncio.create_task(
            quick_mark_course_action(course, action_key, context=context, refresh_fn=refresh_fn, client=client)
        )

    # Obsidian
    _obs_configured = bool(_settings.obsidian_vault_path)
    _obs_uri        = getattr(course, "obsidian_uri", None)
    _obs_exists     = obsidian_service.note_exists(course) if _obs_configured else False

    # URLs externes
    from backend.core.lisa.item_map import lisa_url as _lisa_url_from_map
    _lisa_url   = _lisa_url_from_map(course.display_item_number, course.title)
    _notion_url = f"https://www.notion.so/{course.id.replace('-', '')}"

    # ── Card ──────────────────────────────────────────────────────────────────
    with ui.card().classes(
        "synapse-course-card w-full"
    ).style(f"--card-accent:{accent_hex};"):

        # ── Corps ─────────────────────────────────────────────────────────────
        with ui.element("div").classes("px-3.5 pt-3.5 pb-3 flex flex-col gap-2 flex-1"):

            # Ligne 1 (jamais de wrap) : ITEM · [badge retard] · [spacer] · menu ⋯
            with ui.row().classes("items-center gap-1.5 w-full flex-nowrap"):
                if item_lbl:
                    ui.label(item_lbl).classes(
                        "synapse-item-mono px-1.5 py-0.5 rounded "
                        "bg-slate-100 dark:bg-slate-800 "
                        "text-slate-500 dark:text-slate-400 shrink-0"
                    )
                if is_urgent:
                    ui.badge("En retard", color="red").classes(
                        "text-[10px] font-bold px-1.5 py-0.5 shrink-0 cursor-pointer"
                    ).on("click", lambda: open_start_tracking_dialog(
                        course, context, refresh_fn, client, is_restart=True
                    )).tooltip("Révision J30 dépassée — cliquer pour redémarrer le suivi espacé")
                if knowledge_service.is_to_situate(course.id, list(course.college or []), context):
                    ui.badge("À situer", color="grey").props("outline").classes(
                        "text-[10px] font-bold px-1.5 py-0.5 shrink-0"
                    ).tooltip("Collège validé, niveau pas encore déclaré")
                ui.element("div").classes("flex-1 min-w-0")

                # ⋯ Menu — actions secondaires (PDF, suivi, liens, Obsidian, complétion)
                # Toujours en fin de ligne 1 pour ne jamais être poussé sous le texte.
                with ui.button(icon="more_vert").props(
                    "flat round dense size=xs"
                ).classes("text-slate-300 dark:text-slate-600 shrink-0 -mr-1"):
                    with ui.menu().classes("w-64"):

                        # ── 1. PDF ─────────────────────────────────────────────
                        if has_pdf:
                            ui.menu_item(
                                "Ouvrir le PDF",
                                on_click=lambda c=course: ui.navigate.to(f"/pdf/{c.id}", new_tab=True),
                            ).props("dense").classes("text-[13px]")
                            ui.menu_item(
                                "Modifier le PDF",
                                on_click=lambda c=course: open_pdf_wizard(c, context, refresh_fn, client),
                            ).props("dense").classes("text-[13px]")
                        else:
                            ui.menu_item(
                                "Chercher un PDF…",
                                on_click=lambda c=course: open_pdf_wizard(c, context, refresh_fn, client),
                            ).props("dense").classes("text-[13px]")

                        ui.separator().classes("my-1")

                        # ── 2. Suivi de lecture ───────────────────────────────
                        _is_relance = bool(date_1ere)
                        if _is_relance:
                            ui.menu_item(
                                f"Suivi depuis {date_str}…",
                                on_click=lambda: open_start_tracking_dialog(
                                    course, context, refresh_fn, client, True
                                ),
                            ).props("dense").classes("text-[13px]")
                        else:
                            ui.menu_item(
                                "Démarrer le suivi J3/J7/J14/J30",
                                on_click=lambda: open_start_tracking_dialog(
                                    course, context, refresh_fn, client, False
                                ),
                            ).props("dense").classes("text-[13px]")

                        ui.separator().classes("my-1")

                        # ── 3. Liens externes & Obsidian ──────────────────────
                        ui.menu_item(
                            "Fiche LISA",
                            on_click=lambda url=_lisa_url: ui.navigate.to(url, new_tab=True),
                        ).props("dense").classes("text-[13px]")

                        if getattr(course, "agregation_fiche_edn", None):
                            ui.menu_item(
                                "Fiche EDN",
                                on_click=lambda url=course.agregation_fiche_edn: ui.navigate.to(
                                    url, new_tab=True
                                ),
                            ).props("dense").classes("text-[13px]")

                        if _obs_configured:
                            if _obs_uri or _obs_exists:
                                ui.menu_item(
                                    "Ouvrir note Obsidian",
                                    on_click=lambda c=course: _open_obsidian_note_action(c),
                                ).props("dense").classes("text-[13px]")
                            else:
                                ui.menu_item(
                                    "Créer note Obsidian",
                                    on_click=lambda c=course: asyncio.create_task(
                                        _create_obsidian_note_action(c, refresh_fn, client)
                                    ),
                                ).props("dense").classes("text-[13px]")
                            ui.menu_item(
                                "Lier note Obsidian…",
                                on_click=lambda c=course: _open_link_note_dialog(c, refresh_fn),
                            ).props("dense").classes("text-[13px]")

                        ui.separator().classes("my-1")

                        # ── 4. Section complétion ─────────────────────────────────
                        with ui.element("div").classes("px-2 pt-1 pb-1.5"):
                            ui.label("Complétion").classes(
                                "text-[10px] font-bold uppercase tracking-wider "
                                "text-slate-400 px-2 mb-1.5 block"
                            )

                            _completions = [
                                ("Résumé",  resume_done,  "resume"),
                                ("ChatGPT", chatgpt_done, "chatgpt"),
                                ("Anki",    anki_done,    "anki"),
                            ]
                            for lbl, done, key in _completions:
                                with ui.element("div").classes(
                                    "flex items-center gap-2.5 px-2 py-1.5 rounded-md "
                                    "cursor-pointer select-none "
                                    "hover:bg-slate-50 dark:hover:bg-slate-800/60"
                                ).on("click", _run(key)):
                                    ui.icon(
                                        "check_circle" if done else "radio_button_unchecked"
                                    ).classes(
                                        "text-[18px] shrink-0 " + (
                                            "text-green-500" if done
                                            else "text-slate-300 dark:text-slate-600"
                                        )
                                    )
                                    ui.label(lbl).classes(
                                        "text-[13px] " + (
                                            "text-slate-800 dark:text-slate-100 font-medium" if done
                                            else "text-slate-400 dark:text-slate-500"
                                        )
                                    )

                        ui.separator().classes("my-1")

                        # ── 5. Suppression ────────────────────────────────────
                        ui.menu_item(
                            "Supprimer",
                            on_click=lambda c=course: asyncio.create_task(
                                _delete_course_action(c, refresh_fn, client)
                            ),
                        ).props("dense").classes("text-[13px] text-red-500")

            # Ligne 2 : dot maîtrise + label court · [spacer] · statut lecture
            # Ligne séparée (jamais fusionnée avec le menu ⋯) : peut truncate
            # librement sans jamais faire sauter le menu à la ligne suivante.
            _mastery_labels = {
                "gray":   "À préparer",
                "blue":   "À lire",
                "teal":   "En construction",
                "cyan":   "À consolider",
                "indigo": "À entraîner",
                "orange": "Fragile",
                "red":    "Critique",
                "green":  "Maîtrisé",
                "slate":  "Non commencé",
            }
            _mastery_lbl = _mastery_labels.get(accent_color or "gray", "")
            _tooltip_txt = f"Maîtrise : {_mastery_lbl}" if _mastery_lbl else "Maîtrise non évaluée"
            with ui.row().classes("items-center gap-1.5 w-full flex-nowrap"):
                with ui.row().classes("items-center gap-1 shrink-0").tooltip(_tooltip_txt):
                    ui.element("div").style(
                        f"width:7px;height:7px;border-radius:50%;"
                        f"background:{accent_hex};flex-shrink:0;"
                    )
                    if _mastery_lbl:
                        ui.label(_mastery_lbl).classes(
                            "text-[10px] text-slate-400 dark:text-slate-500 shrink-0 leading-none"
                        )
                ui.element("div").classes("flex-1 min-w-0")

                # Statut lecture (truncate si trop long — ne pousse jamais rien)
                _lec_parts = []
                if date_str:
                    _lec_parts.append(f"1ère {date_str}")
                if nb_lec > 0:
                    _lec_parts.append(f"Lu {nb_lec}×")
                if _lec_parts:
                    ui.label(" · ".join(_lec_parts)).classes(
                        "synapse-lec-mono text-slate-400 dark:text-slate-500 "
                        "shrink truncate min-w-0"
                    )

            # Titre
            ui.label(course.title).classes(
                "text-[14px] font-semibold text-slate-900 dark:text-slate-100 leading-snug"
            ).style(
                "display:-webkit-box;-webkit-line-clamp:2;"
                "-webkit-box-orient:vertical;overflow:hidden;word-break:break-word"
            ).tooltip(course.title)

        # ── Barre d'actions — toujours visible : les 5 actions les + fréquentes ──
        with ui.element("div").classes("synapse-action-bar"):

            # Notion
            ui.button(
                icon="description",
                on_click=lambda url=_notion_url: ui.navigate.to(url, new_tab=True),
            ).props("flat round dense size=sm").classes(
                "text-slate-700 dark:text-slate-300 shrink-0"
            ).tooltip("Ouvrir dans Notion")

            # OIC LiSA — couleur du drapeau reflète l'état d'import :
            #   gris  = jamais récupérés · ambre = récupérés mais vides (0 OIC)
            #   bleu  = objectifs rentrés (le nombre maîtrisés s'affiche en tooltip)
            # Quasar applique "text-primary !important" par défaut sur les
            # boutons flat sans color= explicite, ce qui écrase toute classe
            # Tailwind text-*. On passe donc la couleur via le prop Quasar
            # natif color=, comme pour les autres états (QCM color=grey…).
            _oics = _ls.get_lisa_oic(course.id)
            if _oics is None:
                _flag_color = "grey-5"
                _flag_tip = "Objectifs OIC — non récupérés, cliquer pour charger depuis LiSA"
            elif len(_oics) == 0:
                _flag_color = "amber-7"
                _flag_tip = "Objectifs OIC — aucun trouvé sur LiSA"
            else:
                _oic_mastered = sum(1 for o in _oics if o["mastered"])
                _flag_color = "blue-7"
                _flag_tip = f"Objectifs OIC — {_oic_mastered}/{len(_oics)} maîtrisés"
            ui.button(
                icon="flag",
                on_click=lambda c=course: open_lisa_dialog(c, refresh_fn=refresh_fn),
            ).props(f"flat round dense size=sm color={_flag_color}").classes(
                "shrink-0"
            ).tooltip(_flag_tip)

            # +1 lecture
            ui.button(
                icon="add_circle",
                on_click=_run("lecture"),
            ).props("flat round dense size=sm color=green").classes(
                "shrink-0"
            ).tooltip(f"Ajouter une lecture (actuellement {nb_lec}×)")

            # QCM — état reflète qcm_done, comportement inchangé
            if qcm_done:
                ui.button(
                    icon="quiz",
                    on_click=_run("qcm"),
                ).props("flat round dense size=sm").classes(
                    "text-violet-600 dark:text-violet-400 shrink-0"
                ).tooltip("QCM fait — cliquer pour basculer")
            else:
                ui.button(
                    icon="quiz",
                    on_click=lambda c=course: _open_quick_qcm_dialog(c, refresh_fn),
                ).props("flat round dense size=sm color=grey").classes(
                    "shrink-0"
                ).tooltip("Logger un résultat QCM")

            ui.element("div").classes("flex-1")

            # Séance — CTA principal (outline discret : s'intègre à la barre
            # d'icônes flat plutôt que de la dominer visuellement)
            ui.button(
                "Séance",
                icon="add_task",
                on_click=lambda: open_quick_session_dialog(course, refresh_fn, client),
            ).props("outline dense size=sm color=indigo").classes(
                "shrink-0 !rounded-lg px-3 font-semibold"
            ).tooltip("Nouvelle séance de travail")
