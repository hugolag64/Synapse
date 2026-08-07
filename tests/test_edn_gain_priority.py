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


def test_dashboard_gain_items_uses_frequency_priority_and_question_catalog(monkeypatch):
    from backend.core.reviews import local_store
    from frontend.pages.dashboard._cockpit_today import build_gain_items

    priorities = {"221": "indispensable", "340": "jamais_tombe"}
    availability = {"221": [{}, {}, {}], "340": [{}]}
    monkeypatch.setattr(
        local_store,
        "get_ednpro_item_frequency",
        lambda item_number: {"priority": priorities[item_number]},
    )
    monkeypatch.setattr(
        local_store,
        "get_ednpro_practice_questions",
        lambda item_number, limit=100: availability[item_number],
    )

    items = build_gain_items(
        courses=[
            type("Course", (), {"item_number": "221", "title": "A"})(),
            type("Course", (), {"item_number": "340", "title": "B"})(),
        ],
        tasks=[],
        error_signals=[],
    )
    by_item = {item["item_number"]: item for item in items}

    assert by_item["221"]["edn_weight"] > by_item["340"]["edn_weight"]
    assert by_item["221"]["available_questions"] == 3
    assert by_item["340"]["available_questions"] == 1


def test_gain_priority_uses_frequency_history_when_available():
    from backend.core.edn.trajectory import rank_gain_potential

    ranked = rank_gain_potential(items=[
        {
            "item_number": "221", "edn_weight": 1.0, "mastery": 40,
            "error_count": 0, "available_questions": 10,
            "frequency_sessions": 8, "estimated_minutes": 30,
        },
        {
            "item_number": "340", "edn_weight": 1.0, "mastery": 40,
            "error_count": 0, "available_questions": 10,
            "frequency_sessions": 1, "estimated_minutes": 30,
        },
    ])

    assert ranked[0]["item_number"] == "221"
    assert ranked[0]["factors"]["frequency_recurrence"] > ranked[1]["factors"]["frequency_recurrence"]
