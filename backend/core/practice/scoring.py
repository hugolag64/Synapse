"""Moteur de calcul du score docimologique officiel EDN (R2C).

Fournit les fonctions de calcul de discordances, pénalités pour indispensables / inacceptables,
et conversion des notes sur 20 avec seuil de validation Rang A.
"""

from __future__ import annotations

from typing import Any, Sequence


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
