import pytest

from backend.core.ai.routing import AIModel, AIResponse, AITask, model_for_task


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (AITask.OIC, AIModel.FLASH_LITE),
        (AITask.QCM, AIModel.FLASH_LITE),
        (AITask.ECOS_SIMPLE, AIModel.FLASH_LITE),
        (AITask.DP, AIModel.FLASH),
        (AITask.KFP, AIModel.FLASH),
        (AITask.ECOS_COMPLEX, AIModel.FLASH),
        (AITask.EXTRACTION_GRILLE, AIModel.FLASH),
    ],
)
def test_model_for_task_uses_the_expected_quality_tier(task, expected):
    assert model_for_task(task) is expected


def test_score_task_is_rejected_because_scores_are_deterministic():
    with pytest.raises(ValueError, match="ne passe pas par le service IA"):
        model_for_task(AITask.SCORE)


def test_unknown_task_is_rejected():
    with pytest.raises(ValueError, match="Tâche IA inconnue"):
        model_for_task("not-a-task")


def test_ai_response_keeps_text_model_and_usage_metadata():
    response = AIResponse(
        text="réponse",
        model=AIModel.FLASH_LITE,
        input_tokens=12,
        output_tokens=7,
    )

    assert response.text == "réponse"
    assert response.model is AIModel.FLASH_LITE
    assert response.input_tokens == 12
    assert response.output_tokens == 7
