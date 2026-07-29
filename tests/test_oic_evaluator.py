"""Tests unitaires — évaluateur OIC (logique pure + AnythingLLM)."""
from unittest.mock import patch

from backend.core.ai.routing import AIModel, AIResponse, AITask
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

    def test_none_explication_becomes_empty_string(self):
        q = evaluator.Question(type="qcm", enonce="?", options=["a", "b"], correct_index=1, explication=None)
        result = evaluator.grade_qcm(q, 1)
        assert result.explication == ""


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

    def test_exactly_80_counts_as_high_score(self):
        assert evaluator.next_oic_level(2, 80, []) == 3

    def test_exactly_50_counts_as_partial_not_low(self):
        # 50 should hit the 50<=score<80 branch, not the <50 branch
        assert evaluator.next_oic_level(2, 50, []) == 1  # level<3: max(0, level-1)
        assert evaluator.next_oic_level(3, 50, []) == 3  # level>=3: unchanged

    def test_stays_at_five_with_continued_high_scores(self):
        assert evaluator.next_oic_level(5, 85, [90, 88]) == 5

    def test_drops_from_five_on_low_score(self):
        assert evaluator.next_oic_level(5, 30, [90, 88]) == 4


class TestGenerateQuestions:
    def test_uses_routed_oic_service_when_provided(self):
        raw = '[{"type": "ouverte", "enonce": "Q?", "criteres": ["c"]}]'

        class FakeService:
            def __init__(self):
                self.calls = []

            def generate(self, task, prompt, *, response_format="text", context=None):
                self.calls.append((task, response_format, prompt))
                return AIResponse(raw, AIModel.FLASH_LITE)

        service = FakeService()
        questions = evaluator.generate_questions("Cours", "Intitulé", "A", "slug", ai_service=service)

        assert len(questions) == 1
        assert service.calls[0][0] is AITask.OIC
        assert service.calls[0][1] == "json"

    def test_parses_valid_json_response(self):
        raw = (
            '[{"type": "qcm", "enonce": "Q1?", "options": ["a", "b"], "correct_index": 0, "explication": "exp"},'
            '{"type": "ouverte", "enonce": "Q2?", "criteres": ["c1", "c2"]}]'
        )
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            questions = evaluator.generate_questions("ITEM 1 - Cours", "Intitulé", "A", "slug")
        assert len(questions) == 2
        assert questions[0].type == "qcm"
        assert questions[0].correct_index == 0
        assert questions[1].type == "ouverte"
        assert questions[1].criteres == ["c1", "c2"]

    def test_extracts_json_surrounded_by_text(self):
        raw = 'Voici le résultat :\n[{"type": "ouverte", "enonce": "Q?", "criteres": ["c"]}]\nMerci.'
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            questions = evaluator.generate_questions("Cours", "Intitulé", "A", "slug")
        assert len(questions) == 1
        assert questions[0].enonce == "Q?"

    def test_retries_once_on_invalid_json_then_succeeds(self):
        responses = ["pas du json", '[{"type": "ouverte", "enonce": "Q?", "criteres": ["c"]}]']
        with patch("backend.core.lisa.evaluator._client.query_workspace", side_effect=responses) as mock_q:
            questions = evaluator.generate_questions("Cours", "Intitulé", "A", "slug")
        assert mock_q.call_count == 2
        assert len(questions) == 1

    def test_falls_back_to_generic_question_after_two_failures(self):
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value="pas du json du tout"):
            questions = evaluator.generate_questions("Cours", "Mon Intitulé", "A", "slug")
        assert len(questions) == 1
        assert questions[0].type == "ouverte"
        assert "Mon Intitulé" in questions[0].enonce


class TestEvaluateOpenAnswer:
    def test_parses_valid_json_response(self):
        raw = (
            '{"verdict": "partial", "score": 65, "elements_corrects": ["a"], '
            '"elements_manquants": ["b"], "explication": "exp", "rappel_cours": "rappel"}'
        )
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a", "b"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            result = evaluator.evaluate_open_answer(q, "ma réponse", "slug")
        assert result.verdict == "partial"
        assert result.score == 65
        assert result.elements_manquants == ["b"]

    def test_retries_once_on_invalid_json_then_succeeds(self):
        responses = ["texte invalide", '{"verdict": "correct", "score": 90}']
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", side_effect=responses) as mock_q:
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert mock_q.call_count == 2
        assert result.verdict == "correct"

    def test_falls_back_to_incorrect_after_two_failures(self):
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value="pas du json"):
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert result.verdict == "incorrect"
        assert result.score == 0
        assert result.explication == "Erreur de parsing IA"

    def test_falls_back_when_score_is_non_numeric(self):
        raw = '{"verdict": "correct", "score": "quatre-vingt"}'
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert result.verdict == "incorrect"
        assert result.score == 0
        assert result.explication == "Erreur de parsing IA"

    def test_normalizes_unknown_verdict_to_incorrect(self):
        raw = '{"verdict": "acquis", "score": 70}'
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert result.verdict == "incorrect"

    def test_clamps_score_above_100(self):
        raw = '{"verdict": "correct", "score": 150}'
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert result.score == 100

    def test_clamps_score_below_0(self):
        raw = '{"verdict": "incorrect", "score": -20}'
        q = evaluator.Question(type="ouverte", enonce="Q?", criteres=["a"])
        with patch("backend.core.lisa.evaluator._client.query_workspace", return_value=raw):
            result = evaluator.evaluate_open_answer(q, "réponse", "slug")
        assert result.score == 0
