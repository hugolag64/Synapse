from types import SimpleNamespace


def test_build_focus_rows_prioritizes_overdue_then_next_session():
    from backend.core.planning.focus import build_focus_rows

    plans = [SimpleNamespace(total_min=30), SimpleNamespace(total_min=0)]
    tasks = [SimpleNamespace(days_overdue=2), SimpleNamespace(days_overdue=0)]
    rows = build_focus_rows(plans, tasks)
    assert [row["kind"] for row in rows] == ["overdue", "next_session", "free_slots"]
    assert rows[0]["value"] == 1
    assert rows[2]["value"] == 1


def test_focus_labels_are_actionable_and_stable():
    from backend.core.planning.focus import focus_row_label

    assert focus_row_label({"kind": "overdue", "value": 3}) == "3 révisions en retard"
    assert focus_row_label({"kind": "next_session", "value": 30}) == "Prochaine session recommandée · 30 min"
    assert focus_row_label({"kind": "free_slots", "value": 2}) == "2 créneaux libres à utiliser"


def test_review_focus_query_is_normalized_for_planning_context():
    from frontend.pages.planning_cockpit import _parse_focus_categories

    assert _parse_focus_categories("Cardiologie,  Infectieux,Cardiologie") == (
        "Cardiologie",
        "Infectieux",
    )


def test_planning_route_passes_review_focus_to_the_cockpit():
    from pathlib import Path

    main_source = Path("main.py").read_text(encoding="utf-8")
    page_source = Path("frontend/pages/planning.py").read_text(encoding="utf-8")

    assert "request.query_params.get(\"focus\")" in main_source
    assert "focus=focus" in page_source
