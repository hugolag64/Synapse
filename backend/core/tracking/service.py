"""
CourseTrackingService — source unique de vérité pour le suivi des cours.

Responsabilités :
  - Calculer les dates J3/J7/J14/J30 à partir d'une date de première lecture.
  - Construire le payload Notion pour démarrer/redémarrer le suivi.
  - Retourner l'état de suivi d'un cours (TrackingStatus).

Ce service est PUR pour build_tracking_payload() et get_tracking_status() :
  aucun I/O, aucune dépendance réseau → 100 % testable sans mock.

La persistance Notion (start_course_tracking async) est dans NotionService
qui délègue ici le calcul du payload.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from backend.config.settings import NOTION_PROPS as P
from backend.core.notion.payloads import checkbox, notion_date


# ── Constantes de révision espacée ───────────────────────────────────────────

REVIEW_INTERVALS: dict[str, int] = {
    "J3":  3,
    "J7":  7,
    "J14": 14,
    "J30": 30,
}


# ── Résultat de l'état de suivi ───────────────────────────────────────────────

@dataclass
class TrackingStatus:
    """État de suivi calculé à partir d'un objet Cours."""
    is_started: bool
    first_read_date: Optional[datetime.date]
    j3:  Optional[datetime.date]
    j7:  Optional[datetime.date]
    j14: Optional[datetime.date]
    j30: Optional[datetime.date]
    nb_lectures: int
    # True quand J30 est passé (cycle complet terminé)
    is_completed: bool

    @property
    def review_dates(self) -> dict[str, Optional[datetime.date]]:
        return {"J3": self.j3, "J7": self.j7, "J14": self.j14, "J30": self.j30}

    @property
    def next_review(self) -> Optional[tuple[str, datetime.date]]:
        """Retourne (label, date) de la prochaine révision à venir, ou None."""
        today = datetime.date.today()
        for label, d in self.review_dates.items():
            if d and d >= today:
                return label, d
        return None

    @property
    def overdue_reviews(self) -> list[tuple[str, datetime.date]]:
        """Liste des révisions dont la date est dépassée (sans avoir de révision future)."""
        today = datetime.date.today()
        return [
            (label, d)
            for label, d in self.review_dates.items()
            if d and d < today
        ]


# ── Service ───────────────────────────────────────────────────────────────────

class CourseTrackingService:
    """
    Service centralisé pour le suivi de cours.

    Les méthodes build_tracking_payload() et get_tracking_status() sont PURES :
    elles ne font ni I/O ni appel réseau. Elles peuvent être testées directement.
    """

    # ── Payload Notion ────────────────────────────────────────────────────────

    def build_tracking_payload(
        self,
        context: str,
        first_read_date: datetime.date,
    ) -> dict:
        """
        Retourne le payload Notion complet pour démarrer ou redémarrer le suivi.

        context         : "college" ou "ue"
        first_read_date : date de première lecture (J0)

        Calcule J3 / J7 / J14 / J30 et les encode au format Notion.
        Source unique de vérité — appelé par NotionService ET par le frontend.
        """
        d = first_read_date

        if context == "college":
            return {
                P.RAPPEL_COLLEGE:       checkbox(True),
                P.DATE_LECTURE_COLLEGE: notion_date(d.isoformat()),
                P.LECTURE_J3_COLLEGE:   notion_date(self._j(d, "J3")),
                P.LECTURE_J7_COLLEGE:   notion_date(self._j(d, "J7")),
                P.LECTURE_J14_COLLEGE:  notion_date(self._j(d, "J14")),
                P.LECTURE_J30_COLLEGE:  notion_date(self._j(d, "J30")),
            }
        else:
            return {
                P.RAPPEL_UE:       checkbox(True),
                P.DATE_LECTURE_UE: notion_date(d.isoformat()),
                P.LECTURE_J3_UE:   notion_date(self._j(d, "J3")),
                P.LECTURE_J7_UE:   notion_date(self._j(d, "J7")),
                P.LECTURE_J14_UE:  notion_date(self._j(d, "J14")),
                P.LECTURE_J30_UE:  notion_date(self._j(d, "J30")),
            }

    def compute_review_dates(
        self,
        first_read_date: datetime.date,
    ) -> dict[str, datetime.date]:
        """
        Retourne les 4 dates de révision calculées depuis first_read_date.
        Pur, sans dépendance Notion.
        """
        return {
            label: first_read_date + datetime.timedelta(days=days)
            for label, days in REVIEW_INTERVALS.items()
        }

    # ── Status ────────────────────────────────────────────────────────────────

    def get_tracking_status(self, course, context: str) -> TrackingStatus:
        """
        Retourne l'état de suivi d'un cours pour un contexte donné.

        course  : objet Cours (backend.core.notion.models.Cours)
        context : "college" ou "ue"

        Pur — lit uniquement les attributs du cours, aucun I/O.
        """
        if context == "college":
            first_read = getattr(course, "date_1ere_lecture", None)
            j3  = getattr(course, "lecture_j3_college", None)
            j7  = getattr(course, "lecture_j7_college", None)
            j14 = getattr(course, "lecture_j14_college", None)
            j30 = getattr(course, "lecture_j30_college", None)
            nb  = getattr(course, "nb_lectures", 0) or 0
        else:
            first_read = getattr(course, "date_1ere_lecture_ue", None)
            j3  = getattr(course, "lecture_j3_ue", None)
            j7  = getattr(course, "lecture_j7_ue", None)
            j14 = getattr(course, "lecture_j14_ue", None)
            j30 = getattr(course, "lecture_j30_ue", None)
            nb  = getattr(course, "nb_lectures_ue", 0) or 0

        is_started = bool(first_read)
        is_completed = bool(j30 and j30 < datetime.date.today())

        return TrackingStatus(
            is_started=is_started,
            first_read_date=first_read,
            j3=j3,
            j7=j7,
            j14=j14,
            j30=j30,
            nb_lectures=nb,
            is_completed=is_completed,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _j(self, base: datetime.date, label: str) -> str:
        """Retourne la date ISO J{n} calculée depuis base."""
        days = REVIEW_INTERVALS[label]
        return (base + datetime.timedelta(days=days)).isoformat()


# ── Singleton ─────────────────────────────────────────────────────────────────

tracking_service = CourseTrackingService()
