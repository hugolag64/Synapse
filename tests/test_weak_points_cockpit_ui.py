from frontend.pages.weak_points_cockpit import _weak_point_summary


def _row(status="active", severity=2, source_type="manuel"):
    return {"status": status, "severity": severity, "source_type": source_type}


def test_weak_point_summary_counts_status_severity_and_sources():
    summary = _weak_point_summary([
        _row("active", 5, "qcm"),
        _row("active", 2, "manuel"),
        _row("à revoir", 3, "note"),
        _row("récurrente", 4, "qcm"),
        _row("résolue", 5, "manuel"),
    ])

    assert summary["total"] == 5
    assert summary["open"] == 4
    assert summary["critical"] == 2
    assert summary["status_counts"] == {"active": 2, "à revoir": 1, "récurrente": 1, "résolue": 1}
    assert summary["source_counts"] == {"qcm": 2, "manuel": 2, "note": 1}


def test_weak_point_cockpit_uses_interactive_cards_and_full_width_panel():
    source = open("frontend/pages/weak_points_cockpit.py", encoding="utf-8").read()

    assert "WeakPointCard(w, on_refresh=_render)" in source
    assert "Créer une lacune" in source
    assert ".wp-content { min-width:0; max-width:none; width:100%; }" in source
    assert "Pilotage des lacunes" in source
