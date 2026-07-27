"""
knowledge.service — Synapse
---------------------------
Porte d'entrée unique du domaine « état des connaissances ».

mastery.py ne parle qu'à ce module : il ne connaît ni le SQL, ni les tables.

Responsabilités :
  - calculer la graine dégradée d'un item (get_seed_snapshot)
  - compter les preuves réelles et dater la première (count_evidence, first_evidence_date)
  - agréger la couverture OIC et le badge « Rang A ✓ » (oic_coverage, has_rang_a_badge)
  - exposer l'avancement du triage d'un collège (college_triage_progress)
"""
from __future__ import annotations

import datetime

from backend.core.reviews.local_store import _conn
from backend.core.knowledge import store as ks
from backend.core.knowledge.models import (
    SeedSnapshot, RANG_A_BADGE_THRESHOLD, decayed_seed,
)


# ── Preuves réelles ───────────────────────────────────────────────────────────

def first_evidence_date(course_id: str) -> datetime.date | None:
    """
    Date de la première preuve réelle (session, QCM, tentative OIC), ou None.

    C'est la date à laquelle la dégradation de la graine s'arrête : au-delà,
    c'est l'évidence qui pilote le score, plus le temps.
    """
    with _conn() as con:
        row = con.execute(
            """
            SELECT MIN(d) AS first_d FROM (
                SELECT MIN(session_date) AS d FROM study_sessions WHERE course_id = ?
                UNION ALL
                SELECT MIN(session_date) AS d FROM qcm_sessions   WHERE course_id = ?
                UNION ALL
                SELECT MIN(a.attempted_at) AS d
                    FROM oic_attempts a
                    JOIN lisa_oic o ON o.id = a.oic_id
                   WHERE o.course_id = ?
            )
            """,
            (course_id, course_id, course_id),
        ).fetchone()

    raw = row["first_d"] if row else None
    if not raw:
        return None
    # session_date est une date ISO, attempted_at un timestamp ISO : on tronque.
    return datetime.date.fromisoformat(str(raw)[:10])


def count_evidence(course_id: str) -> int:
    """Nombre de preuves réelles : sessions + QCM + tentatives OIC."""
    with _conn() as con:
        row = con.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM study_sessions WHERE course_id = ?)
              + (SELECT COUNT(*) FROM qcm_sessions   WHERE course_id = ?)
              + (SELECT COUNT(*) FROM oic_attempts a
                    JOIN lisa_oic o ON o.id = a.oic_id
                   WHERE o.course_id = ?) AS n
            """,
            (course_id, course_id, course_id),
        ).fetchone()
    return int(row["n"] or 0)


# ── Graine ────────────────────────────────────────────────────────────────────

def get_seed_snapshot(
    course_id: str,
    context: str = "college",
    today: datetime.date | None = None,
) -> SeedSnapshot:
    """
    Ce que mastery.py a besoin de savoir : le niveau déclaré, sa graine dégradée,
    et le nombre de preuves réelles qui vont la diluer.

    Un item non déclaré renvoie un snapshot vide (seed_score = None) : il reste
    « à situer », il n'hérite d'aucun score par défaut.
    """
    today = today or datetime.date.today()
    state = ks.get_item_state(course_id, context)

    if state is None:
        return SeedSnapshot(declared_level=None, seed_score=None, n_evidence=0)

    n = count_evidence(course_id)
    until = first_evidence_date(course_id) or today

    return SeedSnapshot(
        declared_level=state.declared_level,
        seed_score=decayed_seed(state.declared_level, state.declared_at, until),
        n_evidence=n,
    )


# ── Couverture OIC ────────────────────────────────────────────────────────────

def oic_coverage(course_id: str) -> dict:
    """
    Couverture des objectifs de connaissance d'un item.

    Le rang A conditionne le badge ; le rang B est affiché sans jamais rien
    conditionner — l'ériger en condition transformerait un bonus en dette infinie.
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT rang, mastered FROM lisa_oic WHERE course_id = ? AND active = 1", (course_id,)
        ).fetchall()

    def _tally(rang: str) -> tuple[int, int]:
        subset = [r for r in rows if (r["rang"] or "").strip().upper() == rang]
        return len(subset), sum(1 for r in subset if r["mastered"])

    a_total, a_ok = _tally("A")
    b_total, b_ok = _tally("B")

    return {
        "rang_a_total": a_total,
        "rang_a_ok":    a_ok,
        "rang_a_pct":   (a_ok / a_total) if a_total else 0.0,
        "rang_b_total": b_total,
        "rang_b_ok":    b_ok,
        "rang_b_pct":   (b_ok / b_total) if b_total else 0.0,
    }


def badge_from_coverage(cov: dict) -> bool:
    """
    Badge « Rang A ✓ » à partir d'une couverture déjà chargée.

    Existe pour que mastery.py — qui tourne sur plusieurs centaines de cours —
    n'ait pas à requêter la couverture une seconde fois juste pour le badge.
    """
    if cov["rang_a_total"] == 0:
        return False
    return cov["rang_a_pct"] >= RANG_A_BADGE_THRESHOLD


def has_rang_a_badge(course_id: str) -> bool:
    """Badge « Rang A ✓ » : au moins un OIC de rang A, et >= 80 % réussis."""
    return badge_from_coverage(oic_coverage(course_id))


# ── Triage ────────────────────────────────────────────────────────────────────

def is_to_situate(course_id: str, colleges: list[str], context: str = "college") -> bool:
    """
    Un item est « à situer » s'il appartient à un collège validé
    et n'a encore reçu aucun niveau déclaré. État calculé, jamais stocké.
    """
    statuses = ks.get_all_college_statuses()
    in_validated = any(statuses.get(c) == "valide" for c in (colleges or []))
    if not in_validated:
        return False
    return ks.get_item_state(course_id, context) is None


def college_triage_progress(
    college: str,
    course_ids: list[str],
    context: str = "college",
) -> tuple[int, int]:
    """(nombre d'items situés, nombre total d'items) pour un collège."""
    states = ks.get_all_item_states(context)
    situes = sum(1 for cid in course_ids if cid in states)
    return situes, len(course_ids)
