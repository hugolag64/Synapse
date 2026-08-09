from backend.core.analytics.weekly_report import _qcm_pass_rate


def test_qcm_pass_rate_counts_successful_sessions_not_average_score():
    assert _qcm_pass_rate([80, 60]) == 50.0


def test_qcm_pass_rate_ignores_invalid_scores():
    assert _qcm_pass_rate([105, -5, None, 70]) == 100.0
    assert _qcm_pass_rate([105, -5, None]) is None
