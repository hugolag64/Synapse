import pytest

from backend.core.evaluation.models import EvaluationInput, recommend_evaluation
from backend.core.evaluation.service import record_evaluation
from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "evaluations.db"
    monkeypatch.setattr(local_store, "DB_PATH", db_path)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


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


def test_record_qcm_evaluation_persists_and_returns_recommendation():
    result = record_evaluation(
        EvaluationInput(
            source="qcm",
            course_id="course-1",
            course_title="Cardiologie",
            item_number="75",
            platform="Synapse",
            session_date="2026-07-27",
            score_percent=55,
            error_types=("raisonnement",),
        )
    )

    assert result.source == "qcm"
    assert result.persisted_id > 0
    assert result.recommendation == "review_errors"
    assert local_store.get_qcm_sessions_all(course_id="course-1")[0]["score_percent"] == 55


def test_record_auto_evaluation_persists_without_immediate_weak_point():
    result = record_evaluation(
        EvaluationInput(
            source="auto_eval",
            course_id="course-1",
            item_number="75",
            confidence=2,
            error_types=("raisonnement",),
            detail="Erreur clinique",
        )
    )

    with local_store._conn() as con:
        weak_points = con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]
    assert result.recommendation == "review_errors"
    assert result.persisted_id > 0
    assert weak_points == 0


def test_record_oic_evaluation_requires_canonical_aliases():
    with pytest.raises(ValueError, match="course_ids"):
        record_evaluation(
            EvaluationInput(
                source="oic", course_id="course-1", oic_code="OIC-1", score_percent=80
            )
        )


def test_record_oic_evaluation_preserves_existing_attempt_and_success_state():
    local_store.upsert_lisa_oic(
        "course-1", [{"oic_code": "OIC-1", "intitule": "Évaluer", "rang": "A"}]
    )

    result = record_evaluation(
        EvaluationInput(
            source="oic",
            course_id="course-1",
            course_ids=("course-1",),
            oic_code="OIC-1",
            score_percent=85,
            questions_json="[]",
        )
    )

    row = local_store.get_lisa_oic("course-1")[0]
    assert result.persisted_id > 0
    assert result.recommendation == "consolidate"
    assert local_store.get_oic_attempts(row["id"])[0]["session_score"] == 85
    assert row["mastered"] == 1
