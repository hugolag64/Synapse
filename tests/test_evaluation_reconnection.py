from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_classic_qcm_entry_uses_common_evaluation_facade():
    source = (ROOT / "frontend/pages/qcm.py").read_text(encoding="utf-8")
    assert "record_classic_qcm_result" in source
    assert "local_store.add_qcm_session_full(" not in source


def test_oic_entry_uses_common_evaluation_facade():
    source = (ROOT / "frontend/components/oic_eval_dialog.py").read_text(encoding="utf-8")
    assert "record_evaluation(" in source
    assert "item_service.save_item_oic_attempt(" not in source
