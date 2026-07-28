def test_weak_point_cockpit_uses_row_component_and_centered_column():
    source = open("frontend/pages/weak_points_cockpit.py", encoding="utf-8").read()

    assert "weak_point_row(w, on_refresh=_render)" in source
    assert ".wp-wrap { width:860px; max-width:100%; margin:0 auto;" in source
    assert '"wp-chip active" if state["view"] == key else "wp-chip"' in source
    assert "Créer une lacune" in source
    assert "WeakPointCard" not in source
    assert "Pilotage des lacunes" not in source
    assert "_weak_point_summary" not in source
