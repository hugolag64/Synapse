import json
from types import SimpleNamespace

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.practice.models import PracticeKind
from backend.core.practice.service import PracticeService


def test_item_history_exposes_tutor_dp_action():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")

    assert "render_dp_tutor_action" in source
    assert "_tab_history(course," in source


def test_dp_tutor_context_is_explicit_and_session_is_dp():
    class FakeAI:
        def __init__(self):
            self.context = None

        def generate(self, task, prompt, *, context=None, response_format="text"):
            self.context = context
            payload = {
                "questions": [
                    {"kind": "closed", "prompt": "Q", "choices": ["A", "B"], "answer": "A", "explanation": "E"}
                ]
            }
            return AIResponse(json.dumps(payload), AIModel.FLASH, 1, 1)

    fake = FakeAI()
    store = SimpleNamespace(create_ai_practice_session=lambda **kwargs: kwargs["spec"].practice_kind.value)
    service = PracticeService(ai_service=fake, store=store)

    session_id = service.create_tutor_dp_session(
        item_number="221",
        course_id="course-221",
        course_title="Méningite",
        dossier_context="Patient fébrile avec purpura.",
        errors=[{"category": "rang_a", "detail": "antibiotique retardé"}],
        gap_details=["Urgence thérapeutique"],
        total_questions=1,
    )

    assert session_id == PracticeKind.DP.value
    assert "Patient fébrile" in fake.context
    assert "rang_a" in fake.context
    assert "Urgence thérapeutique" in fake.context
