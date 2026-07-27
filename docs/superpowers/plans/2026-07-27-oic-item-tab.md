# Onglet OIC dans la fiche item — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconnect the existing LiSA + AnythingLLM OIC workflow inside a real `OIC` tab on the cockpit item page, with one shared item-level state across Synapse college aliases.

**Architecture:** Keep LiSA, AnythingLLM, evaluator prompts, and existing SQLite history as the underlying services. Add a thin item-level aggregation service that reads the historical per-`course_id` rows, deduplicates OICs by code, propagates manual validation/levels across aliases, and protects attempts during refresh. Extract the current LiSA dialog list/progress renderer into a reusable panel, then mount it lazily in the cockpit tab while retaining the old dialog as a compatibility wrapper.

**Tech Stack:** Python 3.13, NiceGUI, SQLite, pytest, existing LiSA MediaWiki API client, AnythingLLM HTTP client.

## Global Constraints

- The source OIC remains LiSA/UNESS and the interactive evaluator remains local AnythingLLM; do not add an Ollama call in this feature.
- OIC functional state is canonical per item, not per college; multiple Synapse `course_id` aliases must display the same deduplicated OIC state.
- The OIC tab loads lazily on activation and must display an available cache before attempting a network refresh.
- A LiSA refresh must preserve `mastered`, `oic_level`, and `oic_attempts`; never use a destructive delete that cascades attempts.
- The old `open_lisa_dialog` entry point must continue to work through the shared renderer.
- Do not change the global mastery algorithm, build exam simulations, or redesign the complete item page in this plan.

---

## Task 1: Add item-level OIC aggregation and shared-state operations

**Files:**
- Create: `backend/core/lisa/item_service.py`
- Modify: `backend/core/reviews/local_store.py:2693-2815`
- Test: `tests/test_oic_item_service.py`

**Interfaces:**
- Consumes: existing `get_lisa_oic(course_id)`, `get_oic_attempts(oic_id)`, `toggle_lisa_oic_mastery`, `save_oic_attempt`, `update_oic_level`.
- Produces: `merge_oic_rows(rows) -> list[dict]`, `get_item_oics(course_ids) -> list[dict]`, `set_item_oic_mastery(course_ids, oic_code, mastered) -> None`, `get_item_oic_attempts(course_ids, oic_code) -> list`, and `save_item_oic_attempt(course_ids, oic_code, session_score, questions_json) -> int`.

- [ ] **Step 1: Write the failing aggregation tests**

```python
def test_merges_alias_rows_by_oic_code_and_keeps_strongest_state():
    from backend.core.lisa.item_service import merge_oic_rows

    rows = [
        {"id": 1, "course_id": "mg", "oic_code": "OIC-75-01-A", "intitule": "A", "rang": "A", "mastered": 0, "oic_level": 1},
        {"id": 2, "course_id": "psy", "oic_code": "OIC-75-01-A", "intitule": "A", "rang": "A", "mastered": 1, "oic_level": 3},
        {"id": 3, "course_id": "psy", "oic_code": "OIC-75-02-B", "intitule": "B", "rang": "B", "mastered": 0, "oic_level": 0},
    ]
    merged = merge_oic_rows(rows)
    assert [row["oic_code"] for row in merged] == ["OIC-75-01-A", "OIC-75-02-B"]
    assert merged[0]["mastered"] == 1
    assert merged[0]["oic_level"] == 3
    assert merged[0]["source_ids"] == [1, 2]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `pytest tests/test_oic_item_service.py::test_merges_alias_rows_by_oic_code_and_keeps_strongest_state -q`

Expected: FAIL because the item aggregation service does not exist.

- [ ] **Step 3: Implement the pure merge function and item service wrappers**

Implement `merge_oic_rows(rows)` with deterministic ordering `(rang A before B, ordre, oic_code)`, `source_ids`, `mastered = any(source.mastered)`, and `oic_level = max(source.oic_level)`. Implement the wrapper functions using the existing local-store APIs; writes must update every source row for the selected `oic_code`, while attempts are read from all source IDs and deduplicated by attempt ID.

- [ ] **Step 4: Add write-propagation tests and run them**

```python
def test_manual_mastery_propagates_to_all_alias_rows(monkeypatch):
    from backend.core.lisa import item_service
    from backend.core.reviews import local_store

    calls = []
    monkeypatch.setattr(item_service, "get_item_oics", lambda ids: [
        {"oic_code": "OIC-75-01-A", "mastered": 0, "source_ids": [101, 102]}
    ])
    monkeypatch.setattr(local_store, "toggle_lisa_oic_mastery", lambda oid: calls.append(oid))
    item_service.set_item_oic_mastery(["mg", "psy"], "OIC-75-01-A", True)
    assert calls == [101, 102]
```

Run: `pytest tests/test_oic_item_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the item aggregation slice**

```bash
git add backend/core/lisa/item_service.py backend/core/reviews/local_store.py tests/test_oic_item_service.py
git commit -m "feat: aggregate OIC state by canonical item"
```

## Task 2: Make LiSA refresh non-destructive

**Files:**
- Modify: `backend/core/reviews/local_store.py:2712-2760`
- Test: `tests/test_oic_item_service.py`

