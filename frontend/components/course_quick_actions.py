"""
course_quick_actions.py
-----------------------
Actions rapides sur un cours depuis la page Stats (ou n'importe quelle page).

Chaque action :
  1. Met à jour Notion de façon optimiste via update_course_action().
  2. Si Notion confirme → enregistre une StudySession SQLite.
  3. Refresh UI.

Aucune StudySession n'est écrite si Notion échoue (rollback déjà géré en amont).
"""

from __future__ import annotations

from loguru import logger
from nicegui import ui

from backend.config.settings import settings, NOTION_PROPS as P
from backend.core.notion.payloads import number, checkbox
from backend.core.reviews import local_store
from backend.core.tracking.service import tracking_service
from frontend.utils import update_course_action
from backend.core.files import file_service
from backend.core.google.calendar_service import calendar_service
from backend.core.obsidian.service import obsidian_service
from backend.config.settings import settings as _settings
from backend.core.notion.client import notion_client
from backend.state.store import data_store

import os
import datetime
import asyncio
from zoneinfo import ZoneInfo

_TZ_REUNION = ZoneInfo("Indian/Reunion")


# ── Configuration des actions ─────────────────────────────────────────────────
# Chaque entrée décrit : payload Notion, activité SQLite, durée estimée.

_ACTIONS: dict[str, dict] = {
    "lecture": {
        "label": "+ Lecture",
        "icon": "menu_book",
        "activity_types": ["lecture"],
        "duration": 20,
        # prop résolu dynamiquement selon context (college / ue)
    },
    "resume": {
        "label": "Résumé",
        "icon": "summarize",
        "activity_types": ["fiche"],
        "duration": 30,
        "prop": P.RESUME_COLLEGE,
        "prop_ue": P.RESUME_UE,
        "attr": "resume_done",
    },
    "anki": {
        "label": "Anki",
        "icon": "style",
        "activity_types": ["anki"],
        "duration": 10,
        "prop": P.ANKI_COLLEGE,
        "prop_ue": P.ANKI_UE,
        "attr": "anki",
    },
    "qcm": {
        "label": "QCM",
        "icon": "quiz",
        "activity_types": ["qcm"],
        "duration": 20,
        "prop": P.QCM_COLLEGE,
        "prop_ue": P.QCM_FAIT,
        "attr": "qcm_done",
    },
    "chatgpt": {
        "label": "ChatGPT",
        "icon": "smart_toy",
        "activity_types": ["révision"],
        "duration": 10,
        "prop": P.CHATGPT_COLLEGE,
        "prop_ue": P.CHATGPT_UE,
        "attr": "chatgpt_done",
    },
}


async def quick_mark_course_action(
    course,
    action: str,
    context: str = "college",
    refresh_fn=None,
    client=None,
) -> None:
    """
    Exécute une action rapide sur un cours.

    course     : objet Cours (data_store.cours)
    action     : clé dans _ACTIONS ('lecture', 'anki', 'qcm', 'resume', 'chatgpt')
    context    : 'college' ou 'ue' — détermine quelle propriété Notion écrire
    refresh_fn : callable → re-render la page appelante
    client     : ui.context.client pour notifier depuis un background task
    """
    if not client:
        try:
            client = ui.context.client
        except Exception:
            pass

    cfg = _ACTIONS.get(action)
    if cfg is None:
        logger.warning(f"quick_mark_course_action: action inconnue '{action}'")
        return

    # ── Construire le payload Notion ──────────────────────────────────────────
    properties: dict = {}

    if action == "lecture":
        if context == "ue":
            new_count = (getattr(course, "nb_lectures_ue", 0) or 0) + 1
            properties[P.NB_LECTURES_UE] = number(new_count)
        else:
            new_count = (getattr(course, "nb_lectures", 0) or 0) + 1
            properties[P.NB_LECTURES_COLLEGE] = number(new_count)
    else:
        prop_key = cfg.get("prop_ue") if context == "ue" else cfg.get("prop")
        if prop_key:
            properties[prop_key] = checkbox(True)

    if not properties:
        return

    # ── Mise à jour optimiste + Notion (bloquant — attend la réponse Notion) ──
    success = await update_course_action(
        course, properties, refresh_fn=refresh_fn, client=client
    )

    if not success:
        return  # rollback + notification déjà gérés dans update_course_action

    # ── SQLite : enregistrer la session uniquement si Notion a confirmé ───────
    try:
        local_store.add_study_session(
            course_id=course.id,
            course_title=getattr(course, "title", ""),
            item_number=getattr(course, "item_number", "") or "",
            context="college",
            activity_types=cfg["activity_types"],
            duration_minutes=cfg["duration"],
        )
    except Exception as exc:
        logger.warning(f"quick_action SQLite (non-bloquant): {exc}")

    # Refresh final (inclut maintenant les nouvelles données de session SQLite)
    if refresh_fn:
        if client:
            with client:
                refresh_fn()
        else:
            refresh_fn()


