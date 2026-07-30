from __future__ import annotations

import json
from copy import deepcopy

import pytest

from backend.core.uness.json_io import load_exam, save_exam
from backend.core.uness.models import UnessExam, UnessProposition


def _valid_exam_payload(**overrides) -> dict:
    payload = {
        "faculty": "Université Paris Cité",
        "level": "DFASM3",
        "year": 2026,
        "title": "Gériatrie — dossier progressif",
        "provenance": {
            "source": "UNESS",
            "source_url": "https://entrainement.uness.example/review/42",
            "collected_at": "2026-07-30T09:15:00+02:00",
            "collection_status": "complete",
        },
        "questions": [],
    }
    payload.update(overrides)
    return payload


def test_exam_round_trip_preserves_uness_correction_ai_verdict_and_visual_context(tmp_path) -> None:
    """Catches a serializer that drops metadata or conflates official and IA answers."""
    payload = {
        "faculty": "Universit\u00e9 Paris Cité",
        "level": "DFASM3",
        "year": 2026,
        "title": "Gériatrie — dossier progressif",
        "provenance": {
            "source": "UNESS",
            "source_url": "https://entrainement.uness.example/review/42",
            "collected_at": "2026-07-30T09:15:00+02:00",
            "collection_status": "complete",
            "artifact_path": "imports/exam-42.json",
        },
        "dp_context": {"patient": "Mme Martin, 86 ans", "step": 2},
        "questions": [
            {
                "id": "q-1",
                "type_question": "QRM",
                "enonce": "Quels éléments orientent vers une dénutrition ?",
                "support_visuel_seul": True,
                "images": [
                    {
                        "source_url": "https://uness.example/scan.png",
                        "local_path": "imports/media/scan.png",
                        "alt_text": "Courbe pondérale",
                        "metadata": {"width": 1200, "height": 800},
                    }
                ],
                "propositions": [
                    {
                        "id": "A",
                        "texte": "Perte de poids involontaire",
                        "reponse_uness": True,
                        "verdict_ia": False,
                        "reponse_finale": None,
                        "statut": "desaccord",
                    }
                ],
            }
        ],
    }

    exam = UnessExam.from_dict(payload)
    target = tmp_path / "exam.json"
    save_exam(exam, target)

    persisted = json.loads(target.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1
    assert persisted["faculty"] == "Universit\u00e9 Paris Cité"
    assert persisted["questions"][0]["propositions"][0] == {
        "id": "A",
        "texte": "Perte de poids involontaire",
        "reponse_uness": True,
        "verdict_ia": False,
        "reponse_finale": None,
        "statut": "desaccord",
        "validation_utilisateur": False,
    }
    assert load_exam(target).to_dict() == persisted


@pytest.mark.parametrize("type_question", ["QRM", "QRU", "QRP/L", "DP", "KFP", "QROC"])
def test_exam_accepts_every_supported_question_type(type_question: str) -> None:
    """Catches validation that rejects one of the supported UNESS question kinds."""
    exam = UnessExam.from_dict(
        _valid_exam_payload(
            questions=[{"id": "q1", "type_question": type_question, "enonce": "Question"}]
        )
    )

    assert exam.questions[0].type_question == type_question


def test_exam_rejects_unknown_status_and_question_type() -> None:
    """Catches imports that silently accept values downstream consumers cannot interpret."""
    with pytest.raises(ValueError, match="statut"):
        UnessExam.from_dict(
            _valid_exam_payload(
                questions=[
                    {
                        "id": "q1",
                        "type_question": "QRM",
                        "enonce": "Question",
                        "propositions": [{"id": "A", "texte": "Réponse", "statut": "invalide"}],
                    }
                ]
            )
        )

    with pytest.raises(ValueError, match="type_question"):
        UnessExam.from_dict(
            _valid_exam_payload(
                questions=[{"id": "q1", "type_question": "QCM", "enonce": "Question"}]
            )
        )


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "Credentials",
        "session-token",
        "localStorage",
        "sessionStorage",
        "COOKIE",
        "password",
        "client_secret",
        "id_token",
        "token",
        "auth_token",
        "access_token",
        "refresh_token",
        "Authorization",
        "api-key",
    ],
)
def test_exam_rejects_sensitive_data_from_import_regardless_of_key_spelling(
    sensitive_key: str,
) -> None:
    """Catches an import path that stores credentials or browser-session data."""
    with pytest.raises(ValueError, match="sensible"):
        UnessExam.from_dict(
            _valid_exam_payload(metadata={"nested": [{"browser": {sensitive_key: "secret"}}]})
        )


def test_save_exam_rejects_sensitive_data_on_directly_constructed_model(tmp_path) -> None:
    """Catches direct model construction bypassing loader-only secret validation."""
    exam = UnessExam.from_dict(_valid_exam_payload())
    exam.metadata["Credentials"] = "secret"
    with pytest.raises(ValueError, match="sensible"):
        save_exam(exam, tmp_path / "exam.json")


def test_save_exam_rejects_sensitive_data_nested_in_tuples(tmp_path) -> None:
    """Catches tuple-contained secrets bypassing the final persistence boundary."""
    exam = UnessExam.from_dict(_valid_exam_payload())
    exam.metadata["nested"] = ({"client_secret": "secret"},)

    with pytest.raises(ValueError, match="sensible"):
        save_exam(exam, tmp_path / "exam.json")


def test_direct_model_construction_rejects_sensitive_data() -> None:
    """Catches callers bypassing JSON import to place credentials in an exam."""
    with pytest.raises(ValueError, match="sensible"):
        UnessExam.from_dict(_valid_exam_payload(metadata={"Credentials": "secret"}))


