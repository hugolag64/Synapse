from backend.core.practice.scoring import (
    compute_question_score_edn,
    compute_session_edn_score,
    score_closed_attempt,
    score_qroc_response,
    score_tcs_attempt,
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


def test_session_excludes_non_noted_questions_from_denominator():
    summary = compute_session_edn_score(
        [
            {"score": 1.0},
            {"score": 0.0, "score_mode": "not_noted"},
        ]
    )

    assert summary["total_questions"] == 2
    assert summary["noted_questions"] == 1
    assert summary["excluded_questions"] == 1
    assert summary["score_20"] == 20.0


def test_session_rank_a_validity_uses_only_official_rank_a_formats():
    summary = compute_session_edn_score(
        [
            {"score": 1.0, "rank": "A", "question_kind": "QRU"},
            {"score": 0.0, "rank": "A", "question_kind": "QRM"},
            {"score": 0.0, "rank": "B", "question_kind": "QRU"},
        ]
    )

    assert summary["score_20"] == 6.67
    assert summary["rang_a_score_20"] == 20.0
    assert summary["rang_a_status"] == "calculable"
    assert summary["valide_rang_a"] is True


def test_session_rank_a_is_not_calculable_when_no_eligible_rank_a_question_exists():
    summary = compute_session_edn_score([{"score": 1.0, "rank": "B", "question_kind": "QRU"}])

    assert summary["rang_a_score_20"] is None
    assert summary["rang_a_status"] == "non_calculable"
    assert summary["valide_rang_a"] is False


def test_qrp_uses_x_over_n_with_indispensable_and_inacceptable_guards():
    choices = [
        {"id": "A", "reponse_uness": True},
        {"id": "B", "reponse_uness": False},
        {"id": "C", "reponse_uness": True},
    ]

    assert score_closed_attempt("A, C", choices, question_kind="QRP").score_percent == 100.0
    assert score_closed_attempt("A, B", choices, question_kind="QRP").score_percent == 50.0


def test_qrp_long_and_qzp_count_only_expected_targets():
    choices = [
        {"id": "A", "reponse_uness": True},
        {"id": "B", "reponse_uness": False},
        {"id": "C", "reponse_uness": True},
        {"id": "D", "reponse_uness": False},
    ]

    assert score_closed_attempt("A, B", choices, question_kind="QRP_LONG").score_percent == 50.0
    assert score_closed_attempt("A, B", choices, question_kind="QZP").score_percent == 50.0


def test_tcs_uses_panel_ratio_and_qroc_has_exact_and_acceptable_bands():
    tcs = score_tcs_attempt(
        "A",
        [
            {"id": "A", "tcs_panel_count": 2},
            {"id": "B", "tcs_panel_count": 13},
        ],
    )
    assert round(tcs.score_percent, 2) == round(2 / 13 * 100, 2)

    assert score_qroc_response("exact", exact_answers=["exact"], acceptable_answers=[]).score_percent == 100.0
    assert score_qroc_response("acceptable", exact_answers=[], acceptable_answers=["acceptable"]).score_percent == 50.0
    assert score_qroc_response("other", exact_answers=[], acceptable_answers=[]).score_mode == "not_noted"