def open_quick_session_dialog(course, refresh_fn=None, client=None) -> None:
    """
    Modale légère pour enregistrer une séance détaillée (SQLite uniquement, pas Notion).
    Utilisable depuis Stats et Collèges.
    """
    from types import SimpleNamespace as NS

    title = getattr(course, "display_title", None) or course.title

    s = NS(activity_types=["révision"], duration=20, confidence=3, difficulty="moyen", notes="")

    ACTS = ["révision", "lecture", "qcm", "dp", "anki", "fiche", "correction"]
    ACT_COLORS = {
        "révision": "blue", "lecture": "indigo", "qcm": "purple",
        "dp": "pink", "anki": "green", "fiche": "teal", "correction": "orange",
    }

    def _chip_on(col): return f"unelevated rounded size=sm color={col}"
    def _chip_off(): return "outline rounded size=sm color=grey"

    with ui.dialog() as dlg, ui.card().classes(
        "rounded-2xl p-0 overflow-hidden w-[480px] max-w-[92vw]"
    ):
        with ui.element("div").classes("px-5 pt-5 pb-3"):
            ui.label("Séance de travail").classes("text-sm font-bold text-slate-800 dark:text-slate-100")
            ui.label(title).classes("text-xs text-slate-400 mt-0.5")

        ui.separator()

        with ui.element("div").classes("px-5 py-4 flex flex-col gap-4"):
            # Activités
            ui.label("Activités").classes("text-xs font-bold uppercase tracking-widest text-slate-400")
            act_btns: dict[str, object] = {}
            with ui.row().classes("gap-1 flex-wrap"):
                for act in ACTS:
                    col = ACT_COLORS.get(act, "grey")
                    def toggle_act(a=act, c=col):
                        if a in s.activity_types:
                            if len(s.activity_types) > 1:
                                s.activity_types.remove(a)
                                act_btns[a].props(remove=_chip_on(c), add=_chip_off())
                        else:
                            s.activity_types.append(a)
                            act_btns[a].props(remove=_chip_off(), add=_chip_on(c))
                    btn = ui.button(act.capitalize(), on_click=toggle_act)
                    btn.props(_chip_on(col) if act in s.activity_types else _chip_off())
                    act_btns[act] = btn

            # Durée
            ui.label("Durée (min)").classes("text-xs font-bold uppercase tracking-widest text-slate-400")
            dur_btns: dict[int, object] = {}
            with ui.row().classes("gap-1 flex-wrap"):
                for d in [10, 20, 30, 45, 60]:
                    def set_dur(dv=d):
                        s.duration = dv
                        for dval, db in dur_btns.items():
                            db.props(remove=_chip_on("blue"), add=_chip_off()) if dval != dv else db.props(remove=_chip_off(), add=_chip_on("blue"))
                    btn = ui.button(f"{d} min", on_click=set_dur)
                    btn.props(_chip_on("blue") if d == s.duration else _chip_off())
                    dur_btns[d] = btn

            # Confiance
            ui.label("Confiance").classes("text-xs font-bold uppercase tracking-widest text-slate-400")
            conf_btns: dict[int, object] = {}
            with ui.row().classes("gap-1"):
                for v in range(1, 6):
                    def set_conf(cv=v):
                        s.confidence = cv
                        for cv2, cb in conf_btns.items():
                            cb.props(remove=_chip_on("positive"), add=_chip_off()) if cv2 != cv else cb.props(remove=_chip_off(), add=_chip_on("positive"))
                    btn = ui.button(str(v), on_click=set_conf)
                    btn.props(_chip_on("positive") if v == s.confidence else _chip_off())
                    conf_btns[v] = btn

            # Note
            ui.label("Note / piège EDN").classes("text-xs font-bold uppercase tracking-widest text-slate-400")
            ui.textarea(on_change=lambda e: setattr(s, "notes", e.value)).props(
                "outlined dense autogrow rows=2"
            ).classes("w-full text-sm")

        with ui.element("div").classes("flex justify-end gap-2 px-5 py-3 bg-slate-50 dark:bg-slate-800/50"):
            ui.button("Annuler", on_click=dlg.close).props("flat rounded size=sm color=grey")

            async def on_validate():
                try:
                    local_store.add_study_session(
                        course_id=course.id,
                        course_title=getattr(course, "title", ""),
                        item_number=getattr(course, "item_number", "") or "",
                        context="college",
                        activity_types=s.activity_types,
                        duration_minutes=s.duration,
                        confidence=s.confidence,
                        difficulty=s.difficulty,
                        notes=s.notes or None,
                    )
                    # +1 lecture sur Notion si activité "lecture" ou "révision"
                    if any(a in s.activity_types for a in ("lecture", "révision")):
                        new_count = (getattr(course, "nb_lectures", 0) or 0) + 1
                        await update_course_action(
                            course,
                            {P.NB_LECTURES_COLLEGE: number(new_count)},
                            refresh_fn=None,
                            client=client,
                        )
                    dlg.close()
                    ui.notify("Séance enregistrée ✓", type="positive")
                    if refresh_fn:
                        if client:
                            with client:
                                refresh_fn()
                        else:
                            refresh_fn()
                except Exception as exc:
                    ui.notify(f"Erreur : {exc}", type="negative")

            ui.button("Enregistrer", on_click=on_validate).props("unelevated rounded size=sm color=positive")

    dlg.open()


# ── Quick log QCM ────────────────────────────────────────────────────────────

