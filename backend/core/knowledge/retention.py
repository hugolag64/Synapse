from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Sequence

MASTERY_FLOOR = 25
MAX_STABILITY_DAYS = 730.0

SOURCE_BASE_STABILITY: dict[str, float] = {
    "lecture": 7.0,
    "manual": 14.0,
    "confidence": 14.0,
    "qcm": 21.0,
    "dp": 21.0,
    "kfp": 21.0,
    "oic": 21.0,
    "anki": 14.0,
}


@dataclass(frozen=True)
class Evidence:
    date: datetime.date
    source: str
    quality: float


@dataclass(frozen=True)
class RetentionSnapshot:
    score: int
    stability_days: float
    last_evidence: datetime.date | None


def project_retention(score: int, stability_days: float, days: float) -> float:
    score = max(0, min(100, score))
    if days <= 0:
        return float(score)
    if stability_days <= 0:
        return float(MASTERY_FLOOR)

    stability = min(MAX_STABILITY_DAYS, max(1.0, stability_days))
    projected = MASTERY_FLOOR + (score - MASTERY_FLOOR) * (2 ** (-days / stability))
    return max(0.0, min(100.0, projected))


def evaluate_retention(
    base_score: int,
    evidence: Sequence[Evidence],
    as_of: datetime.date,
) -> RetentionSnapshot:
    score = max(0, min(100, base_score))
    if not evidence:
        return RetentionSnapshot(score=score, stability_days=0.0, last_evidence=None)

    ordered = sorted(evidence, key=lambda item: item.date)
    stability_days = _initial_stability(ordered[0])
    last_evidence = ordered[-1].date

    for item in ordered[1:]:
        stability_days = _update_stability(stability_days, item)

    age_days = max(0.0, float((as_of - last_evidence).days))
    projected = project_retention(score, stability_days, age_days)
    return RetentionSnapshot(
        score=max(0, min(100, int(math.floor(projected)))),
        stability_days=min(MAX_STABILITY_DAYS, stability_days),
        last_evidence=last_evidence,
    )


def _initial_stability(item: Evidence) -> float:
    base = _source_base_stability(item.source)
    quality = _clamp_quality(item.quality)
    return _bounded_stability(base * (2.0 + quality))


def _update_stability(current: float, item: Evidence) -> float:
    base = _source_base_stability(item.source)
    quality = _clamp_quality(item.quality)
    if quality >= 0.5:
        growth = 1.0 + (base / 60.0) * quality
        current *= growth
    else:
        contraction = 1.0 - (base / 40.0) * (0.5 - quality)
        current *= max(0.1, contraction)
    return _bounded_stability(current)


def _source_base_stability(source: str) -> float:
    key = source.strip().lower()
    if key not in SOURCE_BASE_STABILITY:
        raise ValueError(f"Unknown evidence source: {source!r}")
    return SOURCE_BASE_STABILITY[key]


def _clamp_quality(quality: float) -> float:
    return max(0.0, min(1.0, quality))


def _bounded_stability(value: float) -> float:
    return min(MAX_STABILITY_DAYS, max(1.0, value))
