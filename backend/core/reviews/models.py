"""
Modèles virtuels de révision — Synapse
---------------------------------------
Ces objets sont calculés en mémoire à partir de la DB Cours existante.
Ils ne sont JAMAIS persistés dans une base Notion séparée (Règle d'or).
L'historique réel (validations, reports, ignores) est dans SQLite local.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import date

# ── Types ─────────────────────────────────────────────────────────────────────

ReviewType   = Literal["J1", "J3", "J7", "J14", "J30", "bonus", "qcm_error", "manuel", "consolidation", "lacune"]
ReviewStatus = Literal["todo", "done", "postponed", "ignored", "cancelled"]
ReviewContext = Literal["college", "ue"]


# ── Modèle principal ──────────────────────────────────────────────────────────

class ReviewTask(BaseModel):
    """
    Représente une tâche de révision virtuelle calculée à partir d'un Cours,
    enrichie avec l'historique SQLite local.

    Champs clés :
        id                   : Clé unique "{course_id}_{context}_{review_type}_{due_date}"
        context              : 'college' ou 'ue' — détermine quel compteur Notion incrémenter
        theoretical_due_date : Date théorique Notion (date_1ere_lecture + offset)
        due_date             : Date effective (= postponed_to si reporté, sinon = theoretical)
        postponed_count      : Nombre de reports successifs
    """

    id: str
    course_id: str
    course_title: str
    item_number: Optional[str] = None
    college: List[str] = Field(default_factory=list)

    # Contexte : détermine quelle propriété Notion incrémenter à la validation
    context: ReviewContext = "college"

    # PDF : priorité url_pdf (Collège) > url_pdf_ue (Fac)
    url_pdf: Optional[str] = None
    url_pdf_ue: Optional[str] = None
    agregation_fiche_edn: Optional[str] = None

    # Dates
    theoretical_due_date: date          # date originale Notion (non modifiée par report)
    due_date: date                       # date effective (= postponed_to si reporté)

    review_type: ReviewType
    priority_score: float = 0.0
    status: ReviewStatus = "todo"

    nb_lectures: int = 0
    anki: bool = False
    qcm_done: bool = False
    course_status: str = "À lire"
    days_overdue: int = 0
    postponed_count: int = 0

    # Données de qualité (optionnelles, saisies à la validation)
    difficulty: Optional[str] = None    # 'facile' | 'moyen' | 'difficile'
    confidence: Optional[int] = None    # 1..5

    # Score de maîtrise (calculé par mastery.py, injecté par ReviewService)
    mastery_score: Optional[int] = None         # 0..100
    mastery_level: Optional[str] = None         # 'solide'|'correct'|'fragile'|'critique'
    mastery_reasons: List[str] = Field(default_factory=list)

    # Semestre du cours (Notion), utilisé pour pondérer la priorité de consolidation
    semestre: Optional[str] = None

    # Source de la date théorique : 'notion' | 'sm2' | 'fixe'
    date_source: Optional[str] = None

    # ── Propriétés calculées ─────────────────────────────────────────────────

    @property
    def has_pdf(self) -> bool:
        return bool(self.url_pdf or self.url_pdf_ue)

    @property
    def best_pdf_url(self) -> Optional[str]:
        return self.url_pdf or self.url_pdf_ue

    @property
    def display_item(self) -> str:
        return f"ITEM {self.item_number} – " if self.item_number else ""

    @property
    def label(self) -> str:
        return f"{self.display_item}{self.course_title}"

    @property
    def type_color(self) -> str:
        return {
            "J1":       "sky",
            "J3":       "blue",
            "J7":       "indigo",
            "J14":      "violet",
            "J30":      "purple",
            "bonus":    "orange",
            "qcm_error":"red",
            "manuel":   "orange",
        }.get(self.review_type, "slate")

    @property
    def type_badge(self) -> str:
        label = self.review_type
        if self.days_overdue > 0:
            label += f" +{self.days_overdue}j"
        if self.postponed_count > 0:
            label += f" ↻{self.postponed_count}"
        return label

    @property
    def context_badge(self) -> str:
        return "Collège" if self.context == "college" else "UE"
