from pathlib import Path


SOURCE = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")


def test_today_termine_opens_shared_session_feedback_wizard():
    assert "open_session_feedback_dialog" in SOURCE
    assert "validate_fn=_on_done" in SOURCE


def test_today_keeps_full_feedback_fields_on_done_callback():
    assert "qcm_result=qcm_result" in SOURCE
    assert "weak_category=weak_category" in SOURCE
    assert "weak_detail=weak_detail" in SOURCE