@pytest.mark.parametrize(
    ("field_path", "empty_value"),
    [
        (("faculty",), " "),
        (("level",), ""),
        (("year",), None),
        (("title",), ""),
        (("provenance", "source"), ""),
        (("provenance", "source_url"), ""),
        (("provenance", "collected_at"), ""),
        (("provenance", "collection_status"), ""),
    ],
)
def test_exam_rejects_missing_required_identity_and_provenance(
    field_path: tuple[str, ...], empty_value,
) -> None:
    """Catches canonical artifacts that cannot prove their identity or collection origin."""
    payload = deepcopy(_valid_exam_payload())
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = empty_value

    with pytest.raises(ValueError, match=field_path[-1]):
        UnessExam.from_dict(payload)


def test_exam_rejects_source_url_with_embedded_access_token() -> None:
    """Catches provenance URLs that accidentally retain browser authorization data."""
    payload = _valid_exam_payload()
    payload["provenance"]["source_url"] = (
        "https://entrainement.uness.example/review/42?access_token=secret"
    )

    with pytest.raises(ValueError, match="source_url"):
        UnessExam.from_dict(payload)


@pytest.mark.parametrize(
    "token_url",
    [
        "https://uness.example/image.png?token=secret",
        "https://uness.example/callback#id_token=secret",
        "https://user:password@uness.example/review",
    ],
)
def test_exam_rejects_token_bearing_urls_anywhere_in_nested_data(token_url: str) -> None:
    """Catches credential-bearing URLs outside the top-level provenance field."""
    payload = _valid_exam_payload(metadata={"nested": [("safe", {"url": token_url})]})

    with pytest.raises(ValueError, match="sensible"):
        UnessExam.from_dict(payload)


@pytest.mark.parametrize(
    "secret_text",
    [
        "https://uness.example/#/callback?access_token=secret",
        "Ouvrir https://uness.example/review/42?id_token=secret puis continuer.",
        "https://storage.example/scan.png?X-Amz-Signature=secret",
    ],
)
def test_exam_rejects_fragment_embedded_and_signed_secret_urls(secret_text: str) -> None:
    """Catches tokenized URLs that whole-string URL parsing does not inspect correctly."""
    payload = _valid_exam_payload(metadata={"narrative": secret_text})

    with pytest.raises(ValueError, match="sensible"):
        UnessExam.from_dict(payload)


@pytest.mark.parametrize(
    "secret_text",
    [
        (
            "https://uness.example/redirect?"
            "next=https%253A%252F%252Fstorage.example%252Fscan.png"
            "%253Faccess_token%253Dsecret"
        ),
        (
            "https://uness.example/#/redirect?"
            "next=https%253A%252F%252Flogin.example%252Fcallback"
            "%2523id_token%253Dsecret"
        ),
        (
            "https://uness.example/redirect?"
            "next=https%253A%252F%252Fstorage.example%252Fscan.png"
            "%253Fredirect%253Daccess_token%25253Dsecret"
        ),
        (
            "https://uness.example/#/redirect?"
            "next=https%253A%252F%252Flogin.example%252Fcallback"
            "%2523redirect%253Did_token%25253Dsecret"
        ),
    ],
)
def test_exam_rejects_double_encoded_token_urls_in_nested_query_or_fragment(
    secret_text: str,
) -> None:
    """Catches nested redirect secrets hidden behind repeated percent-encoding."""
    payload = _valid_exam_payload(metadata={"redirect": secret_text})

    with pytest.raises(ValueError, match="sensible"):
        UnessExam.from_dict(payload)


@pytest.mark.parametrize(
    "source_url",
    [
        "images/scan.png?access_token=secret",
        "https://storage.example/scan.png?X-Goog-Signature=secret",
    ],
)
def test_exam_rejects_secret_bearing_image_source_urls(source_url: str) -> None:
    """Catches relative or signed visual URLs surviving into persisted artifacts."""
    payload = _valid_exam_payload(
        questions=[
            {
                "id": "q-1",
                "type_question": "QRM",
                "enonce": "Question visuelle",
                "images": [{"source_url": source_url}],
            }
        ]
    )

    with pytest.raises(ValueError, match="sensible"):
        UnessExam.from_dict(payload)


def test_save_exam_rejects_an_embedded_secret_url_added_after_construction(tmp_path) -> None:
    """Catches direct mutation bypassing import-time validation before persistence."""
    exam = UnessExam.from_dict(_valid_exam_payload())
    exam.metadata["note"] = (
        "Relancer via https://uness.example/#/callback?refresh_token=secret"
    )

    with pytest.raises(ValueError, match="sensible"):
        save_exam(exam, tmp_path / "exam.json")


def test_proposition_rejects_final_answer_without_manual_user_validation() -> None:
    """Catches final answers being recorded before a user validates the proposition."""
    with pytest.raises(ValueError, match="validation utilisateur"):
        UnessProposition(id="A", texte="Réponse", reponse_finale=True, statut="incertain")


def test_proposition_rejects_final_answer_when_manual_status_lacks_user_validation() -> None:
    """Catches a final answer marked manually valid without an actual user validation."""
    with pytest.raises(ValueError, match="validation utilisateur"):
        UnessProposition(
            id="A",
            texte="Réponse",
            reponse_finale=True,
            statut="valide_manuellement",
            validation_utilisateur=False,
        )


def test_proposition_accepts_final_answer_after_manual_user_validation() -> None:
    """Catches an invariant that would prevent a legitimately user-validated answer."""
    proposition = UnessProposition(
        id="A",
        texte="Réponse",
        reponse_finale=True,
        statut="valide_manuellement",
        validation_utilisateur=True,
    )

    assert proposition.reponse_finale is True
