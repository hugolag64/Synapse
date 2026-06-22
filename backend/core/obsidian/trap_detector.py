"""
Trap Detector — Synapse F3
--------------------------
Parse les notes Obsidian pour détecter automatiquement les pièges EDN :
  - Callouts > [!danger/warning/caution]
  - Mots-clés piège / attention / ne pas confondre
  - Valeurs chiffrées médicales avec unité
  - Contre-indications

Intégration :
  - Appelé après obsidian_service.create_course_note() lors de la création
  - Appelé via sync_traps_from_vault() dans le background loop
  - Les pièges détectés sont upsert dans weak_points (source_type='auto_detection')
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


# ── Patterns ──────────────────────────────────────────────────────────────────

_CALLOUT_RE = re.compile(
    r'>\s*\[!(?:danger|warning|caution)\][^\n]*',
    re.IGNORECASE,
)
_KEYWORD_RE = re.compile(
    r'(?:piège|attention|ne pas confondre|NE PAS|À NE PAS|erreur classique)[^\n]{0,150}',
    re.IGNORECASE,
)
_VALUE_RE = re.compile(
    r'\b(\d+(?:[,.]\d+)?)\s*(?:mg(?:/kg)?|mmol/L|g/L|%|UI|mEq|pg/mL|ng/mL|µg/kg)\b',
    re.IGNORECASE,
)
_CI_RE = re.compile(
    r'(?:contre-indication|CI absolue|CI relative)[^\n]{0,150}',
    re.IGNORECASE,
)
_SEVERITY_BOOST_RE = re.compile(
    r'\b(?:JAMAIS|TOUJOURS|ABSOLUMENT|FATAL|MORTEL|URGENCE|DANGER)\b',
    re.IGNORECASE,
)

_PATTERNS: list[tuple[re.Pattern, str, int]] = [
    (_CALLOUT_RE, "callout",          4),
    (_KEYWORD_RE, "keyword",          4),
    (_VALUE_RE,   "value",            3),
    (_CI_RE,      "contraindication", 4),
]


# ── Modèle ────────────────────────────────────────────────────────────────────

@dataclass
class DetectedTrap:
    text: str
    trap_type: str      # "callout" | "keyword" | "value" | "contraindication"
    severity: int       # 3..5
    line_number: int


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_traps(note_path: Path) -> list[DetectedTrap]:
    """
    Parse une note Obsidian et retourne les pièges EDN détectés.
    Ligne par ligne — idempotent (les doublons textuels sont dédupliqués).
    """
    try:
        content = note_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug(f"trap_detector: cannot read {note_path}: {exc}")
        return []

    traps: list[DetectedTrap] = []
    seen_texts: set[str] = set()

    for i, line in enumerate(content.splitlines()):
        for pattern, trap_type, base_severity in _PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            text = m.group(0).strip()[:200]
            if text in seen_texts:
                continue
            seen_texts.add(text)
            severity = min(5, base_severity + (1 if _SEVERITY_BOOST_RE.search(line) else 0))
            traps.append(DetectedTrap(
                text=text,
                trap_type=trap_type,
                severity=severity,
                line_number=i,
            ))

    return traps


# ── Sync vault ────────────────────────────────────────────────────────────────

def sync_traps_from_vault(courses: list, vault_path: Path) -> int:
    """
    Scanne le vault Obsidian pour les pièges dans les notes de cours.
    Upsert les DetectedTrap dans weak_points (source_type='auto_detection').

    Retourne le nombre de pièges créés/mis à jour.
    """
    from backend.core.obsidian.service import ObsidianService
    from backend.core.reviews.local_store import upsert_auto_detected_trap

    obsidian_svc = ObsidianService()
    total = 0

    for course in courses:
        note_path = obsidian_svc.find_course_note(course)
        if not note_path or not note_path.exists():
            continue

        traps = extract_traps(note_path)
        for trap in traps:
            upsert_auto_detected_trap(
                course_id=course.id,
                course_title=course.title,
                item_number=course.item_number or "",
                detail=trap.text,
                severity=trap.severity,
                obsidian_path=str(note_path),
            )
            total += 1

    logger.info(f"Trap sync : {total} pièges EDN détectés/mis à jour")
    return total
