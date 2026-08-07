"""
_dialogs.py — Dialogs du dashboard :
  - SR Help dialog (explication spaced repetition)
  - Session feedback dialog (retour de séance)
  - Bilan de fin de session
  - Lacune inline dialog
"""
from __future__ import annotations

import datetime
import asyncio
from types import SimpleNamespace

from nicegui import ui

from backend.core.reviews.models import ReviewTask
from backend.core.reviews import local_store
from backend.core.reviews.recommendation_service import compute_daily_load
from backend.core.reviews.service import review_service
from backend.core.knowledge import store as knowledge_store
from backend.core.knowledge import service as knowledge_service
from backend.state.store import data_store
from frontend.components.session_feedback_ui import (
    confidence_label,
    default_feedback_state,
    qcm_activity_ids,
)

from ._state import DashboardState


# ── SR Help ───────────────────────────────────────────────────────────────────

def open_sr_help_dialog() -> None:
    """Modale explicative sur la répétition espacée."""
    with ui.dialog() as sr_dlg, ui.card().classes(
        "w-[440px] max-w-[94vw] rounded-2xl p-0 overflow-hidden "
        "bg-white dark:bg-slate-900"
    ):
        with ui.element("div").classes("px-5 pt-4 pb-3 border-b border-slate-100 dark:border-slate-800"):
            with ui.row().classes("items-center justify-between"):
                ui.label("Pourquoi ces révisions ?").classes(
                    "text-base font-bold text-slate-900 dark:text-slate-50"
                )
                ui.button(icon="close", on_click=sr_dlg.close).props(
                    "flat round dense size=sm color=grey-7"
                )
        with ui.element("div").classes("px-5 py-4 flex flex-col gap-4"):
            ui.label(
                "Synapse utilise la répétition espacée (spaced repetition), "
                "une méthode scientifiquement prouvée pour ancrer les connaissances "
                "en mémoire à long terme avec un minimum de temps."
            ).classes("text-sm text-slate-600 dark:text-slate-300")
            _SR_STEPS = [
                ("J3",  "blue",   "3 jours après la 1ʳᵉ lecture",  "Ancrage initial — le cours est encore frais mais doit être consolidé."),
                ("J7",  "indigo", "7 jours après la 1ʳᵉ lecture",  "Consolidation — tes neurones renforcent les connexions récentes."),
                ("J14", "violet", "14 jours après la 1ʳᵉ lecture", "Renforcement — résiste à la courbe de l'oubli de Ebbinghaus."),
                ("J30", "purple", "30 jours après la 1ʳᵉ lecture", "Ancrage à long terme — objectif mémorisation EDN durable."),
            ]
            for badge, col, when, why in _SR_STEPS:
                with ui.row().classes("items-start gap-3"):
                    ui.badge(badge, color=col).classes("text-[11px] font-bold px-2 py-1 shrink-0 mt-0.5")
                    with ui.column().classes("gap-0.5"):
                        ui.label(when).classes("text-sm font-semibold text-slate-800 dark:text-slate-100")
                        ui.label(why).classes("text-xs text-slate-400")
            ui.element("div").classes("border-t border-slate-100 dark:border-slate-800 pt-3 mt-1")
            ui.label("🔁 bonus — cours fragile détecté (QCM raté, lacune critique ou maîtrise < 40%)").classes("text-xs text-slate-500 italic")
        with ui.element("div").classes("px-5 pb-4 flex justify-end"):
            ui.button("Compris ✓", on_click=sr_dlg.close).props("unelevated rounded color=violet")
    sr_dlg.open()


# ── Bilan de fin de session ───────────────────────────────────────────────────

