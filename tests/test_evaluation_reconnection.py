from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_classic_qcm_entry_uses_common_evaluation_facade():
    cockpit_source = (ROOT / "frontend/pages/qcm_cockpit.py").read_text(encoding="utf-8")
    actions_source = (ROOT / "frontend/components/course_quick_actions.py").read_text(encoding="utf-8")
    assert "_open_quick_qcm_dialog" in cockpit_source
    assert "record_quick_qcm_result" in actions_source
    assert "record_evaluation(" in actions_source


def test_oic_entry_uses_common_evaluation_facade():
    source = (ROOT / "frontend/components/oic_eval_dialog.py").read_text(encoding="utf-8")
    assert "record_evaluation(" in source
    assert "item_service.save_item_oic_attempt(" not in source
