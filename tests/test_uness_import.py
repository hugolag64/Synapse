"""Integration tests for importing verified local UNESS exams into QCM sessions."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import qcm
from backend.core.reviews import local_store
from backend.core.uness import import_service


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Keep the import flow local and isolated from the user's SQLite data."""
    database = tmp_path / "synapse-test.db"
    monkeypatch.setattr(local_store, "DB_PATH", database)
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(qcm.router)
    return TestClient(app)


@pytest.fixture
def import_dir(tmp_path, monkeypatch):
    directory = tmp_path / "uness-imports"
    directory.mkdir()
    monkeypatch.setattr(import_service, "IMPORT_DIR", directory)
    return directory


@pytest.fixture
def artifact_dir(tmp_path, monkeypatch):
    directory = tmp_path / "data" / "uness" / "artifacts"
    directory.mkdir(parents=True)
    monkeypatch.setattr(import_service, "_ROOT", tmp_path)
    monkeypatch.setattr(import_service, "ARTIFACT_DIR", directory)
    return directory


def _exam_payload() -> dict:
    return {
        "faculty": "Université Paris Cité",
        "level": "DFASM3",
        "year": 2026,
        "title": "Gériatrie — examen vérifié",
        "dp_context": {"text": "Une personne âgée présente une confusion aiguë."},
        "provenance": {
            "source": "UNESS",
            "source_url": "https://entrainement.uness.example/review/42",
            "collected_at": "2026-07-30T09:15:00+02:00",
            "collection_status": "complete",
            "artifact_path": "review/geriatry.json",
        },
        "questions": [
            {
                "id": "q-1",
                "type_question": "QRM",
                "enonce": "Concernant le delirium :",
                "verification_status": "verified",
                "dp_context": {"step": 1, "text": "Les symptômes fluctuent dans la journée."},
                "images": [
                    {
                        "source_url": "images/horloge.png",
                        "local_path": "",
                        "alt_text": "Horloge dessinée par le patient",
                        "caption": "Test de l'horloge",
                        "metadata": {"verification_status": "provided_to_ai"},
                    }
                ],
                "support_visuel_seul": True,
                "propositions": [
                    {
                        "id": "A",
                        "texte": "Il est toujours irréversible.",
                        "reponse_uness": False,
                        "verdict_ia": True,
                        "explication_ia": "Le delirium est souvent réversible si sa cause est traitée.",
                        "sources_ia": ["Item 124"],
                        "confiance_ia": 0.92,
                        "commentaire_desaccord": "La correction officielle semble inversée.",
                        "statut": "desaccord",
                    },
                    {
                        "id": "B",
                        "texte": "Il peut être fluctuant.",
                        "reponse_uness": True,
                        "verdict_ia": True,
                        "explication_ia": "La fluctuation est caractéristique.",
                        "sources_ia": ["Item 124"],
                        "confiance_ia": 0.88,
                        "statut": "concordant",
                    },
                ],
            }
        ],
    }


def _write_exam(directory, name: str, payload: dict | None = None) -> None:
    (directory / name).write_text(
        json.dumps(payload if payload is not None else _exam_payload(), ensure_ascii=False),
        encoding="utf-8",
    )