def _open_quick_qcm_dialog(course, refresh_fn) -> None:
    """
    Popup minimaliste pour logger un résultat QCM en 3 clics :
    plateforme → score → valider.
    """
    from backend.core.reviews.local_store import add_qcm_session_full, add_weak_point_full
    from backend.core.qcm.service import parse_score, is_failed, suggested_severity, QCM_PASS_THRESHOLD

    state = {"platform": "EDNpro", "score_raw": ""}

    with ui.dialog() as dlg:
        with ui.card().classes(
            "w-80 rounded-2xl p-0 overflow-hidden"
        ):
            # Header
            with ui.row().classes(
                "items-center gap-2 px-4 py-3 "
                "bg-indigo-50 dark:bg-indigo-900/20 "
                "border-b border-indigo-100 dark:border-indigo-800"
            ):
                ui.icon("quiz", color="indigo").classes("text-lg shrink-0")
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label("QCM rapide").classes(
                        "font-bold text-sm text-indigo-800 dark:text-indigo-200"
                    )
                    ui.label(course.title or "").classes(
                        "text-[11px] text-violet-500 truncate"
                    )

            with ui.column().classes("px-4 py-3 gap-3 w-full"):
                # Plateforme
                plat_btns: dict[str, ui.button] = {}
                with ui.row().classes("gap-2"):
                    for plat, color in [("EDNpro", "purple"), ("Hypocampus", "blue")]:
                        def _set(p=plat, c=color):
                            state["platform"] = p
                            for k, b in plat_btns.items():
                                col = "purple" if k == "EDNpro" else "blue"
                                b.props(f"{'unelevated' if k == p else 'outline'} rounded size=sm color={col}")
                        b = ui.button(plat).props(
                            f"{'unelevated' if plat == 'EDNpro' else 'outline'} rounded size=sm color={color}"
                        ).on_click(_set)
                        plat_btns[plat] = b

                # Score
                score_feedback = ui.label("").classes("text-[11px] text-slate-400")

                def _on_score(e):
                    state["score_raw"] = e.value or ""
                    try:
                        pct, display = parse_score(state["score_raw"])
                        if pct is not None:
                            color = "text-green-600" if pct >= QCM_PASS_THRESHOLD else "text-red-500"
                            score_feedback.set_text(f"→ {display}")
                            score_feedback.classes(color, remove="text-slate-400 text-green-600 text-red-500")
                        else:
                            score_feedback.set_text("")
                    except Exception:
                        score_feedback.set_text("")

                score_input = ui.input(
                    placeholder="14/20  ou  70%",
                    on_change=_on_score,
                ).props("outlined dense clearable").classes("w-full")
                score_feedback  # already placed above

            # Footer
            with ui.row().classes(
                "px-4 py-3 justify-end gap-2 "
                "border-t border-slate-100 dark:border-slate-800"
            ):
                ui.button("Annuler", on_click=dlg.close).props("flat color=grey-8 size=sm")

                def _submit():
                    try:
                        pct, display = parse_score(state["score_raw"])
                    except Exception:
                        pct = None
                    if pct is None:
                        ui.notify("Score invalide (ex : 14/20 ou 70%)", type="warning")
                        return

                    today = datetime.datetime.now(_TZ_REUNION).date().isoformat()
                    add_qcm_session_full(
                        platform=state["platform"],
                        session_date=today,
                        course_id=getattr(course, "id", ""),
                        course_title=getattr(course, "title", ""),
                        item_number=getattr(course, "item_number", "") or "",
                        session_type="QCM",
                        score_percent=pct,
                        score_raw=state["score_raw"],
                    )

                    dlg.close()

                    if is_failed(pct):
                        sev = suggested_severity(pct)
                        add_weak_point_full(
                            course_id=getattr(course, "id", ""),
                            detail=f"QCM {state['platform']} : {display}",
                            course_title=getattr(course, "title", ""),
                            item_number=getattr(course, "item_number", "") or "",
                            severity=sev,
                            source_type="qcm",
                        )
                        ui.notify(
                            f"QCM enregistré · {display} — lacune créée",
                            type="warning", icon="quiz",
                        )
                    else:
                        ui.notify(f"QCM enregistré · {display}", type="positive", icon="quiz")

                    if refresh_fn:
                        refresh_fn()

                ui.button("Enregistrer ✓", on_click=_submit).props(
                    "unelevated rounded size=sm color=violet"
                )

    dlg.open()


# ── Obsidian helpers ─────────────────────────────────────────────────────────

async def _create_obsidian_note_action(course, refresh_fn, client) -> None:
    ok, result = await obsidian_service.create_course_note(course)
    try:
        ctx = client if client else ui.context.client
        with ctx:
            if ok:
                ui.notify("Note Obsidian créée ✓", type="positive", icon="edit_note")
                if refresh_fn:
                    refresh_fn()
            else:
                ui.notify(f"Erreur Obsidian : {result}", type="negative")
    except Exception:
        pass


async def _delete_course_action(course, refresh_fn, client) -> None:
    """Archive la page Notion du cours puis le retire du cache local (une page = un couple (item, collège))."""
    try:
        await notion_client.archive_page(course.id)
    except Exception as exc:
        try:
            ctx = client if client else ui.context.client
            with ctx:
                ui.notify(f"Erreur suppression : {exc}", type="negative")
        except Exception:
            pass
        return

    await data_store.remove_cours(course.id)

    try:
        ctx = client if client else ui.context.client
        with ctx:
            ui.notify(f"« {course.title} » supprimé de {', '.join(course.college)} ✓", type="warning", icon="delete")
            if refresh_fn:
                refresh_fn()
    except Exception:
        pass


def _open_obsidian_note_action(course) -> None:
    ok = obsidian_service.open_course_note(course)
    if not ok:
        ui.notify("Note Obsidian introuvable", type="warning", icon="warning")


def _open_link_note_dialog(course, refresh_fn) -> None:
    """
    Dialog pour lier manuellement une note Obsidian existante à un cours.
    Affiche les .md du dossier Cours du collège avec une recherche.
    """
    from backend.config.settings import NOTION_PROPS as P
    from backend.core.notion.payloads import rich_text

    notes = obsidian_service.list_available_notes(course)

    with ui.dialog().props("persistent") as dlg:
        with ui.card().classes(
            "w-[520px] max-w-[92vw] rounded-2xl p-0 overflow-hidden"
        ):
            # Header
            with ui.row().classes(
                "items-center gap-3 px-5 py-4 "
                "bg-indigo-50 dark:bg-indigo-900/20 "
                "border-b border-indigo-100 dark:border-indigo-800"
            ):
                ui.icon("link", color="indigo").classes("text-xl shrink-0")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label("Lier une note Obsidian existante").classes(
                        "font-bold text-indigo-800 dark:text-indigo-200"
                    )
                    ui.label(course.title or "").classes(
                        "text-xs text-indigo-500 dark:text-indigo-400 truncate"
                    )

            if not notes:
                with ui.column().classes("px-5 py-6 items-center gap-2"):
                    ui.icon("folder_off", size="lg").classes("text-slate-300")
                    ui.label("Aucune note trouvée dans ce dossier.").classes(
                        "text-sm text-slate-400"
                    )
                with ui.row().classes("px-5 py-3 justify-end border-t border-slate-100"):
                    ui.button("Fermer", on_click=dlg.close).props("flat color=grey-8")
            else:
                # Recherche
                filtered_col = ui.column().classes("px-4 py-2 gap-1 w-full")

                def _render_notes(query: str = ""):
                    filtered_col.clear()
                    q = query.strip().lower()
                    shown = [n for n in notes if q in n.stem.lower()] if q else notes
                    with filtered_col:
                        if not shown:
                            ui.label("Aucun résultat.").classes("text-xs text-slate-400 px-2 py-1")
                            return
                        for note_path in shown[:40]:
                            def _pick(p=note_path):
                                dlg.close()
                                asyncio.create_task(_link_note_to_course(course, p, refresh_fn))
                            with ui.item(on_click=_pick).classes(
                                "cursor-pointer hover:bg-violet-50 dark:hover:bg-violet-900/20 "
                                "rounded px-3 py-2 w-full"
                            ):
                                ui.label(note_path.stem).classes(
                                    "text-sm text-slate-800 dark:text-slate-100"
                                )

                with ui.column().classes("px-4 pt-3 w-full"):
                    ui.input(
                        placeholder="Rechercher…",
                        on_change=lambda e: _render_notes(e.value),
                    ).props("outlined dense clearable").classes("w-full")

                with ui.scroll_area().classes("w-full").style("max-height:320px"):
                    _render_notes()

                with ui.row().classes(
                    "px-5 py-3 justify-end border-t border-slate-100 dark:border-slate-800"
                ):
                    ui.button("Annuler", on_click=dlg.close).props("flat color=grey-8")

    dlg.open()


