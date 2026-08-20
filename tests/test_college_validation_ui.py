from pathlib import Path


def test_college_cockpit_exposes_hybrid_validation_state_and_action():
    source = Path("frontend/pages/colleges_cockpit.py").read_text(encoding="utf-8")

    assert "assess_college_validation" in source
    assert "automatic_ready" in source
    assert "get_all_college_statuses" in source
    assert "confirm_college_validation" in source
    assert "missing_evidence_ids" in source
    assert "completed_j_cycle_ids" in source
    assert "Valider manuellement" in source
