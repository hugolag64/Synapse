"""Tests unitaires — évaluateur OIC (logique pure + AnythingLLM)."""
import pytest
from unittest.mock import patch

from backend.core.lisa import evaluator


class TestGradeQcm:
    def test_correct_answer(self):
        q = evaluator.Question(type="qcm", enonce="?", options=["a", "b"], correct_index=1, explication="car b")
        result = evaluator.grade_qcm(q, 1)
        assert result.verdict == "correct"
        assert result.score == 100
        assert result.explication == "car b"

    def test_incorrect_answer(self):
        q = evaluator.Question(type="qcm", enonce="?", options=["a", "b"], correct_index=1, explication="car b")
        result = evaluator.grade_qcm(q, 0)
        assert result.verdict == "incorrect"
        assert result.score == 0


class TestAggregateSessionScore:
    def test_averages_scores(self):
        results = [
            evaluator.EvalResult(verdict="correct", score=100),
            evaluator.EvalResult(verdict="incorrect", score=0),
        ]
        assert evaluator.aggregate_session_score(results) == 50

    def test_empty_list_returns_zero(self):
        assert evaluator.aggregate_session_score([]) == 0

    def test_rounds_to_nearest_int(self):
        results = [
            evaluator.EvalResult(verdict="correct", score=100),
            evaluator.EvalResult(verdict="correct", score=100),
            evaluator.EvalResult(verdict="incorrect", score=0),
        ]
        assert evaluator.aggregate_session_score(results) == 67


class TestNextOicLevel:
    def test_increments_on_high_score(self):
        assert evaluator.next_oic_level(2, 85, []) == 3

    def test_caps_at_five_only_with_two_prior_high_scores(self):
        assert evaluator.next_oic_level(4, 85, [90, 88]) == 5

    def test_caps_at_four_without_enough_history(self):
        assert evaluator.next_oic_level(4, 85, [90]) == 4

    def test_caps_at_four_when_prior_score_low(self):
        assert evaluator.next_oic_level(4, 85, [90, 40]) == 4

    def test_stays_same_on_partial_score_above_level_three(self):
        assert evaluator.next_oic_level(3, 60, []) == 3

    def test_decrements_on_partial_score_below_level_three(self):
        assert evaluator.next_oic_level(2, 60, []) == 1

    def test_decrements_on_low_score(self):
        assert evaluator.next_oic_level(3, 30, []) == 2

    def test_never_drops_below_zero(self):
        assert evaluator.next_oic_level(0, 20, []) == 0
