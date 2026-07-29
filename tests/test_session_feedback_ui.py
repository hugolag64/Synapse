from types import SimpleNamespace
from pathlib import Path

from frontend.components.session_feedback_ui import (
    confidence_label,
    default_feedback_state,
    qcm_activity_ids,
)


def _task(review_type="qcm_error"):
    return SimpleNamespace(review_type=review_type)


def test_default_state_prefills_qcm_error_context():
    state = default_feedback_state(_task("qcm_error"), None, None)

    assert state["activity_types"] == ["qcm", "correction"]
    assert state["qcm_result"] == "raté"


def test_confidence_labels_are_understandable_without_emoji():
    assert confidence_label(1) == "Très incertain"
    assert confidence_label(5) == "Très solide"


def test_qcm_fields_are_limited_to_qcm_activities():
    assert qcm_activity_ids() == frozenset({"qcm", "dp_kfp"})


def test_session_feedback_uses_linear_panel_structure():
    source = Path("frontend/pages/dashboard/_dialogs.py").read_text(encoding="utf-8")

    assert "Comment s'est passée cette séance ?" in source
    assert "Détails avancés" in source
    assert "Valider la séance" in source
    assert "Très incertain" in source
    assert "emoji" not in source.lower()


def test_expanded_feedback_keeps_footer_visible_and_avoids_duplicate_item_prefix():
    source = Path("frontend/pages/dashboard/_dialogs.py").read_text(encoding="utf-8")

    assert "max-h-[calc(100vh-24px)]" in source
    assert "flex-1 min-h-0 overflow-y-auto" in source
    assert "shrink-0 sticky bottom-0" in source
    assert "ITEM {task.item_number or '—'} · {task.label}" not in source
