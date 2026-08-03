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


def test_question_without_rank_is_explicitly_training():
    result = score_closed_attempt(
        "A",
        [
            {"id": "A", "reponse_uness": True},
            {"id": "B", "reponse_uness": False},
        ],
    )

    assert result.score_percent == 100.0
    assert result.score_mode == "training"
    assert "rang" in result.score_reason.lower()
