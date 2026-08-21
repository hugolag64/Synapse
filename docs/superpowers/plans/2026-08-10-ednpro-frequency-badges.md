# Badges de fréquence EDNpro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher un badge de priorité EDNpro coloré dans les vues Collèges, fiche item et liste générale des Items, avec les statistiques détaillées au survol.

**Architecture:** Ajouter un composant NiceGUI partagé qui transforme une ligne de fréquence EDNpro en badge accessible et compact. Charger toutes les fréquences en une seule requête SQLite dans chaque page, puis transmettre la fréquence de l’item au composant sans recalculer la priorité.

**Tech Stack:** Python 3.11, NiceGUI, SQLite, pytest, CSS inline existant de Synapse.

## Global Constraints

- Utiliser les priorités normalisées existantes : `indispensable`, `important`, `basique`, `jamais_tombe`.
- Ne jamais exécuter une requête SQLite par ligne rendue : utiliser une lecture groupée.
- Conserver les couleurs sémantiques du thème (`var(--danger)`, `var(--warning)`, `var(--info)`, `var(--text-dim)`).
- Le badge doit rester accessible avec un libellé complet via tooltip et `aria-label`.
- Une fréquence absente ou incomplète ne doit pas faire échouer le rendu d’une page.
- Respecter le style compact des tableaux existants et le comportement responsive actuel.

---

### Task 1: Ajouter la lecture groupée des fréquences

**Files:**
- Modify: `backend/core/reviews/local_store.py:745-760`
- Test: `tests/test_ednpro_frequency_store.py`

**Interfaces:**
- Produces `get_all_ednpro_item_frequencies() -> dict[str, dict]`, indexé par le numéro d’item.
- Chaque valeur reprend le format de `get_ednpro_item_frequency()` : `priority`, `session_count`, `question_count`, `years`, `source_url`, `collected_at`.

- [ ] **Step 1: Write the failing test**

```python
def test_get_all_ednpro_item_frequencies_returns_indexed_rows(practice_db):
    from backend.core.reviews import local_store

    local_store.replace_ednpro_item_frequencies([
        {
            "item_number": "247", "priority": "indispensable",
            "session_count": 13, "question_count": 31, "years": [2022, 2025],
            "source_url": "training-v2", "collected_at": "2026-08-10T10:00:00+00:00",
        },
    ])

    frequencies = local_store.get_all_ednpro_item_frequencies()

    assert frequencies["247"]["priority"] == "indispensable"
    assert frequencies["247"]["years"] == [2022, 2025]
    assert local_store.get_all_ednpro_item_frequencies().get("999") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_store.py::test_get_all_ednpro_item_frequencies_returns_indexed_rows -q`

Expected: FAIL with `AttributeError` because the bulk reader does not exist.

- [ ] **Step 3: Write minimal implementation**

Add the reader beside `get_ednpro_item_frequency()`:

```python
def get_all_ednpro_item_frequencies() -> dict[str, dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM ednpro_item_frequency ORDER BY item_number"
        ).fetchall()
    return {str(row["item_number"]): _frequency_row(row) for row in rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_store.py::test_get_all_ednpro_item_frequencies_returns_indexed_rows -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_ednpro_frequency_store.py
git commit -m "feat: add bulk EDNpro frequency lookup"
```

### Task 2: Créer le composant partagé de badge

**Files:**
- Create: `frontend/components/ednpro_frequency_badge.py`
- Test: `tests/test_ednpro_frequency_badge.py`

**Interfaces:**
- `frequency_badge_text(frequency: dict | None) -> str` returns the uppercase priority label.
- `frequency_badge_tooltip(frequency: dict | None) -> str` returns the sessions/questions/years detail.
- `ednpro_frequency_badge(frequency: dict | None, *, compact: bool = False) -> None` renders the NiceGUI badge.

- [ ] **Step 1: Write the failing tests**

