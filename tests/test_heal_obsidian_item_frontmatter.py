from datetime import datetime
from pathlib import Path

from backend.core.notion.models import Cours


def _make_cours(**kwargs) -> Cours:
    defaults = dict(
        id="notion-id-221",
        title="Méningite",
        item_number="221",
        item_lie=None,
        college=[],
        semestre=None,
        ue_id=None,
        created_time=datetime(2024, 1, 1),
        nb_lectures=0,
    )
    defaults.update(kwargs)
    return Cours(**defaults)


_NOTE_WITH_EMPTY_ITEM = """---
notion_id: notion-id-221
synapse_id: syn-221
item:
college:
  - Cardiovasculaire ❤️
tags:
  - cours
  - edn
---
# ITEM 221 – Méningite

Contenu du cours, jamais touché.
"""

_NOTE_WITH_FILLED_ITEM = """---
notion_id: notion-id-340
item: 340
---
# ITEM 340 – Déjà correct
"""

_NOTE_WITH_UNKNOWN_NOTION_ID = """---
notion_id: does-not-exist
item:
---
# Note orpheline sans correspondance
"""


def test_note_with_known_notion_id_empty_item_and_resolved_course_is_a_candidate(tmp_path):
    from scripts.heal_obsidian_item_frontmatter import find_frontmatter_heal_candidates

    note_path = tmp_path / "meningite.md"
    note_path.write_text(_NOTE_WITH_EMPTY_ITEM, encoding="utf-8")
    course_map = {"notion-id-221": _make_cours()}

    candidates = find_frontmatter_heal_candidates([note_path], course_map)

    assert len(candidates) == 1
    assert candidates[0]["path"] == note_path
    assert candidates[0]["item"] == "221"


def test_note_with_item_already_filled_is_not_a_candidate(tmp_path):
    from scripts.heal_obsidian_item_frontmatter import find_frontmatter_heal_candidates

    note_path = tmp_path / "deja-correct.md"
    note_path.write_text(_NOTE_WITH_FILLED_ITEM, encoding="utf-8")
    course_map = {"notion-id-340": _make_cours(id="notion-id-340", item_number="340")}

    assert find_frontmatter_heal_candidates([note_path], course_map) == []


def test_note_with_unknown_notion_id_is_not_a_candidate(tmp_path):
    from scripts.heal_obsidian_item_frontmatter import find_frontmatter_heal_candidates

    note_path = tmp_path / "orpheline.md"
    note_path.write_text(_NOTE_WITH_UNKNOWN_NOTION_ID, encoding="utf-8")

    assert find_frontmatter_heal_candidates([note_path], {}) == []


def test_apply_heal_candidate_only_changes_the_item_line(tmp_path):
    from scripts.heal_obsidian_item_frontmatter import (
        apply_heal_candidate,
        find_frontmatter_heal_candidates,
    )

    note_path = tmp_path / "meningite.md"
    note_path.write_text(_NOTE_WITH_EMPTY_ITEM, encoding="utf-8")
    course_map = {"notion-id-221": _make_cours()}

    candidates = find_frontmatter_heal_candidates([note_path], course_map)
    apply_heal_candidate(candidates[0])

    healed = note_path.read_text(encoding="utf-8")
    assert "item: 221" in healed
    assert "notion_id: notion-id-221" in healed
    assert "synapse_id: syn-221" in healed
    assert "Cardiovasculaire" in healed
    assert "# ITEM 221 – Méningite" in healed
    assert "Contenu du cours, jamais touché." in healed