**Interfaces:**
- Consumes: `upsert_lisa_oic(course_id, oics)`.
- Produces: idempotent refresh preserving existing row IDs, `mastered`, `oic_level`, and `oic_attempts` for matching `oic_code` values.

- [ ] **Step 1: Write the failing preservation test**

```python
def test_refresh_reconciliation_keeps_existing_identity_and_state():
    from backend.core.lisa.item_service import reconcile_oic_rows

    existing = [{"id": 17, "oic_code": "OIC-75-01-A", "mastered": 1, "oic_level": 3}]
    incoming = [{"oic_code": "OIC-75-01-A", "intitule": "Updated", "rang": "A", "ordre": 1}]
    result = reconcile_oic_rows(existing, incoming)
    assert result[0]["id"] == 17
    assert result[0]["mastered"] == 1
    assert result[0]["oic_level"] == 3
```

- [ ] **Step 2: Run it and verify the current destructive refresh fails**

Run: `pytest tests/test_oic_item_service.py::test_refresh_reconciliation_keeps_existing_identity_and_state -q`

Expected: FAIL because the current implementation deletes all course rows before inserting.

- [ ] **Step 3: Replace delete/reinsert with code-keyed reconciliation**

Implement `reconcile_oic_rows(existing_rows, incoming_rows)` as the pure contract, then use it inside one SQLite transaction: load existing rows by `(course_id, oic_code)`, update matching rows in place, insert new codes, and retain missing historical rows as inactive/history-preserving rows rather than deleting them. Keep cache date updates atomic.

- [ ] **Step 4: Run OIC persistence tests**

Run: `pytest tests/test_oic_item_service.py tests/test_oic_evaluator.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the refresh slice**

```bash
git add backend/core/reviews/local_store.py tests/test_oic_item_service.py
git commit -m "fix: preserve OIC history across LiSA refresh"
```

## Task 3: Extract the shared LiSA panel renderer

**Files:**
- Modify: `frontend/components/lisa_dialog.py:17-290`
- Create: `frontend/components/oic_panel.py`
- Test: `tests/test_oic_panel_data.py`

**Interfaces:**
- Consumes: `get_item_oics`, `set_item_oic_mastery`, `open_oic_eval_dialog`, and LiSA load callbacks.
- Produces: `OICPanelController`, `should_load_on_tab_activation(active_tab, loaded) -> bool`, and `render_oic_panel(container, item_context, refresh_fn=None, lazy=True) -> OICPanelController`; `open_lisa_dialog` delegates list/progress rendering to this component.

- [ ] **Step 1: Add data/controller tests for cache states**

```python
def test_panel_uses_empty_cache_without_scraping(monkeypatch):
    from backend.core.lisa import item_service, scraper
    calls = []
    monkeypatch.setattr(item_service, "get_item_oics", lambda ids: [])
    monkeypatch.setattr(scraper, "scrape_oic", lambda *args: calls.append(args))
    controller = OICPanelController(course_ids=["psy"], item_number="75")
    controller.load_cached()
    assert controller.rows == []
    assert calls == []
```

- [ ] **Step 2: Run the focused test and verify the extracted controller is absent**

Run: `pytest tests/test_oic_panel_data.py::test_panel_uses_empty_cache_without_scraping -q`

Expected: FAIL because the shared panel controller does not exist.

- [ ] **Step 3: Extract the existing grouping/progress/row actions**

Move the current Rang A/B list, progress summary, mastery toggle, refresh/error states, and evaluation button into `oic_panel.py`. Keep `open_lisa_dialog` responsible only for dialog shell/loading orchestration and delegate row rendering to the new component. Do not duplicate evaluator logic.

- [ ] **Step 4: Run panel tests and existing dialog/evaluator tests**

Run: `pytest tests/test_oic_panel_data.py tests/test_oic_evaluator.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the shared renderer**

```bash
git add frontend/components/oic_panel.py frontend/components/lisa_dialog.py tests/test_oic_panel_data.py
git commit -m "refactor: share OIC panel renderer"
```

## Task 4: Add the lazy OIC tab to the cockpit item page

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py:274-436`
- Modify: `frontend/components/oic_panel.py`
- Test: `tests/test_course_detail_oic_tab.py`

**Interfaces:**
- Consumes: `render_oic_panel`, canonical item context, existing `ui.tabs`/`ui.tab_panels`.
- Produces: a visible `OIC` tab that does not scrape before activation and refreshes after evaluation.

- [ ] **Step 1: Write the failing tab wiring test**

```python
def test_course_detail_registers_oic_tab_without_initial_scrape(monkeypatch):
    from frontend.components.oic_panel import should_load_on_tab_activation

    assert should_load_on_tab_activation("overview", False) is False
    assert should_load_on_tab_activation("OIC", False) is True
    assert should_load_on_tab_activation("OIC", True) is False
