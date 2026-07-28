from frontend.components.forgetting_curve import project_score


def test_project_score_uses_adaptive_stability():
    assert project_score(80, 60, 120, stability_days=120) > project_score(80, 60, 7, stability_days=7)


def test_project_score_uses_shared_floor():
    assert project_score(80, 10_000, 7, stability_days=7) >= 25


def test_project_score_fallback_clamps_low_scores_to_shared_floor():
    assert project_score(10, 30, 7) == 25
