"""End-to-end local smoke test for the sanitized UNESS Gériatrie fixture."""

from __future__ import annotations

import json
from base64 import b64decode
from pathlib import Path

import pytest

from backend.core.ai.routing import AIModel, AIResponse
from backend.core.reviews import local_store
from backend.core.uness import import_service
from backend.core.uness.ai_verifier import VerificationContext, verify_exam
from backend.core.uness.artifacts import ExamMetadata, RawMedia, RawUnessArtifact
from backend.core.uness.import_service import import_uness_exam
from backend.core.uness.json_io import load_exam, save_exam
from backend.core.uness.normalizer import normalize_artifact

FIXTURE = Path(__file__).parent / "fixtures" / "uness" / "geriatry_review.html"
VALID_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FixtureAIService:
    """Deterministic local response provider for the verification boundary."""

    def generate(self, task, prompt, *, context=None, response_format="text", images=()):
        return AIResponse(
            json.dumps(
                {
                    "propositions": [
                        {
                            "id": "A",
                            "verdict_ia": True,
                            "explication_ia": "La perte de poids involontaire est un critère de dénutrition.",
                            "sources_ia": ["Fixture gériatrie"],
                            "confiance_ia": 0.9,
                            "commentaire_desaccord": "",
                        },
                        {
                            "id": "B",
                            "verdict_ia": False,
                            "explication_ia": "Un IMC supérieur à 30 kg/m² ne définit pas la dénutrition.",
                            "sources_ia": ["Fixture gériatrie"],
                            "confiance_ia": 0.9,
                            "commentaire_desaccord": "",
                        },
                        {
                            "id": "C",
                            "verdict_ia": True,
                            "explication_ia": "La diminution des apports alimentaires est un critère de dénutrition.",
                            "sources_ia": ["Fixture gériatrie"],
                            "confiance_ia": 0.9,
                            "commentaire_desaccord": "",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            AIModel.FLASH_LITE,
        )


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Keep the smoke test entirely local and independent of the user's data."""
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "synapse-smoke.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def test_geriatry_fixture_normalizes_verifies_and_imports_one_explained_session(
    tmp_path, monkeypatch
) -> None:
    """Catches a handoff that cannot turn one reviewed content into a usable local QCM."""
    monkeypatch.setattr(import_service, "ARTIFACT_DIR", tmp_path / "artifacts")
    artifact = RawUnessArtifact(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=29135",
        html_by_content={"nutrition": FIXTURE.read_text(encoding="utf-8")},
        media=[RawMedia("images/courbe-poids.png", VALID_PNG, "image/png", 1)],
        collected_at="2026-07-30T09:15:00+02:00",
        collection_status="complete",
        artifact_root=tmp_path / "artifacts",
    )
    metadata = ExamMetadata(
        faculte="Université Paris Cité",
        niveau="DFASM3",
        matiere="Gériatrie",
        type_epreuve="Annale",
        annee=2026,
        titre="Gériatrie — évaluation nutritionnelle",
        source_url=artifact.source_url,
    )

    normalized = normalize_artifact(artifact, metadata)
    verified = verify_exam(
        normalized,
        VerificationContext("Critères locaux de dénutrition.", ["124"], []),
        FixtureAIService(),
    )
    verified_json = tmp_path / "imports" / "geriatry-verified.json"
    save_exam(verified, verified_json)
    round_tripped = load_exam(verified_json)
    session_id = import_uness_exam(round_tripped)

    sessions = local_store.get_ai_practice_sessions(limit=10)
    questions = local_store.get_ai_practice_session(session_id)
    propositions = verified.questions[0].propositions

    assert len(sessions) == 1
    assert len(questions) == 1
    assert len(propositions) == 3
    assert all(proposition.explication_ia for proposition in propositions)
    assert all(proposition["explication_ia"] for proposition in questions[0]["uness"]["propositions"])
    assert all(proposition.explication_ia in questions[0]["explanation"] for proposition in propositions)
    assert round_tripped.to_dict() == verified.to_dict()


def test_import_uness_exam_tags_item_number_from_ai_classification(
    tmp_path, monkeypatch
) -> None:
    """entrainement.uness.fr never exposes an item number itself (only matière) —
    `import_uness_exam` must fill it in via classification when metadata carries
    none, and record every item of a multi-item DP, not just the primary one."""
    monkeypatch.setattr(import_service, "ARTIFACT_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(
        import_service, "_classify_exam_items", lambda exam, matiere: ("221", ("221", "223"))
    )
    artifact = RawUnessArtifact(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=29999",
        html_by_content={"nutrition": FIXTURE.read_text(encoding="utf-8")},
        media=[RawMedia("images/courbe-poids.png", VALID_PNG, "image/png", 1)],
        collected_at="2026-07-30T09:15:00+02:00",
        collection_status="complete",
        artifact_root=tmp_path / "artifacts",
    )
    metadata = ExamMetadata(
        faculte="Université Paris Cité", niveau="DFASM3", matiere="Cardiovasculaire",
        type_epreuve="Annale", annee=2026, titre="Cas cardiovasculaire",
        source_url=artifact.source_url,
    )
    normalized = normalize_artifact(artifact, metadata)
    verified = verify_exam(
        normalized, VerificationContext("Critères locaux.", ["124"], []), FixtureAIService(),
    )

    session_id = import_uness_exam(verified, matiere="Cardiovasculaire ❤️")

    session = local_store.get_ai_practice_sessions(limit=10)[0]
    questions = local_store.get_ai_practice_session(session_id)
    with local_store._conn() as con:
        linked_items = {
            row["item_number"]
            for row in con.execute(
                "SELECT item_number FROM ai_practice_session_items WHERE session_id = ?",
                (session_id,),
            )
        }

    assert session["item_number"] == "221"
    assert linked_items == {"221", "223"}
    assert all(question["item_number"] == "221" for question in questions)

    # Une session dont l'item est déjà connu (ex: provenance en amont) ne doit
    # jamais être reclassée — garde-fou de coût le plus élémentaire.
    calls: list = []
    monkeypatch.setattr(
        import_service, "_classify_exam_items",
        lambda exam, matiere: calls.append(1) or ("999", ("999",)),
    )
    import dataclasses
    already_tagged = dataclasses.replace(
        verified, metadata={**verified.metadata, "item_number": "500"}
    )
    import_uness_exam(already_tagged, matiere="Cardiovasculaire ❤️")
    assert not calls
