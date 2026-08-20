"""
PlanningService — Synapse Phase F
-----------------------------------
Génère un DailyPlan ou un WeeklyPlan à partir des données disponibles :
  - tâches urgentes (overdue) et du jour (ReviewTask)
  - lacunes actives (SQLite weak_points)
  - événements Google Calendar (optionnel)

Principe :
  1. Tâches urgentes  → slots triés par retard décroissant
  2. Tâches du jour   → slots triés par priority_score
  3. Lacunes actives  → top N par sévérité
  4. Calcul total_min et charge (is_heavy)
  5. Estimation du temps libre selon Calendar (si disponible)

Pas d'I/O réseau dans ce fichier — les données sont injectées en paramètre.
"""
from __future__ import annotations

import datetime
from loguru import logger

from backend.core.planning.models import (
    PlannedSlot, DailyPlan, WeeklyPlan, SLOT_META,
)
from backend.core.reviews.recommendation_service import get_next_action


# ── Clés de préférences ────────────────────────────────────────────────────────
_DUR_KEYS = {
    "revision":    ("dur_revision",    20),
    "lecture":     ("dur_lecture",     30),
    "anki":        ("dur_anki",        30),
    "qcm":         ("dur_qcm",         30),
    "video_ednpro":("dur_video",       30),
    "obsidian":    ("dur_obsidian",    20),
    "lacune":      ("dur_lacune",      15),
    "fiche_edn":   ("dur_fiche_edn",   20),
    "prep_pdf":    ("dur_prep_pdf",    5),
    "prep_resume": ("dur_prep_resume", 20),
}

_PREP_DURATION_KEY = {"pdf": "prep_pdf", "obsidian": "obsidian", "resume": "prep_resume", "first_read": "lecture"}
_PREP_LABEL = {"pdf": "PDF", "obsidian": "Fiche Obsidian", "resume": "Résumé", "first_read": "1ère lecture"}
_PREP_TYPE_ORDER = ("pdf", "obsidian", "resume", "first_read")

# Seuil "journée chargée"
HEAVY_THRESHOLD_MIN = 120   # 2 h

# Plage d'étude estimée par défaut (si Calendar absent)
DEFAULT_STUDY_DAY_MIN = 8 * 60