def show_bilan_session(state: DashboardState, done_today: int) -> None:
    """Modale bilan (PP-07) — affichée une seule fois par session."""
    try:
        ui.run_javascript("synapseConfetti()")
    except Exception:
        pass

    try:
        history = local_store.get_all_history()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        today_sessions = [
            h for h in history
            if getattr(h, "done_date", None) and str(getattr(h, "done_date", "")).startswith(today_str)
        ]
        n_done = len(today_sessions)
        try:
            n_lacunes = local_store.get_open_lacunes_count()
        except Exception:
            n_lacunes = 0
        try:
            _wk_ago = (datetime.date.today() - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            week_sessions = [
                h for h in history
                if getattr(h, "done_date", None) and str(getattr(h, "done_date", "")) >= _wk_ago
            ]
            n_week = len(week_sessions)
        except Exception:
            n_week = done_today
    except Exception:
        n_done = done_today
        n_lacunes = 0
        n_week = done_today

    with ui.dialog() as bilan_dlg, ui.card().classes(
        "w-[420px] max-w-[94vw] rounded-2xl p-0 overflow-hidden "
        "bg-white dark:bg-slate-900"
    ):
        with ui.element("div").classes(
            "px-6 pt-6 pb-4 text-center flex flex-col items-center gap-3"
        ):
            ui.label("🎉").classes("text-5xl")
            ui.label("Révisions du jour terminées !").classes(
                "text-xl font-extrabold text-slate-900 dark:text-slate-50"
            )
            ui.label("Plus aucun retard. Excellent travail.").classes("text-sm text-slate-400")

        with ui.element("div").classes(
            "mx-6 mb-4 rounded-xl bg-slate-50 dark:bg-slate-800 p-4 grid grid-cols-3 gap-4"
        ):
            for icon_n, val, lbl in [
                ("check_circle",   str(n_done),    "Aujourd'hui"),
                ("date_range",     str(n_week),    "Cette semaine"),
                ("report_problem", str(n_lacunes), "Lacunes ouvertes"),
            ]:
                with ui.column().classes("items-center gap-1"):
                    ui.icon(icon_n, size="sm").classes("text-violet-400")
                    ui.label(val).classes(
                        "text-2xl font-extrabold tabular-nums text-slate-800 dark:text-slate-100"
                    )
                    ui.label(lbl).classes("text-[11px] text-slate-400 text-center")

        with ui.element("div").classes("px-6 pb-6 flex flex-col gap-2"):
            ui.button(
                "Voir ma progression",
                on_click=lambda: (bilan_dlg.close(), ui.navigate.to("/stats")),
            ).props("unelevated rounded color=violet").classes("w-full font-semibold")
            ui.button("Fermer", on_click=bilan_dlg.close).props(
                "flat rounded color=grey-7"
            ).classes("w-full")

    bilan_dlg.open()


# ── Lacune inline ─────────────────────────────────────────────────────────────

def open_lacune_inline_dialog(task: ReviewTask, on_save=None) -> None:
    """Mini-modale pour créer une lacune liée au cours."""
    with ui.dialog() as dlg:
        with ui.card().classes(
            "w-[420px] max-w-[95vw] p-0 rounded-2xl overflow-hidden shadow-xl"
        ):
            with ui.element("div").classes(
                "px-5 py-4 border-b border-slate-100 dark:border-slate-800"
            ):
                with ui.row().classes("items-center justify-between"):
                    ui.label("Ajouter une lacune").classes(
                        "font-bold text-slate-800 dark:text-slate-100"
                    )
                    ui.button(icon="close", on_click=dlg.close).props(
                        "flat round dense size=sm color=grey"
                    )
            with ui.element("div").classes("px-5 py-4 flex flex-col gap-3"):
                ui.label(task.label).classes("text-xs text-slate-400 truncate").tooltip(task.label)
                inp_detail = ui.input(
                    label="Ce qui n'est pas clair",
                    placeholder="Ex: mécanisme de la douleur viscérale...",
                ).props("outlined dense").classes("w-full")
                inp_cat = ui.select(
                    label="Catégorie",
                    options=["anatomie", "physiopathologie", "traitement", "diagnostic", "autre"],
                    value="autre",
                ).props("outlined dense").classes("w-full")
            with ui.element("div").classes(
                "px-5 py-3 bg-slate-50 dark:bg-slate-800/50 "
                "border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2"
            ):
                ui.button("Annuler", on_click=dlg.close).props("flat color=grey-8")

                def _save_lacune(_dlg=dlg, _task=task, _on_save=on_save):
                    detail = inp_detail.value.strip()
                    if not detail:
                        ui.notify("Décris la lacune avant de sauvegarder", type="warning")
                        return
                    local_store.add_weak_point(
                        course_id=_task.course_id,
                        course_title=_task.course_title,
                        item_number=_task.item_number or "",
                        category=inp_cat.value,
                        detail=detail,
                        severity=2,
                        source_session_id=None,
                    )
                    _dlg.close()
                    ui.notify("Lacune notée ✓", type="positive")
                    if _on_save:
                        _on_save()

                ui.button("Ajouter", on_click=_save_lacune).props(
                    "unelevated color=amber rounded"
                ).classes("font-semibold")
    dlg.open()


# ── Session feedback dialog ───────────────────────────────────────────────────

def open_session_feedback_dialog(
    task: ReviewTask,
    card,
    validate_fn,
    initial_duration_minutes: int | None = None,
    manual_date: datetime.date | None = None,
) -> None:
    """Open the compact, item-aware Linear-style session feedback panel."""
    state_fb = SimpleNamespace(**default_feedback_state(
        task, initial_duration_minutes, manual_date
    ))

    # ── Socle « état des connaissances » ──────────────────────────────────────
    # Si l'item vient d'un collège validé et n'a pas encore de niveau déclaré,
    # la séance est l'occasion de le situer — un clic, dans un écran déjà ouvert.
    _to_situate = knowledge_service.is_to_situate(
        task.course_id, task.college or [], task.context
    )
    state_fb.declared_level = None
    _declared_buttons: dict = {}

    ACTIVITIES  = [("révision","Révision"),("lecture","Lecture"),("qcm","QCM"),
                   ("dp_kfp","DP/KFP"),("anki","Anki"),("fiche","Fiche"),("correction","Correction")]
    DUR_PRESETS = [5, 10, 20, 30, 45, 60, 90]
    DIFF_OPTS   = [("facile","Facile","positive"),("moyen","Moyen","warning"),("difficile","Difficile","negative")]
    QCM_OPTS    = [(None,"—","grey"),("réussi","Réussi","positive"),("moyen","Moyen","warning"),("raté","Raté","negative")]
    item_label = str(task.label or "")
    if not item_label.upper().startswith("ITEM "):
        item_label = f"ITEM {task.item_number or '—'} · {item_label}"

    def _chip_on(col): return f"unelevated dense size=sm color={col}"
    def _chip_off():   return "outline dense size=sm color=grey-7"

    with ui.dialog() as dialog:
        with ui.card().classes(
            "w-[520px] max-w-[calc(100vw-24px)] max-h-[calc(100vh-24px)] "
            "flex flex-col rounded-lg p-0 overflow-hidden"
        ).style(
            "background:var(--bg); border:1px solid var(--border); box-shadow:var(--shadow-popover);"
        ):

            with ui.element("div").classes("px-6 pt-5 pb-4").style(
                "border-bottom:1px solid var(--border);"
            ):
                with ui.row().classes("items-start justify-between w-full gap-3"):
                    with ui.column().classes("gap-0.5 min-w-0 flex-1"):
                        ui.label("RETOUR DE SÉANCE").classes(
                            "text-[11px] font-bold tracking-[0.16em]"
                        ).style("color:var(--text-muted);")
                        ui.label(
                            item_label
                        ).classes("text-sm font-semibold").style(
                            "color:var(--text); overflow:hidden;white-space:nowrap;text-overflow:ellipsis"
                        )
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense size=sm color=grey-7"
                    )

            with ui.element("div").classes(
                "flex-1 min-h-0 overflow-y-auto px-5 py-4 flex flex-col gap-4"
            ):

                ui.label("Comment s'est passée cette séance ?").classes(
                    "text-base font-semibold"
                ).style("color:var(--text);")
                ui.label(
                    "La validation mettra à jour la maîtrise de l'item et sa prochaine révision."
                ).classes("text-xs").style("color:var(--text-muted);")

                if manual_date is not None:
                    ui.label("DATE DE SÉANCE").classes(
                        "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                    )
                    with ui.input(
                        value=state_fb.session_date.strftime("%d/%m/%Y"),
                        placeholder="JJ/MM/AAAA",
                    ).props("outlined dense mask='##/##/####'").classes("w-full") as date_field:
                        def _set_session_date(event):
                            try:
                                state_fb.session_date = datetime.datetime.strptime(
                                    event.value, "%d/%m/%Y"
                                ).date()
                            except (TypeError, ValueError):
                                pass
                        date_field.on_value_change(_set_session_date)

                def _section(label: str):
                    ui.label(label).classes(
                        "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                    )

                _section("Activité")
                act_btns: dict = {}
                with ui.row().classes("flex-wrap gap-2"):
                    for a_id, a_lbl in ACTIVITIES:
                        is_on = a_id in state_fb.activity_types
                        b = ui.button(a_lbl).props(_chip_on("indigo") if is_on else _chip_off())
                        act_btns[a_id] = b

                def _toggle_act(a: str):
                    if a in state_fb.activity_types:
                        state_fb.activity_types.remove(a)
                        act_btns[a].props(_chip_off(), remove=_chip_on("indigo"))
                    else:
                        state_fb.activity_types.append(a)
                        act_btns[a].props(_chip_on("indigo"), remove=_chip_off())
                    if qcm_section is not None:
                        qcm_section.set_visibility(
                            bool(set(state_fb.activity_types) & qcm_activity_ids())
                        )

                for a_id, _ in ACTIVITIES:
                    act_btns[a_id].on_click(lambda a=a_id: _toggle_act(a))

                _section("Durée")
                dur_btns: dict = {}
                with ui.row().classes("flex-wrap items-center gap-2"):
                    for d in DUR_PRESETS:
                        is_on = d == state_fb.duration
                        b = ui.button(f"{d}′").props(_chip_on("indigo") if is_on else _chip_off())
                        dur_btns[d] = b
                    with ui.element("div").classes("flex items-center gap-1 ml-1"):
                        custom_dur = ui.number(
                            min=1, max=300, placeholder="···",
                            value=(state_fb.duration if state_fb.duration not in DUR_PRESETS else None),
                        ).classes("w-12").props("dense borderless")
                        ui.label("min").classes("text-xs text-slate-400 pb-0.5")

                def _set_dur(val: int):
                    state_fb.duration = val
                    for dv, db in dur_btns.items():
                        if dv == val:
                            db.props(_chip_on("indigo"), remove=_chip_off())
                        else:
                            db.props(_chip_off(), remove=_chip_on("indigo"))

                for d in DUR_PRESETS:
                    dur_btns[d].on_click(lambda val=d: _set_dur(val))

                def _on_custom(e):
                    if e.value:
                        state_fb.duration = int(e.value)
                        for db in dur_btns.values():
                            db.props(_chip_off(), remove=_chip_on("indigo"))
                custom_dur.on_value_change(_on_custom)

                with ui.row().classes("w-full gap-8"):
                    with ui.column().classes("gap-2"):
                        _section("Confiance")
                        _CONF_CONFIG = [
                            (1, "Très incertain", "red"),
                            (2, "Incertain", "orange"),
                            (3, "Correct", "blue"),
                            (4, "Solide", "teal"),
                            (5, "Très solide", "green"),
                        ]
                        conf_btns: dict = {}
                        with ui.row().classes("gap-1.5 flex-wrap"):
                            for _v, _label, _col in _CONF_CONFIG:
                                _is_on = _v == state_fb.confidence
                                _b = ui.button(_label).props(
                                    _chip_on(_col) if _is_on else _chip_off()
                                ).tooltip(f"Confiance {_v}/5 · {confidence_label(_v)}")
                                conf_btns[_v] = _b

                        def _set_conf(val: int):
                            state_fb.confidence = val
                            for v, _, col in _CONF_CONFIG:
                                if v == val:
                                    conf_btns[v].props(_chip_on(col), remove=_chip_off())
                                else:
                                    conf_btns[v].props(_chip_off(), remove=_chip_on(col))

                        for _v, _, _ in _CONF_CONFIG:
                            conf_btns[_v].on_click(lambda val=_v: _set_conf(val))

                    with ui.column().classes("gap-2"):
                        _section("Difficulté")
                        diff_btns: dict = {}
                        with ui.row().classes("gap-1.5"):
                            for d_id, d_lbl, d_col in DIFF_OPTS:
                                is_on = d_id == state_fb.difficulty
                                b = ui.button(d_lbl).props(_chip_on(d_col) if is_on else _chip_off())
                                diff_btns[d_id] = b

                        def _set_diff(val: str):
                            state_fb.difficulty = val
                            for d_id, _, d_col in DIFF_OPTS:
                                if d_id == val:
                                    diff_btns[d_id].props(_chip_on(d_col), remove=_chip_off())
                                else:
                                    diff_btns[d_id].props(_chip_off(), remove=_chip_on(d_col))

                        for d_id, _, _ in DIFF_OPTS:
                            diff_btns[d_id].on_click(lambda val=d_id: _set_diff(val))

                # UX-08 — Sections avancées repliées
                qcm_section = None
                with ui.expansion("Détails avancés", value=False).classes(
                    "w-full rounded-xl"
                ).props("dense"):
                    with ui.column().classes("gap-4 w-full pt-2"):
                        with ui.element("div") as qcm_section:
                            with ui.column().classes("gap-2"):
                                _section("Résultat QCM / DP")
                                ui.label("Visible pour les activités QCM et DP/KFP.").classes(
                                    "text-xs text-slate-500"
                                )
                            qcm_btns: dict = {}
                            with ui.row().classes("gap-1.5 flex-wrap"):
                                for q_id, q_lbl, q_col in QCM_OPTS:
                                    is_on = q_id == state_fb.qcm_result
                                    b = ui.button(q_lbl).props(_chip_on(q_col) if is_on else _chip_off())
                                    qcm_btns[str(q_id)] = b

                            def _set_qcm(val):
                                state_fb.qcm_result = val
                                for q_id, _, q_col in QCM_OPTS:
                                    key = str(q_id)
                                    if q_id == val:
                                        qcm_btns[key].props(_chip_on(q_col), remove=_chip_off())
                                    else:
                                        qcm_btns[key].props(_chip_off(), remove=_chip_on(q_col))

                            for q_id, _, _ in QCM_OPTS:
                                qcm_btns[str(q_id)].on_click(lambda val=q_id: _set_qcm(val))

                        qcm_section.set_visibility(
                            bool(set(state_fb.activity_types) & qcm_activity_ids())
                        )

                        with ui.column().classes("gap-2"):
                            _section("Erreur / piège EDN")
                            _ERR_CATS = [
                                (None,                     "—",           "grey"),
                                ("diagnostic",             "Diagnostic",  "red"),
                                ("clinique",               "Clinique",    "orange"),
                                ("examens complémentaires","Examens",     "deep-orange"),
                                ("traitement",             "Traitement",  "blue"),
                                ("complications",          "Complic.",    "purple"),
                                ("physiopathologie",       "Physiopath.", "indigo"),
                                ("piège EDN",              "Piège EDN",   "pink"),
                                ("valeur chiffrée",        "Valeur chif.","teal"),
                                ("autre",                  "Autre",       "blue-grey"),
                            ]
                            cat_btns: dict = {}
                            with ui.row().classes("flex-wrap gap-1.5"):
                                for _cat_id, _cat_lbl, _cat_col in _ERR_CATS:
                                    _is_on = _cat_id == state_fb.weak_category
                                    _b = ui.button(_cat_lbl).props(
                                        _chip_on(_cat_col) if _is_on else _chip_off()
                                    )
                                    cat_btns[str(_cat_id)] = _b

                            def _set_cat(val):
                                state_fb.weak_category = val
                                for c_id, _, c_col in _ERR_CATS:
                                    key = str(c_id)
                                    if c_id == val:
                                        cat_btns[key].props(_chip_on(c_col), remove=_chip_off())
                                    else:
                                        cat_btns[key].props(_chip_off(), remove=_chip_on(c_col))

                            for _cat_id, _, _ in _ERR_CATS:
                                cat_btns[str(_cat_id)].on_click(lambda val=_cat_id: _set_cat(val))

                            ui.textarea(
                                placeholder="Ex : oubli hémocultures avant ATB, confusion IRM avant PL…"
                            ).classes("w-full").props("outlined dense autogrow").on_value_change(
                                lambda e: setattr(state_fb, "weak_detail", e.value or "")
                            )

                if _to_situate:
                    with ui.element("div").classes("px-6 py-3"):
                        ui.label("Où en es-tu sur cet item ?").classes(
                            "text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2"
                        )
                        with ui.row().classes("gap-1"):
                            for _lvl, _lbl, _col in [
                                ("solide", "Solide", "positive"),
                                ("correct", "Correct", "warning"),
                                ("flou", "Flou", "negative"),
                            ]:
                                def _pick(_l=_lvl):
                                    state_fb.declared_level = _l
                                    _render_declared()

                                _b = ui.button(_lbl, on_click=_pick)
                                _b.props(_chip_off())
                                _declared_buttons[_lvl] = _b

                        def _render_declared():
                            for _l, _btn in _declared_buttons.items():
                                _col = {"solide": "positive", "correct": "warning",
                                        "flou": "negative"}[_l]
                                _btn.props(
                                    _chip_on(_col) if state_fb.declared_level == _l
                                    else _chip_off()
                                )

            with ui.element("div").classes(
                "shrink-0 sticky bottom-0 px-5 py-3 flex justify-end gap-2"
            ).style("background:var(--bg-alt); border-top:1px solid var(--border);"):
                ui.button("Annuler", on_click=dialog.close).props("flat color=grey-8")

                async def _submit():
                    dialog.close()
                    if state_fb.declared_level:
                        knowledge_store.set_item_state(
                            task.course_id, state_fb.declared_level,
                            context=task.context, source="reprise",
                        )
                        review_service.invalidate_cache()
                    await validate_fn(
                        task, card,
                        activity_types=state_fb.activity_types or ["révision"],
                        duration_minutes=state_fb.duration,
                        confidence=state_fb.confidence,
                        difficulty=state_fb.difficulty,
                        qcm_result=state_fb.qcm_result,
                        weak_category=state_fb.weak_category,
                        weak_detail=state_fb.weak_detail or None,
                        **({"session_date": state_fb.session_date} if manual_date is not None else {}),
                    )

                ui.button("Valider la séance", on_click=_submit).props(
                    "unelevated color=primary"
                ).classes("px-4 font-semibold")

    dialog.open()
