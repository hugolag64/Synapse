import json
from pathlib import Path
from types import SimpleNamespace

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.practice.models import PracticeKind
from backend.core.practice.service import PracticeService

COCKPIT_SOURCE = (
    Path(__file__).parents[1] / "frontend/pages/course_detail_cockpit.py"
).read_text(encoding="utf-8")

PANEL_SOURCE = (
    Path(__file__).parents[1] / "frontend/components/ai_practice_panel.py"
).read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    """Renvoie le corps source d'une fonction top-level jusqu'à la prochaine
    définition top-level, sans importer le module (page NiceGUI, import évité
    par convention dans ce fichier de tests)."""
    start = source.index(f"def {name}(")
    rest = source[start:]
    candidates = [i for i in (rest.find("\ndef ", 1), rest.find("\nasync def ", 1)) if i != -1]
    end = min(candidates) if candidates else len(rest)
    return rest[:end]


def test_item_qcm_exposes_tutor_dp_action():
    assert "render_dp_tutor_action" in COCKPIT_SOURCE
    tab_qcm_body = _extract_function(COCKPIT_SOURCE, "_tab_qcm")
    assert "_render_dp_tutor(course, lacunes)" in tab_qcm_body


def test_item_history_no_longer_renders_tutor_dp():
    history_body = _extract_function(COCKPIT_SOURCE, "_tab_history")
    assert "TUTEUR DP" not in history_body
    assert "_render_dp_tutor" not in history_body


def test_tutor_dp_block_uses_primary_color_and_shared_reco_style():
    tutor_body = _extract_function(COCKPIT_SOURCE, "_render_dp_tutor")
    assert "color=indigo" not in tutor_body
    assert tutor_body.count("color=primary") == 2
    assert "ci-reco" in tutor_body


def test_dp_tutor_context_is_explicit_and_session_is_dp():
    class FakeAI:
        def __init__(self):
            self.context = None

        def generate(self, task, prompt, *, context=None, response_format="text", difficulty=None):
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


def test_tutor_dp_chains_into_the_standard_correction_flow():
    """Terminer un Tuteur DP doit ouvrir sa correction, comme une session normale."""
    tutor_body = _extract_function(PANEL_SOURCE, "render_dp_tutor_action")

    assert "_open_answer_dialog(session_id, refresh)" in tutor_body
    assert "on_complete=lambda _sid: None" not in tutor_body


def test_tutor_dp_open_session_does_not_refresh_before_opening_reader():
    """_open_session ne doit pas appeler refresh() avant _open_answer_dialog.

    Depuis /qcm, refresh() vide history_col — le slot parent du dialogue du
    Tuteur DP — avant que le lecteur ne s'y ouvre, ce qui le crée dans un
    slot détruit. Le flux standard rejoue déjà le rafraîchissement via
    on_back -> open_chained_dialog une fois la correction terminée.
    """
    tutor_body = _extract_function(PANEL_SOURCE, "render_dp_tutor_action")

    start = tutor_body.index("def _open_session() -> None:")
    rest = tutor_body[start:]
    end = rest.index("\n\n")
    open_session_body = rest[:end]

    assert "_open_answer_dialog(session_id, refresh)" in open_session_body
    for line in open_session_body.splitlines():
        assert line.strip() != "refresh()", (
            "refresh() ne doit pas être appelé isolément avant l'ouverture "
            "du lecteur du Tuteur DP"
        )
