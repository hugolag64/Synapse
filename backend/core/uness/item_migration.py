"""Helpers for safe question-level migration of broad UNESS item links."""

from __future__ import annotations

from collections.abc import Mapping

MAX_ITEMS_PER_QUESTION = 2
MIGRATION_SOURCE = "uness_question_migration"
CLASSIFIER_VERSION = "2026-08-03-question-v1"
CLASSIFICATION_CONFIDENCE = 0.8


def accepted_item_numbers(
    item_numbers: list[str] | tuple[str, ...],
    *,
    confident: bool,
    max_items: int = MAX_ITEMS_PER_QUESTION,
) -> tuple[str, ...]:
    """Keep only short, confident classifications suitable for evidence."""
    if not confident:
        return ()
    normalized = tuple(dict.fromkeys(str(item).strip() for item in item_numbers if str(item).strip()))
    return normalized if 0 < len(normalized) <= max_items else ()


def build_question_item_links(
    classifications: Mapping[int, tuple[list[str] | tuple[str, ...], bool]],
) -> list[tuple[int, str, float, str, str]]:
    """Convert classifier results into durable question-item rows."""
    rows: list[tuple[int, str, float, str, str]] = []
    for question_id in sorted(classifications):
        item_numbers, confident = classifications[question_id]
        for item_number in accepted_item_numbers(item_numbers, confident=confident):
            rows.append(
                (
                    int(question_id),
                    item_number,
                    CLASSIFICATION_CONFIDENCE,
                    MIGRATION_SOURCE,
                    CLASSIFIER_VERSION,
                )
            )
    return rows
