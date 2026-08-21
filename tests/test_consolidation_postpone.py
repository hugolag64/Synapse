"""Reporter un item à consolider : c'est l'algorithme qui choisit la date.

Les lectures du cycle J1→J30 se reportent à la main (+1 j, +3 j, +1 semaine) :
le cycle est fixe et c'est l'étudiant qui décale une séance. Le flux de
consolidation, lui, est piloté par la maîtrise — un item critique doit revenir
vite, un item solide peut attendre.
"""
from types import SimpleNamespace

import pytest

from backend.core.reviews.consolidation import (
    DEFAULT_POSTPONE_DAYS,
    POSTPONE_DAYS_BY_LEVEL,
    is_algorithmic_postpone,
    postpone_days_for_task,
)


def _task(review_type: str, mastery_level: str | None = None):
    return SimpleNamespace(review_type=review_type, mastery_level=mastery_level)


def test_a_weaker_item_comes_back_sooner_than_a_solid_one():
    ordered = ["critique", "fragile", "en construction", "à consolider", "à entraîner", "maîtrisé"]
    delays = [POSTPONE_DAYS_BY_LEVEL[level] for level in ordered]

    assert delays == sorted(delays)
    assert delays[0] < delays[-1]


@pytest.mark.parametrize(
    ("level", "expected"),
    [("critique", 2), ("fragile", 3), ("en construction", 4),
     ("à consolider", 7), ("à entraîner", 10), ("maîtrisé", 14)],
)
def test_consolidation_delay_follows_the_mastery_level(level, expected):
    assert postpone_days_for_task(_task("consolidation", level)) == expected


def test_an_unknown_or_missing_level_falls_back_to_a_middle_delay():
    assert postpone_days_for_task(_task("consolidation", None)) == DEFAULT_POSTPONE_DAYS
    assert postpone_days_for_task(_task("consolidation", "inconnu")) == DEFAULT_POSTPONE_DAYS


def test_reading_cycle_tasks_keep_the_manual_one_day_default():
    """Pour une J3 ou une J30, c'est le menu de délais qui décide, pas la maîtrise."""
    for review_type in ("J1", "J3", "J7", "J14", "J30", "lacune", "manuel"):
        assert postpone_days_for_task(_task(review_type, "critique")) == 1
        assert is_algorithmic_postpone(_task(review_type)) is False


def test_only_consolidation_is_postponed_algorithmically():
    assert is_algorithmic_postpone(_task("consolidation")) is True


def test_delays_stay_shorter_than_a_full_sm2_cycle():
    """Un report n'est pas une validation : il ne doit pas faire disparaître
    l'item aussi longtemps qu'un cycle réussi."""
    from backend.core.reviews.local_store import CONSOLIDATION_INTERVAL_CAP_BY_LEVEL

    for level, cap in CONSOLIDATION_INTERVAL_CAP_BY_LEVEL.items():
        assert POSTPONE_DAYS_BY_LEVEL[level] < cap
