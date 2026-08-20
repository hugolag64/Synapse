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

def _evidence_scope(course_ids: list[str] | tuple[str, ...] | str) -> tuple[str, ...]:
    """Return the unique fiche ids belonging to the requested item(s).

    ``course_id`` is still the public vocabulary of the legacy store, but a
    single EDN item can have one fiche per college.  Resolving aliases here
    keeps every seed consumer on the same item-level evidence perimeter.
    """
    if isinstance(course_ids, str):
        requested = (course_ids,)
    else:
        requested = tuple(course_ids)

    resolved: list[str] = []
    try:
        from backend.state.store import data_store

        for course_id in requested:
            resolved.extend(str(value) for value in data_store.alias_ids(str(course_id)))
    except Exception:
        resolved.extend(str(value) for value in requested)
    return tuple(dict.fromkeys(value for value in resolved if value.strip()))


def _item_numbers_for_courses(course_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Find EDN numbers for aliases so Anki evidence is item-level too."""
    try:
        from backend.state.store import data_store

        numbers = {
            str(getattr(course, "item_number", "") or "").strip()
            for course in data_store.cours
            if str(getattr(course, "id", "")) in course_ids
        }
        return tuple(sorted(value for value in numbers if value))
    except Exception:
        return ()


def first_evidence_date(course_id: str) -> datetime.date | None:
    """
    Date de la première preuve réelle (session, QCM, tentative OIC), ou None.

    C'est la date à laquelle la dégradation de la graine s'arrête : au-delà,
    c'est l'évidence qui pilote le score, plus le temps.
    """
    scope = _evidence_scope(course_id)
    if not scope:
        return None
    placeholders = ",".join("?" for _ in scope)
    item_numbers = _item_numbers_for_courses(scope)
    with _conn() as con:
        row = con.execute(
            f"""
            SELECT MIN(d) AS first_d FROM (
                SELECT MIN(session_date) AS d FROM study_sessions WHERE course_id IN ({placeholders})
                UNION ALL
                SELECT MIN(session_date) AS d FROM qcm_sessions WHERE course_id IN ({placeholders})
                UNION ALL
                SELECT MIN(a.attempted_at) AS d
                    FROM oic_attempts a
                    JOIN lisa_oic o ON o.id = a.oic_id
                   WHERE o.course_id IN ({placeholders})
                UNION ALL
                SELECT MIN(reviewed_at) AS d FROM anki_review_evidence
                    WHERE item_number IN ({','.join('?' for _ in item_numbers)})
            )
            """,
            (*scope, *scope, *scope, *item_numbers),
        ).fetchone()

    raw = row["first_d"] if row else None
    if not raw:
        return None
    # session_date est une date ISO, attempted_at un timestamp ISO : on tronque.
    return datetime.date.fromisoformat(str(raw)[:10])


def count_evidence_for_courses(course_ids: list[str] | tuple[str, ...]) -> int:
    """Count unique item-level evidence across all requested fiche ids.

    Anki rows are keyed by EDN item number rather than fiche id, so they are
    counted once per item even when several aliases point to that number.
    """
    scope = _evidence_scope(course_ids)
    if not scope:
        return 0
    placeholders = ",".join("?" for _ in scope)
    item_numbers = _item_numbers_for_courses(scope)
    with _conn() as con:
        row = con.execute(
            f"""
            SELECT
                (SELECT COUNT(*) FROM study_sessions WHERE course_id IN ({placeholders}))
              + (SELECT COUNT(*) FROM qcm_sessions WHERE course_id IN ({placeholders}))
              + (SELECT COUNT(*) FROM oic_attempts a
                    JOIN lisa_oic o ON o.id = a.oic_id
                   WHERE o.course_id IN ({placeholders}))
              + (SELECT COUNT(*) FROM anki_review_evidence
                   WHERE item_number IN ({','.join('?' for _ in item_numbers)}) ) AS n
            """,
            (*scope, *scope, *scope, *item_numbers),
        ).fetchone()
    return int(row["n"] or 0)


def count_evidence(course_id: str) -> int:
    """Nombre de preuves réelles au niveau item : sessions + QCM + OIC + Anki."""
    return count_evidence_for_courses((course_id,))


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


def get_seed_snapshot_for_item(
    item_id: str,
    course_ids: list[str] | tuple[str, ...] = (),
    context: str = "college",
    today: datetime.date | None = None,
) -> SeedSnapshot:
    """Return one declared seed and aggregate its evidence across all fiches.

    The legacy table stores declarations against a course id.  During the
    transition to the catalog, an item can therefore have its declaration on
    either the stable catalog id or one of its fiche ids.  The first matching
    state wins deterministically; evidence is always summed across the item.
    """
    today = today or datetime.date.today()
    candidates = tuple(dict.fromkeys([str(item_id), *(str(cid) for cid in course_ids)]))
    state = next((ks.get_item_state(candidate, context) for candidate in candidates if ks.get_item_state(candidate, context)), None)
    if state is None:
        return SeedSnapshot(declared_level=None, seed_score=None, n_evidence=0)

    evidence_count = count_evidence_for_courses(candidates)
    evidence_dates = [first_evidence_date(candidate) for candidate in candidates]
    until = min((value for value in evidence_dates if value is not None), default=today)
    return SeedSnapshot(
        declared_level=state.declared_level,
        seed_score=decayed_seed(state.declared_level, state.declared_at, until),
        n_evidence=evidence_count,
    )


# ── Couverture OIC ────────────────────────────────────────────────────────────

RANG_A_MIN_ATTEMPTS = 3
"""Objectifs de rang A à avoir tentés pour que le socle soit jugeable."""

RANG_A_MIN_RATIO = 1 / 3
"""…ou cette part de la liste, pour ne pas bloquer les items à liste courte."""


def rang_a_verdict(coverage: dict) -> dict:
    """Dit si le socle Rang A est jugeable, et sur quoi le juger.

    L'ancien calcul s'armait dès la première tentative et divisait par le
    nombre TOTAL d'objectifs : ouvrir un objectif sur treize donnait 0 % et
    verrouillait le cours en « fragile » quasi définitivement. Deux corrections :

    - il faut un échantillon représentatif pour conclure — trois objectifs
      tentés, ou un tiers de la liste quand elle est courte ;
    - le verdict porte sur ce qui a été **tenté**, pas sur la liste entière :
      sinon allonger la liste d'objectifs dégrade mécaniquement le résultat.

    `pct` vaut None tant qu'on ne peut pas conclure — « non mesuré » n'est pas
    « raté ».
    """
    total = int(coverage.get("rang_a_total") or 0)
    attempted = int(coverage.get("rang_a_attempted") or 0)
    mastered = int(coverage.get("rang_a_ok") or 0)

    if total <= 0 or attempted <= 0:
        return {"conclusive": False, "pct": None, "attempted": attempted}

    enough = attempted >= RANG_A_MIN_ATTEMPTS or (attempted / total) >= RANG_A_MIN_RATIO
    if not enough:
        return {"conclusive": False, "pct": None, "attempted": attempted}

    return {"conclusive": True, "pct": mastered / attempted, "attempted": attempted}


def oic_coverage(course_id: str | list[str] | tuple[str, ...]) -> dict:
    """
    Couverture des objectifs de connaissance d'un item.

    Le rang A conditionne le badge ; le rang B est affiché sans jamais rien
    conditionner — l'ériger en condition transformerait un bonus en dette infinie.
    """
    course_ids = course_id if isinstance(course_id, (list, tuple)) else (course_id,)
    coverage = oic_coverage_for_courses(tuple(course_ids))
    # Keep the verdict fields explicit at this compatibility boundary:
    # rang_a_conclusive means "measured", while rang_a_pct_attempted remains
    # None when there is no representative attempt (never an implicit zero).
    return {
        **coverage,
        "rang_a_conclusive": coverage["rang_a_conclusive"],
        "rang_a_pct_attempted": coverage["rang_a_pct_attempted"],
    }


def oic_coverage_for_courses(course_ids: list[str] | tuple[str, ...]) -> dict:
    """Aggregate active OIC coverage across every fiche of an item."""
    normalized_ids = tuple(dict.fromkeys(str(value) for value in course_ids if str(value).strip()))
    if not normalized_ids:
        return {
            "rang_a_total": 0, "rang_a_ok": 0, "rang_a_pct": 0.0,
            "rang_a_attempted": 0, "rang_a_conclusive": False,
            "rang_a_pct_attempted": None, "rang_b_total": 0, "rang_b_ok": 0,
            "rang_b_pct": 0.0,
        }
    placeholders = ",".join("?" for _ in normalized_ids)
    with _conn() as con:
        rows = con.execute(
            f"""
            SELECT o.rang, o.mastered, COUNT(a.id) AS attempt_count
            FROM lisa_oic o
            LEFT JOIN oic_attempts a ON a.oic_id = o.id
            WHERE o.course_id IN ({placeholders}) AND o.active = 1
            GROUP BY o.id, o.rang, o.mastered
            """,
            normalized_ids,
        ).fetchall()

    def _tally(rang: str) -> tuple[int, int]:
        subset = [r for r in rows if (r["rang"] or "").strip().upper() == rang]
        return len(subset), sum(1 for r in subset if r["mastered"])

    a_total, a_ok = _tally("A")
    b_total, b_ok = _tally("B")
    a_attempted = sum(
        1
        for row in rows
        if (row["rang"] or "").strip().upper() == "A"
        and int(row["attempt_count"] or 0) > 0
    )

    verdict = rang_a_verdict(
        {"rang_a_total": a_total, "rang_a_ok": a_ok, "rang_a_attempted": a_attempted}
    )
    return {
        "rang_a_total": a_total,
        "rang_a_ok":    a_ok,
        "rang_a_pct":   (a_ok / a_total) if a_total else 0.0,
        "rang_a_attempted": a_attempted,
        "rang_a_conclusive": verdict["conclusive"],
        "rang_a_pct_attempted": verdict["pct"],
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


def declare_college_items(
    course_ids: list[str] | tuple[str, ...],
    level: str = "correct",
    context: str = "college",
) -> int:
    """Déclare `level` pour chaque item qui n'a pas déjà de niveau connu.

    Valider un collège (`set_college_status`) n'écrivait jamais `item_state` :
    aucun de ses items ne devenait éligible au score (`mastery.score` restait
    `None`) ni à la consolidation automatique, qui exige justement un score.
    Mesuré sur la base réelle le 20 août 2026 : 9 collèges validés, 138 items
    reliés, dont 34 réellement sans `item_state` (les 104 autres l'étaient
    déjà via Triage). Un item déjà déclaré n'est jamais écrasé. Retourne le
    nombre d'items déclarés.
    """
    declared = 0
    for course_id in course_ids:
        cid = str(course_id)
        if ks.get_item_state(cid, context) is not None:
            continue
        ks.set_item_state(cid, level, context=context, source="college_valide")
        declared += 1
    return declared


def confirm_college_validation(
    college: str, level: str = "correct", repository=None,
) -> int:
    """Point d'entrée unique pour « ce collège est validé » : statut *et*
    cascade `item_state`, dans la même fonction.

    `declare_college_items()` existait déjà quand ce constat est apparu, mais
    elle demandait à chaque appelant de résoudre lui-même les items du
    collège et de se souvenir de l'appeler après `set_college_status` — un
    contrat facile à oublier. `deploy/reprise_historique_consolidation.py`
    en est la preuve : il appelle `set_college_status` directement, avec sa
    propre logique de déclaration dupliquée en parallèle. N'importe quel
    futur appelant qui ferait de même réintroduirait le même défaut. Cette
    fonction rend l'erreur impossible : valider un collège *sans* passer par
    elle redevient un choix explicite, pas un oubli. Retourne le nombre
    d'items nouvellement déclarés.
    """
    if repository is None:
        from backend.state.catalog_repository import CatalogRepository

        repository = CatalogRepository()

    ks.set_college_status(college, "valide")

    if not repository.is_populated():
        return 0
    # Deux requêtes globales plutôt qu'une par item (N19) : mêmes méthodes
    # que `build_item_rows`.
    colleges_by_item = repository.list_colleges_by_item()
    target_items = {item_id for item_id, names in colleges_by_item.items() if college in names}
    fiche_ids = [
        str(fiche.id) for fiche in repository.list_all_fiches()
        if fiche.item_id in target_items
    ]
    return declare_college_items(fiche_ids, level=level, context="college")


def get_historically_completed_course_ids(
    courses: list,
    context: str = "college",
) -> set[str]:
    """Return courses that may bypass the initial J-cycle after a legacy reprise."""
    if context != "college":
        return set()

    statuses = ks.get_all_college_statuses()
    validated_colleges = {
        college for college, status in statuses.items() if status == "valide"
    }
    states = ks.get_all_item_states(context)
    return {
        course.id
        for course in courses
        if course.id in states
        and validated_colleges.intersection(getattr(course, "college", None) or [])
    }
