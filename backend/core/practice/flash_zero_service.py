"""
flash_zero_service.py — Synapse
--------------------------------
Service backend gérant le "Morning Flash-Zero Quiz" (5 min / 10 questions sur les zéros éliminatoires).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from backend.core.reviews import local_store
from backend.core.edn.error_profile import signals_since


def build_flash_zero_priority(signals, today=None) -> list[str]:
    """Classe les items par répétition puis par récence, sans dépendre de l'IA."""
    grouped: dict[str, list[str]] = {}
    for signal in signals or []:
        item = str(signal.get("item_number") or "").strip().removeprefix("ITEM ")
        if item:
            grouped.setdefault(item, []).append(str(signal.get("occurred_at") or ""))
    return [
        item
        for item, dates in sorted(
            grouped.items(), key=lambda pair: (len(pair[1]), max(pair[1])), reverse=True
        )
    ]


@dataclass(frozen=True)
class FlashZeroQuestion:
    id: str
    item_number: str
    item_title: str
    question_text: str
    choices: tuple[str, ...]
    correct_idx: int
    explanation: str
    is_zero_eliminatoire: bool
    category: str  # ex: "Contre-indication", "Urgence vitale", "Erreur de rang A"


class FlashZeroService:
    """Service d'entraînement rapide sur les zéros éliminatoires EDN."""

    def __init__(self, store=None):
        self.store = store or local_store

    def get_morning_quiz(self, count: int = 10, *, item_number: str | None = None) -> list[FlashZeroQuestion]:
        """
        Génère un quiz de `count` questions (par défaut 10) axé sur :
        1. Les lacunes / erreurs de Rang A récentes dans SQLite.
        2. Une banque de pièges et zéros éliminatoires prédéfinis EDN.
        """
        try:
            critical_history = self.store.get_item_pedagogical_history(limit=50)
        except Exception:
            critical_history = []
        
        # Banque de questions canoniques sur les zéros éliminatoires EDN
        canonical_flash_bank: list[FlashZeroQuestion] = [
            FlashZeroQuestion(
                id="fz-001",
                item_number="ITEM 340",
                item_title="Insuffisance cardiaque",
                question_text="Prescrire des AINS chez un patient en poussée d'insuffisance cardiaque aiguë congestive est :",
                choices=("Une excellente alternative antalgique", "Une contre-indication absolue (Zéro Éliminatoire)", "Indiqué si associé à un diurétique", "Indifférent"),
                correct_idx=1,
                explanation="Les AINS induisent une rétention hydrosodée et une insuffisance rénale aiguë, aggravant mortellement la poussée ICA.",
                is_zero_eliminatoire=True,
                category="Contre-indication",
            ),
            FlashZeroQuestion(
                id="fz-002",
                item_number="ITEM 334",
                item_title="Syndrome coronarien aigu",
                question_text="En cas de SCA ST+ (STEMI) vu à H+1 du début de la douleur dans un centre sans salle de cathétérisme, la conduite immédiate est :",
                choices=("Attendre 24h avant coronarographie", "Fibrinolyse en l'absence de contre-indication", "Donner un bétabloquant IV seul", "Reposer le patient avec des antalgiques simples"),
                correct_idx=1,
                explanation="À H+1 sans PCI accessible < 120 min, la fibrinolyse immédiate est l'indication de Rang A incontournable.",
                is_zero_eliminatoire=True,
                category="Urgence vitale",
            ),
            FlashZeroQuestion(
                id="fz-003",
                item_number="ITEM 221",
                item_title="Méningite infectieuse",
                question_text="Devant une suspicion de méningite à méningocoque avec Purpura Fulminans, la première action médicale prioritaire est :",
                choices=("Faire un scanner cérébral", "Réaliser une ponction lombaire", "Injecter en urgence 2g de Cefotaxime/Ceftriaxone IV ou IM", "Prescrire un bilan sanguin d'hémostase"),
                correct_idx=2,
                explanation="Tout purpura fulminans impose l'injection immédiate d'antibiotique (C3G) AVANT TOUT EXAMEN (y compris avant la PL).",
                is_zero_eliminatoire=True,
                category="Urgence vitale",
            ),
            FlashZeroQuestion(
                id="fz-004",
                item_number="ITEM 135",
                item_title="Anaphylaxie",
                question_text="Le traitement de 1ère ligne absolu d'un choc anaphylactique est :",
                choices=("Les corticoïdes IV", "Les antihistaminiques H1", "L'Adrénaline IM dans la face antéro-latérale de la cuisse", "Le remplissage vasculaire par Macromolécules"),
                correct_idx=2,
                explanation="L'adrénaline IM (0.5 mg chez l'adulte) est le seul traitement salvateur immédiat de l'anaphylaxie aiguë.",
                is_zero_eliminatoire=True,
                category="Urgence vitale",
            ),
            FlashZeroQuestion(
                id="fz-005",
                item_number="ITEM 362",
                item_title="Asthme aigu grave",
                question_text="Chez un patient en crise d'Asthme Aigu Grave avec silence auscultatoire, l'administration de sédatifs pour l'anxiété est :",
                choices=("Recommandée pour calmer l'hyperventilation", "Formellement contre-indiquée (risque d'arrêt cardiorespiratoire)", "Utile si associée à de la Morphine", "Indiquée uniquement en IVD"),
                correct_idx=1,
                explanation="Les sédatifs/anxiolytiques coupent la commande ventilatoire chez l'asthmatique en épuisement : risque de décès rapide.",
                is_zero_eliminatoire=True,
                category="Contre-indication",
            ),
            FlashZeroQuestion(
                id="fz-006",
                item_number="ITEM 344",
                item_title="Fibrillation atriale",
                question_text="La prescription de Flécaïnide chez un patient ayant un antécédent d'infarctus du myocarde est :",
                choices=("La référence absolue", "Contre-indiquée (effet pro-arythmique mortel sur cardiopathie structurale)", "Indiquée à demi-dose", "Sans danger"),
                correct_idx=1,
                explanation="Les anti-arythmiques de classe Ic (Flécaïnide) sont contre-indiqués sur cardiopathie ischémique ou altérée (Essai CAST).",
                is_zero_eliminatoire=True,
                category="Contre-indication",
            ),
            FlashZeroQuestion(
                id="fz-007",
                item_number="ITEM 197",
                item_title="Transfusion sanguine",
                question_text="Avant toute transfusion de culots globulaires rouges, la vérification ultime au lit du malade comprend obligatoirement :",
                choices=("Le contrôle de l'identité et la comparaison Beth-Vincent du patient et de la poche", "Le bilan rénal du patient", "L'auscultation pulmonaire", "La prise de tension 2h après"),
                correct_idx=0,
                explanation="L'épreuve ultime au lit du malade (contrôle d'identité + compatibilité ABO Beth-Vincent) est un geste médico-légal obligatoire.",
                is_zero_eliminatoire=True,
                category="Sécurité / Règle A",
            ),
            FlashZeroQuestion(
                id="fz-008",
                item_number="ITEM 326",
                item_title="Prescription médicamenteuse chez la femme enceinte",
                question_text="La prescription d'un IEC ou ARA2 au 2ème et 3ème trimestre de la grossesse est :",
                choices=("Indiquée pour prévenir la pré-éclampsie", "Formellement contre-indiquée (toxicité fœtale et oligoamnios grave)", "Indifférente", "Recommandée si HTA sévère"),
                correct_idx=1,
                explanation="Les IEC/ARA2 sont fœtotoxiques (insuffisance rénale fœtale, oligoamnios, anurie).",
                is_zero_eliminatoire=True,
                category="Contre-indication",
            ),
            FlashZeroQuestion(
                id="fz-009",
                item_number="ITEM 357",
                item_title="Pneumothorax",
                question_text="Devant un pneumothorax suffocant sous tension avec collapsus cardiovasculaire, la prise en charge immédiate est :",
                choices=("Attendre le cliché de radiographie du thorax F+P", "Exsufflation à l'aiguille au 2e espace intercostal ligne médio-claviculaire", "Poser un drain pleural sous échographie en bloc", "Intubation orotrachéale immédiate sans exsufflation"),
                correct_idx=1,
                explanation="Le PNT sous tension menace le pronostic vital immédiat : l'exsufflation à l'aiguille se fait sans attendre la radio !",
                is_zero_eliminatoire=True,
                category="Urgence vitale",
            ),
            FlashZeroQuestion(
                id="fz-010",
                item_number="ITEM 354",
                item_title="Dépistage du cancer du col de l'utérus",
                question_text="Entre 25 et 30 ans, la modalité de dépistage du cancer du col de l'utérus est :",
                choices=("Test HPV HP16/18 tous les 5 ans", "Examen cytologique tous les 3 ans (après 2 examens annuels normaux)", "Colposcopie systématique", "Echographie pelvienne"),
                correct_idx=1,
                explanation="Rang A EDN : 25-30 ans = Cytologie tous les 3 ans. 30-65 ans = Test HPV tous les 5 ans.",
                is_zero_eliminatoire=False,
                category="Erreur de rang A",
            ),
        ]

        try:
            signals = signals_since(item_number=item_number, days=30, store=self.store)
        except Exception:
            signals = []
        priority = build_flash_zero_priority(signals)
        rank = {item: index for index, item in enumerate(priority)}
        targeted = [q for q in canonical_flash_bank if q.item_number.removeprefix("ITEM ") in rank]
        fallback = [q for q in canonical_flash_bank if q not in targeted]
        targeted.sort(key=lambda q: rank[q.item_number.removeprefix("ITEM ")])
        random.shuffle(fallback)
        return (targeted + fallback)[:count]
