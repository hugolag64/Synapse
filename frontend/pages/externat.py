"""
Externat — Synapse Phase G
---------------------------
Page de gestion du stage actuel et de l'historique des stages.

Layout :
  • Stage en cours : spécialité, dates, objectifs, gardes, boost actif
  • Boutons : Nouveau stage | Modifier | Terminer
  • Cours liés au collège du stage (filtrage rapide)
  • Lacunes liées (actives, du collège du stage)
  • Historique des stages précédents
"""
from __future__ import annotations

import datetime
from nicegui import ui

from frontend.theme import frame
from backend.core.externat import store as externat_store
from backend.core.externat.models import Stage
from backend.core.externat.service import externat_service
from backend.state.store import data_store
from backend.core.reviews.local_store import get_all_weak_points_table


# ── Helpers ────────────────────────────────────────────────────────────────────

months_fr = [
    "jan", "fév", "mar", "avr", "mai", "juin",
    "juil", "août", "sep", "oct", "nov", "déc",
]


def _fmt_date(d: datetime.date) -> str:
    return f"{d.day} {months_fr[d.month - 1]} {d.year}"


def _available_colleges() -> list[str]:
    """Retourne la liste dédupliquée des collèges Notion disponibles."""
    colleges = set()
    for c in data_store.cours:
        for col in (c.college or []):
            colleges.add(col)
    return sorted(colleges)


# ── Dialog création / modification stage ──────────────────────────────────────

def _open_stage_dialog(
    on_saved,
    existing: Stage | None = None,
):
    """Dialog de création ou modification d'un stage."""
    is_edit = existing is not None
    today = datetime.date.today()

    colleges = _available_colleges()
    college_options = [""] + colleges

    # Valeurs initiales
    init_specialty  = existing.specialty       if is_edit else ""
    init_college    = existing.college_notion  if is_edit else ""
    init_start      = existing.start_date.isoformat() if is_edit else today.isoformat()
    init_end        = existing.end_date.isoformat()   if is_edit else (today + datetime.timedelta(weeks=6)).isoformat()
    init_objectives = existing.objectives  if is_edit else ""
    init_schedules  = existing.schedules   if is_edit else "8h–18h, lundi–vendredi"
    init_gardes     = existing.gardes      if is_edit else ""
    init_contraintes= existing.contraintes if is_edit else ""

    with ui.dialog().props("persistent") as dlg:
        with ui.card().classes("w-full max-w-2xl p-0 rounded-2xl overflow-hidden"):

            # ── Header ────────────────────────────────────────────────────────
            with ui.row().classes(
                "items-center gap-3 px-5 py-4 "
                "bg-green-50 dark:bg-green-900/20 "
                "border-b border-green-100 dark:border-green-800"
            ):
                ui.icon("local_hospital", color="green").classes("text-2xl shrink-0")
                ui.label(
                    "Modifier le stage" if is_edit else "Nouveau stage"
                ).classes("font-bold text-green-800 dark:text-green-200 text-lg")

            with ui.scroll_area().classes("w-full").style("max-height: 60vh;"):
                with ui.column().classes("px-5 py-4 gap-4 w-full"):

                    # Spécialité
                    inp_specialty = ui.input(
                        label="Spécialité *",
                        value=init_specialty,
                        placeholder="ex : Cardiologie, Neurologie…",
                    ).props("outlined").classes("w-full")

                    # Collège Notion lié
                    with ui.column().classes("w-full gap-0.5"):
                        select_college = ui.select(
                            label="Collège Notion lié (pour le boost priorité)",
                            options=college_options,
                            value=init_college,
                        ).props("outlined use-input clearable").classes("w-full")
                        ui.label(
                            "Le collège sélectionné bénéficie d'un bonus discret dans le planning."
                        ).classes("text-[11px] text-slate-400 italic mt-0.5")

                    # Dates
                    with ui.row().classes("w-full gap-4"):
                        inp_start = ui.input(
                            label="Date de début *",
                            value=init_start,
                            placeholder="YYYY-MM-DD",
                        ).props("outlined type=date").classes("flex-1")

                        inp_end = ui.input(
                            label="Date de fin *",
                            value=init_end,
                            placeholder="YYYY-MM-DD",
                        ).props("outlined type=date").classes("flex-1")

                    # Horaires
                    inp_schedules = ui.input(
                        label="Horaires habituels",
                        value=init_schedules,
                        placeholder="ex : 8h–18h, Lu–Ve",
                    ).props("outlined").classes("w-full")

                    # Objectifs
                    inp_objectives = ui.textarea(
                        label="Objectifs du stage",
                        value=init_objectives,
                        placeholder="Objectifs cliniques, compétences à acquérir…",
                    ).props("outlined rows=3").classes("w-full")

                    # Gardes
                    inp_gardes = ui.textarea(
                        label="Gardes / astreintes",
                        value=init_gardes,
                        placeholder="ex : Garde 1 lundi 26 mai — nuit complète\nAstreinte 2 juin",
                    ).props("outlined rows=2").classes("w-full")

                    # Contraintes
                    inp_contraintes = ui.textarea(
                        label="Contraintes & repos",
                        value=init_contraintes,
                        placeholder="ex : Repos compensateur jeudi, départ 17h vendredi",
                    ).props("outlined rows=2").classes("w-full")

            # ── Footer ────────────────────────────────────────────────────────
            with ui.row().classes(
                "items-center justify-end gap-3 px-5 py-3 "
                "border-t border-slate-100 dark:border-slate-700"
            ):
                ui.button("Annuler", on_click=dlg.close).props("flat color=slate size=sm")

                def _save():
                    specialty = (inp_specialty.value or "").strip()
                    if not specialty:
                        ui.notify("La spécialité est obligatoire.", type="warning")
                        return

                    try:
                        start = datetime.date.fromisoformat(inp_start.value)
                        end   = datetime.date.fromisoformat(inp_end.value)
                    except ValueError:
                        ui.notify("Date invalide (format YYYY-MM-DD).", type="negative")
                        return

                    if end < start:
                        ui.notify("La date de fin doit être après la date de début.", type="warning")
                        return

                    college = select_college.value or ""
                    kwargs = dict(
                        specialty=specialty,
                        college_notion=college,
                        start_date=start,
                        end_date=end,
                        objectives=(inp_objectives.value or "").strip(),
                        schedules=(inp_schedules.value or "").strip(),
                        gardes=(inp_gardes.value or "").strip(),
                        contraintes=(inp_contraintes.value or "").strip(),
                        is_active=True,
                    )

                    if is_edit and existing:
                        externat_store.update_stage(existing.id, **kwargs)
                        ui.notify(f"Stage « {specialty} » modifié ✓", type="positive")
                    else:
                        externat_store.add_stage(**kwargs)
                        ui.notify(f"Stage « {specialty} » créé ✓", type="positive", icon="local_hospital")

                    dlg.close()
                    on_saved()

                ui.button(
                    "Enregistrer",
                    icon="save",
                    on_click=_save,
                ).props("unelevated color=green size=sm")

    dlg.open()


