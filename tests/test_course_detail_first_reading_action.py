from pathlib import Path


SOURCE = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")


def test_detail_offers_start_study_when_first_reading_is_missing():
    assert "Commencer l'étude" in SOURCE
    assert "open_start_tracking_dialog" in SOURCE


def test_detail_keeps_due_review_action():
    assert "Réviser maintenant" in SOURCE
