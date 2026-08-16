"""Moteur de calcul du score docimologique officiel EDN (R2C).

Fournit les fonctions de calcul de discordances, pénalités pour indispensables / inacceptables,
et conversion des notes sur 20 avec seuil de validation Rang A.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


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
            official = raw.get("reponse_uness", raw.get("is_correct", raw.get("correct", False)))
            expected = official is True
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


def score_qroc_response(
    response: str,
    *,
    exact_answers: Sequence[str],
    acceptable_answers: Sequence[str],
) -> ScoredAttempt:
    """Score a QROC only when the official exact/acceptable lists exist."""
    normalized = str(response or "").strip().casefold()
    exact = {str(value).strip().casefold() for value in exact_answers if str(value).strip()}
    acceptable = {str(value).strip().casefold() for value in acceptable_answers if str(value).strip()}
    if not exact and not acceptable:
        return ScoredAttempt(0.0, "not_noted", "correction_officielle_incomplete", [])
    score = 1.0 if normalized in exact else 0.5 if normalized in acceptable else 0.0
    return ScoredAttempt(score * 100.0, "edn", "" if score else "mauvaise_reponse", [])


def score_tcs_attempt(response: str, choices: Sequence[object]) -> ScoredAttempt:
    """Score a TCS from official panel counts using the modal-panel ratio."""
    rows = [row for row in choices if isinstance(row, dict)]
    counts = [int(row["tcs_panel_count"]) for row in rows if row.get("tcs_panel_count") is not None]
    if not rows or not counts:
        return ScoredAttempt(0.0, "not_noted", "panel_tcs_incomplet", [])
    normalized = str(response or "").strip().casefold()
    selected = next((row for row in rows if str(row.get("id") or row.get("label") or "").strip().casefold() == normalized), None)
    if selected is None or selected.get("tcs_panel_count") is None:
        return ScoredAttempt(0.0, "edn", "mauvaise_reponse", [])
    modal = max(counts)
    score = min(1.0, max(0.0, int(selected["tcs_panel_count"]) / modal))
    return ScoredAttempt(score * 100.0, "edn", "", [])


def score_closed_attempt(
    response: str,
    choices: Sequence[object],
    answer: str = "",
    question_kind: str = "QRM",
    indispensable_choices: Sequence[str] | set[str] | None = None,
    inacceptable_choices: Sequence[str] | set[str] | None = None,
    expected_choice_count: int | None = None,
) -> ScoredAttempt:
    """Score côté serveur et expose une correction propositionnelle stable."""
    official_fields = [
        raw.get("reponse_uness")
        for raw in choices
        if isinstance(raw, dict) and "reponse_uness" in raw
    ]
    if official_fields and any(value is None for value in official_fields):
        normalized_choices = _choice_data(choices)
        selected = _selected_ids(response, normalized_choices)
        return ScoredAttempt(
            score_percent=0.0,
            score_mode="not_noted",
            score_reason="correction_officielle_incomplete",
            propositions=[
                {
                    "proposition_id": choice["id"],
                    "selected": choice["id"] in selected,
                    "expected": None,
                    "rank": choice["rank"],
                    "points": 0.0,
                    "discordance": "non_notee",
                }
                for choice in normalized_choices
            ],
        )
    normalized_choices = _choice_data(choices)
    selected = _selected_ids(response, normalized_choices)
    expected = {choice["id"] for choice in normalized_choices if choice["expected"]}
    if not expected and answer:
        expected = _selected_ids(answer, normalized_choices)
    score = compute_question_score_edn(
        selected,
        expected,
        question_kind=question_kind,
        indispensable_choices=indispensable_choices,
        inacceptable_choices=inacceptable_choices,
        expected_choice_count=expected_choice_count,
    )
    propositions = []
    for choice in normalized_choices:
        is_selected = choice["id"] in selected
        is_expected = choice["id"] in expected
        propositions.append({
            "proposition_id": choice["id"],
            "selected": is_selected,
            "expected": is_expected,
            "rank": choice["rank"],
            "points": 1.0 if is_selected == is_expected else 0.0,
            "discordance": "correct" if is_selected == is_expected else ("omission" if is_expected else "exces"),
        })
    return ScoredAttempt(
        score_percent=float(score["score"]) * 100.0,
        score_mode="edn",
        score_reason=str(score.get("zero_reason") or ""),
        propositions=propositions,
    )


def compute_question_score_edn(
    user_choices: Sequence[str] | set[str],
    correct_choices: Sequence[str] | set[str],
    question_kind: str = "QRM",
    indispensable_choices: Sequence[str] | set[str] | None = None,
    inacceptable_choices: Sequence[str] | set[str] | None = None,
    all_choices: Sequence[str] | None = None,
    expected_choice_count: int | None = None,
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

    if kind_upper in {"QRP", "QRP_LONG", "QRP/L", "QZP"}:
        denominator = int(expected_choice_count or len(correct_set))
        if denominator <= 0 or len(user_set) > denominator or (kind_upper == "QZP" and len(user_set) > 5):
            return {
                "score": 0.0,
                "raw_score": 0.0,
                "discordances": len(correct_set ^ user_set),
                "zero_reason": "contrainte_reponses_invalide",
                "missing_indispensables": [],
                "selected_inacceptables": [],
            }
        score = len(user_set & correct_set) / denominator
        return {
            "score": score,
            "raw_score": score,
            "discordances": len(correct_set ^ user_set),
            "zero_reason": None if score else "mauvaise_reponse",
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
    total_questions = len(question_results)
    noted_results = [
        question
        for question in question_results
        if question.get("score_mode") != "not_noted" and question.get("noted", True) is not False
    ]
    excluded_questions = total_questions - len(noted_results)
    eligible_rank_a_kinds = {"QRU", "QRP", "QRP_LONG", "QRP/L", "QZP", "QROC"}
    has_rank_metadata = any("rank" in question or "rang" in question for question in noted_results)
    rank_a_results = [
        question
        for question in noted_results
        if str(question.get("rank", question.get("rang", ""))).strip().upper() == "A"
        and str(question.get("question_kind", question.get("type_question", ""))).strip().upper()
        in eligible_rank_a_kinds
    ]
    if not noted_results:
        return {
            "score_20": 0.0,
            "total_questions": total_questions,
            "noted_questions": 0,
            "excluded_questions": excluded_questions,
            "total_points": 0.0,
            "max_points": 0.0,
            "score_percent": 0.0,
            "valide_rang_a": False,
            "rang_a_score_20": None,
            "rang_a_status": "non_calculable",
        }

    total_points = sum(float(q.get("score", 0.0)) for q in noted_results)
    max_points = float(len(noted_results))
    score_percent = (total_points / max_points * 100.0) if max_points > 0 else 0.0
    score_20 = round((total_points / max_points) * 20.0, 2) if max_points > 0 else 0.0

    # Le seuil validant Rang A ne porte que sur les formats Rang A prévus par
    # la docimologie R2C. Les sessions historiques dépourvues de métadonnées
    # gardent l'ancien calcul global pour rester rétrocompatibles.
    if has_rank_metadata:
        rang_a_points = sum(float(question.get("score", 0.0)) for question in rank_a_results)
        rang_a_max = float(len(rank_a_results))
        rang_a_score_20 = round((rang_a_points / rang_a_max) * 20.0, 2) if rang_a_max else None
        valide_rang_a = rang_a_score_20 is not None and rang_a_score_20 >= 14.0
        rang_a_status = "calculable" if rang_a_score_20 is not None else "non_calculable"
    else:
        rang_a_score_20 = score_20
        valide_rang_a = score_20 >= 14.0
        rang_a_status = "legacy"

    return {
        "score_20": score_20,
        "total_questions": total_questions,
        "noted_questions": len(noted_results),
        "excluded_questions": excluded_questions,
        "total_points": round(total_points, 2),
        "max_points": max_points,
        "score_percent": round(score_percent, 1),
        "valide_rang_a": valide_rang_a,
        "rang_a_score_20": rang_a_score_20,
        "rang_a_status": rang_a_status,
    }
