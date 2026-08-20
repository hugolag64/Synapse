"""La grille Planning ne fusionne plus consolidation dans 'due', et calcule
les blocs de prépa fac par jour (cf. spec §1/§2)."""
from pathlib import Path


def _source() -> str:
    return Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")


def test_consolidation_is_no_longer_merged_into_due():
    assert "due = due + consolidation_for_day" not in _source()


def test_plan_day_receives_consolidation_as_a_separate_pool():
    source = _source()
    assert "consolidation_tasks=consolidation_for_day" in source
    assert "consolidation_today=d" in source


def test_prep_tasks_are_fetched_and_aggregated_per_course():
    source = _source()
    assert "list_prep_tasks(day=d" in source
    assert "_slot_from_prep_tasks(" in source
