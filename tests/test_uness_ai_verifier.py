import json
from base64 import b64decode
from dataclasses import replace

import pytest

from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AITask
from backend.core.uness import import_service
from backend.core.uness.ai_verifier import VerificationContext, verify_exam, verify_question
from backend.core.uness.import_service import assert_verified_exam
from backend.core.uness.models import UnessExam, UnessImage, UnessProposition, UnessQuestion

_VALID_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeAIService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[
            tuple[AITask, str, str, str | None, tuple[AIImageContent, ...]]
        ] = []

    def generate(self, task, prompt, *, context=None, response_format="text", images=()):
        self.calls.append((task, prompt, response_format, context, tuple(images)))
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


def test_verify_exam_supplies_general_dp_context_and_local_image_content_to_ai(
    tmp_path, monkeypatch
) -> None:
    """Catches clinically relevant local visual content being omitted from verification."""
    artifact_root = tmp_path / "artifacts"
    image_path = artifact_root / "courbe-poids.png"
    artifact_root.mkdir()
    image_path.write_bytes(_VALID_PNG)
    monkeypatch.setattr(import_service, "ARTIFACT_DIR", artifact_root)
    question = replace(
        _question(),
        dp_context={"step": 2, "text": "Perte de poids de 8 kg."},
        images=(
            UnessImage(
                source_url="https://uness.example/images/courbe-poids.png",
                local_path=str(image_path),
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
    assert "https://uness.example/images/courbe-poids.png" not in prompt
    assert str(image_path) not in prompt
    assert "support visuel uniquement" in prompt
    assert service.calls[0][4] == (
        AIImageContent(mime_type="image/png", data=_VALID_PNG),
    )


def test_verifier_marks_unavailable_visual_verification_unsupported() -> None:
    """Catches text-only verification being presented as a visual verification."""
    question = replace(
        _question(),
        images=(
            UnessImage(
                source_url="images/unavailable.png",
                local_path="data/uness/artifacts/missing.png",
            ),
        ),
    )
    service = FakeAIService(_answer_payload())

    verified = verify_question(question, VerificationContext("Cours", [], []), service)

    assert service.calls == []
    assert verified.verification_status == "unsupported"
    assert verified.images[0].metadata["verification_status"] == "unsupported"
    assert all(proposition.verdict_ia is None for proposition in verified.propositions)
    assert all(proposition.statut == "incertain" for proposition in verified.propositions)
    assert all(
        "support visuel" in proposition.explication_ia.lower()
        for proposition in verified.propositions
    )


def test_verifier_rejects_corrupt_image_content_instead_of_trusting_the_filename(
    tmp_path, monkeypatch
) -> None:
    """Catches fake PNG bytes being represented as provided to the multimodal model."""
    artifact_root = tmp_path / "artifacts"
    image_path = artifact_root / "fake.png"
    artifact_root.mkdir()
    image_path.write_bytes(b"not-a-real-png")
    monkeypatch.setattr(import_service, "ARTIFACT_DIR", artifact_root)
    question = replace(
        _question(),
        images=(UnessImage(source_url="images/fake.png", local_path=str(image_path)),),
    )
    service = FakeAIService(_answer_payload())

    verified = verify_question(question, VerificationContext("Cours", [], []), service)

    assert service.calls == []
    assert verified.verification_status == "unsupported"
    assert verified.images[0].metadata["verification_status"] == "unsupported"
    assert all(proposition.verdict_ia is None for proposition in verified.propositions)


def test_verifier_bounds_the_number_of_multimodal_images(
    tmp_path, monkeypatch
) -> None:
    """Catches a question attaching more image parts than the aggregate count budget."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    monkeypatch.setattr(import_service, "ARTIFACT_DIR", artifact_root)
    monkeypatch.setattr("backend.core.uness.ai_verifier._MAX_IMAGE_COUNT", 2)
    images = []
    for index in range(3):
        path = artifact_root / f"scan-{index}.png"
        path.write_bytes(_VALID_PNG)
        images.append(UnessImage(source_url=f"images/scan-{index}.png", local_path=str(path)))
    service = FakeAIService(_answer_payload())

    verified = verify_question(
        replace(_question(), images=tuple(images)),
        VerificationContext("Cours", [], []),
        service,
    )

    assert service.calls == []
    assert verified.verification_status == "unsupported"
    assert [image.metadata["verification_status"] for image in verified.images] == [
        "not_provided_to_ai",
        "not_provided_to_ai",
        "unsupported",
    ]


def test_verifier_bounds_total_multimodal_image_bytes(
    tmp_path, monkeypatch
) -> None:
    """Catches individually valid images exceeding the aggregate byte budget together."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    monkeypatch.setattr(import_service, "ARTIFACT_DIR", artifact_root)
    monkeypatch.setattr(
        "backend.core.uness.ai_verifier._MAX_TOTAL_IMAGE_BYTES",
        len(_VALID_PNG) * 2 - 1,
    )
    images = []
    for index in range(2):
        path = artifact_root / f"scan-{index}.png"
        path.write_bytes(_VALID_PNG)
        images.append(UnessImage(source_url=f"images/scan-{index}.png", local_path=str(path)))
    service = FakeAIService(_answer_payload())

    verified = verify_question(
        replace(_question(), images=tuple(images)),
        VerificationContext("Cours", [], []),
        service,
    )

    assert service.calls == []
    assert verified.verification_status == "unsupported"
    assert [image.metadata["verification_status"] for image in verified.images] == [
        "not_provided_to_ai",
        "unsupported",
    ]


def test_verifier_rejects_sensitive_nested_context_before_calling_ai() -> None:
    """Catches secrets reaching the prompt through direct question verification."""
    question = replace(
        _question(),
        dp_context={"nested": [("safe", {"client_secret": "secret"})]},
    )
    service = FakeAIService(_answer_payload())

    with pytest.raises(ValueError, match="sensible"):
        verify_question(question, VerificationContext("Cours", [], []), service)

    assert service.calls == []


def test_verifier_rejects_token_bearing_image_url_before_calling_ai() -> None:
    """Catches token-bearing image URLs reaching a remote prompt or payload."""
    question = replace(
        _question(),
        images=(UnessImage(source_url="https://uness.example/a.png?id_token=secret"),),
    )
    service = FakeAIService(_answer_payload())

    with pytest.raises(ValueError, match="sensible"):
        verify_question(question, VerificationContext("Cours", [], []), service)

    assert service.calls == []


def test_verifier_rejects_an_embedded_fragment_token_before_calling_ai() -> None:
    """Catches arbitrary prompt text containing a fragment-routed callback secret."""
    context = VerificationContext(
        "Voir https://uness.example/#/callback?access_token=secret",
        [],
        [],
    )
    service = FakeAIService(_answer_payload())

    with pytest.raises(ValueError, match="sensible"):
        verify_question(_question(), context, service)

    assert service.calls == []


def test_verifier_rejects_a_response_missing_a_proposition() -> None:
    service = FakeAIService({"propositions": [_answer_payload()["propositions"][0]]})

    with pytest.raises(ValueError, match="résultat IA manquant.*B"):
        verify_question(_question(), VerificationContext("", [], []), service)


def test_verifier_and_verified_import_both_reject_a_null_ia_verdict() -> None:
    """Catches disagreement between the verification and verified-import contracts."""
    payload = _answer_payload()
    payload["propositions"][0]["verdict_ia"] = None
    service = FakeAIService(payload)

    with pytest.raises(ValueError, match="verdict_ia"):
        verify_question(_question(), VerificationContext("Cours", [], []), service)

    unverified = replace(
        _question(),
        propositions=(
            UnessProposition(
                id="A",
                texte="Il est toujours irréversible.",
                reponse_uness=False,
                verdict_ia=None,
                explication_ia="Explication présente.",
                confiance_ia=0.8,
                statut="incertain",
            ),
        ),
    )
    with pytest.raises(ValueError, match="verdict_ia"):
        assert_verified_exam(_exam(unverified))


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
