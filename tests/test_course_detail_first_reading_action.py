from pathlib import Path


SOURCE = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")


def test_detail_offers_start_study_when_first_reading_is_missing():
    assert "Commencer l'étude" in SOURCE
    assert "open_start_tracking_dialog" in SOURCE


def test_detail_keeps_due_review_action():
    assert "Réviser maintenant" in SOURCE


def test_a_known_item_gets_a_consolidation_label_instead_of_commencer():
    """Un item avec un score déjà présent (déclaré ou mesuré) est déjà connu :
    « Commencer l'étude » mentirait en prétendant une première lecture
    aujourd'hui — même action (`_anchor_cycle`), libellé honnête."""
    assert '"Planifier une révision" if score is not None else "Commencer l\'étude"' in SOURCE
    assert "ne compte pas comme une première lecture" in SOURCE