```

- [ ] **Step 2: Run it and verify the current cockpit has no OIC tab**

Run: `pytest tests/test_course_detail_oic_tab.py::test_course_detail_registers_oic_tab_without_initial_scrape -q`

Expected: FAIL because the current shared OIC panel has no tab-activation seam.

- [ ] **Step 3: Add the tab and activation callback**

Add `t_oic = ui.tab("OIC")`, an associated panel, and a tab value-change handler that calls the shared controller only when `OIC` becomes active. Pass all course aliases for the canonical item and use the current course as the evaluation context.

- [ ] **Step 4: Run tab tests and a NiceGUI import/render smoke test**

Run: `pytest tests/test_course_detail_oic_tab.py -q`

Expected: PASS with no LiSA request during initial render.

- [ ] **Step 5: Commit the cockpit tab slice**

```bash
git add frontend/pages/course_detail_cockpit.py frontend/components/oic_panel.py tests/test_course_detail_oic_tab.py
git commit -m "feat: add lazy OIC tab to item cockpit"
```

## Task 5: Reconnect evaluation refresh and shared item state

**Files:**
- Modify: `frontend/components/oic_panel.py`
- Modify: `frontend/components/oic_eval_dialog.py:27-177`
- Test: `tests/test_oic_item_service.py`

**Interfaces:**
- Consumes: `open_oic_eval_dialog(oic, course, refresh_fn)`.
- Produces: evaluation of an OIC alias updates the canonical item aggregation and every visible college alias after dialog close.

- [ ] **Step 1: Write the failing propagation test**

```python
def test_evaluation_refresh_reads_shared_item_state(monkeypatch):
    refreshes = []
    monkeypatch.setattr(item_service, "save_item_oic_attempt", lambda *args: 42)
    monkeypatch.setattr(item_service, "get_item_oics", lambda ids: [{"oic_code": "OIC-75-01-A", "oic_level": 3, "mastered": 1}])
    panel = OICPanelController(course_ids=["mg", "psy"], item_number="75", refresh_fn=lambda: refreshes.append(1))
    panel.on_evaluation_closed()
    assert panel.rows[0]["mastered"] == 1
    assert refreshes == [1]
```

- [ ] **Step 2: Run it and verify the panel currently refreshes only one course**

Run: `pytest tests/test_oic_item_service.py::test_evaluation_refresh_reads_shared_item_state -q`

Expected: FAIL until the evaluation callback uses the item aggregation service.

- [ ] **Step 3: Route evaluation save/readback through item-level service**

Keep question generation, grading, and level formula unchanged. On recap, save the attempt through `save_item_oic_attempt`, propagate the resulting level/mastery to all alias rows, and invoke the panel refresh callback after the dialog closes.

- [ ] **Step 4: Run evaluator, aggregation, and UI callback tests**

Run: `pytest tests/test_oic_evaluator.py tests/test_oic_item_service.py tests/test_course_detail_oic_tab.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the evaluation slice**

```bash
git add frontend/components/oic_panel.py frontend/components/oic_eval_dialog.py backend/core/lisa/item_service.py tests/test_oic_item_service.py
git commit -m "feat: share OIC evaluation state across item aliases"
```

## Task 6: Realign LiSA API characterization tests

**Files:**
- Modify: `tests/test_lisa_scraper.py`
- Modify: `backend/core/lisa/scraper.py` only if a tested API behavior is actually incorrect

**Interfaces:**
- Consumes: current MediaWiki API contract at `backend/core/lisa/scraper.py`.
- Produces: green deterministic tests for JSON parsing, empty API result, HTTP error contract, auth retry, and timeout.

- [ ] **Step 1: Replace stale HTML fixtures with MediaWiki JSON fixtures**

Use a fixture containing `query.pages[*].revisions[*].slots.main.content`/the exact structure returned by the current parser, plus fixtures for empty pages and malformed JSON. Do not reintroduce the removed HTML URL contract solely to satisfy old tests.

- [ ] **Step 2: Run LiSA tests and classify failures**

Run: `pytest tests/test_lisa_scraper.py -q`

Expected: failures only where the current API implementation violates its documented behavior.

- [ ] **Step 3: Fix only proven contract defects and rerun**

Run: `pytest tests/test_lisa_scraper.py tests/test_oic_item_service.py -q`

Expected: PASS.

- [ ] **Step 4: Commit the contract test slice**

```bash
git add tests/test_lisa_scraper.py backend/core/lisa/scraper.py
git commit -m "test: characterize current LiSA API contract"
```

## Task 7: Full verification and handoff

**Files:**
- Test: all affected OIC and regression tests.

- [ ] **Step 1: Run focused OIC suite**

Run: `pytest tests/test_oic_evaluator.py tests/test_oic_item_service.py tests/test_oic_panel_data.py tests/test_course_detail_oic_tab.py tests/test_lisa_scraper.py -q`

- [ ] **Step 2: Run full suite**

Run: `pytest -q`

Expected: all tests pass, with no new warnings attributable to the OIC tab.

- [ ] **Step 3: Review the diff for scope**

Run: `git diff --stat HEAD~7..HEAD` and confirm only OIC aggregation, LiSA refresh safety, shared renderer, cockpit tab, and contract tests changed.

- [ ] **Step 4: Commit verification metadata if needed**

Do not add screenshots, generated caches, or unrelated UI changes to the feature commits.
