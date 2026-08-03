"""
gap_dp_generator.py — Synapse
-----------------------------
Générateur IA de Dossiers Progressifs (DP) axés spécifiquement sur les lacunes actives enregistrées dans SQLite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.core.ai.gemini_client import GeminiClient
from backend.core.ai.routing import AITask
from backend.core.ai.service import AIService
from backend.core.practice.models import PracticeDifficulty, PracticeKind, PracticeSessionSpec
from backend.core.practice.service import PracticeService


class GapDPGeneratorService:
    """Service de génération de DP ciblés sur les lacunes cognitives/pédagogiques."""

    def __init__(self, practice_service: PracticeService | None = None):
        self.practice_service = practice_service or PracticeService()

    def generate_dp_from_gaps(
        self,
        item_number: str,
        item_title: str,
        gaps_descriptions: list[str],
        total_questions: int = 5,
        difficulty: PracticeDifficulty = PracticeDifficulty.EDN,
    ) -> dict[str, Any]:
        """
        Génère un Dossier Progressif IA personnalisé en injectant explicitement les lacunes de l'étudiant
        dans le prompt d'ingénierie clinique.
        """
        gaps_formatted = "\n".join(f"- {g}" for g in gaps_descriptions) if gaps_descriptions else "- Lacunes générales sur le diagnostic et la prise en charge de Rang A"
        
        context_prompt = f"""
DOSSIER PROGRESSIF SUR MES LACUNES ACTIVES — ITEM {item_number} ({item_title})

L'étudiant présente des lacunes documentées et des erreurs passées sur cet item :
{gaps_formatted}

CONSIGNE CLÉ :
Construis un cas clinique vivant et progressif de {total_questions} questions où le scénario confronte directement l'étudiant à ces pièges et lacunes !
Chaque question doit tester la résolution de ces erreurs de Rang A / Rang B spécifiques.
        """.strip()

        spec = PracticeSessionSpec(
            practice_kind=PracticeKind.DP,
            total_questions=total_questions,
            open_questions=0,
            closed_questions=total_questions,
            item_number=item_number,
            course_title=item_title,
            difficulty=difficulty,
        )

        questions = self.practice_service.generate_questions(spec, context=context_prompt)
        
        return {
            "item_number": item_number,
            "item_title": item_title,
            "spec": spec,
            "questions": questions,
            "targeted_gaps": gaps_descriptions,
        }
