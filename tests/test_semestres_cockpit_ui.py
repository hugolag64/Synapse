from types import SimpleNamespace

from frontend.pages.semestres_cockpit import _semester_advancement


def test_semester_advancement_counts_read_courses():
    courses = [
        SimpleNamespace(date_1ere_lecture="2026-08-01"),
        SimpleNamespace(date_1ere_lecture=None),
    ]
    assert _semester_advancement(courses) == {"done": 1, "total": 2, "percent": 50}


def test_semester_advancement_has_no_false_zero_for_empty_input():
    assert _semester_advancement([]) == {"done": 0, "total": 0, "percent": None}


def test_semester_subtitle_names_avancement_explicitly():
    source = open("frontend/pages/semestres_cockpit.py", encoding="utf-8").read()
    assert "Avancement par UE / semestre" in source
    assert "Progression par UE / semestre" not in source
