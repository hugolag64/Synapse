from frontend.pages.weak_points_cockpit import filter_weak_points_view


def test_points_faibles_vue_separe_lacunes_ancrages_et_resolues():
    rows = [
        {"id": 1, "status": "active", "severity": 2, "recurrence_count": 0},
        {"id": 2, "status": "récurrente", "severity": 3, "recurrence_count": 2},
        {"id": 3, "status": "résolue", "severity": 4, "recurrence_count": 2},
    ]

    assert [r["id"] for r in filter_weak_points_view(rows, "lacunes")] == [1]
    assert [r["id"] for r in filter_weak_points_view(rows, "anchors")] == [2]
    assert [r["id"] for r in filter_weak_points_view(rows, "resolved")] == [3]
