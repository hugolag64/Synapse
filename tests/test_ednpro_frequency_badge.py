import pytest


@pytest.mark.parametrize(("priority", "label"), [
    ("indispensable", "INDISPENSABLE"),
    ("important", "IMPORTANT"),
    ("basique", "BASIQUE"),
    ("jamais_tombe", "JAMAIS TOMBÉ"),
])
def test_frequency_badge_text_uses_priority_label(priority, label):
    from frontend.components.ednpro_frequency_badge import frequency_badge_text

    assert frequency_badge_text({"priority": priority}) == label


def test_frequency_badge_tooltip_includes_counts_and_years():
    from frontend.components.ednpro_frequency_badge import frequency_badge_tooltip

    assert frequency_badge_tooltip({
        "priority": "indispensable", "session_count": 13,
        "question_count": 31, "years": [2022, 2025],
    }) == "13 sessions · 31 questions · 2022, 2025"


def test_frequency_badge_tooltip_handles_singular_and_missing_frequency():
    from frontend.components.ednpro_frequency_badge import frequency_badge_tooltip

    assert frequency_badge_tooltip({
        "priority": "basique", "session_count": 1,
        "question_count": 1, "years": [],
    }) == "1 session · 1 question · années indisponibles"
    assert frequency_badge_tooltip(None) == "Fréquence EDNpro indisponible"
