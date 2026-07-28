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
}

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
        max_today:  int = 5,
        max_lacunes: int = 3,
        target_minutes: int | None = None,
        target_items: int | None = None,
    ) -> DailyPlan:
        """
        Génère le planning d'une journée.

        Ordre de priorité :
          1. Tâches urgentes (overdue), triées par retard décroissant
          2. Tâches du jour, triées par priority_score
          3. Lacunes actives, triées par sévérité décroissante

        Les lacunes sont filtrées aux statuts actifs/à revoir/récurrents.
        """
        durations = self.get_durations()
        slots: list[PlannedSlot] = []

        # ── 1. Urgentes ───────────────────────────────────────────────────────
        for t in sorted(urgent_tasks, key=lambda x: -x.days_overdue)[:max_urgent]:
            slots.append(self._slot_from_task(t, "urgent"))

        # ── 2. Du jour ────────────────────────────────────────────────────────
        for t in sorted(today_tasks, key=lambda x: -x.priority_score)[:max_today]:
            slots.append(self._slot_from_task(t, "today"))

        # ── 3. Lacunes ────────────────────────────────────────────────────────
        active_statuses = {"active", "à revoir", "récurrente"}
        lacunes_filtered = [
            lc for lc in active_lacunes
            if (lc["status"] or "").lower() in active_statuses
        ]
        lacunes_filtered.sort(key=lambda x: -(x["severity"] or 0))
        for lc in lacunes_filtered[:max_lacunes]:
            slots.append(self._slot_from_lacune(lc, durations))

        # ── Totaux ────────────────────────────────────────────────────────────
        skipped: list[PlannedSlot] = []
        if target_minutes is not None or target_items is not None:
            kept: list[PlannedSlot] = []
            used_minutes = 0
            used_items = 0
            for slot in slots:
                over_minutes = target_minutes is not None and used_minutes + slot.duration_min > target_minutes
                over_items = target_items is not None and used_items >= target_items
                if slot.is_urgent or (not over_minutes and not over_items):
                    kept.append(slot)
                    used_minutes += slot.duration_min
                    used_items += 1
                else:
                    skipped.append(slot)
            slots = kept

        total_min = sum(s.duration_min for s in slots)
        cal_busy  = self._calendar_busy_min(calendar_events)
        free_min  = max(0, DEFAULT_STUDY_DAY_MIN - cal_busy)

        logger.debug(
            f"PlanningService.plan_day : {len(slots)} slots, "
            f"{total_min} min estimé, {cal_busy} min Calendar occupé"
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
        max_items: int = 6,
        max_per_college: int = 2,
    ):
        """
        Sélection du jour pour le flux de consolidation long terme (items
        ayant fini leur cycle J3-J30, ou déclarés flou/correct/solide sans
        avoir jamais été suivis dans l'app). Retourne (selected, skipped).
        """
        from backend.core.reviews import consolidation

        tasks = consolidation.get_due_consolidation_tasks()
        return consolidation.select_daily(
            tasks, max_items=max_items, max_per_college=max_per_college,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

planning_service = PlanningService()
