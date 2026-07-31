import json
from pathlib import Path

from backend.core.uness.chatgpt_bridge import build_chatgpt_input, validate_chatgpt_output
from backend.core.uness.models import UnessExam, UnessProposition, UnessQuestion


def _exam() -> UnessExam:
    return UnessExam(
        faculty="Faculté test", level="DFASM1", year=2024, title="Gériatrie",
        questions=(UnessQuestion(
            id="q1", type_question="QRM", enonce="Question ?",
            propositions=(UnessProposition(id="A", texte="Oui", reponse_uness=True),),
        ),),
        provenance={"source": "UNESS", "source_url": "https://entrainement.uness.fr/annales/course/view.php?id=1", "collected_at": "2024-01-01", "collection_status": "submitted"},
    )


def test_build_upload_package_contains_prompt_and_exam():
    package = build_chatgpt_input(_exam())
    assert package["instructions"]
    assert package["exam"]["questions"][0]["id"] == "q1"


def test_validate_chatgpt_output_accepts_french_aliases(tmp_path: Path):
    payload = _exam().to_dict()
    payload["questions"][0]["propositions"][0].update({
        "reponse_officielle": True, "avis_ia": "valide", "explication": "Explication.", "confiance": 0.9,
    })
    payload["questions"][0]["propositions"][0].pop("reponse_uness")
    payload["questions"][0]["propositions"][0].pop("verdict_ia")
    payload["questions"][0]["propositions"][0]["statut"] = "concordant"
    path = tmp_path / "verified.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    exam = validate_chatgpt_output(path)
    assert exam.questions[0].propositions[0].verdict_ia is True