# ── Carte stage actif ─────────────────────────────────────────────────────────

def _render_active_stage(stage: Stage, on_refresh):
    """Affiche la carte du stage en cours avec ses infos et actions."""
    today = datetime.date.today()
    progress = 0.0
    if stage.duration_weeks > 0:
        total_days = (stage.end_date - stage.start_date).days
        elapsed    = (today - stage.start_date).days
        progress   = min(1.0, max(0.0, elapsed / total_days)) if total_days > 0 else 0.0

    with ui.card().classes(
        "w-full p-0 rounded-2xl border-l-4 border-l-green-500 "
        "border-y border-r border-slate-100 dark:border-slate-800 shadow-md overflow-hidden"
    ):
        # Header vert
        with ui.row().classes(
            "items-center gap-4 px-5 py-4 "
            "bg-gradient-to-r from-green-50 to-teal-50 "
            "dark:from-green-900/20 dark:to-teal-900/20"
        ):
            ui.icon("local_hospital", size="lg").classes("text-green-600 shrink-0")
            with ui.column().classes("flex-1 gap-0"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(stage.specialty).classes(
                        "text-xl font-extrabold text-green-900 dark:text-green-100"
                    )
                    ui.badge("En cours", color="green").classes("text-[11px] font-bold")
                ui.label(
                    f"{_fmt_date(stage.start_date)} → {_fmt_date(stage.end_date)} "
                    f"· {stage.duration_weeks} semaines"
                ).classes("text-sm text-green-700 dark:text-green-300")

            with ui.column().classes("items-end gap-1 shrink-0"):
                ui.label(f"J-{stage.days_remaining}").classes(
                    "text-2xl font-bold text-green-700 dark:text-green-300 tabular-nums"
                )
                ui.label("jours restants").classes("text-[11px] text-green-500 uppercase tracking-wide")

        # Barre de progression
        ui.linear_progress(value=progress, show_value=False).props(
            "color=green track-color=green-100"
        ).classes("w-full h-1.5")

        # Corps
        with ui.column().classes("px-5 py-4 gap-4"):

            # Infos en grille
            with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-2 md:grid-cols-3"):
                if stage.college_notion:
                    with ui.row().classes("items-center gap-2 col-span-1"):
                        ui.icon("business", size="xs").classes("text-green-500 shrink-0")
                        with ui.column().classes("gap-0"):
                            ui.label("Collège lié").classes("text-[11px] text-slate-400 uppercase")
                            ui.label(stage.college_notion).classes(
                                "text-xs font-semibold text-slate-700 dark:text-slate-200"
                            )
                    with ui.row().classes("items-center gap-2 col-span-1"):
                        ui.icon("trending_up", size="xs").classes("text-teal-500 shrink-0")
                        with ui.column().classes("gap-0"):
                            ui.label("Priorité boostée").classes("text-[11px] text-slate-400 uppercase")
                            ui.label("Cours du collège remontent dans le dashboard").classes(
                                "text-xs font-semibold text-teal-600 dark:text-teal-400"
                            ).tooltip("Le moteur de recommandation ajoute +5 pts aux tâches du collège de stage")

                if stage.schedules:
                    with ui.row().classes("items-center gap-2 col-span-1"):
                        ui.icon("schedule", size="xs").classes("text-slate-400 shrink-0")
                        with ui.column().classes("gap-0"):
                            ui.label("Horaires").classes("text-[11px] text-slate-400 uppercase")
                            ui.label(stage.schedules).classes(
                                "text-xs text-slate-600 dark:text-slate-300"
                            )

            # Objectifs
            if stage.objectives:
                with ui.expansion("Objectifs", icon="flag").classes(
                    "w-full rounded-xl border border-slate-200 dark:border-slate-700"
                ):
                    ui.label(stage.objectives).classes(
                        "text-sm text-slate-600 dark:text-slate-300 px-3 pb-3 whitespace-pre-wrap"
                    )

            # Gardes
            if stage.gardes:
                with ui.expansion("Gardes & astreintes", icon="nights_stay").classes(
                    "w-full rounded-xl border border-slate-200 dark:border-slate-700"
                ):
                    ui.label(stage.gardes).classes(
                        "text-sm text-slate-600 dark:text-slate-300 px-3 pb-3 whitespace-pre-wrap"
                    )

            # Contraintes
            if stage.contraintes:
                with ui.expansion("Contraintes & repos", icon="event_busy").classes(
                    "w-full rounded-xl border border-slate-200 dark:border-slate-700"
                ):
                    ui.label(stage.contraintes).classes(
                        "text-sm text-slate-600 dark:text-slate-300 px-3 pb-3 whitespace-pre-wrap"
                    )

        # Actions
        with ui.row().classes(
            "items-center gap-3 px-5 py-3 "
            "border-t border-slate-100 dark:border-slate-700 flex-wrap"
        ):
            ui.button(
                "Modifier",
                icon="edit",
                on_click=lambda: _open_stage_dialog(on_refresh, existing=stage),
            ).props("outline color=green size=sm rounded")

            def _deactivate():
                externat_store.update_stage(stage.id, is_active=False)
                ui.notify("Stage marqué comme terminé.", type="info", icon="check")
                on_refresh()

            ui.button(
                "Marquer terminé",
                icon="check_circle",
                on_click=_deactivate,
            ).props("flat color=slate size=sm")

            def _delete():
                externat_store.delete_stage(stage.id)
                ui.notify("Stage supprimé.", type="warning")
                on_refresh()

            with ui.button(icon="more_horiz").props("flat round dense size=sm").classes("text-slate-400"):
                with ui.menu():
                    ui.menu_item("🗑 Supprimer ce stage", on_click=_delete).classes("text-xs text-red-400")


# ── Section : cours liés ──────────────────────────────────────────────────────

def _render_stage_courses(stage: Stage):
    courses = externat_service.get_stage_courses(stage)
    n = len(courses)

    with ui.expansion(
        f"Cours du collège ({n})",
        icon="menu_book",
        value=True,
    ).classes("w-full rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm"):
        with ui.column().classes("p-3 gap-2 w-full"):
            if not courses:
                ui.label("Aucun cours trouvé pour ce collège.").classes(
                    "text-sm text-slate-400 italic py-2"
                )
                return

            # Afficher max 15, avec "Voir plus"
            shown = courses[:15]
            for c in shown:
                with ui.card().classes(
                    "w-full p-2.5 bg-slate-50 dark:bg-slate-800 "
                    "border border-slate-200 dark:border-slate-700 rounded-xl"
                ):
                    with ui.row().classes("items-center gap-2 w-full"):
                        if c.display_item_number:
                            ui.badge(f"ITEM {c.display_item_number}", color="slate").classes(
                                "text-[11px] font-bold shrink-0"
                            )
                        ui.label(c.title).classes(
                            "text-sm font-medium text-slate-700 dark:text-slate-200 flex-1 truncate"
                        )
                        # Statut lecture
                        nb = getattr(c, "nb_lectures", 0) or 0
                        if nb == 0:
                            ui.badge("Jamais lu", color="red").classes("text-[11px] shrink-0")
                        else:
                            ui.badge(f"{nb}× lu", color="green").classes("text-[11px] shrink-0")

            if n > 15:
                ui.label(f"… et {n - 15} cours de plus.").classes(
                    "text-[11px] text-slate-400 italic mt-1"
                )


# ── Section : lacunes liées ───────────────────────────────────────────────────

def _render_stage_lacunes(stage: Stage):
    lacunes = externat_service.get_stage_lacunes(stage)
    active = [l for l in lacunes if l["status"] in ("active", "à revoir", "récurrente")]
    n = len(active)

    icon_color = "red" if n > 5 else "orange" if n > 0 else "slate"
    with ui.expansion(
        f"Lacunes du collège ({n} actives)",
        icon="report_problem",
    ).classes(f"w-full rounded-xl border border-{icon_color}-100 dark:border-slate-800 shadow-sm"):
        with ui.column().classes("p-3 gap-2 w-full"):
            if not active:
                with ui.row().classes("items-center gap-2 py-2 text-green-600 dark:text-green-400"):
                    ui.icon("check_circle_outline", size="sm")
                    ui.label("Aucune lacune active pour ce collège — bien joué !").classes("text-sm")
                return

            for lc in active[:10]:
                sev = lc["severity"] or 1
                sev_color = "red" if sev >= 4 else "orange" if sev >= 3 else "slate"
                with ui.card().classes(
                    f"w-full p-2.5 bg-slate-50 dark:bg-slate-800 "
                    f"border-l-2 border-l-{sev_color}-400 "
                    "border-y border-r border-slate-200 dark:border-slate-700 rounded-xl"
                ):
                    with ui.row().classes("items-center gap-2 w-full min-w-0"):
                        ui.badge(f"{sev}/5", color=sev_color).classes("text-[11px] shrink-0")
                        ui.label(lc["detail"] or lc["category"] or "—").classes(
                            "text-xs text-slate-700 dark:text-slate-200 flex-1 truncate"
                        )
                        ui.label(lc["course_title"] or "").classes(
                            "text-[11px] text-slate-400 shrink-0 truncate max-w-[120px]"
                        )

            if n > 10:
                ui.label(f"… et {n - 10} autres lacunes.").classes(
                    "text-[11px] text-slate-400 italic mt-1"
                )
                ui.button(
                    "Voir toutes les lacunes",
                    icon="open_in_new",
                    on_click=lambda: ui.navigate.to("/lacunes"),
                ).props("flat color=orange size=xs")


# ── Page principale ───────────────────────────────────────────────────────────

@ui.page('/externat')
@frame('Externat')
def externat_page():
    # ── Refonte : cartes de stage cockpit (feature-flag ui_mode) ───────────────
    if data_store.preferences.get("ui_mode", "cockpit") == "cockpit":
        from frontend.pages.externat_cockpit import render_externat_cockpit
        render_externat_cockpit()
        return

    container = ui.column().classes("w-full gap-6 max-w-4xl mx-auto")

    def _refresh():
        container.clear()
        _build(container)

    _build(container)


def _build(container):
    """Construction principale (rechargeable après une action)."""
    with container:
        # ── Titre ─────────────────────────────────────────────────────────────
        with ui.row().classes("items-center gap-3"):
            ui.icon("local_hospital", size="lg").classes("text-green-600")
            with ui.column().classes("gap-0"):
                ui.label("Mode Externat").classes(
                    "text-2xl font-extrabold text-slate-900 dark:text-slate-50 tracking-tight"
                )
                ui.label(
                    "Gérez votre stage, boostez les cours du collège concerné."
                ).classes("text-sm text-slate-400")

        def _refresh():
            container.clear()
            _build(container)

        # ── Auto-clôture si la date de fin est dépassée ──────────────────────
        active_stage = externat_service.get_active_stage()
        if active_stage and active_stage.days_remaining < 0:
            with ui.row().classes(
                "items-center gap-3 w-full px-4 py-3 rounded-xl "
                "bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800"
            ):
                ui.icon("event_busy", color="amber").classes("text-lg shrink-0")
                ui.label(
                    f"Le stage '{active_stage.specialty}' s'est terminé "
                    f"le {_fmt_date(active_stage.end_date)}."
                ).classes("text-sm text-amber-800 dark:text-amber-200 flex-1")
                def _auto_close(s=active_stage):
                    externat_store.update_stage(s.id, {"is_active": False})
                    ui.notify("Stage clôturé automatiquement.", type="info")
                    _refresh()
                ui.button("Clôturer", icon="check", on_click=_auto_close).props(
                    "unelevated color=amber size=sm rounded"
                )

        if active_stage:
            _render_active_stage(active_stage, _refresh)
            ui.separator().classes("my-1 dark:bg-slate-800")
            _render_stage_courses(active_stage)
            _render_stage_lacunes(active_stage)

        else:
            # Empty state
            with ui.card().classes(
                "w-full p-8 rounded-2xl border border-dashed "
                "border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900"
            ):
                with ui.column().classes("w-full items-center gap-3 text-slate-400"):
                    ui.icon("local_hospital", size="xl").classes("text-green-300")
                    ui.label("Aucun stage en cours").classes("text-lg font-semibold")
                    ui.label(
                        "Configurez votre stage pour activer le boost de priorité "
                        "sur les cours du collège correspondant."
                    ).classes("text-sm text-center max-w-sm")
                    ui.button(
                        "Configurer mon stage",
                        icon="add",
                        on_click=lambda: _open_stage_dialog(_refresh),
                    ).props("unelevated color=indigo size=md rounded").classes("mt-2")

        # ── Bouton ajout (si stage actif, le bouton est en haut de la carte)
        if not active_stage:
            pass  # bouton déjà dans le empty state

        ui.separator().classes("my-2 dark:bg-slate-800")

        # ── Historique ────────────────────────────────────────────────────────
        all_stages = externat_store.get_all_stages()
        past_stages = [s for s in all_stages if s.is_past and not s.is_current]

        if past_stages or active_stage:
            with ui.row().classes("items-center justify-between w-full"):
                ui.label("Historique des stages").classes(
                    "text-sm font-bold text-slate-600 dark:text-slate-300 uppercase tracking-wider"
                )
                ui.button(
                    "Nouveau stage",
                    icon="add",
                    on_click=lambda: _open_stage_dialog(_refresh),
                ).props("outline color=indigo size=sm rounded")

        if past_stages:
            with ui.column().classes("w-full gap-2"):
                for s in past_stages:
                    with ui.card().classes(
                        "w-full p-3 rounded-xl border border-slate-200 dark:border-slate-700 "
                        "bg-slate-50 dark:bg-slate-800/50"
                    ):
                        with ui.row().classes("items-center gap-3 w-full"):
                            ui.icon("local_hospital", size="sm").classes("text-slate-400 shrink-0")
                            with ui.column().classes("flex-1 gap-0 min-w-0"):
                                ui.label(s.specialty).classes(
                                    "text-sm font-semibold text-slate-600 dark:text-slate-300"
                                )
                                ui.label(
                                    f"{_fmt_date(s.start_date)} → {_fmt_date(s.end_date)} "
                                    f"· {s.duration_weeks} sem."
                                ).classes("text-[11px] text-slate-400")
                            ui.badge("Terminé", color="slate").classes("text-[11px] shrink-0")

                            def _edit(stage=s):
                                _open_stage_dialog(_refresh, existing=stage)

                            def _del(stage=s):
                                externat_store.delete_stage(stage.id)
                                ui.notify("Stage supprimé.", type="warning")
                                _refresh()

                            ui.button(icon="edit", on_click=_edit).props(
                                "flat round dense size=xs color=slate"
                            )
                            ui.button(icon="delete", on_click=_del).props(
                                "flat round dense size=xs color=red"
                            )

        elif not active_stage:
            pass  # rien à afficher
