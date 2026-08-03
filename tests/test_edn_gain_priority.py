def test_gain_priority_explains_high_impact_item_first():
    from backend.core.edn.trajectory import rank_gain_potential

    ranked = rank_gain_potential(items=[
        {"item_number": "221", "edn_weight": 1.0, "mastery": 40, "error_count": 5, "available_questions": 20, "estimated_minutes": 30},
        {"item_number": "340", "edn_weight": 0.5, "mastery": 80, "error_count": 1, "available_questions": 4, "estimated_minutes": 60},
    ])

    assert ranked[0]["item_number"] == "221"
    assert ranked[0]["potential_score"] > ranked[1]["potential_score"]
    assert "mastery_gap" in ranked[0]["factors"]
    assert "error_recurrence" in ranked[0]["factors"]


def test_dashboard_gain_items_aggregates_courses_by_item():
    from frontend.pages.dashboard._cockpit_today import build_gain_items

    items = build_gain_items(
        courses=[
            type("Course", (), {"item_number": "221", "title": "A"})(),
            type("Course", (), {"item_number": "221", "title": "A bis"})(),
        ],
        tasks=[type("Task", (), {"item_number": "221", "mastery_score": 40})()],
        error_signals=[{"item_number": "221"}, {"item_number": "221"}],
    )

    assert len(items) == 1
    assert items[0]["item_number"] == "221"
    assert items[0]["mastery"] == 40
    assert items[0]["error_count"] == 2
