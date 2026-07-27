from backend.core.evaluation.models import EvaluationInput, recommend_evaluation


def test_failed_qcm_with_error_type_recommends_error_review():
    evaluation = EvaluationInput(
        source="qcm",
        course_id="course-1",
        item_number="75",
        score_percent=55,
        error_types=("raisonnement",),
    )

    assert recommend_evaluation(evaluation) == "review_errors"


def test_low_confidence_auto_evaluation_recommends_error_review():
    evaluation = EvaluationInput(
        source="auto_eval", course_id="course-1", item_number="75", confidence=2
    )

    assert recommend_evaluation(evaluation) == "review_errors"


def test_low_oic_score_recommends_oic_practice():
    evaluation = EvaluationInput(
        source="oic", course_id="course-1", item_number="75", score_percent=40
    )

    assert recommend_evaluation(evaluation) == "practice_oic"


def test_successful_evaluation_recommends_consolidation():
    evaluation = EvaluationInput(
        source="qcm", course_id="course-1", item_number="75", score_percent=85
    )

    assert recommend_evaluation(evaluation) == "consolidate"