async def _link_note_to_course(course, note_path, refresh_fn) -> None:
    """
    Lie une note Obsidian existante à un cours :
    - écrit notion_id + synapse_id dans le frontmatter
    - pousse l'URI obsidian:// dans la propriété Notion "Obsidian"
    - met à jour course.obsidian_uri localement
    """
    from backend.core.obsidian.sync import vault_sync_service
    from backend.core.notion.service import notion_service
    from backend.core.notion.payloads import rich_text
    from backend.config.settings import NOTION_PROPS as P

    try:
        # 1. Frontmatter
        vault_sync_service._write_frontmatter_fields(note_path, {
            "notion_id":  course.id,
            "synapse_id": course.id,
        })

        # 2. URI Obsidian → Notion
        uri = obsidian_service.build_obsidian_uri(note_path)
        ok  = await notion_service.update_course(course.id, {P.OBSIDIAN: rich_text(uri)})

        if ok:
            course.obsidian_uri = uri
            ui.notify(f"Note liée ✓ — {note_path.stem}", type="positive", icon="link")
            if refresh_fn:
                refresh_fn()
        else:
            ui.notify("Frontmatter mis à jour, mais erreur Notion", type="warning")

    except Exception as exc:
        from loguru import logger
        logger.error(f"_link_note_to_course: {exc}")
        ui.notify(f"Erreur : {exc}", type="negative")


# ── COMPOSANT UNIFIÉ : CourseQuickActions (V4) ────────────────────────────────

