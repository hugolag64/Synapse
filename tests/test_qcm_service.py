from backend.core.qcm.service import parse_score


def test_parse_score_accepts_a_complete_fraction():
    assert parse_score("20/20") == (100.0, "20/20")


def test_parse_score_rejects_an_impossible_fraction():
    assert parse_score("21/20") == (None, None)
