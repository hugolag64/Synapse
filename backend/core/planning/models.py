"""
Planning models — Synapse Phase F
----------------------------------
PlannedSlot  : un créneau d'activité généré par le PlanningService.
DailyPlan    : ensemble de slots pour une journée + méta (charge, Calendar).
WeeklyPlan   : liste de DailyPlan sur 7 jours.

Tous ces objets sont calculés en mémoire, jamais persistés.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional


# ── Couleurs et icônes par type de slot ──────────────────────────────────────

SLOT_META: dict[str, dict] = {
    "review":       {"color": "blue",   "icon": "menu_book"},
    "review_urgent":{"color": "red",    "icon": "emergency"},
    "consolidation":{"color": "cyan",  "icon": "history_edu"},
    "anki":         {"color": "teal",   "icon": "style"},
    "qcm":          {"color": "indigo", "icon": "quiz"},
    "lacune":       {"color": "orange", "icon": "report_problem"},
    "lacune_crit":  {"color": "red",    "icon": "report_problem"},
    "video_ednpro": {"color": "violet", "icon": "play_circle"},
    "obsidian":     {"color": "purple", "icon": "edit_note"},
    "fiche_edn":    {"color": "slate",  "icon": "description"},
    "lecture":      {"color": "green",  "icon": "auto_stories"},
}


@dataclass
class PlannedSlot:
    """Un créneau d'activité dans le planning."""

    slot_type: str          # clé dans SLOT_META
    label: str              # titre affiché (ex: "ITEM 235 – Péricardite")
    subtitle: str           # raison / action recommandée
    duration_min: int       # durée estimée en minutes
    color: str              # couleur Tailwind (ex: "red", "indigo")
    icon: str               # nom d'icône Material

    is_urgent: bool = False
    course_id: Optional[str] = None
    course_title: Optional[str] = None
    item_number: Optional[str] = None
    url_pdf: Optional[str] = None
    source_ref: str = ""    # "urgent" | "today" | "lacune" | "week"


@dataclass
class DailyPlan:
    """Planning d'une journée."""

    date: datetime.date
    slots: list[PlannedSlot] = field(default_factory=list)
    skipped: list[PlannedSlot] = field(default_factory=list)  # overflow non planifié

    total_min: int = 0
    is_heavy: bool = False          # True si > HEAVY_THRESHOLD

    calendar_busy_min: int = 0      # minutes occupées par Google Calendar
    free_min: int = 0               # estimation du temps d'étude disponible

    @property
    def estimated_h(self) -> int:
        return self.total_min // 60

    @property
    def estimated_m(self) -> int:
        return self.total_min % 60

    @property
    def label_duration(self) -> str:
        if self.estimated_h:
            return f"{self.estimated_h}h{self.estimated_m:02d}"
        return f"{self.total_min} min"

    @property
    def is_today(self) -> bool:
        return self.date == datetime.date.today()


# Pour la vue semaine : liste de DailyPlan
WeeklyPlan = list[DailyPlan]
