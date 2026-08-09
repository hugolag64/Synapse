from pathlib import Path

from frontend.pages.stats_cockpit import _compute_learning_summary


class _Course:
    def __init__(self, course_id, *, colleges=(), read=False):
        self.id = course_id
        self.college = list(colleges)
        self.date_1ere_lecture = object() if read else None


class _Snapshot:
    def __init__(self, mastery, retention):
        self.score = mastery
        self.retention_score = retention


def test_statistics_navigation_uses_explicit_title():
    stats_source = Path("frontend/pages/stats.py").read_text(encoding="utf-8")
    dashboard_source = Path("frontend/pages/dashboard/_dialogs.py").read_text(encoding="utf-8")
    shell_source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert 'with frame("Statistiques")' in stats_source
    assert "Voir mes statistiques" in dashboard_source
    assert '"Statistiques": "Statistiques"' in shell_source


def test_item_surfaces_do_not_use_generic_progression_label_for_learning_metrics():
    items_source = Path("frontend/pages/items.py").read_text(encoding="utf-8")
    detail_source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    stats_source = Path("frontend/pages/stats.py").read_text(encoding="utf-8")

    assert 'ui.label("Progression")' not in items_source
    assert 'ui.label("Progression")' not in detail_source
    assert 'ui.label("Progression des objectifs")' in stats_source


def test_statistics_summary_keeps_advancement_mastery_and_retention_separate():
    courses = [
        _Course("c1", colleges=("Cardio",), read=True),
        _Course("c2", colleges=("Cardio",)),
        _Course("c3", colleges=("Neuro",)),
    ]
    snapshots = [
        (_Snapshot(80, 65), courses[0]),
        (_Snapshot(None, None), courses[1]),
        (_Snapshot(40, 35), courses[2]),
    ]

    summary = _compute_learning_summary(
        courses,
        snapshots,
        validated_colleges={"Neuro"},
    )

    assert summary["advancement"] == {"done": 2, "total": 3, "percent": 67}
    assert summary["mastery"] == {"score": 60, "level": None}
    assert summary["retention"]["score"] == 50


def test_statistics_summary_does_not_fabricate_zero_for_empty_metrics():
    summary = _compute_learning_summary([], [])

    assert summary["advancement"] == {"done": 0, "total": 0, "percent": None}
    assert summary["mastery"]["score"] is None
    assert summary["retention"]["score"] is None
