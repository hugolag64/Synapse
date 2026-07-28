"""
mastery.py — Synapse
--------------------
Score de maîtrise et niveau de progression d'un cours.
Calculé à partir des données Notion et de l'historique local SQLite.
"""

from __future__ import annotations
import datetime
import json
from dataclasses import dataclass, field
from typing import Literal

from backend.core.knowledge.retention import Evidence, evaluate_retention


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
    # ── Socle « état des connaissances » ──────────────────────────────────────
    declared_level: str | None = None      # solide | correct | flou
    oic_coverage_a: float = 0.0            # part d'OIC de rang A réussis
    has_rang_a_badge: bool = False
    anki_review_count: int = 0
    anki_knowledge_score: int | None = None


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

    Un cours non préparé (sans PDF) ou non lu a un score = None et ne peut
    jamais être fragile ou critique — sauf s'il porte un niveau déclaré
    (ancien collège validé) : dans ce cas la graine tient lieu de score,
    et son niveau peut être critique/fragile/à consolider.
    """
    sessions = sessions or []

    # ── Socle « état des connaissances » ──────────────────────────────────────
    # Un item déclaré (ancien collège validé) possède une graine de score qui se
    # dégrade avec le temps et se dilue devant les preuves réelles.
    from backend.core.knowledge.service import (
        get_seed_snapshot, oic_coverage, badge_from_coverage,
    )
    from backend.core.knowledge.models import blend, level_from_seed

    seed = get_seed_snapshot(course.id, context)
    # La couverture OIC ne concerne que les items déclarés (anciens collèges) :
    # évite une requête lisa_oic par cours pour les ~99% de cours non déclarés.
    if seed.declared_level is not None:
        _cov = oic_coverage(course.id)      # une seule lecture, réutilisée pour le badge
        _oic_coverage_a   = _cov["rang_a_pct"]
        _has_rang_a_badge = badge_from_coverage(_cov)
    else:
        _oic_coverage_a   = 0.0
        _has_rang_a_badge = False
    _extra = {
        "declared_level":   seed.declared_level,
        "oic_coverage_a":   _oic_coverage_a,
        "has_rang_a_badge": _has_rang_a_badge,
    }

    # 1. Extraction des propriétés du cours selon le contexte
    has_pdf = bool(course.url_pdf if context == "college" else course.url_pdf_ue)
    has_first_read = bool(course.date_1ere_lecture if context == "college" else course.date_1ere_lecture_ue)
    nb_lectures = (course.nb_lectures if context == "college" else course.nb_lectures_ue) or 0
    anki_done = getattr(course, "anki", False)
    qcm_done = getattr(course, "qcm_done", False) or qcm_done_local
    item_number = str(getattr(course, "item_number", "") or "").strip()
    anki_rows = []
    if item_number:
        from backend.core.reviews import local_store
        anki_rows = local_store.get_anki_review_evidence(item_number)
    anki_knowledge_score = _anki_knowledge_score(anki_rows)
    anki_review_count = len(anki_rows)

    # 2. Règles strictes (non commencés)
    # Note: un cours sans PDF peut quand même avoir une première lecture et être révisable
    if not has_pdf and not has_first_read:
        return CourseProgressSnapshot(
            course_id=course.id, context=context, level="à préparer", score=None,
            has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
            qcm_done=qcm_done, anki_done=anki_done, reasons=["Pas de PDF lié"],
            next_action="Lier PDF", **_extra,
        )

    if not has_first_read:
        # Item déclaré sans preuve réelle : la graine tient lieu de score.
        # C'est ce qui rend planifiables les items des anciens collèges validés.
        if seed.seed_score is not None and seed.n_evidence == 0:
            return CourseProgressSnapshot(
                course_id=course.id, context=context,
                level=level_from_seed(seed.seed_score), score=seed.seed_score,
                has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
                qcm_done=qcm_done, anki_done=anki_done,
                reasons=[f"Niveau déclaré : {seed.declared_level}"],
                next_action="Réviser", **_extra,
            )
        if seed.seed_score is None:
            return CourseProgressSnapshot(
                course_id=course.id, context=context, level="à lire", score=None,
                has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
                qcm_done=qcm_done, anki_done=anki_done,
                reasons=["Première lecture manquante"], next_action="1ère lecture",
                **_extra,
            )
        # Item déclaré ET porteur de preuves : on poursuit vers le calcul normal.

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

    # L'absence d'Anki ne pénalise jamais : le paquet peut être déconnecté et
    # son existence ne constitue pas une preuve de maîtrise.
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

    # Fusion graine / évidence : le poids de la graine décroît avec les preuves.
    if seed.seed_score is not None:
        score = blend(seed.seed_score, score, seed.n_evidence)
        reasons.append(f"Niveau déclaré : {seed.declared_level}")

    if anki_knowledge_score is not None:
        score = round(score * 0.75 + anki_knowledge_score * 0.25)
        reasons.append(f"Anki : {anki_review_count} révision(s)")

    retention_evidence = _build_retention_evidence(course, sessions, anki_rows)
    if retention_evidence:
        score = evaluate_retention(score, retention_evidence, datetime.date.today()).score

    # 4. Détermination du niveau
    if score < 40:
        level = "critique"
    elif score < 60:
        level = "fragile"
    elif score >= 80 and qcm_done:
        level = "maîtrisé"
    else:
        # Score entre 60 et 80, ou >= 80 sans QCM
        if not qcm_done:
            level = "en construction" if nb_lectures < 2 else "à consolider"
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
        next_action=next_action,
        anki_review_count=anki_review_count,
        anki_knowledge_score=anki_knowledge_score,
        **_extra,
    )


# ── Utilitaire ────────────────────────────────────────────────────────────────

def _safe_get(row, key: str, default=None):
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _build_retention_evidence(course, sessions: list, anki_rows: list) -> list[Evidence]:
    fallback_date = _fallback_evidence_date(course)
    evidence: list[Evidence] = []

    for session in sessions:
        session_date = _coerce_evidence_date(_safe_get(session, "session_date"), fallback_date)
        primary = _session_primary_evidence(session, session_date)
        if primary is not None:
            evidence.append(primary)

        confidence_quality = _confidence_quality(
            _safe_get(session, "confidence"),
            _safe_get(session, "difficulty"),
        )
        if confidence_quality is not None:
            evidence.append(Evidence(session_date, "confidence", confidence_quality))

    for row in anki_rows:
        quality = _anki_retention_quality(_safe_get(row, "rating"))
        if quality is None:
            continue
        reviewed_at = _coerce_evidence_date(_safe_get(row, "reviewed_at"), fallback_date)
        evidence.append(Evidence(reviewed_at, "anki", quality))

    return evidence


def _session_primary_evidence(session, session_date: datetime.date) -> Evidence | None:
    activities = _activity_types_for_evidence(session)

    for activity in activities:
        if "qcm" in activity:
            return Evidence(session_date, "qcm", _qcm_quality(_safe_get(session, "qcm_result")))
        if "dp" in activity:
            return Evidence(session_date, "dp", _qcm_quality(_safe_get(session, "qcm_result")))
        if "kfp" in activity:
            return Evidence(session_date, "kfp", _qcm_quality(_safe_get(session, "qcm_result")))
        if "oic" in activity:
            return Evidence(session_date, "oic", _oic_quality(_safe_get(session, "perceived_mastery")))

    if _safe_get(session, "confidence") is not None or _safe_get(session, "difficulty"):
        return Evidence(session_date, "manual", 0.5)
    return Evidence(session_date, "lecture", 0.5)


def _activity_types_for_evidence(session) -> list[str]:
    raw = _safe_get(session, "activity_types")
    values: list[object]

    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            values = []
        else:
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = stripped
            if isinstance(decoded, list):
                values = decoded
            elif decoded is None:
                values = []
            else:
                values = [decoded]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    elif raw is None:
        values = []
    else:
        values = [raw]

    if not values:
        session_type = _safe_get(session, "session_type")
        values = [session_type] if session_type else []

    return [str(value).strip().lower() for value in values if str(value).strip()]


def _fallback_evidence_date(course) -> datetime.date:
    fallback = getattr(course, "date_1ere_lecture", None)
    if isinstance(fallback, datetime.datetime):
        return fallback.date()
    if isinstance(fallback, datetime.date):
        return fallback
    return datetime.date.today()


def _coerce_evidence_date(raw_value, fallback: datetime.date) -> datetime.date:
    if isinstance(raw_value, datetime.datetime):
        return raw_value.date()
    if isinstance(raw_value, datetime.date):
        return raw_value

    text = str(raw_value or "").strip()
    if not text:
        return fallback

    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        try:
            return datetime.datetime.fromisoformat(text).date()
        except ValueError:
            return fallback


def _qcm_quality(result) -> float:
    normalized = str(result or "").strip().lower()
    if normalized in {"réussi", "reussi"}:
        return 1.0
    if normalized in {"raté", "rate"}:
        return 0.15
    return 0.5


def _oic_quality(score) -> float:
    try:
        attempted_mastery = float(score)
    except (TypeError, ValueError):
        attempted_mastery = 0.0
    return 1.0 if attempted_mastery >= 70.0 else 0.15


def _confidence_quality(confidence, difficulty) -> float | None:
    try:
        quality = (float(confidence) - 1.0) / 3.0
    except (TypeError, ValueError):
        return None

    quality = max(0.0, min(1.0, quality))
    if str(difficulty or "").strip().lower() == "difficile":
        quality = min(quality, 0.35)
    return quality


def _anki_retention_quality(rating) -> float | None:
    return {
        "again": 0.15,
        "hard": 0.45,
        "good": 0.8,
        "easy": 1.0,
    }.get(str(rating or "").strip().lower())


def _anki_knowledge_score(rows: list) -> int | None:
    if not rows:
        return None
    base = {"again": 20, "hard": 50, "good": 78, "easy": 92}
    now = datetime.datetime.now(datetime.timezone.utc)
    values: list[tuple[float, float]] = []
    for row in rows:
        rating = str(_safe_get(row, "rating", "")).lower()
        if rating not in base:
            continue
        raw_date = _safe_get(row, "reviewed_at")
        try:
            reviewed_at = datetime.datetime.fromisoformat(str(raw_date))
            if reviewed_at.tzinfo is None:
                reviewed_at = reviewed_at.replace(tzinfo=datetime.timezone.utc)
            age_days = max(0.0, (now - reviewed_at).total_seconds() / 86400)
        except (TypeError, ValueError):
            age_days = 365.0
        recency = max(0.25, 1.0 - age_days / 180.0)
        interval = max(0, int(_safe_get(row, "interval", 0) or 0))
        maturity = min(1.5, 1.0 + interval / 30.0)
        weight = recency * maturity
        values.append((base[rating], weight))
    if not values:
        return None
    return round(sum(value * weight for value, weight in values) / sum(weight for _, weight in values))
