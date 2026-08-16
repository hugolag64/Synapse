"""Question-level rank resolution with explicit provenance and safety rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

INFERENCE_THRESHOLD = 0.85
VALID_RANKS = frozenset({"A", "B"})


@dataclass(frozen=True)
class RankDecision:
    rank: str = ""
    source: str = "unknown"
    confidence: float | None = None
    evidence: tuple[str, ...] = ()
    rationale: str = ""
    status: str = "unknown"
    alternatives: tuple[dict[str, Any], ...] = ()


def _valid_rank(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in VALID_RANKS else ""


def resolve_rank(
    *,
    official_rank: Any = "",
    official_evidence: tuple[str, ...] | list[str] = (),
    gemini_rank: Any = "",
    gemini_confidence: float | None = None,
    gemini_evidence: tuple[str, ...] | list[str] = (),
    gemini_rationale: str = "",
    gemini_ambiguous: bool = False,
    admin_rank: Any = "",
    admin_reason: str = "",
) -> RankDecision:
    """Resolve one question's rank without allowing an uncertain guess through.

    The precedence is deliberate: explicit source data, reliable Gemini inference,
    then an admin fallback. A manual contradiction is retained as an alternative,
    but cannot silently replace a reliable inference.
    """
    official = _valid_rank(official_rank)
    gemini = _valid_rank(gemini_rank)
    admin = _valid_rank(admin_rank)
    alternatives: list[dict[str, Any]] = []
    if admin:
        alternatives.append({"rank": admin, "source": "admin", "reason": str(admin_reason or "").strip()})

    if official:
        return RankDecision(
            rank=official,
            source="official",
            confidence=1.0,
            evidence=tuple(str(item).strip() for item in official_evidence if str(item).strip()),
            status="resolved",
            alternatives=tuple(alternatives),
        )

    try:
        confidence = float(gemini_confidence) if gemini_confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    if gemini and confidence is not None and confidence >= INFERENCE_THRESHOLD and not gemini_ambiguous:
        if admin and admin != gemini:
            alternatives = [
                {
                    "rank": admin,
                    "source": "admin_conflict",
                    "reason": str(admin_reason or "").strip(),
                }
            ]
            status = "admin_conflict"
        else:
            status = "resolved"
        return RankDecision(
            rank=gemini,
            source="gemini",
            confidence=confidence,
            evidence=tuple(str(item).strip() for item in gemini_evidence if str(item).strip()),
            rationale=str(gemini_rationale or "").strip()[:500],
            status=status,
            alternatives=tuple(alternatives),
        )

    if admin:
        return RankDecision(
            rank=admin,
            source="admin",
            confidence=1.0,
            rationale=str(admin_reason or "").strip()[:500],
            status="resolved",
            alternatives=tuple(alternatives),
        )

    return RankDecision(
        status="ambiguous" if gemini_ambiguous else "unknown",
        alternatives=tuple(alternatives),
    )


def apply_rank_decision(question: Mapping[str, Any], decision: RankDecision) -> dict[str, Any]:
    """Return a question payload carrying the complete rank audit trail."""
    result = dict(question)
    result.update(
        {
            "rank": decision.rank,
            "rank_source": decision.source,
            "rank_confidence": decision.confidence,
            "rank_evidence": list(decision.evidence),
            "rank_rationale": decision.rationale,
            "rank_status": decision.status,
            "rank_alternatives": list(decision.alternatives),
        }
    )
    return result
