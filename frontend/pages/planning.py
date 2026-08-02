"""
Planning — Synapse Phase F
---------------------------
Page de planification automatique de la journée et de la semaine.

Layout :
  • En-tête : date + toggle Journée/Semaine + bouton Planifier
  • Bannière : total estimé · charge · Calendar occupé
  • Slots : cartes urgentes | prévues | lacunes  (checkboxes pour Calendar)
  • Section semaine : 7 panneaux jours
  • CTA : "Envoyer à Google Calendar"
"""
from __future__ import annotations

import datetime
from nicegui import ui

from backend.core.planning.models import PlannedSlot, DailyPlan
from backend.core.google.calendar_service import calendar_service


# ── Couleurs Tailwind par couleur de slot ─────────────────────────────────────
_COLOR_RING = {
    "red":    "border-l-red-500",
    "orange": "border-l-orange-400",
    "blue":   "border-l-blue-500",
    "indigo": "border-l-indigo-500",
    "teal":   "border-l-teal-500",
    "violet": "border-l-violet-500",
    "purple": "border-l-purple-500",
    "green":  "border-l-green-500",
    "slate":  "border-l-slate-400",
}
_COLOR_BADGE = {
    "red":    "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300",
    "orange": "bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-300",
    "blue":   "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300",
    "indigo": "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300",
    "teal":   "bg-teal-50 text-teal-700 dark:bg-teal-900/20 dark:text-teal-300",
    "violet": "bg-violet-50 text-violet-700 dark:bg-violet-900/20 dark:text-violet-300",
    "purple": "bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-300",
    "green":  "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300",
    "slate":  "bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
}

