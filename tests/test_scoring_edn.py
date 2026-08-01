import pytest

from backend.core.practice.scoring import (
    compute_question_score_edn,
    compute_session_edn_score,
)


def test_qrm_discordances_scoring():
    # 0 discordance -> 1.0 pt
    res = compute_question_score_edn(["A", "B"], ["A", "B"])
    assert res["score"] == 1.0
    assert res["discordances"] == 0

    # 1 discordance -> 0.5 pt
    res = compute_question_score_edn(["A"], ["A", "B"])
    assert res["score"] == 0.5
    assert res["discordances"] == 1

    # 2 discordances -> 0.2 pt
    res = compute_question_score_edn(["A", "C"], ["A", "B"])
    assert res["score"] == 0.2
    assert res["discordances"] == 2

    # 3 discordances -> 0.0 pt
    res = compute_question_score_edn(["C", "D"], ["A"])
    assert res["score"] == 0.0
    assert res["discordances"] == 3


def test_indispensable_penalty():
    # 'A' est indispensable, mais l'utilisateur coche seulement 'B'
    res = compute_question_score_edn(["B"], ["A", "B"], indispensable_choices=["A"])
    assert res["score"] == 0.0
    assert res["zero_reason"] == "indispensable_manquante"
    assert "A" in res["missing_indispensables"]


def test_inacceptable_penalty():
    # 'C' est inacceptable, et l'utilisateur l'a coché avec 'A'
    res = compute_question_score_edn(["A", "C"], ["A"], inacceptable_choices=["C"])
    assert res["score"] == 0.0
    assert res["zero_reason"] == "inacceptable_cochee"
    assert "C" in res["selected_inacceptables"]


def test_session_edn_scoring():
    questions = [
        {"score": 1.0},
        {"score": 0.5},
        {"score": 1.0},
        {"score": 0.2},
    ]
    # Total = 2.7 / 4.0 = 67.5% -> 13.5 / 20 -> Non validé Rang A (< 14)
    summary = compute_session_edn_score(questions)
    assert summary["score_20"] == 13.5
    assert summary["valide_rang_a"] is False

    # 4/4 -> 20/20 -> Validé Rang A
    summary_perfect = compute_session_edn_score([{"score": 1.0}] * 4)
    assert summary_perfect["score_20"] == 20.0
    assert summary_perfect["valide_rang_a"] is True
