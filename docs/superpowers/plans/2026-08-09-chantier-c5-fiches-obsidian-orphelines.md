# Chantier C5 — Fiches Obsidian orphelines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two one-off scripts, run in sequence: fix the Notion Cours pages whose `ITEM (number)` is
empty but resolvable via `ITEM lié`, then repair the `item:` frontmatter of the Obsidian notes
already created from those pages — without touching anything else in either place.

**Architecture:** Each script's decision logic (which pages/notes qualify for correction) is a pure,
independently testable function with no I/O, following the exact pattern already established by
`scripts/reconcile_colleges.py` (page_id→item_number fallback resolution) and
`scripts/apply_college_corrections.py` (dry-run / `--apply` CLI convention, JSON plan export, rate-
limited writes). The I/O shell (Notion calls, file reads/writes, CLI flag handling) wraps that pure
function but isn't itself unit-tested — same division of labor as the two reference scripts.

**Tech Stack:** Python, `asyncio` (Notion calls), Pydantic (`Cours` model), the existing
`_split_frontmatter` / `_parse_fm_lines` / `_rebuild_fm` frontmatter helpers
(`backend/core/obsidian/templates.py`), pytest (`tmp_path` for real-file round-trip tests, direct
`Cours(**kwargs)` construction matching `tests/test_models.py`'s `_make_cours` pattern).

## Global Constraints

- `Course.display_item_number` (`backend/core/notion/models.py:192-202`) is not modified — it stays
  "never `item_lie`". Both scripts correct the underlying data so it already returns the right value
  with zero code changes.
- Script 2 must run **after** script 1 has been applied with `--apply` — it reads live Notion data
  that only reflects the fix once script 1 has written it.
- Script 2 touches only the `item:` frontmatter line of a note — body and every other field are
  byte-for-byte identical before and after, guaranteed by reusing `_rebuild_fm` with a single-key
  override (never touches `overrides` for any other key).
- No permanent Settings UI button — both are one-off scripts under `scripts/`, dry-run by default,
  `--apply` to write for real (same convention as `apply_college_corrections.py`).
- Full suite (`./.venv/Scripts/python.exe -m pytest -q`) run before Task 1 Step 1 and after the last
  step, zero regressions.

---

### Task 1: `scripts/reconcile_item_numbers.py`

**Files:**
- Create: `scripts/reconcile_item_numbers.py`
- Test: `tests/test_reconcile_item_numbers.py`

**Interfaces:**
- Consumes: `Cours` (`backend/core/notion/models.py`, fields `.id`, `.title`, `.item_number`,
  `.item_lie`), `notion_service.get_all_cours()` / `get_all_items_map()` /
  `update_course(course_id, properties)` (`backend/core/notion/service.py`, all pre-existing,
  unchanged), `NOTION_PROPS.ITEM` (`backend/config/settings.py:50`, value `"ITEM"`).
- Produces: `find_item_number_corrections(cours: list[Cours], page_id_to_item_num: dict[str, int])
  -> list[dict]`, each dict shaped `{"page_id": str, "title": str, "item_number": int}`. Task 2 does
  not depend on this — the two scripts share no code, only a run-order dependency on live Notion
  state.

- [ ] **Step 1: Run the full suite to record the baseline**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1164 tests (the count left by C4).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_reconcile_item_numbers.py`:

```python
from datetime import datetime

from backend.core.notion.models import Cours


def _make_cours(**kwargs) -> Cours:
    defaults = dict(
        id="test-id",
        title="Pathologie cardiovasculaire",
        item_number=None,
        item_lie=None,
        college=[],
        semestre=None,
        ue_id=None,
        created_time=datetime(2024, 1, 1),
        nb_lectures=0,
    )
    defaults.update(kwargs)
    return Cours(**defaults)


def test_empty_item_number_with_resolvable_item_lie_is_a_correction():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", title="Méningite", item_number=None, item_lie="item-page-221")]
    page_id_to_item_num = {"item-page-221": 221}

    corrections = find_item_number_corrections(cours, page_id_to_item_num)

    assert corrections == [{"page_id": "page-1", "title": "Méningite", "item_number": 221}]


def test_already_filled_item_number_is_never_a_correction():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", item_number="221", item_lie="item-page-340")]
    page_id_to_item_num = {"item-page-340": 340}

    assert find_item_number_corrections(cours, page_id_to_item_num) == []


def test_no_item_lie_at_all_is_not_a_correction():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", item_number=None, item_lie=None)]

    assert find_item_number_corrections(cours, {}) == []


def test_item_lie_pointing_to_unknown_page_is_not_a_correction_and_does_not_raise():
    from scripts.reconcile_item_numbers import find_item_number_corrections

    cours = [_make_cours(id="page-1", item_number=None, item_lie="deleted-page-id")]

    assert find_item_number_corrections(cours, {}) == []
```

- [ ] **Step 3: Run the tests to verify they fail for the right reason**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reconcile_item_numbers.py -v`
Expected: all 4 FAIL with `ModuleNotFoundError: No module named 'scripts.reconcile_item_numbers'`
(the file doesn't exist yet).

- [ ] **Step 4: Write the script**

Create `scripts/reconcile_item_numbers.py`:

```python
"""
scripts/reconcile_item_numbers.py
----------------------------------
Corrige les pages Cours Notion dont ITEM (number) est vide alors qu'ITEM lié
(relation) est renseignée et resolvable — cause racine des fiches Obsidian
orphelines (chantier C5, voir docs/superpowers/specs/2026-08-09-chantier-c5-*).

Ne modifie que la propriété ITEM (number) des pages concernées. Rien d'autre.

À exécuter AVANT scripts/heal_obsidian_item_frontmatter.py --apply : ce
script-ci doit avoir été lancé en --apply pour que le second script trouve
des display_item_number déjà corrigés côté Notion.

Usage :
    python scripts/reconcile_item_numbers.py            # dry-run (rapporte le plan)
    python scripts/reconcile_item_numbers.py --apply     # écrit réellement dans Notion
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from loguru import logger

from backend.config.settings import NOTION_PROPS as P
from backend.core.notion.models import Cours
from backend.core.notion.service import notion_service

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_PATH = os.path.join(BASE, "data", "item_number_reconcile_report.json")
RESULT_PATH = os.path.join(BASE, "data", "item_number_apply_result.json")

RATE_LIMIT_DELAY = 0.35  # ~3 req/s, marge sous la limite Notion


def find_item_number_corrections(cours: list[Cours], page_id_to_item_num: dict[str, int]) -> list[dict]:
    """Cours avec ITEM (number) vide mais ITEM lié résolvable vers un item connu."""
    corrections: list[dict] = []
    for c in cours:
        has_number = bool((c.item_number or "").strip())
        if has_number or not c.item_lie:
            continue
        resolved = page_id_to_item_num.get(c.item_lie)
        if resolved is not None:
            corrections.append({"page_id": c.id, "title": c.title, "item_number": resolved})
    return corrections


async def main() -> None:
    apply_mode = "--apply" in sys.argv

    logger.info("Récupération des cours et des items Notion…")
    cours = await notion_service.get_all_cours()
    items_map = await notion_service.get_all_items_map()  # item_number(int) -> Item page id
    page_id_to_item_num = {v: k for k, v in items_map.items()}

    corrections = find_item_number_corrections(cours, page_id_to_item_num)
    logger.info(f"{len(corrections)} correction(s) trouvée(s) sur {len(cours)} cours.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"corrections": corrections}, f, ensure_ascii=False, indent=2)

    if not apply_mode:
        print(f"\n[DRY RUN] {len(corrections)} correction(s) prévue(s).")
        print(f"Détail : {REPORT_PATH}")
        print("Relancer avec --apply pour écrire réellement dans Notion.")
        return

    applied: list[dict] = []
    errors: list[dict] = []
    for i, corr in enumerate(corrections, 1):
        try:
            ok = await notion_service.update_course(
                corr["page_id"], {P.ITEM: {"number": float(corr["item_number"])}},
            )
            if ok:
                applied.append(corr)
            else:
                errors.append({**corr, "error": "update_course a renvoyé False"})
        except Exception as e:
            logger.error(f"Échec correction {corr['title']!r} (item {corr['item_number']}): {e}")
            errors.append({**corr, "error": str(e)})
        if i % 20 == 0 or i == len(corrections):
            logger.info(f"  traité {i}/{len(corrections)}")
        await asyncio.sleep(RATE_LIMIT_DELAY)

    result = {"applied_count": len(applied), "error_count": len(errors), "applied": applied, "errors": errors}
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== Terminé ===")
    print(f"  corrigées : {len(applied)}/{len(corrections)}")
    print(f"  erreurs   : {len(errors)}")
    print(f"\nRésultat détaillé : {RESULT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
```

`scripts/__init__.py` already exists in this repo, so `from scripts.reconcile_item_numbers import
...` works as a package import without any extra setup.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reconcile_item_numbers.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/reconcile_item_numbers.py tests/test_reconcile_item_numbers.py
git commit -m "feat: add reconcile_item_numbers.py to fix Cours pages with empty ITEM but resolvable ITEM lié"
```

---

### Task 2: `scripts/heal_obsidian_item_frontmatter.py`

**Files:**
- Create: `scripts/heal_obsidian_item_frontmatter.py`
- Test: `tests/test_heal_obsidian_item_frontmatter.py`

**Interfaces:**
- Consumes: `Cours.display_item_number` (already correct once Task 1 has been applied),
  `_split_frontmatter` / `_parse_fm_lines` / `_rebuild_fm`
  (`backend/core/obsidian/templates.py:101-205`, all pre-existing, unchanged).
- Produces: `find_frontmatter_heal_candidates(md_paths: list[Path], course_map: dict[str, Cours]) ->
  list[dict]`, each dict shaped `{"path": Path, "fields": list[tuple], "body": str, "item": str}`.
  `apply_heal_candidate(candidate: dict) -> None`, which writes the healed frontmatter back to
  `candidate["path"]`. No other task depends on these — this is the last task in the plan.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_heal_obsidian_item_frontmatter.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail for the right reason**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_heal_obsidian_item_frontmatter.py -v`
Expected: all 4 FAIL with `ModuleNotFoundError: No module named
'scripts.heal_obsidian_item_frontmatter'` (the file doesn't exist yet).

- [ ] **Step 3: Write the script**

Create `scripts/heal_obsidian_item_frontmatter.py`:

```python
"""
scripts/heal_obsidian_item_frontmatter.py
-------------------------------------------
Répare le champ `item:` du frontmatter des fiches Obsidian déjà créées à
partir d'un cours dont ITEM (number) était vide (chantier C5).

À exécuter APRÈS scripts/reconcile_item_numbers.py --apply : ce script lit
Cours.display_item_number, qui ne sera correct que si la correction Notion a
déjà été appliquée.

Ne touche jamais le corps de la note ni aucun autre champ du frontmatter —
seule la ligne `item:` est réécrite, via les mêmes helpers que la création
de note (_rebuild_fm avec un override sur une seule clé).

Usage :
    python scripts/heal_obsidian_item_frontmatter.py            # dry-run
    python scripts/heal_obsidian_item_frontmatter.py --apply    # écrit réellement dans le vault
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from loguru import logger

from backend.config.settings import settings
from backend.core.notion.models import Cours
from backend.core.notion.service import notion_service
from backend.core.obsidian.templates import _parse_fm_lines, _rebuild_fm, _split_frontmatter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_PATH = os.path.join(BASE, "data", "obsidian_item_heal_report.json")


def find_frontmatter_heal_candidates(md_paths: list[Path], course_map: dict[str, Cours]) -> list[dict]:
    """Notes déjà liées (notion_id connu) avec item: vide et un cours désormais résolu."""
    candidates: list[dict] = []
    for md_path in md_paths:
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm_raw, body = _split_frontmatter(text)
        if not fm_raw:
            continue
        fields = _parse_fm_lines(fm_raw)
        fm = dict(fields)
        notion_id = str(fm.get("notion_id", "") or "").strip()
        current_item = str(fm.get("item", "") or "").strip()
        if current_item or not notion_id or notion_id not in course_map:
            continue
        resolved = course_map[notion_id].display_item_number
        if resolved:
            candidates.append({"path": md_path, "fields": fields, "body": body, "item": resolved})
    return candidates


def apply_heal_candidate(candidate: dict) -> None:
    new_fm = _rebuild_fm(candidate["fields"], {"item": candidate["item"]})
    candidate["path"].write_text(new_fm + candidate["body"], encoding="utf-8")


async def main() -> None:
    apply_mode = "--apply" in sys.argv

    vault_path_str = settings.obsidian_vault_path
    if not vault_path_str:
        logger.error("obsidian_vault_path non configuré — rien à faire.")
        return

    vault = Path(vault_path_str)
    md_paths = list(vault.glob("01 - Cours EDN/*/Cours/*.md"))
    logger.info(f"{len(md_paths)} fiche(s) de cours trouvée(s) dans le vault.")

    logger.info("Récupération des cours Notion (état corrigé attendu)…")
    cours = await notion_service.get_all_cours()
    course_map = {c.id: c for c in cours}

    candidates = find_frontmatter_heal_candidates(md_paths, course_map)
    logger.info(f"{len(candidates)} fiche(s) à réparer.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"candidates": [{"path": str(c["path"]), "item": c["item"]} for c in candidates]},
            f, ensure_ascii=False, indent=2,
        )

    if not apply_mode:
        print(f"\n[DRY RUN] {len(candidates)} fiche(s) seraient réparées.")
        print(f"Détail : {REPORT_PATH}")
        print("Relancer avec --apply pour écrire réellement dans le vault.")
        return

    healed = 0
    errors: list[dict] = []
    for candidate in candidates:
        try:
            apply_heal_candidate(candidate)
            healed += 1
        except OSError as e:
            logger.error(f"Échec réparation {candidate['path']}: {e}")
            errors.append({"path": str(candidate["path"]), "error": str(e)})

    print(f"\n=== Terminé ===")
    print(f"  réparées : {healed}/{len(candidates)}")
    print(f"  erreurs  : {len(errors)}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_heal_obsidian_item_frontmatter.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 1172 tests (1164 baseline + 8 net new: 4 in Task 1, 4 in Task 2), zero regressions.

- [ ] **Step 6: Update the tracking doc**

In `docs/UI_REFONTE_ETAT_DES_LIEUX.md`, mark C5 as terminé (commit hash, tests before → after) in
the same table format used for A/B1-B4/C1-C4, note that chantier C is now **entirely** complete, and
update the "▶ REPRISE" header to point at chantier D as the only remaining open work. This file
stays uncommitted, per the established convention for this series of chantiers.

- [ ] **Step 7: Commit**

```bash
git add scripts/heal_obsidian_item_frontmatter.py tests/test_heal_obsidian_item_frontmatter.py
git commit -m "feat: add heal_obsidian_item_frontmatter.py to repair item: on already-created course notes"
```

---

## Post-plan manual step (not part of this plan's tasks)

Once both scripts are committed, running them against the real Notion workspace and vault is a
**manual step outside this plan** — it writes to live Notion data and the user's actual Obsidian
vault, which is exactly the kind of action that needs the user's explicit go-ahead at the time,
not baked into an automated plan step. The order is:

```bash
python scripts/reconcile_item_numbers.py            # dry-run, review data/item_number_reconcile_report.json
python scripts/reconcile_item_numbers.py --apply     # writes to Notion
python scripts/heal_obsidian_item_frontmatter.py         # dry-run, review data/obsidian_item_heal_report.json
python scripts/heal_obsidian_item_frontmatter.py --apply # writes to the vault
```

## Self-Review Notes

- **Spec coverage:** Script 1 (`find_item_number_corrections`, dry-run/`--apply`, JSON report/result,
  rate limiting) → Task 1. Script 2 (`find_frontmatter_heal_candidates`, `apply_heal_candidate`,
  dry-run/`--apply`) → Task 2. Run-order constraint → documented in both scripts' docstrings, Global
  Constraints, and the "Post-plan manual step" section. Vault-not-configured guard (Risks section) →
  Task 2 Step 3's `if not vault_path_str: logger.error(...); return`. Unknown `item_lie` target /
  `item_lie` absent (Risks section) → covered by Task 1's tests 3 and 4.
- **Placeholder scan:** none found — every step has literal code, exact commands, exact expected
  output.
- **Type/name consistency:** `find_item_number_corrections(cours, page_id_to_item_num)` is used
  identically in its definition (Task 1 Step 4) and all 4 tests (Task 1 Step 2).
  `find_frontmatter_heal_candidates(md_paths, course_map)` and `apply_heal_candidate(candidate)` are
  used identically in their definitions (Task 2 Step 3) and all 4 tests (Task 2 Step 1). Both scripts
  import `Cours` from the same module and construct it with the same field set as
  `tests/test_models.py`'s existing `_make_cours` helper, confirmed against that file's actual
  defaults during plan-writing (not guessed).
- **`scripts/__init__.py` verified during plan-writing:** the tests import `from
  scripts.reconcile_item_numbers import ...`, which requires `scripts` to be an importable package —
  confirmed it already exists (`scripts/__init__.py` is present in the repo today), so no setup step
  was needed in the plan.
