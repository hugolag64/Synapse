from types import SimpleNamespace

import frontend.components.dp_coverage_panel as panel


def test_coverage_rows_include_cross_college_course_membership(monkeypatch):
    monkeypatch.setattr(
        panel,
        "all_items",
        lambda: [{"item": 269, "title": "Douleur abdominale", "college": "HGE"}],
    )
    course = SimpleNamespace(
        item_number="269",
        college=["Dermatologie 🧴"],
        title="Douleur abdominale",
    )

    rows = panel._coverage_rows([course], {"269": 2})

    row = next(row for row in rows if row["item"] == 269)
    assert "Dermatologie 🧴" in row["colleges"]
    assert row["count"] == 2


def test_coverage_rows_deduplicate_course_aliases(monkeypatch):
    monkeypatch.setattr(
        panel,
        "all_items",
        lambda: [{"item": 269, "title": "Douleur abdominale", "college": "HGE"}],
    )
    courses = [
        SimpleNamespace(item_number="269", college=["Dermatologie 🧴"], title="Alias collège"),
        SimpleNamespace(item_number="269", college=["Dermatologie 🧴"], title="Alias UE"),
    ]

    rows = panel._coverage_rows(courses, {})

    assert [row["item"] for row in rows].count(269) == 1


def test_dp_coverage_css_uses_a_non_scrolling_grid():
    assert "grid-template-columns:56px minmax(0,1fr) 64px" in panel._CSS
    assert "overflow-x:hidden" in panel._CSS
