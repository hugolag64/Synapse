"""Profilage explicable des erreurs EDN."""

from __future__ import annotations

import datetime

ERROR_CATEGORIES = (
    "oubli", "raisonnement", "piege_edn", "rang_a", "rang_b", "inattention", "temps", "non_classe",
)

DEFAULT_ERROR_WINDOW_DAYS = 30
FALLBACK_ERROR_WINDOW_DAYS = 90
MIN_SIGNALS_FOR_RECENT_WINDOW = 2


def map_discordance_to_error_category(
    proposition: dict,
    question: dict | None = None,
    item_context: dict | None = None,
) -> str:
    """Translate proposition-level evidence into the product taxonomy."""
    question = question or {}
    item_context = item_context or {}
    explicit = (
        proposition.get("error_category")
        or proposition.get("weak_category")
        or question.get("error_category")
        or question.get("weak_category")
    )
    if explicit in ERROR_CATEGORIES:
        return str(explicit)

    discordance = str(proposition.get("discordance") or "").strip().lower()
    rank = str(
        proposition.get("rank")
        or question.get("rank")
        or item_context.get("rank")
        or ""
    ).strip().upper()
    if discordance == "omission" and rank == "A":
        return "rang_a"
    if discordance == "omission" and rank == "B":
        return "rang_b"
    if discordance == "exces" and (
        proposition.get("is_trap")
        or question.get("is_trap")
        or question.get("trap")
    ):
        return "piege_edn"
    return "non_classe"


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