class PlanningService:
    """
    Service pur : génère des plans sans faire d'I/O réseau.
    Appelle uniquement recommendation_service pour les durées de révision.
    """

    # ── Durées ────────────────────────────────────────────────────────────────

    def get_durations(self) -> dict[str, int]:
        """Lit les durées depuis data_store.preferences (ou valeurs par défaut)."""
        try:
            from backend.state.store import data_store
            prefs = data_store.preferences
        except Exception:
            prefs = {}
        return {k: int(prefs.get(pkey, default)) for k, (pkey, default) in _DUR_KEYS.items()}

    def _dur(self, key: str, durations: dict) -> int:
        return durations.get(key, _DUR_KEYS.get(key, ("", 20))[1])

    # ── Conversion ReviewTask → PlannedSlot ────────────────────────────────────

    def _slot_from_task(self, task, source_ref: str) -> PlannedSlot:
        na = get_next_action(task)
        item_txt = f"ITEM {task.item_number} – " if task.item_number else ""
        label = f"{item_txt}{task.course_title}"
        subtitle = "À consolider" if task.review_type == "consolidation" else f"{na.label}"
        if na.reason:
            subtitle += f" · {na.reason}"

        color = na.color
        icon = na.icon
        urgent = task.days_overdue > 0

        slot_type = "consolidation" if task.review_type == "consolidation" else (
            "review_urgent" if urgent else "review"
        )
        return PlannedSlot(
            slot_type=slot_type,
            label=label,
            subtitle=subtitle,
            duration_min=na.duration_min,
            color=color,
            icon=icon,
            is_urgent=urgent,
            course_id=task.course_id,
            course_title=task.course_title,
            item_number=task.item_number,
            url_pdf=task.best_pdf_url,
            source_ref="consolidation" if task.review_type == "consolidation" else source_ref,
        )

    # ── Conversion lacune → PlannedSlot ───────────────────────────────────────

    def _slot_from_lacune(self, lc, durations: dict) -> PlannedSlot:
        course_title = lc["course_title"] or "Cours inconnu"
        item_nb = lc["item_number"] or ""
        item_txt = f"ITEM {item_nb} – " if item_nb else ""
        severity = lc["severity"] or 1
        detail = lc["detail"] or lc["category"] or "Lacune à revoir"
        critical = severity >= 4

        return PlannedSlot(
            slot_type="lacune_crit" if critical else "lacune",
            label=f"{item_txt}{course_title}",
            subtitle=f"Lacune {severity}/5 · {detail[:60]}",
            duration_min=self._dur("lacune", durations),
            color="red" if critical else "orange",
            icon="report_problem",
            is_urgent=critical,
            course_id=lc["course_id"],
            course_title=course_title,
            item_number=item_nb,
            source_ref="lacune",
        )

    # ── Conversion tâches de prépa fac → PlannedSlot ──────────────────────────

    def _slot_from_prep_tasks(self, course_tasks: list, durations: dict) -> PlannedSlot:
        """Un seul bloc par cours, agrégeant ses tâches de prépa fac 'todo' du jour."""
        first = course_tasks[0]
        by_type = {t.task_type: t for t in course_tasks}
        ordered_types = [t for t in _PREP_TYPE_ORDER if t in by_type]
        total = sum(self._dur(_PREP_DURATION_KEY[t], durations) for t in ordered_types)
        subtitle = " · ".join(_PREP_LABEL[t] for t in ordered_types)
        return PlannedSlot(
            slot_type="prep",
            label=f"ITEM {first.item_number} – Préparer",
            subtitle=subtitle,
            duration_min=total,
            color="amber",
            icon="assignment",
            course_id=first.course_id,
            course_title=None,
            item_number=first.item_number,
            source_ref="prep",
        )

    # ── Calendar busy time ────────────────────────────────────────────────────

    @staticmethod
    def _calendar_busy_min(calendar_events: list) -> int:
        """Calcule le total des minutes occupées par les événements Calendar."""
        total = 0
        for ev in (calendar_events or []):
            try:
                s = ev.get("start", {}).get("dateTime")
                e = ev.get("end", {}).get("dateTime")
                if s and e:
                    start = datetime.datetime.fromisoformat(s)
                    end   = datetime.datetime.fromisoformat(e)
                    total += max(0, int((end - start).total_seconds() / 60))
            except Exception:
                pass
        return total

    # ── plan_day ─────────────────────────────────────────────────────────────

    def plan_day(
        self,
        urgent_tasks: list,
        today_tasks:  list,
        active_lacunes: list,
        calendar_events: list | None = None,
        max_urgent: int = 8,
        max_lacunes: int = 3,
        target_minutes: int | None = None,
        prep_slots: list | None = None,
        consolidation_tasks: list | None = None,
        consolidation_today: datetime.date | None = None,
    ) -> DailyPlan:
        """
        Génère le planning d'une journée en deux voies :

          1. Lecture  : urgentes (retard) + du jour + lacunes + prépa fac (prep_slots),
                        triées par priorité, consomment `target_minutes` en premier.
                        Les tâches en retard ne sont jamais coupées (mais comptent bien
                        dans le total consommé).
          2. Consolidation : ce qu'il reste de `target_minutes` après la voie Lecture,
                        sélectionnée par urgence avec le plafond diversité-par-collège
                        existant (consolidation.select_daily/daily_caps).

        Tout item écarté (Lecture par le budget, Consolidation par le budget ou le
        plafond diversité) est renvoyé dans `skipped` plutôt que silencieusement perdu.
        """
        durations = self.get_durations()
        lecture_slots: list[PlannedSlot] = []

        # ── Lecture : urgentes ────────────────────────────────────────────────
        for t in sorted(urgent_tasks, key=lambda x: -x.days_overdue)[:max_urgent]:
            lecture_slots.append(self._slot_from_task(t, "urgent"))

        # ── Lecture : du jour ─────────────────────────────────────────────────
        for t in sorted(today_tasks, key=lambda x: -x.priority_score):
            lecture_slots.append(self._slot_from_task(t, "today"))

        # ── Lecture : lacunes ─────────────────────────────────────────────────
        active_statuses = {"active", "à revoir", "récurrente"}
        lacunes_filtered = [
            lc for lc in active_lacunes
            if (lc["status"] or "").lower() in active_statuses
        ]
        lacunes_filtered.sort(key=lambda x: -(x["severity"] or 0))
        for lc in lacunes_filtered[:max_lacunes]:
            lecture_slots.append(self._slot_from_lacune(lc, durations))

        # ── Lecture : prépa fac ───────────────────────────────────────────────
        lecture_slots.extend(prep_slots or [])

        # ── Trim Lecture par le budget (les urgentes ne sont jamais coupées) ──
        skipped: list[PlannedSlot] = []
        lecture_min = 0
        if target_minutes is not None:
            kept: list[PlannedSlot] = []
            used = 0
            for slot in lecture_slots:
                if slot.is_urgent or used + slot.duration_min <= target_minutes:
                    kept.append(slot)
                    used += slot.duration_min
                else:
                    skipped.append(slot)
            lecture_slots = kept
            lecture_min = used
        else:
            lecture_min = sum(s.duration_min for s in lecture_slots)

        # ── Consolidation : ce qu'il reste du budget ─────────────────────────
        consolidation_slots: list[PlannedSlot] = []
        if consolidation_tasks:
            from backend.core.reviews import consolidation
            from backend.state.store import data_store

            weekend_light = bool(data_store.preferences.get("weekend_light_consolidation", False))
            max_items, max_per_college = consolidation.daily_caps(
                today=consolidation_today, weekend_light=weekend_light,
            )
            diversity_selected, diversity_skipped = consolidation.select_daily(
                consolidation_tasks, max_items=max_items, max_per_college=max_per_college,
            )

            remaining = None if target_minutes is None else max(0, target_minutes - lecture_min)
            cons_skipped_tasks = list(diversity_skipped)
            used = 0
            for t in diversity_selected:
                slot = self._slot_from_task(t, "consolidation")
                if remaining is None or used + slot.duration_min <= remaining:
                    consolidation_slots.append(slot)
                    used += slot.duration_min
                else:
                    cons_skipped_tasks.append(t)

            skipped.extend(self._slot_from_task(t, "consolidation") for t in cons_skipped_tasks)

        slots = lecture_slots + consolidation_slots
        total_min = sum(s.duration_min for s in slots)
        cal_busy  = self._calendar_busy_min(calendar_events)
        free_min  = max(0, DEFAULT_STUDY_DAY_MIN - cal_busy)

        logger.debug(
            f"PlanningService.plan_day : {len(slots)} slots, "
            f"{total_min} min estimé, {cal_busy} min Calendar occupé, "
            f"{len(skipped)} en attente"
        )

        return DailyPlan(
            date=datetime.date.today(),
            slots=slots,
            skipped=skipped,
            total_min=total_min,
            is_heavy=total_min > HEAVY_THRESHOLD_MIN,
            calendar_busy_min=cal_busy,
            free_min=free_min,
        )

    # ── plan_week ─────────────────────────────────────────────────────────────

    def plan_week(
        self,
        all_tasks: list,
        active_lacunes: list,
    ) -> WeeklyPlan:
        """
        Génère un planning sur 7 jours.

        - Jour 0 (aujourd'hui) : tâches overdue + due today + lacunes
        - Jours 1–6 : tâches dont due_date correspond à ce jour
        """
        today = datetime.date.today()
        plans: list[DailyPlan] = []

        for offset in range(7):
            day = today + datetime.timedelta(days=offset)

            if offset == 0:
                urgent = [t for t in all_tasks if t.days_overdue > 0]
                due    = [t for t in all_tasks if t.days_overdue == 0 and t.due_date == day]
                lacunes_day = active_lacunes
            else:
                urgent = []
                due    = [t for t in all_tasks if t.due_date == day]
                lacunes_day = []

            plan = self.plan_day(urgent, due, lacunes_day)
            plan.date = day
            plans.append(plan)

        return plans

    # ── plan_consolidation ───────────────────────────────────────────────────

    def plan_consolidation(
        self,
        max_items: int | None = None,
        max_per_college: int | None = None,
        today: datetime.date | None = None,
    ):
        """
        Sélection du jour pour le flux de consolidation long terme (items
        ayant fini leur cycle J3-J30, ou déclarés flou/correct/solide sans
        avoir jamais été suivis dans l'app). Retourne (selected, skipped).

        Sans max_items/max_per_college explicites, les plafonds sont dérivés
        de consolidation.daily_caps() + la préférence "weekend_light_consolidation"
        — réduits le week-end si activée, inchangés sinon (défaut désactivé).
        """
        from backend.core.reviews import consolidation
        from backend.state.store import data_store

        if max_items is None or max_per_college is None:
            weekend_light = bool(data_store.preferences.get("weekend_light_consolidation", False))
            default_items, default_per_college = consolidation.daily_caps(
                today=today, weekend_light=weekend_light,
            )
            max_items = max_items if max_items is not None else default_items
            max_per_college = max_per_college if max_per_college is not None else default_per_college

        tasks = consolidation.get_due_consolidation_tasks()
        return consolidation.select_daily(
            tasks, max_items=max_items, max_per_college=max_per_college,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

planning_service = PlanningService()
