"""
ai_qcm/lacunes.py — Synapse
----------------------------
Construction et création de lacunes depuis un résultat d'import QCM.

Règles de filtrage :
  - severity >= 3, OU
  - récurrence détectée par fuzzy matching (token_sort_ratio >= 80) sur les
    lacunes existantes du même cours → severity bumped de +1

Les lacunes ne sont JAMAIS créées automatiquement.
Cette fonction construit des candidats ; c'est l'UI qui demande confirmation.
"""
from __future__ import annotations

import unicodedata
import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from backend.core.reviews import local_store


LACUNE_MIN_SEVERITY       = 3
RECURRENCE_FUZZY_THRESHOLD = 80   # token_sort_ratio (0-100)
RECURRENCE_SEVERITY_BUMP  = 1


@dataclass
class LacuneCandidate:
    detail: str
    category: Optional[str]
    severity: int              # après éventuel bump récurrence
    severity_original: int     # tel que dans le fichier source
    course_id: str
    course_title: str
    item_number: str
    session_id: int
    is_recurrence: bool
    existing_wp_id: Optional[int]  # id de la lacune existante si récurrence


def _normalize(text: str) -> str:
    s = unicodedata.normalize("NFD", text.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]", " ", s)
    return " ".join(s.split())


def _check_recurrence(course_id: str, detail: str) -> tuple[bool, Optional[int]]:
    """Retourne (is_recurrence, existing_wp_id) via fuzzy match sur les lacunes existantes."""
    if not course_id:
        return False, None
    try:
        from fuzzywuzzy import fuzz
    except ImportError:
        return False, None

    existing = local_store.get_weak_points_for_course(course_id)
    if not existing:
        return False, None

    needle = detail[:150]
    for wp in existing:
        haystack = (wp["detail"] or "")[:150]
        score = fuzz.token_sort_ratio(needle, haystack)
        if score >= RECURRENCE_FUZZY_THRESHOLD:
            return True, wp["id"]

    return False, None


def build_lacune_candidates(raw_sessions: list[dict]) -> list[LacuneCandidate]:
    """
    Construit la liste de LacuneCandidate depuis les sessions brutes retournées
    par import_file() dans result["raw_sessions"].

    Filtre : severity >= LACUNE_MIN_SEVERITY OU récurrence fuzzy confirmée.
    """
    candidates: list[LacuneCandidate] = []

    for session_data in raw_sessions:
        course_id    = session_data.get("course_id", "")
        course_title = session_data.get("course_title", "")
        item_number  = session_data.get("item_number", "")
        session_id   = session_data.get("session_id", 0)
        weak_points  = session_data.get("weak_points", [])

        for wp in weak_points:
            # Support WeakPointEntry dataclass ou dict
            if hasattr(wp, "detail"):
                detail   = wp.detail or ""
                category = wp.category
                sev_orig = int(wp.severity)
            else:
                detail   = wp.get("detail") or ""
                category = wp.get("category")
                sev_orig = int(wp.get("severity", 2))

            if not detail.strip():
                continue

            is_rec, existing_id = _check_recurrence(course_id, detail)
            sev = sev_orig
            if is_rec:
                sev = min(sev + RECURRENCE_SEVERITY_BUMP, 5)

            if sev < LACUNE_MIN_SEVERITY and not is_rec:
                continue

            candidates.append(LacuneCandidate(
                detail=detail,
                category=category,
                severity=sev,
                severity_original=sev_orig,
                course_id=course_id,
                course_title=course_title,
                item_number=item_number,
                session_id=session_id,
                is_recurrence=is_rec,
                existing_wp_id=existing_id,
            ))

    return candidates


def create_lacune(
    candidate: LacuneCandidate,
    severity: int,
    detail_override: Optional[str] = None,
    create_obsidian: bool = False,
) -> int:
    """
    Crée une lacune depuis un LacuneCandidate après validation utilisateur.
    Retourne l'id SQLite de la ligne créée.
    """
    detail = (detail_override or candidate.detail).strip() or "Lacune sans titre"
    severity = max(1, min(5, severity))

    wp_id = local_store.add_weak_point_full(
        course_id=candidate.course_id or "—",
        detail=detail,
        course_title=candidate.course_title,
        item_number=candidate.item_number,
        category=candidate.category,
        severity=severity,
        source_type="qcm",
        source_session_id=candidate.session_id or None,
    )

    if create_obsidian:
        try:
            from backend.core.obsidian.weak_points_sync import create_obsidian_lacune_note
            ok, obs_path, obs_uri = create_obsidian_lacune_note(
                title=detail,
                college="",
                severity=severity,
                course_title=candidate.course_title,
                item_number=candidate.item_number,
                synapse_id=str(wp_id),
                source="qcm",
            )
            if ok:
                local_store.update_weak_point_obsidian(wp_id, obs_path, obs_uri)
        except Exception as exc:
            logger.warning(f"Obsidian lacune création échouée (non-bloquant) : {exc}")

    return wp_id