```python
import pytest


@pytest.mark.parametrize(("priority", "label"), [
    ("indispensable", "INDISPENSABLE"),
    ("important", "IMPORTANT"),
    ("basique", "BASIQUE"),
    ("jamais_tombe", "JAMAIS TOMBÉ"),
])
def test_frequency_badge_text_uses_priority_label(priority, label):
    from frontend.components.ednpro_frequency_badge import frequency_badge_text

    assert frequency_badge_text({"priority": priority}) == label


def test_frequency_badge_tooltip_includes_counts_and_years():
    from frontend.components.ednpro_frequency_badge import frequency_badge_tooltip

    assert frequency_badge_tooltip({
        "priority": "indispensable", "session_count": 13,
        "question_count": 31, "years": [2022, 2025],
    }) == "13 sessions · 31 questions · 2022, 2025"


def test_frequency_badge_tooltip_handles_singular_and_missing_frequency():
    from frontend.components.ednpro_frequency_badge import frequency_badge_tooltip

    assert frequency_badge_tooltip({
        "priority": "basique", "session_count": 1,
        "question_count": 1, "years": [],
    }) == "1 session · 1 question · années indisponibles"
    assert frequency_badge_tooltip(None) == "Fréquence EDNpro indisponible"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_badge.py -q`

Expected: FAIL with `ModuleNotFoundError` because the component does not exist.

- [ ] **Step 3: Write minimal implementation**

Define a presentation table and render one `span`-like element with a colored dot, label, tooltip and `aria-label`:

```python
_PRIORITY_PRESENTATION = {
    "indispensable": ("INDISPENSABLE", "var(--danger)"),
    "important": ("IMPORTANT", "var(--warning)"),
    "basique": ("BASIQUE", "var(--info)"),
    "jamais_tombe": ("JAMAIS TOMBÉ", "var(--text-dim)"),
}
```

Use a neutral `jamais_tombe` fallback for a missing row, compact CSS classes, and `element.tooltip(frequency_badge_tooltip(frequency))`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_badge.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ednpro_frequency_badge.py tests/test_ednpro_frequency_badge.py
git commit -m "feat: add EDNpro frequency badge component"
```

### Task 3: Intégrer le badge dans Collèges et la fiche item

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py:155-166,169-209,620-675`
- Modify: `frontend/pages/course_detail_cockpit.py:380-430`
- Test: `tests/test_ednpro_frequency_ui.py`

**Interfaces:**
- Both pages consume `local_store.get_all_ednpro_item_frequencies()` once per render.
- Both pages call `ednpro_frequency_badge(frequency, compact=True)`.

- [ ] **Step 1: Write the failing source-contract tests**

```python
def test_colleges_and_item_detail_render_ednpro_frequency_badge():
    from frontend.pages import colleges_cockpit, course_detail_cockpit
    import inspect

    colleges_source = inspect.getsource(colleges_cockpit)
    detail_source = inspect.getsource(course_detail_cockpit)
    assert "get_all_ednpro_item_frequencies" in colleges_source
    assert "ednpro_frequency_badge" in colleges_source
    assert "EDNpro" in colleges_source
    assert "get_all_ednpro_item_frequencies" in detail_source
    assert "ednpro_frequency_badge" in detail_source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_ui.py::test_colleges_and_item_detail_render_ednpro_frequency_badge -q`

Expected: FAIL because the pages do not call the shared component or bulk reader.

- [ ] **Step 3: Add the bulk data to the page render paths**

In `render_colleges_cockpit()`, load `frequency_map = local_store.get_all_ednpro_item_frequencies()` once, pass it into `_college_item_rows()`, store each row’s frequency by `course.item_number`, and add an `EDNpro` `GridColumn` immediately after `qcm`.

In the expanded item grid, render the badge after the QCM cell and before the action cell. Update both `.cg-item-head, .cg-item` CSS grid templates and `_COLLEGE_ITEM_GRID` to add the same-width column.