def open_pdf_wizard(c, context: str, refresh_fn, client) -> None:
    """
    Wizard PDF : scan automatique puis recherche manuelle en fallback.

    1. Ouvre un dialog avec un spinner.
    2. Lance auto_detect_pdf en tâche async.
    3. Si trouvé → affiche le fichier + bouton "Lier".
    4. Si non trouvé → affiche une recherche manuelle pré-remplie.
    """
    from backend.core.files import file_service as _fs

    state = {"found_path": None}

    # Répertoire de recherche pour la recherche manuelle
    if context == "college":
        base_dir = os.path.join(settings.medicine_dir, "Collèges")
        manual_search_path = base_dir
        if c.college:
            college_dir = _fs._get_college_folder(base_dir, c.college[0])
            if college_dir:
                manual_search_path = college_dir
    else:
        manual_search_path = settings.fac_dir or settings.medicine_dir
    if not manual_search_path or not os.path.exists(manual_search_path):
        manual_search_path = settings.medicine_dir or ""

    with ui.dialog() as dlg, ui.card().classes(
        "w-[520px] max-w-[92vw] rounded-2xl p-0 overflow-hidden"
    ):
        # Header
        with ui.row().classes(
            "items-center gap-3 px-5 py-4 "
            "bg-indigo-50 dark:bg-indigo-900/20 "
            "border-b border-indigo-100 dark:border-indigo-800"
        ):
            ui.icon("picture_as_pdf", color="indigo").classes("text-xl shrink-0")
            with ui.column().classes("gap-0 flex-1"):
                ui.label("Lier un PDF").classes(
                    "font-bold text-sm text-indigo-800 dark:text-indigo-200"
                )
                ui.label(c.title or "").classes(
                    "text-xs text-indigo-500 dark:text-indigo-400 truncate"
                )

        # Corps — zone reactive
        body = ui.element("div").classes("px-5 py-4 w-full")

        # Footer
        with ui.row().classes(
            "px-5 py-3 justify-end gap-2 "
            "border-t border-slate-100 dark:border-slate-800"
        ):
            ui.button("Fermer", on_click=dlg.close).props("flat color=grey-8")
            link_btn = (
                ui.button("Lier ce PDF", icon="link")
                .props("unelevated rounded color=green")
                .classes("hidden")
            )

        # ── Helpers d'affichage ────────────────────────────────────────────────

        def _show_scanning():
            body.clear()
            with body:
                with ui.row().classes("items-center gap-3 py-4"):
                    ui.spinner("dots", size="sm", color="indigo")
                    ui.label("Scan automatique en cours…").classes(
                        "text-sm text-slate-500 dark:text-slate-400"
                    )

        def _show_found(path: str):
            body.clear()
            with body:
                filename = os.path.basename(path)
                with ui.row().classes(
                    "items-start gap-3 p-3 rounded-xl "
                    "bg-green-50 dark:bg-green-900/20 "
                    "border border-green-200 dark:border-green-800"
                ):
                    ui.icon("check_circle", color="green").classes("text-xl shrink-0 mt-0.5")
                    with ui.column().classes("gap-0.5 min-w-0"):
                        ui.label("PDF trouvé automatiquement").classes(
                            "text-sm font-bold text-green-800 dark:text-green-300"
                        )
                        ui.label(filename).classes(
                            "text-xs text-green-600 dark:text-green-400 break-all"
                        )
                        ui.label(path).classes("text-[10px] text-slate-400 break-all")

        def _build_manual_search():
            results_col = ui.column().classes("w-full gap-0.5 mt-1 max-h-[280px] overflow-y-auto")

            def _run_search(query: str):
                results_col.clear()
                if not query or len(query) < 2:
                    with results_col:
                        ui.label("Tapez au moins 2 caractères…").classes(
                            "text-xs text-slate-400 italic px-2 py-1"
                        )
                    return
                if not manual_search_path:
                    with results_col:
                        ui.label("Dossier Collèges non configuré.").classes("text-xs text-red-500 px-2")
                    return
                files = _fs.find_pdf(
                    query,
                    search_path=manual_search_path,
                    item_number=str(c.item_number) if c.item_number else None,
                    limit=10,
                )
                with results_col:
                    if not files:
                        ui.label("Aucun résultat.").classes(
                            "text-xs text-slate-400 italic px-2 py-1"
                        )
                        return
                    for p in files:
                        fname = os.path.basename(p)

                        def _pick(picked=p):
                            state["found_path"] = picked
                            results_col.clear()
                            with results_col:
                                with ui.row().classes(
                                    "items-center gap-2 p-2 rounded-lg "
                                    "bg-green-50 dark:bg-green-900/20 "
                                    "border border-green-200 dark:border-green-800"
                                ):
                                    ui.icon("check_circle", color="green").classes("shrink-0 text-base")
                                    ui.label(os.path.basename(picked)).classes(
                                        "text-sm font-medium text-green-800 dark:text-green-300 break-all"
                                    )
                            link_btn.classes(remove="hidden")

                        with ui.item(on_click=_pick).classes(
                            "w-full cursor-pointer rounded-lg "
                            "hover:bg-slate-50 dark:hover:bg-slate-800/60 p-2"
                        ):
                            with ui.column().classes("gap-0"):
                                ui.label(fname).classes(
                                    "text-sm font-medium text-slate-800 dark:text-slate-100"
                                )
                                ui.label(p).classes("text-[10px] text-slate-400 break-all")

            init_q = c.title or ""
            ui.input(
                placeholder="Rechercher…",
                value=init_q,
                on_change=lambda e: _run_search(e.value),
            ).props("outlined dense clearable autofocus").classes("w-full")
            _run_search(init_q)

        def _show_not_found():
            body.clear()
            with body:
                with ui.row().classes(
                    "items-center gap-2 p-3 mb-3 rounded-xl "
                    "bg-amber-50 dark:bg-amber-900/20 "
                    "border border-amber-200 dark:border-amber-700"
                ):
                    ui.icon("search_off", color="amber-600").classes("text-lg shrink-0")
                    ui.label("Aucun PDF détecté — recherche manuelle :").classes(
                        "text-sm text-amber-800 dark:text-amber-300"
                    )
                _build_manual_search()

        # ── Action de liaison ──────────────────────────────────────────────────

        async def _link_pdf():
            path = state.get("found_path")
            if not path:
                return
            uri = f"file:///{path.replace(os.sep, '/')}"
            attr = "url_pdf" if context == "college" else "url_pdf_ue"
            prop = P.URL_PDF_COLLEGE if context == "college" else P.URL_PDF_UE
            dlg.close()
            await update_course_action(
                c, {prop: {"url": uri}}, refresh_fn=refresh_fn, client=client
            )
            try:
                ctx = client if client else ui.context.client
                with ctx:
                    setattr(c, attr, uri)
                    ui.notify("PDF lié ✓", type="positive", icon="picture_as_pdf")
                    if refresh_fn:
                        refresh_fn()
            except Exception:
                pass

        link_btn.on("click", lambda: asyncio.create_task(_link_pdf()))

        # ── Scan automatique au chargement ─────────────────────────────────────

        async def _do_scan():
            try:
                path = await _fs.auto_detect_pdf(c, context)
                try:
                    ctx = client if client else ui.context.client
                    with ctx:
                        if path:
                            state["found_path"] = path
                            _show_found(path)
                            link_btn.classes(remove="hidden")
                        else:
                            _show_not_found()
                except Exception:
                    if path:
                        state["found_path"] = path
                        _show_found(path)
                        link_btn.classes(remove="hidden")
                    else:
                        _show_not_found()
            except Exception as exc:
                body.clear()
                with body:
                    ui.label(f"Erreur scan : {exc}").classes("text-sm text-red-500")

        _show_scanning()
        asyncio.create_task(_do_scan())

    dlg.open()


# Alias rétro-compatible (utilisé dans les menus ⋯ existants)
open_link_pdf_unified = open_pdf_wizard


