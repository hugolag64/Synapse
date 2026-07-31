"""Échange local avec ChatGPT, sans appel API.

Le module prépare un paquet JSON à téléverser manuellement et normalise la
réponse de ChatGPT vers le contrat canonique UNESS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .json_io import load_exam
from .models import UnessExam

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "uness_correction_prompt.txt"


def prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_chatgpt_input(exam: UnessExam) -> dict[str, Any]:
    """Return the uploadable wrapper containing the exam and strict instructions."""
    return {
        "bridge_schema_version": 1,
        "instructions": prompt_text(),
        "exam": exam.to_dict(),
    }


def save_chatgpt_input(exam: UnessExam, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_chatgpt_input(exam), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _canonicalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept the human-friendly field names from the prompt while preserving IDs."""
    source = dict(payload.get("exam", payload))
    source.setdefault("faculty", source.pop("faculte", ""))
    source.setdefault("level", source.pop("niveau", ""))
    source.setdefault("year", source.pop("annee", None))
    source.setdefault("title", source.pop("titre", ""))
    for question in source.get("questions", []):
        question.setdefault("enonce", question.pop("question", question.pop("prompt", "")))
        question.setdefault("verification_status", "verified")
        for prop in question.get("propositions", []):
            prop.setdefault("reponse_uness", prop.pop("reponse_officielle", None))
            verdict = prop.pop("avis_ia_bool", prop.pop("verdict", None))
            if verdict is None and prop.get("avis_ia") in {"valide", "invalide"}:
                verdict = prop["avis_ia"] == "valide"
            prop.setdefault("verdict_ia", verdict)
            prop.setdefault("explication_ia", prop.pop("explication", ""))
            prop.setdefault("confiance_ia", prop.get("confiance", None))
            if prop.get("desaccord_officiel") is True:
                prop["statut"] = "desaccord"
                prop.setdefault("commentaire_desaccord", "Désaccord signalé par ChatGPT.")
            elif prop.get("statut") not in {"concordant", "desaccord", "incertain", "valide_manuellement"}:
                official = prop.get("reponse_uness")
                verdict = prop.get("verdict_ia")
                prop["statut"] = "incertain" if official is None or verdict is None else ("concordant" if official == verdict else "desaccord")
                if prop["statut"] == "desaccord":
                    prop.setdefault("commentaire_desaccord", "Désaccord entre la correction officielle et l'avis IA.")
    return source


def validate_chatgpt_output(path: Path) -> UnessExam:
    """Load and validate a ChatGPT JSON output against the canonical contract."""
    with Path(path).open(encoding="utf-8") as source:
        payload = json.load(source)
    return UnessExam.from_dict(_canonicalize(payload))
