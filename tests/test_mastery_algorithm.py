from backend.core.reviews.mastery import _qcm_score_quality


def test_mastery_qcm_quality_accepts_a_valid_fraction():
    assert _qcm_score_quality(None, "18/20") == 0.9


def test_mastery_qcm_quality_treats_an_impossible_fraction_as_neutral():
    assert _qcm_score_quality(None, "21/20") == 0.5
