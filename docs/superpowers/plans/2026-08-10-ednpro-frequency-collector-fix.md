# EDNpro Frequency Collector Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the EDNpro frequency synchronizer consume `get_annales_items_index` and persist the exact session, question, year, and priority data for all 367 items.

**Architecture:** Keep the authenticated browser as the only holder of the EDNpro session. Add a pure payload normalizer/builder for the RPC response, then make the Playwright collector request that RPC from the page context and validate a complete 367-item snapshot before calling the existing atomic store replacement.

**Tech Stack:** Python 3, Playwright, SQLite, pytest, existing `backend.core.ednpro` and `local_store` modules.

## Global Constraints

- Do not persist or print browser access tokens.
- Do not replace the active snapshot when the RPC response is empty, malformed, duplicated, or incomplete.
- Preserve the canonical 367-item catalog from `backend.core.qcm.items_mapping.all_items()`.
- Preserve legacy payload normalization tests and CLI/CDP behavior.

---

### Task 1: Normalize the real EDNpro RPC payload

**Files:**
- Modify: `backend/core/ednpro/frequency.py:46-124`
- Test: `tests/test_ednpro_frequency.py`

**Interfaces:**
- Consumes rows containing `item_number`, `nb_sessions`, `nb_questions`, and `annees`.
- Produces the existing normalized fields `item_number`, `priority`, `session_count`, `question_count`, `years`, `source_url`, and `collected_at`.

- [ ] **Step 1: Write the failing test**

Add a test with the exact RPC shape:

```python
def test_normalize_training_payload_accepts_ednpro_annales_index_shape():
    from backend.core.ednpro.frequency import normalize_training_payload

    rows = normalize_training_payload(
        [{"item_number": 247, "nb_sessions": 13, "nb_questions": 31,
          "annees": [2025, 2024, 2023, 2022]}],
        source_url="https://ednpro.app/training-v2",
        collected_at="2026-08-10T10:27:04+00:00",
    )

    assert rows[0]["priority"] == "indispensable"
    assert rows[0]["session_count"] == 13
    assert rows[0]["question_count"] == 31
    assert rows[0]["years"] == [2022, 2023, 2024, 2025]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency.py::test_normalize_training_payload_accepts_ednpro_annales_index_shape -q
```

Expected: FAIL because the current normalizer does not read `nb_sessions`, `nb_questions`, or `annees` and defaults the priority to `basique`.

- [ ] **Step 3: Write the minimal implementation**

Extend the existing alias lists in `normalize_training_payload` with:

```python
"nb_sessions"
"nb_questions"
"annees"
```

When no textual priority is supplied, derive it from the normalized session count using the existing EDNpro thresholds: `>=3` indispensable, `2` important, `1` basique, `0` jamais_tombe.

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency.py -q
```

Expected: all tests pass.

### Task 2: Build and validate a complete 367-item snapshot

**Files:**
- Modify: `backend/core/ednpro/frequency_sync.py:15-48`
- Test: `tests/test_ednpro_frequency_sync.py`

**Interfaces:**
- Add `build_complete_frequency_snapshot(remote_rows, catalog_items, source_url, collected_at) -> list[dict]`.
- The function must return exactly one normalized row per catalog item, filling missing RPC rows with zero sessions, zero questions, empty years, and `jamais_tombe`.
- The function must raise `ValueError` for duplicate remote item numbers or a catalog that is not exactly 367 unique items.

- [ ] **Step 1: Write the failing tests**

Add tests for filling the absent items and rejecting duplicate/incomplete inputs:

```python
def test_build_complete_frequency_snapshot_fills_never_seen_items():
    from backend.core.ednpro.frequency_sync import build_complete_frequency_snapshot

    rows = build_complete_frequency_snapshot(
        [{"item_number": 247, "nb_sessions": 13, "nb_questions": 31,
          "annees": [2025, 2024, 2023, 2022]}],
        ["1", "247"],
        source_url="training-v2",
        collected_at="2026-08-10T10:27:04+00:00",
        expected_catalog_size=2,
    )

    assert rows[0]["priority"] == "jamais_tombe"
    assert rows[1]["session_count"] == 13


