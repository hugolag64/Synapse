"""
Externat models — Synapse Phase G
-----------------------------------
Stage : représente un stage hospitalier actuel ou passé.

Stocké en SQLite (synapse_local.db).
Jamais dans Notion : données personnelles de planning, pas de cours.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Stage:
    """Un stage d'externat (stage hospitalier)."""

    id: int
    specialty: str                    # "Cardiologie", "Neurologie", etc.
    college_notion: str               # Nom du collège Notion → boost priorité
    start_date: datetime.date
    end_date: datetime.date

    objectives: str = ""              # Objectifs libres (markdown OK)
    schedules: str = ""               # Horaires habituels (ex: "8h-17h Lu-Ve")
    gardes: str = ""                  # Gardes (texte libre ou JSON)
    contraintes: str = ""             # Contraintes et repos

    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    # ── Propriétés calculées ──────────────────────────────────────────────────

    @property
    def is_current(self) -> bool:
        """Vrai si le stage est en cours aujourd'hui."""
        today = datetime.date.today()
        return self.is_active and self.start_date <= today <= self.end_date

    @property
    def is_past(self) -> bool:
        return self.end_date < datetime.date.today()

    @property
    def is_future(self) -> bool:
        return self.start_date > datetime.date.today()

    @property
    def duration_weeks(self) -> int:
        return max(0, (self.end_date - self.start_date).days // 7)

    @property
    def days_remaining(self) -> int:
        """Jours restants (0 si passé)."""
        today = datetime.date.today()
        return max(0, (self.end_date - today).days)

    @property
    def days_elapsed(self) -> int:
        """Jours écoulés depuis le début."""
        today = datetime.date.today()
        return max(0, (today - self.start_date).days)

    @property
    def status_label(self) -> str:
        if self.is_current:
            return "En cours"
        if self.is_future:
            return "À venir"
        return "Terminé"

    @property
    def status_color(self) -> str:
        return {
            "En cours": "green",
            "À venir":  "indigo",
            "Terminé":  "slate",
        }.get(self.status_label, "slate")


@dataclass
class ActiveStage:
    """
    Vue allégée du stage en cours, utilisée par ReviewService._calculate_priority().
    Construit depuis le Stage SQLite courant via externat.store.get_active_stage().
    """
    college: str            # = Stage.college_notion
    start_date: datetime.date
    end_date: datetime.date
    boost_factor: float = 1.5

    @classmethod
    def from_stage(cls, stage: "Stage") -> "ActiveStage":
        return cls(
            college=stage.college_notion,
            start_date=stage.start_date,
            end_date=stage.end_date,
        )
