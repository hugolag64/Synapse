from pathlib import Path

import frontend.components.calendar_sources_panel as panel


def test_display_rows_uses_label_when_present():
    rows = panel._display_rows([{"id": "abc@x.com", "label": "Fac"}])
    assert rows == [{"id": "abc@x.com", "display_label": "Fac"}]


def test_display_rows_falls_back_to_id_when_label_is_empty():
    rows = panel._display_rows([{"id": "abc@x.com", "label": ""}])
    assert rows == [{"id": "abc@x.com", "display_label": "abc@x.com"}]


def test_display_rows_preserves_order():
    sources = [{"id": "a@x.com", "label": "A"}, {"id": "b@x.com", "label": "B"}]
    rows = panel._display_rows(sources)
    assert [row["id"] for row in rows] == ["a@x.com", "b@x.com"]


def test_settings_cockpit_renders_the_calendar_sources_panel():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert "render_calendar_sources" in source
    assert "calendar_sources_panel import render as render_calendar_sources" in source
