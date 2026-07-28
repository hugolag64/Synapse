from pathlib import Path


def test_course_detail_always_exposes_pdf_repair():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "Modifier le PDF" in source


def test_today_context_panel_exposes_pdf_repair():
    source = Path("frontend/components/context_panel.py").read_text(encoding="utf-8")
    assert "Modifier le PDF" in source


def test_classic_course_card_exposes_pdf_repair_for_existing_pdf():
    source = Path("frontend/components/course_card.py").read_text(encoding="utf-8")
    assert "Modifier le PDF" in source