def test_import_endpoint_creates_local_qcm_session_with_verified_correction(client, import_dir):
    """Catches an importer that drops provenance or uses the official answer as primary."""
    _write_exam(import_dir, "geriatry.json")

    response = client.post("/api/qcm/uness/import", json={"path": "geriatry.json", "verify": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] > 0
    assert payload["questions"] == 1
    assert payload["disagreements"] == 1

    session = client.get(f"/api/qcm/sessions/{payload['session_id']}")
    assert session.status_code == 200
    question = session.json()["questions"][0]
    assert json.loads(question["answer"]) == ["Il est toujours irréversible.", "Il peut être fluctuant."]
    assert question["correction"]["primary"]["explanation"].startswith("A. Le delirium")
    assert question["correction"]["official"]["answer"] == ["Il peut être fluctuant."]
    assert question["correction"]["disagreement"]["present"] is True
    assert question["correction"]["disagreement"]["comments"] == [
        "La correction officielle semble inversée."
    ]
    assert question["uness"]["provenance"]["source"] == "UNESS"
    assert question["uness"]["provenance"]["source_url"] == (
        "https://entrainement.uness.example/review/42"
    )
    assert question["uness"]["provenance"]["collected_at"] == "2026-07-30T09:15:00+02:00"
    assert question["uness"]["provenance"]["collection_status"] == "complete"
    assert question["uness"]["exam"]["faculty"] == "Université Paris Cité"
    assert question["uness"]["exam"]["level"] == "DFASM3"
    assert question["uness"]["exam"]["year"] == 2026
    assert question["uness"]["exam"]["dp_context"]["text"].startswith("Une personne âgée")
    assert question["uness"]["question"]["images"][0]["alt_text"] == (
        "Horloge dessinée par le patient"
    )
    assert question["uness"]["question"]["support_visuel_seul"] is True
    assert question["uness"]["question"]["verification_status"] == "verified"
    assert question["uness"]["propositions"][0]["statut"] == "desaccord"

    assert client.post(
        f"/api/qcm/sessions/{payload['session_id']}/attempts",
        json={"question_id": question["id"], "response": question["answer"]},
    ).status_code == 200
    completed = client.post(f"/api/qcm/sessions/{payload['session_id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["rows"][0]["correction"]["primary"]["source"] == "ia"
    assert completed.json()["rows"][0]["correction"]["official"]["source"] == "UNESS"
    assert completed.json()["rows"][0]["correction"]["disagreement"]["present"] is True


def test_import_endpoint_rejects_malformed_json_with_400(client, import_dir):
    """Catches JSON decoder errors escaping as a server error."""
    (import_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    response = client.post("/api/qcm/uness/import", json={"path": "broken.json", "verify": True})

    assert response.status_code == 400


@pytest.mark.parametrize("payload", [[], {"questions": "not-a-list"}])
def test_import_endpoint_rejects_parseable_invalid_exam_shapes_with_400(client, import_dir, payload):
    """Catches model AttributeErrors escaping parseable but invalid JSON as a 500."""
    _write_exam(import_dir, "invalid-shape.json", payload)

    response = client.post("/api/qcm/uness/import", json={"path": "invalid-shape.json", "verify": True})

    assert response.status_code == 400


def test_import_endpoint_returns_404_for_missing_local_artifact(client, import_dir):
    """Catches a missing local file being reported as a generic import failure."""
    response = client.post("/api/qcm/uness/import", json={"path": "absent.json", "verify": True})

    assert response.status_code == 404


def test_import_keeps_partial_official_correction_marked_as_incomplete(client, import_dir):
    """Catches a partial UNESS correction being falsely labelled complete."""
    payload = _exam_payload()
    payload["questions"][0]["propositions"][1]["reponse_uness"] = None
    payload["questions"][0]["propositions"][1]["statut"] = "incertain"
    _write_exam(import_dir, "partial-official.json", payload)

    imported = client.post(
        "/api/qcm/uness/import", json={"path": "partial-official.json", "verify": True}
    )

    assert imported.status_code == 200
    question = client.get(f"/api/qcm/sessions/{imported.json()['session_id']}").json()["questions"][0]
    assert question["correction"]["official"]["available"] is False
    assert question["uness"]["propositions"][1]["reponse_uness"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verdict_ia", None),
        ("explication_ia", " "),
        ("confiance_ia", None),
        ("confiance_ia", 1.2),
        ("statut", "incertain"),
    ],
)
def test_verified_import_rejects_incomplete_or_incoherent_ai_review(
    client, import_dir, field, value
):
    """Catches the request's verify flag being trusted instead of the artifact contents."""
    payload = _exam_payload()
    payload["questions"][0]["propositions"][0][field] = value
    _write_exam(import_dir, "not-verified.json", payload)

    response = client.post(
        "/api/qcm/uness/import", json={"path": "not-verified.json", "verify": True}
    )

    assert response.status_code == 400
    assert "vérification IA" in response.json()["detail"]


def test_verified_import_rejects_an_unsupported_visual_question(client, import_dir):
    """Catches a missing visual being silently imported as a boolean AI correction."""
    payload = _exam_payload()
    question = payload["questions"][0]
    question["verification_status"] = "unsupported"
    question["images"][0]["metadata"] = {"verification_status": "unsupported"}
    for proposition in question["propositions"]:
        proposition.update(
            verdict_ia=None,
            explication_ia="Vérification IA indisponible : support visuel non pris en charge.",
            sources_ia=[],
            confiance_ia=None,
            commentaire_desaccord="",
            statut="incertain",
        )
    _write_exam(import_dir, "unsupported-visual.json", payload)

    response = client.post(
        "/api/qcm/uness/import",
        json={"path": "unsupported-visual.json", "verify": True},
    )

    assert response.status_code == 400
    assert "visuelle" in response.json()["detail"]
    assert "non prise en charge" in response.json()["detail"]


def test_import_uses_manually_validated_final_answer_for_payload_and_scoring(
    client, import_dir
):
    """Catches a validated final answer being ignored in favor of the earlier IA verdict."""
    payload = _exam_payload()
    proposition = payload["questions"][0]["propositions"][0]
    proposition.update(
        reponse_finale=False,
        statut="valide_manuellement",
        validation_utilisateur=True,
    )
    _write_exam(import_dir, "manually-validated.json", payload)

    imported = client.post(
        "/api/qcm/uness/import", json={"path": "manually-validated.json", "verify": True}
    )
    assert imported.status_code == 200
    session_id = imported.json()["session_id"]
    question = client.get(f"/api/qcm/sessions/{session_id}").json()["questions"][0]

    assert json.loads(question["answer"]) == ["Il peut être fluctuant."]
    assert question["correction"]["primary"]["source"] == "validated"
    attempt = client.post(
        f"/api/qcm/sessions/{session_id}/attempts",
        json={
            "question_id": question["id"],
            "response": json.dumps(["Il peut être fluctuant."], ensure_ascii=False),
        },
    )
    assert attempt.status_code == 200
    completed = client.post(f"/api/qcm/sessions/{session_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["session"]["score_percent"] == 100


def test_imported_local_image_is_available_to_the_react_reader(client, import_dir):
    """Catches replay metadata pointing at a local file the browser cannot request."""
    media = import_dir / "media"
    media.mkdir()
    image = media / "horloge.png"
    image.write_bytes(b"png-fixture")
    payload = _exam_payload()
    payload["questions"][0]["images"][0]["local_path"] = str(image)
    _write_exam(import_dir, "with-image.json", payload)

    imported = client.post(
        "/api/qcm/uness/import", json={"path": "with-image.json", "verify": True}
    )
    assert imported.status_code == 200
    session_id = imported.json()["session_id"]
    question = client.get(f"/api/qcm/sessions/{session_id}").json()["questions"][0]

    response = client.get(
        f"/api/qcm/sessions/{session_id}/questions/{question['id']}/images/0"
    )

    assert response.status_code == 200
    assert response.content == b"png-fixture"


def test_normalized_relative_artifact_image_is_available_to_the_react_reader(
    client, import_dir, artifact_dir
):
    """Catches default normalized paths being incorrectly anchored under the import inbox."""
    media = artifact_dir / "geriatry"
    media.mkdir()
    image = media / "q01-horloge.png"
    image.write_bytes(b"relative-png-fixture")
    payload = _exam_payload()
    payload["questions"][0]["images"][0]["local_path"] = (
        "data/uness/artifacts/geriatry/q01-horloge.png"
    )
    _write_exam(import_dir, "with-relative-image.json", payload)

    imported = client.post(
        "/api/qcm/uness/import",
        json={"path": "with-relative-image.json", "verify": True},
    )
    assert imported.status_code == 200
    session_id = imported.json()["session_id"]
    question = client.get(f"/api/qcm/sessions/{session_id}").json()["questions"][0]

    response = client.get(
        f"/api/qcm/sessions/{session_id}/questions/{question['id']}/images/0"
    )

    assert response.status_code == 200
    assert response.content == b"relative-png-fixture"


def test_import_endpoint_rejects_paths_outside_local_import_directory(client, import_dir, tmp_path):
    """Catches path traversal or arbitrary-file access through the API."""
    outside = tmp_path / "outside.json"
    _write_exam(tmp_path, "outside.json")

    response = client.post("/api/qcm/uness/import", json={"path": str(outside), "verify": True})

    assert response.status_code == 400