days_fr  = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
months_fr = ["janvier", "février", "mars", "avril", "mai", "juin",
             "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _date_label(d: datetime.date) -> str:
    today = datetime.date.today()
    if d == today:
        return "Aujourd'hui"
    if d == today + datetime.timedelta(days=1):
        return "Demain"
    return f"{days_fr[d.weekday()]} {d.day} {months_fr[d.month - 1]}"


# ── Composant SlotCard ────────────────────────────────────────────────────────

def _slot_card(slot: PlannedSlot, selected: dict[str, bool], slot_key: str):
    """Carte représentant un créneau planifié, avec checkbox pour export Calendar."""
    ring  = _COLOR_RING.get(slot.color, "border-l-slate-400")
    badge = _COLOR_BADGE.get(slot.color, _COLOR_BADGE["slate"])

    with ui.card().classes(
        f"w-full p-0 rounded-xl border-l-4 {ring} "
        "border-y border-r border-slate-100 dark:border-slate-800 "
        "shadow-sm hover:shadow-md transition-all overflow-hidden"
    ):
        with ui.row().classes("items-center gap-3 px-3 py-2.5 w-full"):

            # Checkbox pour sélection Calendar
            chk = ui.checkbox(value=selected.get(slot_key, True))
            def _toggle(e, k=slot_key):
                selected[k] = e.value
            chk.on("update:model-value", _toggle)

            # Icône
            ui.icon(slot.icon, size="sm").classes(f"text-{slot.color}-500 shrink-0")

            # Texte
            with ui.column().classes("flex-1 gap-0 min-w-0"):
                ui.label(slot.label).classes(
                    "text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug"
                ).style(
                    "overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                ).tooltip(slot.label)
                if slot.subtitle:
                    ui.label(slot.subtitle).classes(
                        "text-[11px] text-slate-500 dark:text-slate-400 leading-snug"
                    ).style(
                        "overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                    )

            # Durée + badge type
            with ui.column().classes("items-end gap-1 shrink-0"):
                with ui.element("div").classes(f"px-2 py-0.5 rounded-full text-[11px] font-bold {badge}"):
                    ui.label(f"{slot.duration_min} min")
                if slot.is_urgent:
                    ui.badge("Urgent", color="red").classes("text-[11px] px-1 py-0")

            # Ouvrir PDF
            if slot.url_pdf:
                ui.button(icon="picture_as_pdf").props(
                    "flat round dense size=xs color=slate"
                ).on(
                    "click", lambda u=slot.url_pdf: ui.navigate.to(u, new_tab=True)
                ).tooltip("Ouvrir le PDF")


# ── Dialog export Google Calendar ─────────────────────────────────────────────

def _open_calendar_export_dialog(slots: list[PlannedSlot], selected: dict[str, bool]):
    """Dialog pour envoyer les slots sélectionnés dans Google Calendar."""
    now = datetime.datetime.now()
    # Heure de début par défaut : prochaine heure entière
    default_start = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    start_time_str = {"v": default_start.strftime("%H:%M")}

    to_export = [s for i, s in enumerate(slots) if selected.get(f"slot_{i}", True)]

    with ui.dialog() as dlg:
        with ui.card().classes("w-full max-w-xl p-0 rounded-2xl overflow-hidden"):

            # ── Header ────────────────────────────────────────────────────────
            with ui.row().classes(
                "items-center gap-3 px-5 py-4 "
                "bg-indigo-50 dark:bg-indigo-900/20 "
                "border-b border-indigo-100 dark:border-indigo-800"
            ):
                ui.icon("event", color="indigo").classes("text-2xl shrink-0")
                with ui.column().classes("gap-0"):
                    ui.label("Envoyer à Google Calendar").classes(
                        "font-bold text-indigo-800 dark:text-indigo-200"
                    )
                    ui.label(
                        f"{len(to_export)} créneau(x) sélectionné(s) · "
                        f"{sum(s.duration_min for s in to_export)} min total"
                    ).classes("text-xs text-indigo-600 dark:text-indigo-400")

            with ui.column().classes("px-5 py-4 gap-4 w-full"):

                # ── Heure de début ────────────────────────────────────────────
                with ui.row().classes("items-center gap-3"):
                    ui.icon("schedule", size="sm").classes("text-slate-400 shrink-0")
                    ui.label("Heure de début :").classes("text-sm text-slate-600 dark:text-slate-300 shrink-0")
                    start_input = ui.input(
                        value=default_start.strftime("%H:%M"),
                        placeholder="08:30",
                    ).props("outlined dense").classes("w-28")
                    start_input.on("update:model-value", lambda e: start_time_str.update({"v": e.value}))

                # ── Liste des créneaux ─────────────────────────────────────────
                with ui.scroll_area().classes("w-full max-h-56"):
                    with ui.column().classes("gap-1 w-full"):
                        for slot in to_export:
                            with ui.row().classes("items-center gap-2 py-1"):
                                ui.icon(slot.icon, size="xs").classes(f"text-{slot.color}-500 shrink-0")
                                ui.label(slot.label).classes(
                                    "text-xs text-slate-700 dark:text-slate-200 flex-1 truncate"
                                )
                                ui.label(f"{slot.duration_min} min").classes(
                                    "text-[11px] text-slate-400 shrink-0"
                                )

                ui.label(
                    "Les événements sont créés en séquence à partir de l'heure choisie."
                ).classes("text-[11px] text-slate-400 italic")

            # ── Footer ────────────────────────────────────────────────────────
            with ui.row().classes(
                "items-center justify-end gap-3 px-5 py-3 "
                "border-t border-slate-100 dark:border-slate-700"
            ):
                ui.button("Annuler", on_click=dlg.close).props("flat color=slate size=sm")

                async def _create_events():
                    if not to_export:
                        ui.notify("Aucun créneau sélectionné.", type="warning")
                        dlg.close()
                        return

                    try:
                        h, m = map(int, start_time_str["v"].split(":"))
                    except Exception:
                        ui.notify("Heure invalide (format HH:MM).", type="negative")
                        return

                    today = datetime.date.today()
                    cursor = datetime.datetime(today.year, today.month, today.day, h, m)
                    created = 0

                    for slot in to_export:
                        try:
                            result = await calendar_service.create_event(
                                summary=slot.label,
                                start_time_iso=cursor,
                                duration_minutes=slot.duration_min,
                                description=slot.subtitle,
                                color_id="9" if slot.is_urgent else None,
                            )
                            if result:
                                created += 1
                            cursor += datetime.timedelta(minutes=slot.duration_min)
                        except Exception as exc:
                            from loguru import logger
                            logger.warning(f"Calendar export échoué pour {slot.label}: {exc}")

                    dlg.close()
                    if created:
                        s = "s" if created > 1 else ""
                        ui.notify(
                            f"✅ {created} événement{s} créé{s} dans Google Calendar",
                            type="positive",
                            icon="event",
                        )
                    else:
                        ui.notify(
                            "Impossible de créer les événements. Vérifiez la connexion Calendar.",
                            type="negative",
                        )

                ui.button(
                    "Créer les événements",
                    icon="event_available",
                    on_click=_create_events,
                ).props("unelevated color=indigo size=sm")

    dlg.open()


# ── Rendu du plan journée ─────────────────────────────────────────────────────

def _render_day_plan(plan: DailyPlan, selected: dict[str, bool], container):
    """Remplit un conteneur avec le plan d'une journée."""
    container.clear()
    with container:
        if not plan.slots:
            with ui.column().classes("w-full items-center py-8 gap-2 text-slate-400"):
                ui.icon("check_circle_outline", size="xl").classes("text-green-400")
                ui.label("Rien à planifier pour cette journée — tout est à jour !").classes(
                    "text-sm"
                )
            return

        # ── Bannière résumé ────────────────────────────────────────────────────
        with ui.row().classes("items-center gap-3 flex-wrap mb-4"):
            with ui.element("div").classes(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full "
                "bg-slate-50 dark:bg-slate-800"
            ):
                ui.icon("schedule", size="xs").classes("text-slate-400")
                ui.label(f"{plan.label_duration} estimé").classes(
                    "text-sm font-semibold text-slate-600 dark:text-slate-300"
                )

            with ui.element("div").classes(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full "
                "bg-blue-50 dark:bg-blue-900/20"
            ):
                ui.icon("event_note", size="xs").classes("text-blue-500")
                ui.label(f"{len(plan.slots)} créneaux").classes(
                    "text-sm font-semibold text-blue-700 dark:text-blue-400"
                )

            if plan.calendar_busy_min:
                with ui.element("div").classes(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-full "
                    "bg-violet-50 dark:bg-violet-900/20"
                ):
                    ui.icon("calendar_today", size="xs").classes("text-violet-500")
                    cal_h, cal_m = divmod(plan.calendar_busy_min, 60)
                    cal_str = f"{cal_h}h{cal_m:02d}" if cal_h else f"{cal_m} min"
                    ui.label(f"{cal_str} Calendar").classes(
                        "text-sm font-semibold text-violet-700 dark:text-violet-400"
                    )

            if plan.is_heavy:
                with ui.element("div").classes(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-full "
                    "bg-amber-50 dark:bg-amber-900/20"
                ):
                    ui.icon("warning", size="xs").classes("text-amber-500")
                    ui.label("Journée chargée").classes(
                        "text-sm font-semibold text-amber-700 dark:text-amber-400"
                    )

        # ── Urgentes ─────────────────────────────────────────────────────────
        urgent_slots = [s for s in plan.slots if s.source_ref == "urgent"]
        if urgent_slots:
            ui.label("🔴 Révisions urgentes").classes(
                "text-xs font-bold text-red-500 uppercase tracking-wider mb-1"
            )
            for i, slot in enumerate(urgent_slots):
                key = f"slot_{i}"
                selected.setdefault(key, True)
                _slot_card(slot, selected, key)
            ui.separator().classes("my-3 dark:bg-slate-800")

        # ── Prévues aujourd'hui ───────────────────────────────────────────────
        today_slots = [s for s in plan.slots if s.source_ref == "today"]
        if today_slots:
            ui.label("📅 Prévues aujourd'hui").classes(
                "text-xs font-bold text-blue-500 uppercase tracking-wider mb-1"
            )
            offset = len(urgent_slots)
            for i, slot in enumerate(today_slots):
                key = f"slot_{offset + i}"
                selected.setdefault(key, True)
                _slot_card(slot, selected, key)
            ui.separator().classes("my-3 dark:bg-slate-800")

        # ── Lacunes ──────────────────────────────────────────────────────────
        lacune_slots = [s for s in plan.slots if s.source_ref == "lacune"]
        if lacune_slots:
            ui.label("⚠ Lacunes à revoir").classes(
                "text-xs font-bold text-orange-500 uppercase tracking-wider mb-1"
            )
            offset = len(urgent_slots) + len(today_slots)
            for i, slot in enumerate(lacune_slots):
                key = f"slot_{offset + i}"
                selected.setdefault(key, True)
                _slot_card(slot, selected, key)


# ── Rendu du plan semaine ─────────────────────────────────────────────────────

def _render_week_plan(plans: list[DailyPlan], selected: dict[str, bool], container):
    """Affiche les 7 jours sous forme d'accordéons compacts."""
    container.clear()
    today = datetime.date.today()

    with container:
        for day_idx, plan in enumerate(plans):
            day_label = _date_label(plan.date)
            has_tasks = bool(plan.slots)
            n = len(plan.slots)
            total = plan.label_duration
            heavy_icon = "⚠ " if plan.is_heavy else ""

            header_txt = (
                f"{heavy_icon}{day_label} · {n} créneaux · {total}"
                if has_tasks else
                f"{day_label} · Rien de prévu"
            )
            header_color = (
                "text-red-700 dark:text-red-400"   if plan.is_heavy else
                "text-slate-700 dark:text-slate-200"
            )

            with ui.expansion(
                header_txt,
                value=(plan.date == today),
            ).classes(
                "w-full rounded-xl border border-slate-200 dark:border-slate-800 mb-2 shadow-sm"
            ).props(f'header-class="font-semibold {header_color}"'):
                with ui.column().classes("p-3 w-full gap-2"):
                    if not has_tasks:
                        ui.label("Rien à planifier ce jour-là.").classes(
                            "text-sm text-slate-400 italic py-2"
                        )
                    else:
                        for i, slot in enumerate(plan.slots):
                            key = f"week_{day_idx}_{i}"
                            selected.setdefault(key, True)
                            _slot_card(slot, selected, key)


# ── Page principale ───────────────────────────────────────────────────────────

async def planning_page():
    # ── Vue cockpit ───────────────────────────────────────────────────────────
    from frontend.pages.planning_cockpit import render_planning_cockpit
    await render_planning_cockpit()
    return
