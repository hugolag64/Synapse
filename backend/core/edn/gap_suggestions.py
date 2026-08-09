"""Suggestions de lacunes issues d'erreurs répétées."""

from __future__ import annotations

from collections import defaultdict

from .error_profile import ERROR_CATEGORIES, signals_since


def suggest_gap_candidates(*, item_number: str | None = None, days: int = 30, store) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for signal in signals_since(item_number=item_number, days=days, store=store):
        category = signal["category"] if signal["category"] in ERROR_CATEGORIES else "non_classe"
        groups[(signal["item_number"], category)].append(signal)

    existing = {
        row["dedupe_key"]
        for row in store.get_edn_recommendations(status="proposée")
    }
    suggestions = []
    for (item, category), signals in sorted(groups.items()):
        if len(signals) < 2:
            continue
        dedupe_key = f"gap:{item}:{category}"
        if dedupe_key in existing:
            continue
        evidence_ids = [row["evidence_id"] for row in signals]
        detail = f"Erreur répétée : {category} ({len(signals)} signal(s))"
        recommendation_id = store.create_edn_recommendation(
            recommendation_type="gap",
            item_number=item,
            category=category,
            detail=detail,
            evidence_ids=evidence_ids,
            dedupe_key=dedupe_key,
        )
        suggestions.append({
            "id": recommendation_id,
            "item_number": item,
            "category": category,
            "detail": detail,
            "evidence_ids": evidence_ids,
        })
    return suggestions


def accept_gap_suggestion(suggestion_id: int, *, store) -> int:
    recommendation = store.get_edn_recommendation(suggestion_id)
    if recommendation is None:
        raise ValueError("Suggestion de lacune introuvable")
    weak_point_id = store.add_weak_point_full(
        course_id=f"item:{recommendation['item_number']}",
        item_number=recommendation["item_number"],
        category=recommendation["category"],
        detail=recommendation["detail"],
        severity=3,
        source_type="qcm",
    )
    store.update_edn_recommendation(suggestion_id, "acceptée")
    return weak_point_id


def ignore_gap_suggestion(suggestion_id: int, *, store) -> None:
    if store.get_edn_recommendation(suggestion_id) is None:
        raise ValueError("Suggestion de lacune introuvable")
    store.update_edn_recommendation(suggestion_id, "ignorée")
