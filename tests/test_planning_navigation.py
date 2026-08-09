"""Les blocs Synapse de la grille Planning ouvrent leur cible au clic."""
from pathlib import Path

from frontend.pages.planning_cockpit import block_target, event_display_title


def test_review_block_opens_the_course_sheet():
    assert block_target("review", "c1") == "/cours/c1"
    assert block_target("review_urgent", "c1") == "/cours/c1"
    assert block_target("consolidation", "c1") == "/cours/c1"


def test_lacune_blocks_open_the_weak_points_view():
    assert block_target("lacune", "c1") == "/lacunes"
    assert block_target("lacune_crit", "c1") == "/lacunes"


def test_block_without_a_course_is_not_navigable():
    assert block_target("review", None) is None
    assert block_target("review", "") is None


def test_day_cells_wire_the_click_handler():
    source = Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")

    assert "block_target(" in source
    assert "pl-block-clickable" in source


def test_event_display_title_prefixes_labeled_source():
    ev = {"summary": "Cours de sémiologie", "_synapse_source_label": "Fac"}
    assert event_display_title(ev) == "Fac · Cours de sémiologie"


def test_event_display_title_returns_summary_when_unlabeled():
    ev = {"summary": "Rendez-vous perso", "_synapse_source_label": ""}
    assert event_display_title(ev) == "Rendez-vous perso"


def test_event_display_title_defaults_missing_summary():
    ev = {"_synapse_source_label": ""}
    assert event_display_title(ev) == "Événement"


def test_day_events_use_the_display_title_helper():
    source = Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")

    assert "event_display_title(ev)" in source
