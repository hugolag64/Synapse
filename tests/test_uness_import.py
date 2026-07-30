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


def _exam_payload() -> dict:
    return {
        "faculty": "Université Paris Cité",
        "level": "DFASM3",
        "year": 2026,
        "title": "Gériatrie — examen vérifié",
        "provenance": {"source": "UNESS", "artifact_path": "review/geriatry.json"},
        "questions": [
            {
                "id": "q-1",
                "type_question": "QRM",
                "enonce": "Concernant le delirium :",
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
    assert question["uness"]["provenance"]["source"] == "UNESS"
    assert question["uness"]["propositions"][0]["statut"] == "desaccord"

    assert client.post(
        f"/api/qcm/sessions/{payload['session_id']}/attempts",
        json={"question_id": question["id"], "response": question["answer"]},
    ).status_code == 200
    completed = client.post(f"/api/qcm/sessions/{payload['session_id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["rows"][0]["correction"]["primary"]["source"] == "ia"
    assert completed.json()["rows"][0]["correction"]["official"]["source"] == "UNESS"


def test_import_endpoint_rejects_malformed_json_with_400(client, import_dir):
    """Catches JSON decoder errors escaping as a server error."""
    (import_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    response = client.post("/api/qcm/uness/import", json={"path": "broken.json", "verify": True})

    assert response.status_code == 400


def test_import_endpoint_returns_404_for_missing_local_artifact(client, import_dir):
    """Catches a missing local file being reported as a generic import failure."""
    response = client.post("/api/qcm/uness/import", json={"path": "absent.json", "verify": True})

    assert response.status_code == 404


def test_import_endpoint_rejects_paths_outside_local_import_directory(client, import_dir, tmp_path):
    """Catches path traversal or arbitrary-file access through the API."""
    outside = tmp_path / "outside.json"
    _write_exam(tmp_path, "outside.json")

    response = client.post("/api/qcm/uness/import", json={"path": str(outside), "verify": True})

    assert response.status_code == 400
