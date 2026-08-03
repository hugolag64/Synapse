from types import SimpleNamespace


def test_edn_insights_model_contains_progress_and_sprint_fields():
    from frontend.components.edn_insights_panel import edn_insights_model

    model = edn_insights_model(
        SimpleNamespace(
            days_remaining=73,
            target_date=SimpleNamespace(strftime=lambda _fmt: "15/10/2026"),
            phase=SimpleNamespace(value="consolidation"),
            covered_items=20,
            total_items=367,
            average_mastery=61.5,
            overdue_reviews=4,
            remaining_reviews=28,
        )
    )

    assert model["countdown"] == "J-73"
    assert model["coverage"] == "20/367"
    assert model["mastery"] == "61.5 %"
    assert model["overdue"] == "4"
