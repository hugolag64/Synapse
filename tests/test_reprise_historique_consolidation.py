"""Tests du rapport et de la sélection idempotente de la reprise historique."""
from types import SimpleNamespace

import deploy.reprise_historique_consolidation as reprise


def _course(course_id: str, *colleges: str):
    return SimpleNamespace(id=course_id, college=list(colleges))


def test_target_colleges_are_exactly_the_ten_validated_legacy_colleges():
    assert len(reprise.TARGET_COLLEGES) == 10
    assert "Hépato-Gastro-entérologie 🧻" in reprise.TARGET_COLLEGES
    assert "Pneumologie 🫁" in reprise.TARGET_COLLEGES


def test_build_report_counts_courses_and_missing_states():
    courses = [
        _course("c1", "Cardiovasculaire ❤️"),
        _course("c2", "Pneumologie 🫁"),
        _course("outside", "Médecine générale"),
    ]
    report = reprise.build_report(
        courses,
        states={"c1": SimpleNamespace(declared_level="flou")},
        college_statuses={"Cardiovasculaire ❤️": "valide"},
    )

    assert report["target_course_count"] == 2
    assert report["target_course_assignment_count"] == 2
    assert report["missing_item_state_count"] == 1
    assert report["missing_item_state_ids"] == ["c2"]
    assert "Pneumologie 🫁" in report["colleges_needing_validation"]


def test_missing_state_selection_becomes_empty_after_second_plan():
    courses = [_course("c1", "Cardiovasculaire ❤️"), _course("c2", "Dermatologie 🧴")]
    statuses = {college: "valide" for college in reprise.TARGET_COLLEGES}
    first = reprise.get_missing_state_course_ids(courses, states={}, college_statuses=statuses)
    assert first == ["c1", "c2"]

    states = {course_id: SimpleNamespace(declared_level="correct") for course_id in first}
    second = reprise.get_missing_state_course_ids(courses, states, college_statuses=statuses)
    assert second == []
