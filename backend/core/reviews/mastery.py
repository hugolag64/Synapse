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
from backend.core.reviews import local_store


# ── Snapshot ──────────────────────────────────────────────────────────────────

@dataclass
class CourseProgressSnapshot:
    course_id: str
    context: Literal["college", "ue"]
    level: str
    mastery_score: int | None
    retention_score: int | None
    has_pdf: bool
    has_first_read: bool
    nb_lectures: int
    qcm_done: bool
    anki_done: bool
    reasons: list[str] = field(default_factory=list)
    next_action: str = ""
    # ── Socle « état des connaissances » ──────────────────────────────────────
    declared_level: str | None = None      # solide | correct | flou
    evidence_count: int = 0                # preuves réelles (0 = score purement déclaré)
    oic_coverage_a: float = 0.0            # part d'OIC de rang A réussis
    has_rang_a_badge: bool = False
    score_rang_a: int | None = None        # Score de maîtrise Rang A (0-100)
    score_rang_b: int | None = None        # Score de maîtrise Rang B (0-100)
    rang_a_referential: bool = False
    rang_a_evaluated: bool = False
    anki_review_count: int = 0
    anki_knowledge_score: int | None = None
    retention_stability_days: float = 0.0
    retention_last_evidence: datetime.date | None = None

    @property
    def score(self) -> int | None:
        """Backward-compatible alias for the competency/mastery score."""
        return self.mastery_score


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

def _item_fiche_ids(course) -> tuple[str, ...]:
    """Fiches Notion décrivant le même item EDN que ce cours.

    Un item est souvent saisi une fois par collège : 162 items sur 365 ont de 2
    à 4 fiches, et toutes portent une part des preuves. Lire une seule fiche
    revient à diviser la maîtrise par le nombre de fiches.
    """
    try:
        from backend.state.store import data_store

        return data_store.alias_ids(course.id)
    except Exception:
        return (str(course.id),)


