"""
mastery.py — Synapse
--------------------
Score de maîtrise et niveau de progression d'un cours.
Calculé à partir des données Notion et de l'historique local SQLite.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


# ── Snapshot ──────────────────────────────────────────────────────────────────

@dataclass
class CourseProgressSnapshot:
    course_id: str
    context: Literal["college", "ue"]
    level: str
    score: int | None
    has_pdf: bool
    has_first_read: bool
    nb_lectures: int
    qcm_done: bool
    anki_done: bool
    reasons: list[str] = field(default_factory=list)
    next_action: str = ""


# ── Couleurs UI par niveau ─────────────────────────────────────────────────────

PROGRESSION_COLORS: dict[str, str] = {
    "à préparer": "gray",
    "à lire": "blue",
    "en construction": "teal",
    "à consolider": "cyan",
    "à entraîner": "indigo",
    "fragile": "orange",
    "critique": "red",
    "maîtrisé": "green",
}


# ── Calcul principal ──────────────────────────────────────────────────────────

def get_course_mastery(
    course,
    context: Literal["college", "ue"] = "college",
    sessions: list | None = None,
    total_postpone: int = 0,
    qcm_done_local: bool = False,
) -> CourseProgressSnapshot:
    """
    Calcule le snapshot de progression d'un cours.
    
    Un cours non préparé (sans PDF) ou non lu a toujours un score = None
    et ne peut jamais être fragile ou critique.
    """
    sessions = sessions or []

    # 1. Extraction des propriétés du cours selon le contexte
    has_pdf = bool(course.url_pdf if context == "college" else course.url_pdf_ue)
    has_first_read = bool(course.date_1ere_lecture if context == "college" else course.date_1ere_lecture_ue)
    nb_lectures = (course.nb_lectures if context == "college" else course.nb_lectures_ue) or 0
    anki_done = getattr(course, "anki", False)
    qcm_done = getattr(course, "qcm_done", False) or qcm_done_local

    # 2. Règles strictes (non commencés)
    # Note: un cours sans PDF peut quand même avoir une première lecture et être révisable
    if not has_pdf and not has_first_read:
        return CourseProgressSnapshot(
            course_id=course.id, context=context, level="à préparer", score=None,
            has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
            qcm_done=qcm_done, anki_done=anki_done, reasons=["Pas de PDF lié"], next_action="Lier PDF"
        )

    if not has_first_read:
        return CourseProgressSnapshot(
            course_id=course.id, context=context, level="à lire", score=None,
            has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
            qcm_done=qcm_done, anki_done=anki_done, reasons=["Première lecture manquante"], next_action="1ère lecture"
        )

    # 3. Calcul du score (cours commencés)
    score = 50
    reasons: list[str] = []

    is_consolidation = nb_lectures >= 3 or qcm_done

    if nb_lectures == 1:
        score -= 5
    elif nb_lectures == 2:
        score += 5
    elif nb_lectures >= 3:
        score += 10

    # L'absence d'Anki/QCM pénalise uniquement si le cours est avancé
    if is_consolidation and not anki_done:
        score -= 3
        reasons.append("Anki non fait")
    
    if nb_lectures >= 2 and not qcm_done:
        score -= 4
        reasons.append("QCM non fait")

    if total_postpone > 0:
        score -= min(total_postpone * 5, 20)
        reasons.append(f"{total_postpone} report(s)")

    if sessions:
        confidences = [s["confidence"] for s in sessions if s["confidence"]]
        difficulties = [s["difficulty"] for s in sessions if s["difficulty"]]
        qcm_results = [_safe_get(s, "qcm_result") for s in sessions]
        qcm_results = [r for r in qcm_results if r]

        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            if avg_conf <= 2:
                score -= 15
                reasons.append("confiance basse")
            elif avg_conf >= 4:
                score += 10

        if "difficile" in difficulties:
            score -= 10
            reasons.append("cours difficile")

        if qcm_results:
            if "raté" in qcm_results:
                score -= 15
                reasons.append("QCM raté")
            elif all(r == "réussi" for r in qcm_results):
                score += 10

    score = max(0, min(100, score))

    # 4. Détermination du niveau
    if score < 40:
        level = "critique"
    elif score < 60:
        level = "fragile"
    elif score >= 80 and qcm_done:
        level = "maîtrisé"
    else:
        # Score entre 60 et 80, ou >= 80 sans QCM
        if not qcm_done and not anki_done:
            level = "en construction" if nb_lectures < 2 else "à consolider"
        elif not qcm_done and anki_done:
            level = "à entraîner"
        else:
            level = "à consolider" if score < 70 else "maîtrisé"

    # Action suggérée
    next_action = "Réviser"
    if level == "en construction":
        next_action = "Ficher/Résumer"
    elif level == "à consolider":
        next_action = "Faire Anki"
    elif level == "à entraîner":
        next_action = "Faire des QCM"

    return CourseProgressSnapshot(
        course_id=course.id,
        context=context,
        level=level,
        score=score,
        has_pdf=has_pdf,
        has_first_read=has_first_read,
        nb_lectures=nb_lectures,
        qcm_done=qcm_done,
        anki_done=anki_done,
        reasons=reasons[:3],
        next_action=next_action
    )


# ── Utilitaire ────────────────────────────────────────────────────────────────

def _safe_get(row, key: str, default=None):
    try:
        return row[key]
    except (KeyError, IndexError):
        return default
