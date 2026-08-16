"""The Rang A sprint bonus only applies to a conclusive measurement."""

from datetime import date
from types import SimpleNamespace

from backend.core.reviews.service import ReviewService


def _course():
    return SimpleNamespace(
        nb_lectures=1,
        agregation_fiche_edn=True,
        qcm_done=False,
        college=[],
        id="course-1",
    )


def _mastery(conclusive: bool):
    return SimpleNamespace(
        level="à entraîner",
        score_rang_a=40,
        rang_a_conclusive=conclusive,
    )


def test_rang_a_bonus_is_not_applied_before_a_conclusive_measurement():
    service = ReviewService()
    score = service._calculate_priority(
        _course(), date.today(), date.today(), "J3", mastery=_mastery(False)
    )

    assert score == -4.0


def test_rang_a_bonus_is_applied_after_a_conclusive_measurement():
    service = ReviewService()
    score = service._calculate_priority(
        _course(), date.today(), date.today(), "J3", mastery=_mastery(True)
    )

    assert score == 31.0
