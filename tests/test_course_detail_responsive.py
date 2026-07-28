from pathlib import Path


DETAIL = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")


def test_course_detail_uses_shared_responsive_drawer_contract():
    assert "responsive_drawer" in DETAIL
    assert "synapse-responsive-drawer" in DETAIL


def test_course_detail_keeps_context_panel_class():
    assert "ci-panel" in DETAIL