def test_build_complete_frequency_snapshot_rejects_duplicate_remote_items():
    from backend.core.ednpro.frequency_sync import build_complete_frequency_snapshot

    with pytest.raises(ValueError, match="duplicate"):
        build_complete_frequency_snapshot(
            [{"item_number": 247}, {"item_number": 247}],
            ["247"],
            source_url="training-v2",
            collected_at="2026-08-10T10:27:04+00:00",
            expected_catalog_size=1,
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_sync.py::test_build_complete_frequency_snapshot_fills_never_seen_items tests/test_ednpro_frequency_sync.py::test_build_complete_frequency_snapshot_rejects_duplicate_remote_items -q
```

Expected: FAIL because the builder does not exist.

- [ ] **Step 3: Implement the builder**

Use `all_items()` as the production catalog source, normalize catalog item numbers to strings, reject duplicates, normalize the remote rows through `normalize_training_payload`, and fill missing items before returning the rows sorted by numeric item number.

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_sync.py -q
```

Expected: all synchronization tests pass.

### Task 3: Collect the RPC from the authenticated browser

**Files:**
- Modify: `backend/core/ednpro/frequency_sync.py:50-125`
- Test: `tests/test_ednpro_frequency_sync.py`

**Interfaces:**
- Add an internal async browser helper that returns only the decoded `get_annales_items_index` payload and never returns token material.
- Add `sync_from_annales_index_payload(payload, catalog_items, source_url, collected_at) -> dict` as the persistence seam for a validated RPC payload.
- `collect_frequency()` uses the helper, builds the complete snapshot, and calls `replace_ednpro_item_frequencies()` only after validation.

- [ ] **Step 1: Write the failing test**

Add this test with a fake store and a two-item catalog so it exercises the persistence seam without launching a browser:

```python
def test_sync_from_annales_index_payload_persists_only_complete_snapshot(monkeypatch):
    from backend.core.ednpro import frequency_sync

    class Store:
        def __init__(self):
            self.rows = None

        def replace_ednpro_item_frequencies(self, rows):
            self.rows = rows

        def compare_latest_ednpro_frequency_snapshots(self):
            return []

    store = Store()
    monkeypatch.setattr(frequency_sync, "local_store", store)

    result = asyncio.run(
        frequency_sync.sync_from_annales_index_payload(
            [{"item_number": 247, "nb_sessions": 13, "nb_questions": 31,
              "annees": [2025, 2024, 2023, 2022]}],
            catalog_items=["1", "247"],
            source_url="training-v2",
            collected_at="2026-08-10T10:27:04+00:00",
            expected_catalog_size=2,
        )
    )

    assert result["status"] == "updated"
    assert len(store.rows) == 2
    assert store.rows[1]["session_count"] == 13
    assert store.rows[1]["question_count"] == 31
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_sync.py -q
```

Expected: FAIL because `sync_from_annales_index_payload` does not exist.

- [ ] **Step 3: Implement the minimal collector change**

From the authenticated page context, retrieve the Supabase project key from the loaded application bundle and use the browser’s existing auth token only in page memory to POST `get_annales_items_index`. Retry transient non-200 responses a bounded number of times, return `auth_required` when no auth token is available, and never write the token to logs, files, or the database.

After decoding the RPC response, call `build_complete_frequency_snapshot(..., all_items(), ..., expected_catalog_size=367)` and persist only the validated result.

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency_sync.py tests/test_ednpro_frequency.py -q
```

Expected: all focused tests pass.

### Task 4: Verify against the authenticated EDNpro page

**Files:**
- No source changes.
- Verify: `data/synapse_local.db`

- [ ] **Step 1: Run the collector against the existing CDP session**

Run:

```powershell
.venv\Scripts\python.exe scripts/ednpro/frequency_collector.py --force --cdp-url http://127.0.0.1:9222
```

Expected: `status=updated` and `rows=367`.

- [ ] **Step 2: Verify the stored snapshot**

Check that SQLite contains 367 rows, source URL `https://ednpro.app/training-v2`, priority totals `205/57/67/38`, and these exact samples:

```text
245: 3 sessions, 3 questions, [2022, 2023]
246: 1 session, 3 questions, [2022]
247: 13 sessions, 31 questions, [2022, 2023, 2024, 2025]
248: 3 sessions, 6 questions, [2023, 2024, 2025]
```

- [ ] **Step 3: Run the complete relevant test set**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ednpro_frequency.py tests/test_ednpro_frequency_sync.py tests/test_ednpro_frequency_store.py tests/test_ednpro_frequency_ui.py -q
```

Expected: all tests pass with zero failures.