In `render_item_cockpit()`, load the map once after resolving `course`, obtain `frequency = frequency_map.get(str(course.item_number))`, and render a compact badge in `.ci-meta` after the QCM average cell (or as the final metadata cell when no QCM average exists).

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_ui.py::test_colleges_and_item_detail_render_ednpro_frequency_badge -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/colleges_cockpit.py frontend/pages/course_detail_cockpit.py tests/test_ednpro_frequency_ui.py
git commit -m "feat: show EDNpro frequency in college and item detail views"
```

### Task 4: Intégrer le badge dans la liste Items et corriger l’alignement

**Files:**
- Modify: `frontend/pages/items.py:40-92,238-258,329-363`
- Test: `tests/test_ednpro_frequency_ui.py`

**Interfaces:**
- The page loads `frequency_map = local_store.get_all_ednpro_item_frequencies()` once in `_compute()`.
- Each row exposes `ednpro_frequency` to `_draw_row()`.

- [ ] **Step 1: Write the failing source-contract test**

```python
def test_items_page_renders_frequency_badge_and_wrapped_title():
    from frontend.pages import items
    import inspect

    source = inspect.getsource(items)
    assert "get_all_ednpro_item_frequencies" in source
    assert "ednpro_frequency_badge" in source
    assert "EDNpro" in source
    assert "white-space:normal" in source or "white-space: normal" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_ui.py::test_items_page_renders_frequency_badge_and_wrapped_title -q`

Expected: FAIL because the general list has no frequency badge or wrapped title style.

- [ ] **Step 3: Implement the list layout**

Import the shared badge, load the frequency map in `_compute()`, and attach the row frequency using the normalized item number. Add `EDNpro` after `TITRE` in `_draw_head()` and add the compact badge directly after the title in `_draw_row()`.

Reduce the title flex basis to roughly half of its current available width by giving the title cell a bounded `flex: 0 1 min(42%, 420px)`, create an `.it-title-stack` flex container, allow `.it-title-cell` to wrap to two lines with `line-height:1.25`, and give the new `.it-frequency` column a fixed compact width. Apply the same flex basis and gap to header classes so `TITRE` is aligned with row titles.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_ui.py::test_items_page_renders_frequency_badge_and_wrapped_title -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/items.py tests/test_ednpro_frequency_ui.py
git commit -m "feat: show EDNpro frequency in items list"
```

### Task 5: Vérification complète et contrôle visuel

**Files:**
- Test: `tests/test_ednpro_frequency_badge.py`
- Test: `tests/test_ednpro_frequency_store.py`
- Test: `tests/test_ednpro_frequency_ui.py`

- [ ] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_badge.py tests/test_ednpro_frequency_store.py tests/test_ednpro_frequency_ui.py -q`

Expected: all focused tests PASS.

- [ ] **Step 2: Run the related full regression set**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency.py tests/test_ednpro_frequency_store.py tests/test_ednpro_frequency_sync.py tests/test_ednpro_frequency_ui.py -q`

Expected: all EDNpro frequency tests PASS.

- [ ] **Step 3: Run syntax and diff checks**

Run: `.\.venv\Scripts\python.exe -m compileall -q frontend backend tests/test_ednpro_frequency_badge.py tests/test_ednpro_frequency_store.py tests/test_ednpro_frequency_ui.py`

Expected: exit code 0 and no syntax errors.

- [ ] **Step 4: Verify the three routes visually**

Open `/colleges`, expand a college containing item 247, and confirm the `EDNpro` badge appears immediately after `QCM`. Open `/items` and confirm long titles wrap while the `TITRE` header aligns with the title cell and the badge stays visible. Open `/cours/<id>` for item 247 and confirm the same badge appears in the header. Hover each priority and verify counts and years are visible.

- [ ] **Step 5: Report the result**

Report the exact test counts, the three routes checked, and any unavailable lint/browser verification without claiming success for an unchecked route.
