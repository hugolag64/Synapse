"""Profilage explicable des erreurs EDN."""

from __future__ import annotations

import datetime

ERROR_CATEGORIES = (
    "oubli", "raisonnement", "piege_edn", "rang_a", "rang_b", "inattention", "temps", "non_classe",
)


def build_error_profile(*, item_number: str | None = None, days: int = 30, store) -> dict[str, dict]:
    signals = store.get_error_signals(item_number=item_number, days=days)
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
    return store.get_error_signals(item_number=item_number, days=days)
