"""Moteur de calcul du score docimologique officiel EDN (R2C).

Fournit les fonctions de calcul de discordances, pénalités pour indispensables / inacceptables,
et conversion des notes sur 20 avec seuil de validation Rang A.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class ScoredAttempt:
    score_percent: float
    score_mode: str
    score_reason: str
    propositions: list[dict[str, Any]]


def _choice_data(choices: Sequence[object]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(choices):
        if isinstance(raw, dict):
            identifier = str(raw.get("id") or raw.get("label") or chr(ord("A") + index)).strip().upper()
            text = str(raw.get("texte") or raw.get("text") or raw.get("label") or identifier)
            expected = bool(raw.get("reponse_uness", raw.get("is_correct", raw.get("correct", False))))
            rank = str(raw.get("rank") or raw.get("rang") or "").strip().upper()
        else:
            identifier = chr(ord("A") + index)
            text = str(raw)
            expected = False
            rank = ""
        result.append({"id": identifier, "text": text, "expected": expected, "rank": rank})
    return result


def _selected_ids(response: str, choices: list[dict[str, Any]]) -> set[str]:
    try:
        parsed = json.loads(str(response or ""))
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, list):
        tokens = [str(value).strip() for value in parsed]
    else:
        tokens = [part.strip() for part in re.split(r"[,;|/]", str(response or "")) if part.strip()]
    selected: set[str] = set()
    for token in tokens:
        normalized = token.casefold()
        match = next(
            (choice["id"] for choice in choices if normalized in {choice["id"].casefold(), choice["text"].casefold()}),
            None,
        )
        if match:
            selected.add(match)
    return selected


def score_closed_attempt(response: str, choices: Sequence[object], answer: str = "") -> ScoredAttempt:
    """Score côté serveur et expose une correction propositionnelle stable."""
    normalized_choices = _choice_data(choices)
    selected = _selected_ids(response, normalized_choices)
    expected = {choice["id"] for choice in normalized_choices if choice["expected"]}
    if not expected and answer:
        expected = _selected_ids(answer, normalized_choices)
    score = compute_question_score_edn(selected, expected)
    propositions = []
    for choice in normalized_choices:
        is_selected = choice["id"] in selected
        is_expected = choice["id"] in expected
        propositions.append({
            "proposition_id": choice["id"],
            "selected": is_selected,
            "expected": is_expected,
            "rank": choice["rank"],
            "points": float(score["score"]) if is_selected == is_expected else 0.0,
            "discordance": "correct" if is_selected == is_expected else ("omission" if is_expected else "exces"),
        })
    return ScoredAttempt(
        score_percent=float(score["score"]) * 100.0,
        score_mode="edn",
        score_reason="",
        propositions=propositions,
    )


def compute_question_score_edn(
    user_choices: Sequence[str] | set[str],
    correct_choices: Sequence[str] | set[str],
    question_kind: str = "QRM",
    indispensable_choices: Sequence[str] | set[str] | None = None,
    inacceptable_choices: Sequence[str] | set[str] | None = None,
    all_choices: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Calcule le score docimologique d'une question selon les règles EDN R2C.

    Règles pour QRM / QRP (questions à choix multiples) :
    - 0 discordance = 1.0 pt
    - 1 discordance = 0.5 pt
    - 2 discordances = 0.2 pt
    - 3+ discordances = 0.0 pt

    Penalités absolues :
    - Si une proposition indispensable n'est pas cochée par l'élève -> 0 pt
    - Si une proposition inacceptable est cochée par l'élève -> 0 pt

    Règles pour QRU (choix unique) :
    - 1.0 pt si la bonne réponse est choisie, sinon 0 pt.
    """
    user_set = set(user_choices)
    correct_set = set(correct_choices)
    indisp_set = set(indispensable_choices or [])
    inacc_set = set(inacceptable_choices or [])

    # Vérification des pénalités absolues
    # 1. Indispensable non cochée ?
    missing_indispensables = indisp_set - user_set
    if missing_indispensables:
        return {
            "score": 0.0,
            "raw_score": 0.0,
            "discordances": len(correct_set ^ user_set),
            "zero_reason": "indispensable_manquante",
            "missing_indispensables": list(missing_indispensables),
            "selected_inacceptables": [],
        }

    # 2. Inacceptable cochée ?
    selected_inacceptables = inacc_set & user_set
    if selected_inacceptables:
        return {
            "score": 0.0,
            "raw_score": 0.0,
            "discordances": len(correct_set ^ user_set),
            "zero_reason": "inacceptable_cochee",
            "missing_indispensables": [],
            "selected_inacceptables": list(selected_inacceptables),
        }

    kind_upper = str(question_kind).upper()
    if kind_upper in {"QRU", "SINGLE"}:
        is_correct = user_set == correct_set and len(user_set) > 0
        return {
            "score": 1.0 if is_correct else 0.0,
            "raw_score": 1.0 if is_correct else 0.0,
            "discordances": 0 if is_correct else 1,
            "zero_reason": None if is_correct else "mauvaise_reponse",
            "missing_indispensables": [],
            "selected_inacceptables": [],
        }

    # Calcul des discordances (différence symétrique entre réponses données et réponses exactes)
    discordances = len(correct_set ^ user_set)

    if discordances == 0:
        score = 1.0
    elif discordances == 1:
        score = 0.5
    elif discordances == 2:
        score = 0.2
    else:
        score = 0.0

    return {
        "score": score,
        "raw_score": score,
        "discordances": discordances,
        "zero_reason": None if score > 0 else "trop_de_discordances",
        "missing_indispensables": [],
        "selected_inacceptables": [],
    }


def compute_session_edn_score(
    question_results: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Calcule le score global d'un partiel / session sur 20 et le rang de réussite."""
    if not question_results:
        return {
            "score_20": 0.0,
            "total_questions": 0,
            "total_points": 0.0,
            "max_points": 0.0,
            "score_percent": 0.0,
            "valide_rang_a": False,
        }

    total_points = sum(float(q.get("score", 0.0)) for q in question_results)
    max_points = float(len(question_results))
    score_percent = (total_points / max_points * 100.0) if max_points > 0 else 0.0
    score_20 = round((total_points / max_points) * 20.0, 2) if max_points > 0 else 0.0

    # Validé si Note / 20 >= 14.0 (correspond aux 70% requis EDN Rang A)
    valide_rang_a = score_20 >= 14.0

    return {
        "score_20": score_20,
        "total_questions": len(question_results),
        "total_points": round(total_points, 2),
        "max_points": max_points,
        "score_percent": round(score_percent, 1),
        "valide_rang_a": valide_rang_a,
    }
