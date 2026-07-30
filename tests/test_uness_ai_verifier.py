import json

import pytest

from backend.core.ai.routing import AIModel, AIResponse, AITask
from backend.core.uness.ai_verifier import VerificationContext, verify_exam, verify_question
from backend.core.uness.models import UnessExam, UnessProposition, UnessQuestion


class FakeAIService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[AITask, str, str, str | None]] = []

    def generate(self, task, prompt, *, context=None, response_format="text"):
        self.calls.append((task, prompt, response_format, context))
        return AIResponse(json.dumps(self.payload), AIModel.FLASH_LITE)


def _question() -> UnessQuestion:
    return UnessQuestion(
        id="q-1",
        type_question="QRM",
        enonce="Concernant le delirium :",
        propositions=(
            UnessProposition(id="A", texte="Il est toujours irréversible.", reponse_uness=False),
            UnessProposition(id="B", texte="Il peut être fluctuant.", reponse_uness=True),
        ),
    )


def _answer_payload() -> dict:
    return {
        "propositions": [
            {
                "id": "A",
                "verdict_ia": True,
                "explication_ia": "Le delirium est souvent réversible si sa cause est traitée.",
                "sources_ia": ["Item 124"],
                "confiance_ia": 1.4,
                "commentaire_desaccord": "La correction UNESS semble inversée.",
            },
            {
                "id": "B",
                "verdict_ia": True,
                "explication_ia": "La fluctuation est caractéristique.",
                "sources_ia": ["Cours de gériatrie"],
                "confiance_ia": -0.2,
                "commentaire_desaccord": "",
            },
        ]
    }


def test_verifier_preserves_official_answers_and_persists_complete_ai_review() -> None:
    service = FakeAIService(_answer_payload())

    verified = verify_question(
        _question(),
        VerificationContext(course_text="Le delirium est fluctuant.", item_refs=["124"], external_refs=[]),
        service,
    )

    disagreement, agreement = verified.propositions
    assert disagreement.reponse_uness is False
    assert disagreement.verdict_ia is True
    assert disagreement.statut == "desaccord"
    assert disagreement.explication_ia == "Le delirium est souvent réversible si sa cause est traitée."
    assert disagreement.sources_ia == ("Item 124",)
    assert disagreement.confiance_ia == 1.0
    assert disagreement.commentaire_desaccord == "La correction UNESS semble inversée."
    assert agreement.reponse_uness is True
    assert agreement.statut == "concordant"
    assert agreement.confiance_ia == 0.0
    assert disagreement.to_dict()["sources_ia"] == ["Item 124"]
    assert disagreement.to_dict()["commentaire_desaccord"] == "La correction UNESS semble inversée."
    assert service.calls[0][0] is AITask.QCM
    assert service.calls[0][2] == "json"
    assert service.calls[0][3] == "Le delirium est fluctuant."


def test_verifier_rejects_a_response_missing_a_proposition() -> None:
    service = FakeAIService({"propositions": [_answer_payload()["propositions"][0]]})

    with pytest.raises(ValueError, match="résultat IA manquant.*B"):
        verify_question(_question(), VerificationContext("", [], []), service)


def test_verifier_marks_results_context_limited_without_course_or_references() -> None:
    service = FakeAIService(_answer_payload())

    verified = verify_question(_question(), VerificationContext("", [], []), service)

    assert verified.propositions[0].sources_ia[-1] == "Contexte limité : aucune source pédagogique fournie."
    assert "CONTEXTE LIMITÉ" in service.calls[0][1]


def test_verify_exam_replaces_every_question_without_changing_exam_metadata() -> None:
    exam = UnessExam(title="Gériatrie", questions=(_question(),))
    service = FakeAIService(_answer_payload())

    verified = verify_exam(exam, VerificationContext("Cours", ["124"], ["HAS" ]), service)

    assert verified.title == "Gériatrie"
    assert verified.questions[0].propositions[0].statut == "desaccord"