def _normalized_item_number(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return ""


def _courses_for_item(item_id) -> list:
    """Resolve a fiche id or item number to every active fiche."""
    from backend.state.store import data_store

    value = str(item_id).strip()
    numeric = _normalized_item_number(value)
    courses = list(data_store.cours)
    if numeric:
        return [
            course for course in courses
            if _normalized_item_number(getattr(course, "item_number", "")) == numeric
        ]
    selected = next((course for course in courses if str(course.id) == value), None)
    if selected is None:
        return []
    selected_number = _normalized_item_number(getattr(selected, "item_number", ""))
    return [
        course for course in courses
        if _normalized_item_number(getattr(course, "item_number", "")) == selected_number
    ]


def get_item_fiche_ids(item_id: str | int) -> tuple[str, ...]:
    """Return every active fiche id belonging to an item."""
    return tuple(str(course.id) for course in _courses_for_item(item_id))


def get_item_sessions(item_id: str | int) -> list:
    """Return study sessions aggregated across every fiche of an item."""
    sessions_map = local_store.get_sessions_by_course()
    sessions = [
        session
        for fiche_id in get_item_fiche_ids(item_id)
        for session in sessions_map.get(fiche_id, [])
    ]
    return sorted(
        sessions,
        key=lambda row: str(_safe_get(row, "session_date", "") or ""),
        reverse=True,
    )


def get_item_qcm_sessions(item_id: str | int) -> list:
    """Return QCM sessions aggregated across every fiche of an item."""
    rows = [
        row
        for fiche_id in get_item_fiche_ids(item_id)
        for row in local_store.get_qcm_sessions_by_course(fiche_id)
    ]
    return sorted(
        rows,
        key=lambda row: str(_safe_get(row, "session_date", "") or ""),
        reverse=True,
    )


def get_item_qcm_summary(item_id: str | int) -> dict:
    """Return the QCM summary using sessions from every fiche of an item."""
    rows = [
        row for row in get_item_qcm_sessions(item_id)
        if _safe_get(row, "score_percent") is not None
    ]
    if not rows:
        return {
            "count": 0, "avg_score": None, "last_score": None,
            "last_date": None, "passed": 0, "failed": 0,
        }
    scores = [float(_safe_get(row, "score_percent")) for row in rows]
    passed = sum(1 for score in scores if score >= local_store.QCM_PASS_THRESHOLD)
    return {
        "count": len(scores),
        "avg_score": round(sum(scores) / len(scores), 1),
        "last_score": scores[0],
        "last_date": _safe_get(rows[0], "session_date"),
        "passed": passed,
        "failed": len(scores) - passed,
    }


def get_item_weak_points(item_id: str | int) -> list:
    """Return active weak points from every fiche of an item."""
    return [
        row
        for fiche_id in get_item_fiche_ids(item_id)
        for row in local_store.get_weak_points_for_course(fiche_id)
    ]


def get_item_review_history(item_id: str | int) -> list:
    """Return review history aggregated across every fiche of an item."""
    rows = [
        row
        for fiche_id in get_item_fiche_ids(item_id)
        for row in local_store.get_review_history_by_course(fiche_id)
    ]
    return sorted(
        rows,
        key=lambda row: str(
            _safe_get(row, "effective_due_date", "")
            or _safe_get(row, "completed_at", "")
            or ""
        ),
        reverse=True,
    )


def get_item_manual_reviews(item_id: str | int) -> list:
    """Return completed manual reviews from every fiche of an item."""
    return [
        row
        for row in get_item_review_history(item_id)
        if _safe_get(row, "review_type") == "manuel"
        and _safe_get(row, "status") == "done"
    ]


def _merged_item_course(courses: list):
    from backend.core.knowledge.course_aliases import canonical_course, colleges_of_item

    canonical = canonical_course(courses)
    updates = {
        "college": colleges_of_item(courses),
        "url_pdf": next((c.url_pdf for c in courses if c.url_pdf), None),
        "url_pdf_ue": next((c.url_pdf_ue for c in courses if c.url_pdf_ue), None),
        "date_1ere_lecture": next((c.date_1ere_lecture for c in courses if c.date_1ere_lecture), None),
        "date_1ere_lecture_ue": next((c.date_1ere_lecture_ue for c in courses if c.date_1ere_lecture_ue), None),
        "nb_lectures": max((getattr(c, "nb_lectures", 0) or 0) for c in courses),
        "nb_lectures_ue": max((getattr(c, "nb_lectures_ue", 0) or 0) for c in courses),
        "qcm_done": any(getattr(c, "qcm_done", False) for c in courses),
        "anki": any(getattr(c, "anki", False) for c in courses),
    }
    return canonical.model_copy(update=updates) if hasattr(canonical, "model_copy") else canonical.copy(update=updates)


@dataclass(frozen=True)
class EvidenceSummary:
    """Counts of real evidence aggregated at item level."""

    sessions: int = 0
    qcm: int = 0
    oic_attempts: int = 0
    anki_reviews: int = 0
    annales: int = 0

    @property
    def total(self) -> int:
        return self.sessions + self.qcm + self.oic_attempts + self.anki_reviews + self.annales

    @property
    def evidence_count(self) -> int:
        return self.total


def get_item_evidence(item_id: str | int) -> EvidenceSummary:
    """Aggregate all locally recorded evidence across an item's fiches."""
    fiche_ids = get_item_fiche_ids(item_id)
    if not fiche_ids:
        return EvidenceSummary()
    sessions = local_store.get_sessions_by_course()
    session_count = sum(len(sessions.get(fiche_id, [])) for fiche_id in fiche_ids)
    qcm_count = sum(len(local_store.get_qcm_sessions_by_course(fiche_id) or []) for fiche_id in fiche_ids)
    with local_store._conn() as connection:
        placeholders = ",".join("?" for _ in fiche_ids)
        row = connection.execute(
            f"""SELECT COUNT(a.id) FROM oic_attempts a
                JOIN lisa_oic o ON o.id = a.oic_id
                WHERE o.course_id IN ({placeholders})""",
            fiche_ids,
        ).fetchone()
    item_number = _normalized_item_number(getattr(_courses_for_item(item_id)[0], "item_number", ""))
    anki_rows = local_store.get_anki_review_evidence(item_number) if item_number else []
    annales = local_store.get_ai_practice_sessions(item_number=item_number, limit=1000) if item_number else []
    return EvidenceSummary(session_count, qcm_count, int(row[0] or 0), len(anki_rows), len(annales))


def get_item_mastery(
    item_id: str | int,
    context: Literal["college", "ue"] = "college",
) -> CourseProgressSnapshot:
    """Calculate one coherent mastery snapshot for every fiche of an item."""
    courses = _courses_for_item(item_id)
    if not courses:
        raise LookupError(f"Item introuvable : {item_id}")
    course = _merged_item_course(courses)
    fiche_ids = tuple(str(c.id) for c in courses)
    sessions = get_item_sessions(item_id)
    qcm_done = any(local_store.get_qcm_sessions_by_course(fiche_id) for fiche_id in fiche_ids)
    return get_course_mastery(
        course,
        context=context,
        sessions=sessions,
        qcm_done_local=qcm_done,
        knowledge_id=str(course.id),
    )


def _qcm_rows_for_item(course) -> list:
    """Sessions QCM de toutes les fiches de l'item, pas de la seule fiche ouverte."""
    from backend.core.reviews import local_store

    rows: list = []
    for course_id in _item_fiche_ids(course):
        rows.extend(local_store.get_qcm_sessions_by_course(course_id) or [])
    return rows


def _oic_rows_for_item(course) -> list:
    """Objectifs OIC de toutes les fiches de l'item, dédoublonnés par identifiant."""
    from backend.core.reviews import local_store

    rows: list = []
    seen: set = set()
    for course_id in _item_fiche_ids(course):
        for row in local_store.get_lisa_oic(course_id) or []:
            identifier = _safe_get(row, "id")
            if identifier in seen:
                continue
            seen.add(identifier)
            rows.append(row)
    return rows


def get_course_mastery(
    course,
    context: Literal["college", "ue"] = "college",
    sessions: list | None = None,
    total_postpone: int = 0,
    qcm_done_local: bool = False,
    knowledge_id: str | None = None,
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
        get_seed_snapshot_for_item, oic_coverage_for_courses, badge_from_coverage,
    )
    from backend.core.knowledge.models import blend, level_from_seed

    fiche_ids = _item_fiche_ids(course)
    seed = get_seed_snapshot_for_item(
        knowledge_id or course.id,
        (course.id, *fiche_ids),
        context,
    )
    # Couverture OIC calculée pour tout cours (plus seulement les items déclarés) :
    # sinon un cours réellement évalué sur ses OIC de Rang A voyait sa couverture
    # ignorée faute de "niveau déclaré" (ancien système collèges), et le verrou
    # Rang A ci-dessous appliquait une pénalité à l'aveugle.
    _cov = oic_coverage_for_courses((course.id, *fiche_ids))
    _oic_coverage_a      = _cov["rang_a_pct"]
    _has_rang_a_referential = _cov["rang_a_total"] > 0
    _has_rang_a_evaluated = _cov.get("rang_a_attempted", 0) > 0
    _rang_a_conclusive = bool(_cov.get("rang_a_conclusive"))
    _oic_coverage_a_attempted = _cov.get("rang_a_pct_attempted")
    _has_rang_a_badge    = badge_from_coverage(_cov)
    _extra = {
        "declared_level":   seed.declared_level,
        # Nombre de preuves réelles derrière le score. Sans lui, un score issu
        # d'une auto-déclaration qui s'efface avec le temps est visuellement
        # indiscernable d'un score mesuré : 96 % des cours affichés « fragile »
        # ou « critique » viennent de cette graine, pas d'un échec constaté.
        "evidence_count":   int(seed.n_evidence or 0),
        "oic_coverage_a":   _oic_coverage_a,
        "has_rang_a_badge": _has_rang_a_badge,
        "rang_a_referential": _has_rang_a_referential,
        "rang_a_evaluated": _has_rang_a_evaluated,
    }
    _retention_defaults = {
        "retention_stability_days": 0.0,
        "retention_last_evidence": None,
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
        get_anki_evidence = getattr(local_store, "get_anki_review_evidence", None)
        if callable(get_anki_evidence):
            anki_rows = get_anki_evidence(item_number)
    anki_knowledge_score = _anki_knowledge_score(anki_rows)
    anki_review_count = len(anki_rows)

    # 2. Règles strictes (non commencés)
    # Note: un cours sans PDF peut quand même avoir une première lecture et être révisable
    if seed.seed_score is not None and seed.n_evidence == 0:
        return CourseProgressSnapshot(
            course_id=course.id, context=context,
            level=level_from_seed(seed.seed_score), mastery_score=seed.seed_score, retention_score=seed.seed_score,
            has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
            qcm_done=qcm_done, anki_done=anki_done,
            reasons=[f"Niveau déclaré : {seed.declared_level}"],
            next_action="Réviser", **_extra, **_retention_defaults,
        )

    if not has_pdf and not has_first_read:
        return CourseProgressSnapshot(
            course_id=course.id, context=context, level="à préparer", mastery_score=None, retention_score=None,
            has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
            qcm_done=qcm_done, anki_done=anki_done, reasons=["Pas de PDF lié"],
            next_action="Lier PDF", **_extra, **_retention_defaults,
        )

    if not has_first_read:
        # Item déclaré sans preuve réelle : la graine tient lieu de score.
        # C'est ce qui rend planifiables les items des anciens collèges validés.
        if seed.seed_score is None:
            return CourseProgressSnapshot(
                course_id=course.id, context=context, level="à lire", mastery_score=None, retention_score=None,
                has_pdf=has_pdf, has_first_read=has_first_read, nb_lectures=nb_lectures,
                qcm_done=qcm_done, anki_done=anki_done,
                reasons=["Première lecture manquante"], next_action="1ère lecture",
                **_extra, **_retention_defaults,
            )
        # Item déclaré ET porteur de preuves : on poursuit vers le calcul normal.

    # 3. Calcul du score (cours commencés)
    mastery_score = 50
    reasons: list[str] = []
    recent_low_qcm = False

    is_consolidation = nb_lectures >= 3 or qcm_done

    if nb_lectures == 1:
        mastery_score -= 5
    elif nb_lectures == 2:
        mastery_score += 5
    elif nb_lectures >= 3:
        mastery_score += 10

    # L'absence d'Anki ne pénalise jamais : le paquet peut être déconnecté et
    # son existence ne constitue pas une preuve de maîtrise.
    if nb_lectures >= 2 and not qcm_done:
        mastery_score -= 4
        reasons.append("QCM non fait")

    if total_postpone > 0:
        mastery_score -= min(total_postpone * 5, 20)
        reasons.append(f"{total_postpone} report(s)")

    if sessions:
        confidences = [s["confidence"] for s in sessions if s["confidence"]]
        difficulties = [s["difficulty"] for s in sessions if s["difficulty"]]
        qcm_results = [_safe_get(s, "qcm_result") for s in sessions]
        qcm_results = [r for r in qcm_results if r]

        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            if avg_conf <= 2:
                mastery_score -= 15
                reasons.append("confiance basse")
            elif avg_conf >= 4:
                mastery_score += 10

        if "difficile" in difficulties:
            mastery_score -= 10
            reasons.append("cours difficile")

        if qcm_results:
            if "raté" in qcm_results:
                mastery_score -= 15
                reasons.append("QCM raté")
            elif all(r == "réussi" for r in qcm_results):
                mastery_score += 10

    # Une performance fraîche est un signal diagnostique, pas une simple
    # exposition : un échec robuste doit immédiatement remonter dans le plan.
    try:
        from backend.core.reviews import local_store
        today = datetime.date.today()
        recent_rows = _qcm_rows_for_item(course)
        for row in recent_rows:
            try:
                when = _coerce_evidence_date(_safe_get(row, "session_date"), today)
                percent = float(_safe_get(row, "score_percent"))
                total = int(_safe_get(row, "total_questions") or 0)
            except (TypeError, ValueError):
                continue
            if 0 <= (today - when).days <= 14 and total >= 10 and percent < 50:
                mastery_score -= 15
                reasons.append(f"QCM récent faible ({int(percent)}% sur {total} questions)")
                recent_low_qcm = True
                break
    except Exception:
        pass

    # Prise en compte prioritaire des sessions d'annales UNESS officielles
    if item_number:
        try:
            from backend.core.reviews import local_store
            annale_sess = local_store.get_ai_practice_sessions(item_number=item_number, limit=5)
            scores_annales = [float(s["score_percent"]) for s in (annale_sess or []) if s.get("annale_id") and s.get("score_percent") is not None]
            if scores_annales:
                avg_annale = sum(scores_annales) / len(scores_annales)
                if avg_annale >= 80:
                    mastery_score += 15
                    reasons.append(f"Annales : {int(avg_annale)}% (Solide)")
                elif avg_annale < 50:
                    mastery_score -= 15
                    reasons.append(f"Annales : {int(avg_annale)}% (Fragile)")
        except Exception:
            pass

    mastery_score = max(0, min(100, mastery_score))

    # Fusion graine / évidence : le poids de la graine décroît avec les preuves.
    if seed.seed_score is not None:
        mastery_score = blend(seed.seed_score, mastery_score, seed.n_evidence)
        reasons.append(f"Niveau déclaré : {seed.declared_level}")

    if anki_knowledge_score is not None:
        mastery_score = round(mastery_score * 0.75 + anki_knowledge_score * 0.25)
        reasons.append(f"Anki : {anki_review_count} révision(s)")

    retention_evidence = _build_retention_evidence(course, context, sessions, anki_rows)
    retention_snapshot = evaluate_retention(mastery_score, retention_evidence, datetime.date.today())
    retention_score = retention_snapshot.score

    # 3b. Calcul dédoublé Rang A / Rang B
    # Le verrou Rang A (utilisé plus bas pour fragile/critique) ne doit s'appliquer
    # que si le cours a réellement été évalué sur ses OIC de Rang A — sinon
    # l'absence de mesure serait traitée comme un échec (score_rang_a < 75).
    # Le verrou ne juge que sur un échantillon représentatif, et sur les
    # objectifs réellement tentés : ouvrir le premier objectif d'une liste de
    # treize ne doit pas valoir 0 % de couverture.
    if _rang_a_conclusive and _oic_coverage_a_attempted is not None:
        score_rang_a = max(
            0, min(100, round(mastery_score * 0.5 + (_oic_coverage_a_attempted * 100) * 0.5))
        )
    else:
        score_rang_a = mastery_score
    
    # Pénalité Rang A en cas d'échec QCM/Session
    if sessions:
        for s in sessions:
            if isinstance(s, dict) and (s.get("qcm_result") == "raté" or s.get("error_category") == "rang_a"):
                score_rang_a = max(0, score_rang_a - 15)
                break

    if score_rang_a < 70:
        score_rang_b = max(0, score_rang_a - 20)
    else:
        score_rang_b = max(0, min(100, round(mastery_score * 0.9)))

    # 4. Détermination du niveau (avec Sécurité Rang A stricte)
    if mastery_score < 40 or (
        _has_rang_a_evaluated and score_rang_a is not None and score_rang_a < 40
    ):
        level = "critique"
        if _rang_a_conclusive and score_rang_a is not None and score_rang_a < 40:
            reasons.append("Socle Rang A critique (<40%)")
    elif mastery_score < 60 or (
        _rang_a_conclusive and score_rang_a is not None and score_rang_a < 75
    ):
        level = "fragile"
        if _rang_a_conclusive and score_rang_a is not None and score_rang_a < 75:
            reasons.append("Sécurité Rang A non atteinte (<75%)")
    elif mastery_score >= 80 and qcm_done:
        level = "maîtrisé"
    else:
        # Score entre 60 et 80, ou >= 80 sans QCM
        if not qcm_done:
            level = "en construction" if nb_lectures < 2 else "à consolider"
        else:
            level = "à consolider" if mastery_score < 70 else "maîtrisé"

    # Action suggérée
    next_action = "Réviser"
    if recent_low_qcm:
        next_action = "Corriger les erreurs"
    elif level == "en construction":
        next_action = "Ficher/Résumer"
    elif level == "à consolider":
        next_action = "Faire Anki"
    return CourseProgressSnapshot(
        course_id=course.id,
        context=context,
        level=level,
        mastery_score=mastery_score,
        retention_score=retention_score,
        score_rang_a=score_rang_a,
        score_rang_b=score_rang_b,
        has_pdf=has_pdf,
        has_first_read=has_first_read,
        nb_lectures=nb_lectures,
        qcm_done=qcm_done,
        anki_done=anki_done,
        reasons=reasons[:3],
        next_action=next_action,
        anki_review_count=anki_review_count,
        anki_knowledge_score=anki_knowledge_score,
        retention_stability_days=retention_snapshot.stability_days,
        retention_last_evidence=retention_snapshot.last_evidence,
        **_extra,
    )


# ── Utilitaire ────────────────────────────────────────────────────────────────

def _safe_get(row, key: str, default=None):
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _build_retention_evidence(
    course,
    context: str | list = "college",
    sessions: list | None = None,
    anki_rows: list | None = None,
) -> list[Evidence]:
    # Compatibilité avec les tests/consommateurs historiques :
    # _build_retention_evidence(course, sessions, anki_rows).
    if not isinstance(context, str):
        context, sessions, anki_rows = "college", context, sessions
    sessions = sessions or []
    anki_rows = anki_rows or []
    fallback_date = _fallback_evidence_date(course, context)
    evidence: list[Evidence] = []
    study_evidence_keys: set[tuple[str, datetime.date]] = set()
    confidence_by_day: dict[datetime.date, float] = {}

    for session in sessions:
        session_date = _coerce_evidence_date(_safe_get(session, "session_date"), fallback_date)
        primary = _session_primary_evidence(session, session_date)
        if primary is not None:
            evidence.append(primary)
            study_evidence_keys.add((primary.source, primary.date))

        confidence_quality = _confidence_quality(
            _safe_get(session, "confidence"),
            _safe_get(session, "difficulty"),
        )
        if confidence_quality is not None:
            confidence_by_day[session_date] = min(
                confidence_by_day.get(session_date, confidence_quality),
                confidence_quality,
            )

    evidence.extend(
        Evidence(day, "confidence", quality)
        for day, quality in sorted(confidence_by_day.items())
    )

    for row in anki_rows:
        quality = _anki_retention_quality(_safe_get(row, "rating"))
        if quality is None:
            continue
        reviewed_at = _coerce_evidence_date(_safe_get(row, "reviewed_at"), fallback_date)
        evidence.append(Evidence(reviewed_at, "anki", quality))

    evidence.extend(_canonical_retention_evidence(course, fallback_date, study_evidence_keys))

    first_read = getattr(course, "date_1ere_lecture" if context == "college" else "date_1ere_lecture_ue", None)
    if not sessions and first_read:
        evidence.append(Evidence(fallback_date, "lecture", 0.5))

    return evidence


def _canonical_retention_evidence(
    course,
    fallback_date: datetime.date,
    study_evidence_keys: set[tuple[str, datetime.date]],
) -> list[Evidence]:
    from backend.core.reviews import local_store

    evidence: list[Evidence] = []
    qcm_by_day: dict[tuple[str, datetime.date], float] = {}
    for row in _qcm_rows_for_item(course):
        source = _qcm_source(_safe_get(row, "session_type"))
        if source is None:
            continue
        session_date = _coerce_evidence_date(_safe_get(row, "session_date"), fallback_date)
        if (source, session_date) not in study_evidence_keys:
            quality = _qcm_score_quality(_safe_get(row, "score_percent"), _safe_get(row, "score_raw"))
            # Plusieurs rejouages le même jour sont une seule exposition : on
            # conserve la qualité la plus prudente au lieu de gonfler la stabilité.
            key = (source, session_date)
            qcm_by_day[key] = min(qcm_by_day.get(key, quality), quality)

    evidence.extend(Evidence(day, source, quality) for (source, day), quality in qcm_by_day.items())

    for oic_row in _oic_rows_for_item(course):
        for attempt in local_store.get_oic_attempts(_safe_get(oic_row, "id")):
            attempted_at = _coerce_evidence_date(_safe_get(attempt, "attempted_at"), fallback_date)
            if ("oic", attempted_at) not in study_evidence_keys:
                evidence.append(Evidence(
                    attempted_at,
                    "oic",
                    _oic_quality(_safe_get(attempt, "session_score")),
                ))

    # Annales UNESS officielles réalisées
    item_num = str(getattr(course, "item_number", "") or "").strip()
    if item_num:
        try:
            annale_sessions = local_store.get_ai_practice_sessions(item_number=item_num, limit=20)
            for s_row in (annale_sessions or []):
                if s_row.get("annale_id") and s_row.get("score_percent") is not None and s_row.get("completed_at"):
                    s_date = _coerce_evidence_date(s_row["completed_at"], fallback_date)
                    if ("annale", s_date) not in study_evidence_keys:
                        pct = float(s_row["score_percent"])
                        quality = max(0.0, min(1.0, pct / 100.0))
                        evidence.append(Evidence(s_date, "annale", quality))
        except Exception:
            pass

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


def _fallback_evidence_date(course, context: str = "college") -> datetime.date:
    fallback = getattr(course, "date_1ere_lecture" if context == "college" else "date_1ere_lecture_ue", None)
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


def _qcm_source(session_type) -> str | None:
    return {
        "qcm": "qcm",
        "dp": "dp",
        "kfp": "kfp",
    }.get(str(session_type or "").strip().lower())


def _qcm_score_quality(score_percent, score_raw) -> float:
    try:
        percent = float(score_percent)
        if 0.0 <= percent <= 100.0:
            return percent / 100.0
    except (TypeError, ValueError):
        pass

    from backend.core.qcm.service import parse_score

    parsed, _ = parse_score(str(score_raw or ""))
    if parsed is None:
        return 0.5
    return parsed / 100.0


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
