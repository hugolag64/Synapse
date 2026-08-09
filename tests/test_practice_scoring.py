from backend.core.practice.scoring import score_closed_attempt


def test_ranked_question_uses_official_edn_scale():
    result = score_closed_attempt(
        "A, B",
        [
            {"id": "A", "reponse_uness": True, "rank": "A"},
            {"id": "B", "reponse_uness": False, "rank": "B"},
        ],
    )

    assert result.score_percent == 50.0
    assert result.score_mode == "edn"
    assert result.propositions[1]["discordance"] == "exces"


def test_question_without_rank_still_uses_edn_mode():
    result = score_closed_attempt(
        "A",
        [
            {"id": "A", "reponse_uness": True},
            {"id": "B", "reponse_uness": False},
        ],
    )

    assert result.score_percent == 100.0
    assert result.score_mode == "edn"
    assert result.score_reason == ""


def test_score_closed_attempt_passes_qru_semantics():
    result = score_closed_attempt(
        "B",
        [
            {"id": "A", "reponse_uness": True},
            {"id": "B", "reponse_uness": False},
        ],
        question_kind="QRU",
    )

    assert result.score_percent == 0.0


def test_score_closed_attempt_applies_absolute_proposition_constraints():
    result = score_closed_attempt(
        "A",
        [{"id": "A", "reponse_uness": True}],
        indispensable_choices=["B"],
    )

    assert result.score_percent == 0.0
    assert result.score_reason == "indispensable_manquante"