async def _sync_calendar_events(
    course, context: str, date_ref: datetime.date, client
) -> None:
    """
    Crée les 4 événements J3/J7/J14/J30 dans Google Calendar.
    Appelé après validation Notion, uniquement si l'utilisateur l'a demandé.
    """
    events_data = [
        (f"J3  ({context.upper()})",  date_ref + datetime.timedelta(days=3)),
        (f"J7  ({context.upper()})",  date_ref + datetime.timedelta(days=7)),
        (f"J14 ({context.upper()})", date_ref + datetime.timedelta(days=14)),
        (f"J30 ({context.upper()})", date_ref + datetime.timedelta(days=30)),
    ]
    item_part = f"ITEM {course.item_number} - " if getattr(course, "item_number", None) else ""
    count = 0
    for prefix, day in events_data:
        start_dt = datetime.datetime.combine(day, datetime.time(8, 0))
        res = await calendar_service.create_event(
            summary=f"{prefix} - {item_part}{course.title}",
            start_time_iso=start_dt,
            duration_minutes=60,
            description=f"Rappel Synapse — {course.title}",
            color_id="6" if context == "college" else "5",
            reminders={"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]},
        )
        if res:
            count += 1
    if client:
        with client:
            if count == len(events_data):
                ui.notify(f"📅 {count} événements Google Calendar ajoutés", type="positive")
            else:
                ui.notify(f"📅 {count}/{len(events_data)} événements ajoutés", type="warning")


def open_start_tracking_dialog(
    course, context: str, refresh_fn, client, is_restart: bool = False
) -> None:
    """
    Modale «Démarrer le suivi du cours» (Phase A).

    - Bloque si aucun PDF n'est lié.
    - Date par défaut = aujourd'hui, modifiable.
    - Affiche un bandeau d'avertissement en cas de redémarrage.
    - Explique la programmation J3/J7/J14/J30.
    - Switch optionnel Google Calendar.
    - Appelle notion_service.start_course_tracking() via update_course_action.
    """
    # ── Vérification PDF ──────────────────────────────────────────────────────
    has_pdf = bool(course.url_pdf if context == "college" else course.url_pdf_ue)
    if not has_pdf:
        _notify = ui.notify if client is None else (lambda *a, **kw: (lambda: ui.notify(*a, **kw))()  )
        try:
            if client:
                with client:
                    ui.notify(
                        "Liez d'abord un PDF avant de démarrer le suivi.",
                        type="warning",
                        icon="link",
                    )
            else:
                ui.notify(
                    "Liez d'abord un PDF avant de démarrer le suivi.",
                    type="warning",
                    icon="link",
                )
        except Exception:
            pass
        return

    # ── État local du dialog ──────────────────────────────────────────────────
    _state = {
        "date_str": datetime.date.today().isoformat(),
        "sync_calendar": False,
    }

    # ── Dialog ───────────────────────────────────────────────────────────────
    with ui.dialog().props("persistent") as dlg:
        with ui.card().classes(
            "w-[460px] max-w-[94vw] rounded-2xl p-0 overflow-hidden "
            "bg-white dark:bg-slate-900 shadow-2xl"
        ).style("max-height:92vh;display:flex;flex-direction:column"):
            # Header
            with ui.element("div").classes(
                "px-6 pt-5 pb-4 border-b border-slate-100 dark:border-slate-800"
            ):
                with ui.row().classes("items-start justify-between gap-3"):
                    with ui.column().classes("gap-0.5 min-w-0 flex-1"):
                        ui.label(
                            "Redémarrer le suivi" if is_restart else "Démarrer le suivi du cours"
                        ).classes("text-[15px] font-bold text-slate-900 dark:text-slate-50")
                        ui.label(course.display_title).classes(
                            "text-xs text-slate-400"
                        ).style("overflow:hidden;white-space:nowrap;text-overflow:ellipsis")
                    ui.button(icon="close", on_click=dlg.close).props(
                        "flat round dense size=sm color=grey-7"
                    )

            # Body (scrollable si contenu haut)
            with ui.element("div").classes("px-6 py-5 flex flex-col gap-5 flex-1").style("overflow-y:auto"):

                # Avertissement si redémarrage
                if is_restart:
                    with ui.row().classes(
                        "items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 "
                        "rounded-xl border border-amber-200 dark:border-amber-700"
                    ):
                        ui.icon("warning_amber", color="amber-600").classes(
                            "text-lg shrink-0 mt-0.5"
                        )
                        ui.label(
                            "Les rappels J3, J7, J14 et J30 seront recalculés "
                            "à partir de la nouvelle date choisie."
                        ).classes("text-xs text-amber-800 dark:text-amber-300 leading-snug")

                # Date — champ texte avec popup calendrier (évite le grand inline QDate)
                ui.label("DATE DE PREMIÈRE LECTURE").classes(
                    "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                )
                with ui.input(
                    value=datetime.date.today().strftime("%d/%m/%Y"),
                    placeholder="JJ/MM/AAAA",
                ).props("outlined dense mask='##/##/####'").classes("w-full") as date_field:
                    with date_field.add_slot("append"):
                        ui.icon("event").classes("cursor-pointer").on(
                            "click", lambda: date_picker.open()
                        )
                    with ui.menu().props("no-parent-event") as date_picker:
                        with ui.date(mask="DD/MM/YYYY").props(
                            "today-btn first-day-of-week=1"
                        ) as date_cal:
                            date_cal.bind_value(date_field)
                            date_cal.on_value_change(lambda e: (
                                _state.update({
                                    "date_str": (
                                        datetime.datetime.strptime(e.value, "%d/%m/%Y").date().isoformat()
                                        if e.value and len(e.value) == 10
                                        else datetime.date.today().isoformat()
                                    )
                                }),
                                date_picker.close(),
                            ))

                # Info J3→J30
                with ui.row().classes(
                    "items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 "
                    "rounded-xl border border-blue-100 dark:border-blue-800"
                ):
                    ui.icon("info_outline", color="blue-500").classes(
                        "text-base shrink-0 mt-0.5"
                    )
                    ui.label(
                        "Synapse programmera les rappels J3, J7, J14 et J30 "
                        "dans Notion à partir de cette date."
                    ).classes("text-xs text-blue-700 dark:text-blue-300 leading-snug")

                # Google Calendar switch
                cal_switch = ui.switch(
                    "Ajouter les rappels à Google Calendar"
                ).props("color=indigo")
                cal_switch.on_value_change(
                    lambda e: _state.update({"sync_calendar": e.value})
                )

            # Footer
            with ui.element("div").classes(
                "px-6 py-4 bg-slate-50 dark:bg-slate-800/50 "
                "border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2"
            ):
                ui.button("Annuler", on_click=dlg.close).props("flat color=grey-8")

                async def _on_confirm():
                    try:
                        date_ref = datetime.date.fromisoformat(_state["date_str"])
                    except (ValueError, TypeError):
                        date_ref = datetime.date.today()

                    # Payload calculé par tracking_service (source unique de vérité)
                    updates = tracking_service.build_tracking_payload(context, date_ref)

                    dlg.close()
                    ok = await update_course_action(
                        course, updates, refresh_fn=refresh_fn, client=client
                    )

                    if ok:
                        lbl = "Suivi redémarré" if is_restart else "Suivi démarré"
                        try:
                            ctx = client if client else ui.context.client
                            with ctx:
                                ui.notify(f"✓ {lbl} : {course.title}", type="positive")
                        except Exception:
                            pass

                        if _state["sync_calendar"]:
                            try:
                                ctx = client if client else ui.context.client
                                with ctx:
                                    ui.notify("Connexion à Google Calendar…", type="info")
                                await _sync_calendar_events(course, context, date_ref, client)
                            except Exception as exc:
                                logger.warning(f"Calendar sync failed: {exc}")

                ui.button(
                    "Redémarrer" if is_restart else "Démarrer",
                    on_click=lambda: asyncio.create_task(_on_confirm()),
                ).props("unelevated color=orange rounded").classes("px-5 font-semibold")

    dlg.open()


def CourseQuickActions(course, context: str = "college", mode: str = "full", refresh_fn=None, client=None):
    """
    Composant unifié de pilotage d'un cours.
    - 'micro'   : PDF/Lier · Lu X× · Fiche EDN · menu ⋯
    - 'compact' : PDF/Lier · Lu X× · Fiche EDN · menu ⋯  (idem micro, menu enrichi)
    - 'full'    : Tous les boutons affichés directement.
    """
    if client is None:
        try:
            client = ui.context.client
        except Exception:
            pass

    has_pdf = bool(course.url_pdf if context == "college" else course.url_pdf_ue)
    has_first_read = bool(course.date_1ere_lecture if context == "college" else course.date_1ere_lecture_ue)
    nb_lectures = getattr(course, "nb_lectures", 0) if context == "college" else getattr(course, "nb_lectures_ue", 0)
    resume_done = getattr(course, "resume_done", False)
    qcm_done = getattr(course, "qcm_done", False)
    anki_done = getattr(course, "anki", False)
    chatgpt_done = getattr(course, "chatgpt_done", False)

    obsidian_configured = bool(_settings.obsidian_vault_path)
    obsidian_note_exists = obsidian_service.note_exists(course) if obsidian_configured else False

    def _run(action_key: str):
        return lambda c=course, a=action_key: asyncio.create_task(
            quick_mark_course_action(c, a, context=context, refresh_fn=refresh_fn, client=client)
        )

    DONE = "unelevated size=sm rounded color=positive"
    READY = "outline size=sm rounded color=grey-7"
    MENU_ITEM = "text-sm text-slate-700 dark:text-slate-300 w-full"

    with ui.row().classes("gap-1.5 items-center flex-nowrap w-full"):

        # 1. PDF / Lier
        if has_pdf:
            ui.button(
                icon="picture_as_pdf",
                on_click=lambda c=course: ui.navigate.to(f"/pdf/{c.id}", new_tab=True),
            ).props("flat size=sm round color=slate").classes(
                "text-red-500 bg-red-50 dark:bg-red-900/20 shrink-0"
            ).tooltip("Ouvrir PDF")
        else:
            ui.button(
                icon="picture_as_pdf",
                on_click=lambda c=course: open_pdf_wizard(c, context, refresh_fn, client),
            ).props("flat size=sm round").classes(
                "text-slate-300 hover:text-indigo-400 shrink-0"
            ).tooltip("Chercher un PDF automatiquement")

        # 2. Lectures : compteur + bouton +
        with ui.row().classes(
            "items-center gap-0 border border-slate-200 dark:border-slate-700 "
            "rounded-lg overflow-hidden bg-white dark:bg-slate-800 shrink-0"
        ):
            ui.label(f"Lu {nb_lectures}×").classes(
                "px-2 text-xs font-semibold text-slate-600 dark:text-slate-300 select-none"
            )
            ui.button(icon="add", on_click=_run("lecture")).props(
                "flat dense size=sm color=green"
            ).classes(
                "border-l border-slate-200 dark:border-slate-700 "
                "hover:bg-green-50 dark:hover:bg-green-900/20"
            )

        # 3. Boutons full uniquement
        if mode == "full":
            if not has_first_read:
                # PDF absent → bouton désactivé avec tooltip explicatif
                _track_btn = ui.button(
                    "Démarrer le suivi",
                    icon="play_circle",
                    on_click=lambda c=course: open_start_tracking_dialog(
                        c, context, refresh_fn, client, is_restart=False
                    ),
                ).props(
                    f"{'outline' if not has_pdf else 'unelevated'} size=sm rounded color=orange"
                ).classes("shrink-0 font-semibold")
                if not has_pdf:
                    _track_btn.tooltip("Liez d'abord un PDF pour démarrer le suivi")
            else:
                # Suivi déjà démarré → bouton discret pour redémarrer
                date_1ere = course.date_1ere_lecture if context == "college" else course.date_1ere_lecture_ue
                ui.button(
                    f"Depuis {date_1ere.strftime('%d/%m')}",
                    icon="restart_alt",
                    on_click=lambda c=course: open_start_tracking_dialog(
                        c, context, refresh_fn, client, is_restart=True
                    ),
                ).props("flat size=sm rounded color=indigo").classes(
                    "bg-indigo-50 dark:bg-indigo-900/20 shrink-0"
                ).tooltip("Redémarrer le suivi avec une nouvelle date")

            ui.button("Résumé", icon="summarize", on_click=_run("resume")).props(
                DONE if resume_done else READY
            )
            # QCM : si déjà fait → marquer/démarquer via _run ; sinon → quick log
            if qcm_done:
                ui.button("QCM ✓", icon="quiz", on_click=_run("qcm")).props(DONE)
            else:
                with ui.button("QCM", icon="quiz").props(READY):
                    with ui.menu():
                        ui.menu_item(
                            "📝 Logger un résultat EDNpro / Hypocampus",
                            on_click=lambda c=course: _open_quick_qcm_dialog(c, refresh_fn),
                        ).classes("text-sm font-semibold text-violet-700")
                        ui.menu_item(
                            "✓ Marquer QCM fait (sans score)",
                            on_click=_run("qcm"),
                        ).classes("text-sm text-slate-500")
            ui.button("Anki", icon="style", on_click=_run("anki")).props(
                DONE if anki_done else READY
            )
            ui.button("ChatGPT", icon="smart_toy", on_click=_run("chatgpt")).props(
                DONE if chatgpt_done else READY
            )
            ui.button(
                "Séance",
                icon="edit_note",
                on_click=lambda c=course: open_quick_session_dialog(c, refresh_fn, client),
            ).props("outline size=sm rounded color=indigo")

        # 4. Fiche EDN (tous modes)
        if getattr(course, "agregation_fiche_edn", None):
            ui.button(
                icon="auto_stories",
                on_click=lambda c=course: ui.navigate.to(c.agregation_fiche_edn, new_tab=True),
            ).props("flat size=sm round color=slate-600").classes(
                "bg-slate-100 dark:bg-slate-800 shrink-0"
            ).tooltip("Fiche EDN")

        # 4b. Obsidian (tous modes — toujours visible)
        if not obsidian_configured:
            ui.button(
                icon="edit_note",
                on_click=lambda: ui.navigate.to("/settings"),
            ).props("flat size=sm round color=grey").classes(
                "text-slate-300 shrink-0 opacity-50"
            ).tooltip("Configurer Obsidian dans les Paramètres")
        elif obsidian_note_exists:
            ui.button(
                icon="edit_note",
                on_click=lambda c=course: _open_obsidian_note_action(c),
            ).props("flat size=sm round color=violet").classes(
                "bg-violet-50 dark:bg-violet-900/20 shrink-0"
            ).tooltip("Ouvrir note Obsidian")
        else:
            # Pas de note liée → mini-menu Créer / Lier
            with ui.button(icon="note_add").props(
                "flat size=sm round color=violet"
            ).classes("text-violet-400 shrink-0 opacity-70").tooltip(
                "Note Obsidian — Créer ou lier"
            ):
                with ui.menu():
                    ui.menu_item(
                        "📝 Créer une nouvelle note",
                        on_click=lambda c=course: asyncio.create_task(
                            _create_obsidian_note_action(c, refresh_fn, client)
                        ),
                    ).classes("text-sm text-violet-700 font-semibold")
                    ui.menu_item(
                        "🔗 Lier une note existante…",
                        on_click=lambda c=course: _open_link_note_dialog(c, refresh_fn),
                    ).classes("text-sm text-violet-500")

        # 5. Menu ⋯ (micro et compact)
        if mode in ("micro", "compact"):
            ui.element("div").classes("flex-1")  # pousse le menu à droite
            with ui.button(icon="more_horiz").props(
                "flat size=sm round color=slate-400"
            ).tooltip("Plus d'actions"):
                with ui.menu().classes("w-60"):
                    # Résumé
                    _r_lbl = f"✓ Résumé fait" if resume_done else "Faire Résumé"
                    ui.menu_item(_r_lbl, on_click=_run("resume")).classes(
                        MENU_ITEM + (" text-positive" if resume_done else "")
                    )
                    # Anki
                    _a_lbl = f"✓ Anki fait" if anki_done else "Faire Anki"
                    ui.menu_item(_a_lbl, on_click=_run("anki")).classes(
                        MENU_ITEM + (" text-positive" if anki_done else "")
                    )
                    # ChatGPT
                    _cg_lbl = f"✓ ChatGPT fait" if chatgpt_done else "Faire ChatGPT"
                    ui.menu_item(_cg_lbl, on_click=_run("chatgpt")).classes(MENU_ITEM)
                    # QCM
                    if qcm_done:
                        ui.menu_item("✓ QCM fait", on_click=_run("qcm")).classes(
                            MENU_ITEM + " text-positive"
                        )
                    else:
                        ui.menu_item(
                            "📝 Logger un résultat QCM",
                            on_click=lambda c=course: _open_quick_qcm_dialog(c, refresh_fn),
                        ).classes(MENU_ITEM + " text-violet-700 font-semibold")
                        ui.menu_item(
                            "✓ Marquer QCM fait (sans score)",
                            on_click=_run("qcm"),
                        ).classes(MENU_ITEM + " text-slate-400")
                    ui.separator()
                    ui.menu_item(
                        "Nouvelle séance…",
                        on_click=lambda c=course: open_quick_session_dialog(c, refresh_fn, client),
                    ).classes(MENU_ITEM + " text-indigo-600 font-semibold")
                    ui.separator()
                    # PDF absent → proposer de lier directement
                    if not has_pdf:
                        ui.menu_item(
                            "🔴 Lier un PDF…",
                            on_click=lambda c=course: open_link_pdf_unified(c, context, refresh_fn, client),
                        ).classes(MENU_ITEM + " text-red-500 font-semibold")
                    # Suivi du cours
                    if not has_first_read:
                        _track_label = (
                            "🟠 Démarrer le suivi du cours…"
                            if has_pdf
                            else "🔒 Démarrer le suivi (PDF requis)"
                        )
                        _track_cls = (
                            MENU_ITEM + " text-indigo-600 font-semibold"
                            if has_pdf
                            else MENU_ITEM + " text-slate-400"
                        )
                        ui.menu_item(
                            _track_label,
                            on_click=(
                                (lambda c=course: open_start_tracking_dialog(
                                    c, context, refresh_fn, client, is_restart=False
                                ))
                                if has_pdf else None
                            ),
                        ).classes(_track_cls)
                    else:
                        ui.menu_item(
                            "↺ Redémarrer le suivi…",
                            on_click=lambda c=course: open_start_tracking_dialog(
                                c, context, refresh_fn, client, is_restart=True
                            ),
                        ).classes(MENU_ITEM + " text-indigo-700")

                    # Obsidian
                    ui.separator()
                    if not obsidian_configured:
                        ui.menu_item(
                            "⚙️ Configurer Obsidian…",
                            on_click=lambda: ui.navigate.to("/settings"),
                        ).classes(MENU_ITEM + " text-slate-400")
                    elif obsidian_note_exists:
                        ui.menu_item(
                            "📝 Ouvrir note Obsidian",
                            on_click=lambda c=course: _open_obsidian_note_action(c),
                        ).classes(MENU_ITEM + " text-violet-600 font-semibold")
                    else:
                        ui.menu_item(
                            "📝 Créer note Obsidian",
                            on_click=lambda c=course: asyncio.create_task(
                                _create_obsidian_note_action(c, refresh_fn, client)
                            ),
                        ).classes(MENU_ITEM + " text-violet-500")
                        ui.menu_item(
                            "🔗 Lier une note existante…",
                            on_click=lambda c=course: _open_link_note_dialog(c, refresh_fn),
                        ).classes(MENU_ITEM + " text-violet-400")

