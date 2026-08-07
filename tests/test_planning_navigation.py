"""Les blocs Synapse de la grille Planning ouvrent leur cible au clic."""
from pathlib import Path

from frontend.pages.planning_cockpit import block_target


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
