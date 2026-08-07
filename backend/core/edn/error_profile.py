"""Profilage explicable des erreurs EDN."""

from __future__ import annotations

import datetime

ERROR_CATEGORIES = (
    "oubli", "raisonnement", "piege_edn", "rang_a", "rang_b", "inattention", "temps", "non_classe",
)

DEFAULT_ERROR_WINDOW_DAYS = 30
FALLBACK_ERROR_WINDOW_DAYS = 90
MIN_SIGNALS_FOR_RECENT_WINDOW = 2


def get_adaptive_error_signals(
    *,
    item_number: str | None = None,
    days: int = DEFAULT_ERROR_WINDOW_DAYS,
    fallback_days: int = FALLBACK_ERROR_WINDOW_DAYS,
    min_signals: int = MIN_SIGNALS_FOR_RECENT_WINDOW,
    store,
) -> list[dict]:
    """Use recent signals first, then widen the window when evidence is sparse."""
    signals = store.get_error_signals(item_number=item_number, days=days)
    if len(signals) >= min_signals or days >= fallback_days:
        return signals
    fallback_signals = store.get_error_signals(item_number=item_number, days=fallback_days)
    return signals if len(signals) >= min_signals else fallback_signals


def build_error_profile(*, item_number: str | None = None, days: int = 30, store) -> dict[str, dict]:
    signals = get_adaptive_error_signals(item_number=item_number, days=days, store=store)
    profile: dict[str, dict] = {}
    for signal in signals:
        category = signal["category"] if signal["category"] in ERROR_CATEGORIES else "non_classe"
        entry = profile.setdefault(category, {"count": 0, "evidence_ids": [], "items": {}})
        entry["count"] += 1
        entry["evidence_ids"].append(signal["evidence_id"])
        item = signal["item_number"]
        entry["items"][item] = entry["items"].get(item, 0) + 1
    return profile


def signals_since(*, item_number: str | None = None, days: int = 30, store) -> list[dict]:
    return get_adaptive_error_signals(item_number=item_number, days=days, store=store)
