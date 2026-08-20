"""daily_budget_min est retiré ; ses deux usages pointent la vraie capacité —
sauf le tronquage, qui reste désactivé (cf. spec §3, décision explicite)."""
from pathlib import Path


def test_daily_budget_min_is_fully_removed():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert "daily_budget_min" not in source


def test_sprint_projection_uses_the_real_capacity():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert "capacity_from_preferences(data_store.preferences)" in source


def test_dashboard_trim_stays_disabled_without_a_day_override():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert 'budget = target.get("value", 0) if target.get("mode") == "minutes" else 0' in source
