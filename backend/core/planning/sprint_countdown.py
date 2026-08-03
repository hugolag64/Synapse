"""
sprint_countdown.py — Synapse
-----------------------------
Moteur de pilotage Sprint Countdown EDN.
Calcule la proximité J-EDN et ajuste dynamiquement les stratégies de révision et ratios de travail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class SprintPhase(StrEnum):
    LONG_TERM = "long_term"  # > 120 jours
    CONSOLIDATION = "consolidation"  # 30 à 120 jours
    SPRINT_FLASH = "sprint_flash"  # <= 30 jours


@dataclass(frozen=True)
class SprintConfig:
    days_remaining: int
    target_date: date
    phase: SprintPhase
    recommended_new_ratio: float
    recommended_review_ratio: float
    recommended_qcm_dp_ratio: float
    daily_target_items: int
    focus_message: str


class SprintCountdownService:
    """Service de gestion du compte à rebours EDN et adaptation des rythmes de révision."""

    def __init__(self, target_date_str: str = "2026-10-15"):
        try:
            self.target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            self.target_date = date(2026, 10, 15)

    def get_sprint_status(self, today: date | None = None) -> SprintConfig:
        """Calcule le statut du sprint et préconise l'ajustement du rythme."""
        today = today or date.today()
        delta = (self.target_date - today).days

        if delta > 120:
            phase = SprintPhase.LONG_TERM
            new_r, rev_r, qcm_r = 0.50, 0.35, 0.15
            daily_items = 4
            msg = "⚡ Mode Apprentissage Profond : Sécurisation méthodique du Rang A et prise de notes."
        elif delta > 30:
            phase = SprintPhase.CONSOLIDATION
            new_r, rev_r, qcm_r = 0.25, 0.45, 0.30
            daily_items = 6
            msg = "🎯 Mode Consolidation : Entraînement QCM/DP quotidien et rattrapage des lacunes Rang A."
        else:
            phase = SprintPhase.SPRINT_FLASH
            new_r, rev_r, qcm_r = 0.05, 0.35, 0.60
            daily_items = 8
            msg = "🔥 Mode SPRINT FLASH EDN : 100% Annales UNESS, DP, Flash-Zero & High-Yield Index !"

        return SprintConfig(
            days_remaining=max(0, delta),
            target_date=self.target_date,
            phase=phase,
            recommended_new_ratio=new_r,
            recommended_review_ratio=rev_r,
            recommended_qcm_dp_ratio=qcm_r,
            daily_target_items=daily_items,
            focus_message=msg,
        )
