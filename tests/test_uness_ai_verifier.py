import json
from dataclasses import replace

import pytest

from backend.core.ai.routing import AIModel, AIResponse, AITask
from backend.core.uness.ai_verifier import VerificationContext, verify_exam, verify_question
from backend.core.uness.models import UnessExam, UnessImage, UnessProposition, UnessQuestion


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


def _exam(*questions: UnessQuestion, dp_context: dict | None = None) -> UnessExam:
    return UnessExam(
        faculty="Université Paris Cité",
        level="DFASM3",
        year=2026,
        title="Gériatrie",
        dp_context=dp_context or {},
        questions=questions,
        provenance={
            "source": "UNESS",
            "source_url": "https://entrainement.uness.example/review/42",
            "collected_at": "2026-07-30T09:15:00+02:00",
            "collection_status": "complete",
        },
    )


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


def test_verifier_prompt_supplies_official_answers_as_non_authoritative_comparison() -> None:
    """Catches a disagreement contract the model cannot satisfy from the supplied prompt."""
    service = FakeAIService(_answer_payload())

    verify_question(_question(), VerificationContext("Cours", [], []), service)

    prompt = service.calls[0][1]
    assert "Correction officielle UNESS (comparaison non autoritative)" in prompt
    assert "A: faux" in prompt
    assert "B: vrai" in prompt
    assert "raisonnement indépendant" in prompt


def test_verify_exam_supplies_general_dp_question_context_and_image_metadata_to_ai() -> None:
    """Catches clinically relevant dossier or visual context being omitted from verification."""
    question = replace(
        _question(),
        dp_context={"step": 2, "text": "Perte de poids de 8 kg."},
        images=(
            UnessImage(
                source_url="images/courbe-poids.png",
                local_path="imports/media/courbe-poids.png",
                alt_text="Courbe pondérale",
                caption="Évolution sur six mois",
            ),
        ),
        support_visuel_seul=True,
    )
    service = FakeAIService(_answer_payload())

    verify_exam(
        _exam(question, dp_context={"patient": "Personne de 86 ans"}),
        VerificationContext("Cours", [], []),
        service,
    )

    prompt = service.calls[0][1]
    assert "Contexte général du dossier" in prompt
    assert "Personne de 86 ans" in prompt
    assert "Perte de poids de 8 kg." in prompt
    assert "images/courbe-poids.png" in prompt
    assert "Courbe pondérale" in prompt
    assert "support visuel uniquement" in prompt
    assert "imports/media/courbe-poids.png" not in prompt


def test_verifier_rejects_a_response_missing_a_proposition() -> None:
    service = FakeAIService({"propositions": [_answer_payload()["propositions"][0]]})

    with pytest.raises(ValueError, match="résultat IA manquant.*B"):
        verify_question(_question(), VerificationContext("", [], []), service)


def test_verifier_marks_results_context_limited_without_course_or_references() -> None:
    service = FakeAIService(_answer_payload())

    verified = verify_question(_question(), VerificationContext("", [], []), service)

    assert verified.propositions[0].sources_ia[-1] == "Contexte limité : aucune source pédagogique fournie."
    assert "CONTEXTE LIMITÉ" in service.calls[0][1]


def test_verifier_loads_course_text_for_item_references_when_not_supplied() -> None:
    service = FakeAIService(_answer_payload())
    requested_refs: list[list[str]] = []

    def load_course_text(item_refs: list[str]) -> str:
        requested_refs.append(item_refs)
        return "Le cours local confirme que le delirium est fluctuant."

    verified = verify_question(
        _question(),
        VerificationContext("", ["124"], [], course_text_loader=load_course_text),
        service,
    )

    assert requested_refs == [["124"]]
    assert service.calls[0][3] == "Le cours local confirme que le delirium est fluctuant."
    assert "Contexte limité : aucune source pédagogique fournie." not in verified.propositions[0].sources_ia


def test_verifier_keeps_false_verdict_with_its_explanation() -> None:
    payload = _answer_payload()
    payload["propositions"][0].update(
        verdict_ia=False,
        explication_ia="L'absence de réversibilité n'est pas absolue.",
        commentaire_desaccord="",
    )
    service = FakeAIService(payload)

    verified = verify_question(_question(), VerificationContext("Cours", [], []), service)

    assert verified.propositions[0].verdict_ia is False
    assert verified.propositions[0].explication_ia == "L'absence de réversibilité n'est pas absolue."
    assert verified.propositions[0].statut == "concordant"


def test_verifier_rejects_empty_comment_for_a_disagreement() -> None:
    payload = _answer_payload()
    payload["propositions"][0]["commentaire_desaccord"] = " "
    service = FakeAIService(payload)

    with pytest.raises(ValueError, match="commentaire_desaccord est requis"):
        verify_question(_question(), VerificationContext("Cours", [], []), service)


def test_verify_exam_replaces_every_question_without_changing_exam_metadata() -> None:
    exam = _exam(_question())
    service = FakeAIService(_answer_payload())

    verified = verify_exam(exam, VerificationContext("Cours", ["124"], ["HAS" ]), service)

    assert verified.title == "Gériatrie"
    assert verified.questions[0].propositions[0].statut == "desaccord"


def test_verify_exam_loads_course_context_once_and_reuses_it_for_every_question() -> None:
    requested_refs: list[list[str]] = []

    def load_course_text(item_refs: list[str]) -> str:
        requested_refs.append(item_refs)
        return "Contexte de cours partagé."

    exam = _exam(_question(), _question())
    service = FakeAIService(_answer_payload())

    verify_exam(
        exam,
        VerificationContext("", ["124"], [], course_text_loader=load_course_text),
        service,
    )

    assert requested_refs == [["124"]]
    assert [call[3] for call in service.calls] == [
        "Contexte de cours partagé.",
        "Contexte de cours partagé.",
    ]


def test_verify_exam_does_not_retry_an_unavailable_course_context_loader() -> None:
    requested_refs: list[list[str]] = []

    def unavailable_loader(item_refs: list[str]) -> None:
        requested_refs.append(item_refs)
        return None

    exam = _exam(_question(), _question())
    service = FakeAIService(_answer_payload())

    verified = verify_exam(
        exam,
        VerificationContext("", ["124"], [], course_text_loader=unavailable_loader),
        service,
    )

    assert requested_refs == [["124"]]
    assert all(
        proposition.sources_ia[-1] == "Contexte limité : aucune source pédagogique fournie."
        for question in verified.questions
        for proposition in question.propositions
    )
