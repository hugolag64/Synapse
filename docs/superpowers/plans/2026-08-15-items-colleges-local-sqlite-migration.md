# Migration locale SQLite des Items et Collèges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `data/synapse_local.db` the runtime source of truth for all screens, then deliver the item-level Items/Collèges model and audit corrections without losing existing local history.

**Architecture:** Extend the existing SQLite database with a versioned catalog layer. Keep the existing `Cours` compatibility model so all screens can migrate through one local repository boundary, while item-level services aggregate fiches and evidence. Use explicit import runs with backups, dry-run diffs, provenance and reversible local overrides.

**Tech Stack:** Python 3, Pydantic `Cours`, SQLite via `sqlite3`, NiceGUI, pytest, existing `data_cache.json`, `data/nexternat_items.json`, and `data/college_consolidation.json`.

## Global Constraints

- SQLite database: `data/synapse_local.db`.
- Import source: `data_cache.json` first; Notion remains read-only and never receives automatic writes.
- Official item referential: `data/nexternat_items.json`, translated through `data/college_consolidation.json`.
- All 367 official items must exist locally; 125 non-college/non-item courses are archived, not deleted.
- `/items` is one row per item; `/colleges` counts multi-college items locally and deduplicates global KPIs.
- Existing behavior outside the audited Items/Collèges corrections must remain stable.
- Every migration/import is dry-run capable, backed up, versioned, idempotent and reversible.
- Production code is written only after a failing test exists and has been observed.
- No existing user changes may be overwritten; commit only files belonging to this plan.

---

## Task 1: Add versioned SQLite catalog schema and migration runner

**Files:**
- Create: `backend/state/catalog_migrations.py`
- Create: `backend/state/catalog_schema.py`
- Modify: `backend/core/reviews/local_store.py:150-180`
- Test: `tests/test_catalog_migrations.py`

**Interfaces:**
- `run_catalog_migrations(db_path: Path | None = None) -> tuple[int, ...]`
- `backup_database(db_path: Path | None = None) -> Path`
- `catalog_schema_version(db_path: Path | None = None) -> int`
- `ensure_catalog_tables(connection: sqlite3.Connection) -> None`

- [ ] **Step 1: Write failing migration tests.**

```python
def test_catalog_migration_creates_versioned_item_and_fiche_tables(tmp_path):
    db_path = tmp_path / "synapse.sqlite"
    applied = run_catalog_migrations(db_path)
    assert applied
    assert catalog_schema_version(db_path) >= 1
    tables = sqlite3.connect(db_path).execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {row[0] for row in tables}
    assert {"catalog_items", "catalog_colleges", "catalog_fiches", "catalog_fiche_colleges"} <= names


def test_catalog_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "synapse.sqlite"
    first = run_catalog_migrations(db_path)
    second = run_catalog_migrations(db_path)
    assert first
    assert second == ()
```

- [ ] **Step 2: Run the focused tests and verify the expected missing-runner failure.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_catalog_migrations.py`

Expected: FAIL because the migration module and tables do not yet exist.

- [ ] **Step 3: Implement migrations.**

Create a `schema_migrations` table and one migration containing:

```sql
CREATE TABLE catalog_items (
    id TEXT PRIMARY KEY,
    item_number INTEGER NOT NULL UNIQUE,
    official_title TEXT NOT NULL DEFAULT '',
    local_title TEXT,
    archived_at TEXT,
    provenance TEXT NOT NULL DEFAULT 'official_referential',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE catalog_colleges (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    archived_at TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE catalog_college_aliases (
    college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
    alias TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT 'official_referential',
    PRIMARY KEY (college_id, alias)
);
CREATE TABLE catalog_fiches (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES catalog_items(id),
    external_notion_id TEXT UNIQUE,
    imported_title TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    archived_at TEXT,
    provenance TEXT NOT NULL DEFAULT 'import',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE catalog_fiche_colleges (
    fiche_id TEXT NOT NULL REFERENCES catalog_fiches(id),
    college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
    source TEXT NOT NULL DEFAULT 'import',
    PRIMARY KEY (fiche_id, college_id)
);
CREATE TABLE catalog_official_item_colleges (
    item_id TEXT NOT NULL REFERENCES catalog_items(id),
    college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
    source_acronym TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (item_id, college_id)
);
CREATE TABLE catalog_local_overrides (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES catalog_items(id),
    college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
    action TEXT NOT NULL CHECK(action IN ('add', 'remove')),
    justification TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE catalog_resources (
    id TEXT PRIMARY KEY,
    fiche_id TEXT NOT NULL REFERENCES catalog_fiches(id),
    resource_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    checked_at TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE catalog_resource_colleges (
    resource_id TEXT NOT NULL REFERENCES catalog_resources(id),
    college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
    PRIMARY KEY (resource_id, college_id)
);
CREATE TABLE catalog_audit_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    justification TEXT,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE catalog_import_runs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('dry_run', 'apply', 'rollback')),
    status TEXT NOT NULL,
    backup_path TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX catalog_fiches_item_idx ON catalog_fiches(item_id);
CREATE INDEX catalog_fiche_colleges_college_idx ON catalog_fiche_colleges(college_id);
CREATE INDEX catalog_official_item_colleges_college_idx ON catalog_official_item_colleges(college_id);
```

Call the runner from the existing SQLite initialization path, never from an import or page render.

- [ ] **Step 4: Run the focused tests and the existing local-store tests.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_catalog_migrations.py tests/test_store_dedup.py`

Expected: PASS with no schema duplication errors.

- [ ] **Step 5: Commit the schema task.**

```bash
git add backend/state/catalog_migrations.py backend/state/catalog_schema.py backend/core/reviews/local_store.py tests/test_catalog_migrations.py
git commit -m "feat: add versioned local catalog schema"
```

## Task 2: Implement catalog import, backup, dry-run and rollback

**Files:**
- Create: `backend/state/catalog_import.py`
- Create: `backend/state/catalog_repository.py`
- Modify: `backend/state/store.py:300-370`
- Test: `tests/test_catalog_import.py`

**Interfaces:**
- `CatalogImportService.preview(source_path: Path) -> ImportPreview`
- `CatalogImportService.apply(source_path: Path, preview_id: str) -> ImportRun`
- `CatalogImportService.rollback(import_run_id: str) -> None`
- `CatalogRepository.list_items(include_archived: bool = False) -> list[CatalogItem]`
- `CatalogRepository.list_fiches(item_id: str, include_archived: bool = False) -> list[CatalogFiche]`
- `CatalogRepository.get_item_by_number(item_number: int) -> CatalogItem | None`
- `CatalogRepository.save_override(item_id: str, college_id: str, action: str, justification: str) -> None`

- [ ] **Step 1: Write failing import tests for the real data shape.**

```python
def test_preview_import_contains_all_official_items_and_archives_non_item_courses(tmp_path):
    db_path = tmp_path / "synapse.sqlite"
    source = Path("data_cache.json")
    service = CatalogImportService(db_path=db_path)
    preview = service.preview(source)
    assert preview.item_count == 367
    assert preview.fiche_count == 707
    assert preview.archived_course_count == 125
    assert preview.ambiguous_matches == 0


def test_apply_then_rollback_restores_catalog(tmp_path):
    db_path = tmp_path / "synapse.sqlite"
    service = CatalogImportService(db_path=db_path)
    preview = service.preview(Path("data_cache.json"))
    run = service.apply(Path("data_cache.json"), preview.id)
    assert service.repository.count_items() == 367
    service.rollback(run.id)
    assert service.repository.count_items() == 0
```

- [ ] **Step 2: Run the focused tests and verify the import API failure.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_catalog_import.py`

Expected: FAIL because the repository/import service does not exist.

- [ ] **Step 3: Implement deterministic normalization.**

Use `nexternat_items.json` to upsert all 367 item rows, `college_consolidation.json` to create local colleges and aliases, and `data_cache.json` to import course fiches. Match existing local records first by `id`, then by `item_number` plus normalized title; ambiguous matches become `catalog_import_runs` proposals and are not applied. Preserve all imported JSON in `catalog_fiches.payload_json`.

Use the existing course id as the first local fiche id when it is stable; generate a UUID only for new local fiches. Preserve `external_notion_id` separately. Populate official item-college relations independently from observed fiche-college relations. Mark courses without both college and item number as archived.

Implement `backup_database()` with SQLite backup API or a consistent byte-for-byte copy while holding the database lock. Store every backup under `data/backups/` and record its path in the import run.

- [ ] **Step 4: Add repository read/write methods and verify round trips.**

Repository reads must return the existing `Cours` shape through a compatibility adapter so existing consumers remain valid while the source becomes SQLite.

- [ ] **Step 5: Run import tests plus the data snapshot count check.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_catalog_import.py tests/test_catalog_migrations.py`

Expected: PASS; preview remains read-only and apply/rollback restore the exact catalog counts.

- [ ] **Step 6: Commit the import task.**

```bash
git add backend/state/catalog_import.py backend/state/catalog_repository.py backend/state/store.py tests/test_catalog_import.py
git commit -m "feat: import and rollback local catalog data"
```

## Task 3: Make the local catalog the runtime source for all screens

**Files:**
- Modify: `backend/state/store.py:312-376`
- Modify: `backend/core/reviews/service.py:48-160`
- Modify: `backend/core/knowledge/store.py:30-150`
- Modify: `backend/core/knowledge/service.py:77-245`
- Modify: `frontend/pages/*.py` only where direct course loading bypasses `data_store`
- Test: `tests/test_runtime_catalog_source.py`

**Interfaces:**
- `data_store.load_from_disk()` loads the catalog repository, not `data_cache.json`, after the migration is applied.
- `data_store.cours` remains a compatibility list of `Cours` objects backed by SQLite.
- `data_store.get_colleges()` returns active local colleges.
- `data_store.get_cours_for_college(college)` reads active fiche-college relations.

- [ ] **Step 1: Write failing runtime-source tests.**

```python
def test_data_store_reads_catalog_rows_after_json_changes(tmp_path, monkeypatch):
    db_path = tmp_path / "synapse.sqlite"
    import_catalog_fixture(db_path)
    monkeypatch.setenv("SYNAPSE_TEST_DB_PATH", str(db_path))
    store = DataStore()
    assert store.load_from_disk(force=True)
    assert store.get_item_by_number(255).title == "Diabète gestationnel"
    assert len(store.get_cours_for_college("Endocrinologie")) >= 1
```

- [ ] **Step 2: Run the test and verify the JSON-backed behavior fails.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_runtime_catalog_source.py`

Expected: FAIL because `DataStore.load_from_disk()` still reads only JSON.

- [ ] **Step 3: Route `DataStore` through `CatalogRepository`.**

Keep `data_cache.json` as the explicit import fallback only when the catalog schema has never been initialized. Preserve preferences and unrelated JSON fields until their own SQLite migrations exist. Update `alias_ids()` to use catalog item/fiche relations while retaining the public return type expected by review history.

Update knowledge and review services to use the local catalog adapter rather than independently reconstructing course lists from JSON. Remove runtime assumptions that Notion ids are the only identity; keep them as external ids.

- [ ] **Step 4: Inventory and migrate all direct course lookups.**

Use `rg -n "data_store\\.cours|data_store\\.get_colleges|load_from_disk" frontend backend main.py` and update each consumer that needs item-level semantics. Do not change unrelated page behavior; add adapter methods when a page needs a stable `Cours` compatibility object.

- [ ] **Step 5: Run the full existing test suite.**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: no regression in existing tests; any fixture requiring the old JSON path must use the test database fixture explicitly.

- [ ] **Step 6: Commit the runtime migration task.**

```bash
git add backend/state/store.py backend/core/reviews/service.py backend/core/knowledge/store.py backend/core/knowledge/service.py frontend main.py tests/test_runtime_catalog_source.py
git commit -m "feat: use local catalog as runtime source"
```

## Task 4: Unify item-level mastery, evidence and planning

**Files:**
- Modify: `backend/core/reviews/mastery.py:48-220`
- Modify: `backend/core/reviews/service.py:48-355`
- Modify: `backend/core/knowledge/service.py:143-220`
- Modify: `frontend/pages/items.py:230-390`
- Modify: `frontend/pages/colleges_cockpit.py:279-430`
- Modify: `frontend/pages/course_detail_cockpit.py:303-430`
- Test: `tests/test_item_mastery_coherence.py`

**Interfaces:**
- `get_item_mastery(item_id: str | int, context: Literal["college", "ue"] = "college") -> CourseProgressSnapshot`
- `get_item_fiche_ids(item_id: str | int) -> tuple[str, ...]`
- `get_item_evidence(item_id: str | int) -> EvidenceSummary`
- `review_service.get_tasks_for_item(item_id: str | int, context: ReviewContext = "college") -> list[ReviewTask]`

- [ ] **Step 1: Add failing tests for the four acceptance invariants.**

```python
def test_declared_seed_survives_missing_pdf_and_first_read(item_state_fixture):
    snapshot = get_item_mastery(item_state_fixture.item_id)
    assert snapshot.score is not None
    assert snapshot.evidence_count == 0


def test_item_mastery_is_identical_from_each_fiche(multi_fiche_fixture):
    snapshots = [get_item_mastery(fiche.id) for fiche in multi_fiche_fixture.fiches]
    assert {snapshot.score for snapshot in snapshots} == {snapshots[0].score}
    assert {snapshot.evidence_count for snapshot in snapshots} == {snapshots[0].evidence_count}


def test_item_tasks_are_unique_across_fiches(multi_fiche_fixture):
    tasks = review_service.get_tasks_for_item(multi_fiche_fixture.item_id)
    assert len({task.item_number for task in tasks}) == len(tasks)


def test_oic_without_attempt_is_not_zero_percent(unmeasured_oic_fixture):
    coverage = oic_coverage(unmeasured_oic_fixture.item_id)
    assert coverage["rang_a_conclusive"] is False
    assert coverage["rang_a_pct_attempted"] is None
```

- [ ] **Step 2: Run the tests and observe the expected failures.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_item_mastery_coherence.py`

Expected: FAIL because there is no public item-level mastery API, declared seeds are short-circuited, and OIC reads one fiche.

- [ ] **Step 3: Implement the public item-level facade.**

Resolve an item number or fiche id to the local item, gather all fiche ids, merge sessions/history/QCM/OIC/lacunes/annales/Anki by item, and call the existing scoring rules once. Move the declared seed check ahead of the no-PDF/no-first-read early return while preserving the current conservative mapping where a declared `solide` remains at most `À consolider` without evidence.

- [ ] **Step 4: Make OIC coverage accept all fiche ids.**

Aggregate active OIC rows and attempts across all aliases, treat no attempts as unmeasured, and preserve the current Rang A thresholds.

- [ ] **Step 5: Route all three audited pages and the review service through the facade.**

Remove the private cache call from `items.py`, stop deriving Collèges mastery from `ReviewTask`, aggregate last-review data, and expose tasks by item while retaining course ids in legacy task payloads.

- [ ] **Step 6: Run focused and full tests.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_item_mastery_coherence.py tests/test_mastery_algorithm.py tests/test_mastery_provenance.py tests/test_colleges_cockpit.py tests/test_items_sorting.py`

Expected: PASS, then run `.venv\Scripts\python.exe -m pytest -q` with no regressions.

- [ ] **Step 7: Commit the mastery task.**

```bash
git add backend/core/reviews/mastery.py backend/core/reviews/service.py backend/core/knowledge/service.py frontend/pages/items.py frontend/pages/colleges_cockpit.py frontend/pages/course_detail_cockpit.py tests/test_item_mastery_coherence.py
git commit -m "feat: unify item mastery and review evidence"
```

## Task 5: Implement item-level Items/Collèges views and navigation

**Files:**
- Modify: `frontend/pages/items.py:120-390`
- Modify: `frontend/pages/colleges_cockpit.py:179-760`
- Modify: `frontend/pages/course_detail_cockpit.py:380-430`
- Modify: `backend/core/knowledge/course_aliases.py:48-145`
- Modify: `backend/core/qcm/items_mapping.py:1-130`
- Modify: `frontend/components/status_badge.py:1-30`
- Modify: `frontend/components/mastery_indicator.py:60-100`
- Test: `tests/test_items_colleges_coherence.py`

**Interfaces:**
- `items_mapping.item_colleges(item_number: str | int) -> tuple[str, ...]`
- `course_aliases.item_id_for_course(course_id: str) -> str`
- `course_aliases.canonical_course(courses: Sequence) -> Cours`
- `items_page.build_item_rows(repository: CatalogRepository) -> list[dict]`
- `colleges_cockpit.build_college_rows(repository: CatalogRepository) -> list[dict]`

- [ ] **Step 1: Write failing cross-view tests.**

The fixture must contain one item with two fiches, one missing official fiche, one declared score, one measured score, and one shared PDF.

```python
def test_items_has_one_row_per_official_item(coherence_fixture):
    rows = build_item_rows(coherence_fixture.catalog)
    assert len(rows) == 367
    assert len({row["item_number"] for row in rows}) == 367


def test_college_global_total_deduplicates_multi_college_items(coherence_fixture):
    summary = build_pilotage_summary(coherence_fixture.college_rows)
    assert summary["total_items"] == 367


def test_breadcrumb_context_always_contains_item(coherence_fixture):
    for fiche in coherence_fixture.fiches:
        assert breadcrumb_target(fiche).contains_item


def test_status_vocabulary_has_label_and_css_class():
    produced = set(PROGRESSION_COLORS)
    assert produced <= set(STATUS_LABELS)
    assert all(status_class(status) for status in produced)
```

- [ ] **Step 2: Run the tests and verify failures against current per-fiche rendering.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_items_colleges_coherence.py`

Expected: FAIL because `/items` currently collects fiches directly and the pilotage total sums college rows.

- [ ] **Step 3: Build item-level row aggregation.**

Group active fiches by local item UUID, use official item title, union college names, expose missing-fiche flags, choose the canonical fiche from the first official local college present, and use a deterministic UUID fallback. Preserve the `Cours` object in the row for navigation compatibility.

- [ ] **Step 4: Implement multi-college mapping and breadcrumb fallback.**

Load official item colleges from `nexternat_items.json`, map names through `college_consolidation.json`, keep `resolve()` as a compatibility first-college function, and choose a breadcrumb college only if it exists on an actual fiche; otherwise use the opened fiche’s college context. URL-encode the query parameter.

- [ ] **Step 5: Correct college rows, counters and filters.**

Count item-college relations for local rows, deduplicate pilotage totals by item UUID, count missing PDFs per item-college relation, make filters cumulative, and preserve the selected college when clicking a status chip.

- [ ] **Step 6: Align labels, provenance and events.**

Pass `evidence_count` to both list indicators, add a CSS class for `maîtrisé`, build status distribution from the single vocabulary, stop propagation for nested actions, and expose explicit `Non évaluée` values.

- [ ] **Step 7: Add targeted rendering/performance tests.**

Assert that filter and expand callbacks reuse computed rows, no task lookup scans the full task list per course, and no full `_compute()` occurs for pure UI state changes.

- [ ] **Step 8: Run focused and full tests, then commit.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_items_colleges_coherence.py tests/test_colleges_cockpit.py tests/test_colleges_cockpit_items.py tests/test_colleges_cockpit_ui.py tests/test_course_aliases.py tests/test_items_sorting.py`

```bash
git add frontend/pages/items.py frontend/pages/colleges_cockpit.py frontend/pages/course_detail_cockpit.py backend/core/knowledge/course_aliases.py backend/core/qcm/items_mapping.py frontend/components/status_badge.py frontend/components/mastery_indicator.py tests/test_items_colleges_coherence.py
git commit -m "fix: make items and colleges item-centric"
```

## Task 6: Add local administration, import assistant and recovery UI

**Files:**
- Create: `frontend/pages/catalog_admin.py`
- Modify: `frontend/pages/settings_cockpit.py:400-520`
- Modify: `backend/state/catalog_import.py`
- Modify: `backend/state/catalog_repository.py`
- Test: `tests/test_catalog_admin.py`

**Interfaces:**
- `render_catalog_admin() -> None`
- `CatalogImportService.preview(source_path: Path) -> ImportPreview`
- `CatalogImportService.apply(source_path: Path, preview_id: str) -> ImportRun`
- `CatalogImportService.rollback(import_run_id: str) -> None`
- `CatalogRepository.archive_item(item_id: str, justification: str) -> None`
- `CatalogRepository.restore_item(item_id: str, justification: str) -> None`
- `CatalogRepository.merge_items(master_id: str, duplicate_id: str, justification: str) -> None`

- [ ] **Step 1: Write failing admin tests.**

```python
def test_manual_override_requires_justification(admin_repository):
    with pytest.raises(ValueError, match="justification"):
        admin_repository.add_college_override("item-1", "college-1", "add", "")


def test_archive_is_reversible(admin_repository):
    admin_repository.archive_item("item-1")
    assert admin_repository.get_item("item-1").archived_at is not None
    admin_repository.restore_item("item-1")
    assert admin_repository.get_item("item-1").archived_at is None
```

- [ ] **Step 2: Implement repository mutations with audit log entries.**

Every mutation writes an audit row containing before/after JSON, provenance, operation, timestamp and required justification for overrides, merges and manual mappings.

- [ ] **Step 3: Implement the Settings assistant.**

Add tabs for catalog search/edit, import simulation, pending proposals, backups and audit history. Use guided forms, preview impacts before applying, and support batch acceptance of import changes. Do not add authentication.

- [ ] **Step 4: Add item/fiche/college/resource workflows.**

Support creating missing fiches prefilled from the official item, editing local titles, managing aliases, attaching resources to multiple colleges, marking resources `À vérifier`/`Invalide`, archiving/restoring items and fiches, and merging duplicate items while retaining evidence and aliases.

- [ ] **Step 5: Run focused UI/repository tests.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_catalog_admin.py tests/test_catalog_import.py`

Expected: PASS with test database isolation and no writes to the real database.

- [ ] **Step 6: Commit the administration task.**

```bash
git add frontend/pages/catalog_admin.py frontend/pages/settings_cockpit.py backend/state/catalog_import.py backend/state/catalog_repository.py tests/test_catalog_admin.py
git commit -m "feat: add local catalog administration"
```

## Task 7: Complete performance, integration coverage and verification

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py:350-760`
- Modify: `frontend/pages/course_detail_cockpit.py:318-355`
- Modify: `backend/core/knowledge/college_validation.py:56-110`
- Modify: `backend/core/reviews/service.py:100-370`
- Create: `tests/fixtures/catalog_snapshot.json`
- Create: `tests/test_items_colleges_integration.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- `build_tasks_by_item(tasks: Iterable[ReviewTask]) -> dict[str, list[ReviewTask]]`
- `build_history_by_course(history: Mapping) -> dict[str, set[str]]`
- `render_colleges_cockpit` reuses an immutable computed view model for pure UI state changes.

- [ ] **Step 1: Add a sanitized snapshot fixture.**

Include the structural cases: 367 official items, multi-college items, missing fiches, shared resources, declared state, measured evidence, archived non-item courses and one ambiguous import match. Do not include Notion page ids, raw URLs, personal data or real history content.

- [ ] **Step 2: Write integration invariant tests.**

```python
def test_snapshot_has_identical_item_mastery_in_all_views(snapshot_app):
    item_id = snapshot_app.item_id("255")
    assert snapshot_app.items_mastery(item_id) == snapshot_app.college_mastery(item_id)
    assert snapshot_app.items_mastery(item_id) == snapshot_app.detail_mastery(item_id)


def test_snapshot_has_one_items_row_per_official_item(snapshot_app):
    rows = snapshot_app.item_rows()
    assert len(rows) == 367
    assert len({row["item_id"] for row in rows}) == 367


def test_snapshot_pilotage_total_equals_official_item_count(snapshot_app):
    assert snapshot_app.pilotage_summary()["total_items"] == 367


def test_snapshot_breadcrumbs_resolve_or_show_missing_fiche(snapshot_app):
    for breadcrumb in snapshot_app.breadcrumbs():
        assert breadcrumb.contains_item or breadcrumb.missing_fiche


def test_snapshot_import_dry_run_is_read_only(snapshot_app):
    before = snapshot_app.database_bytes()
    snapshot_app.preview_import()
    assert snapshot_app.database_bytes() == before


def test_snapshot_import_rollback_restores_database(snapshot_app):
    before = snapshot_app.database_digest()
    run_id = snapshot_app.apply_import()
    snapshot_app.rollback_import(run_id)
    assert snapshot_app.database_digest() == before
```

- [ ] **Step 3: Implement indexed task/history lookups.**

Build `tasks_by_item`, `tasks_by_course` and `history_by_course` once per computed view. Replace nested `next()` scans and per-course full-history scans with dictionary lookups. Add a targeted performance test asserting the indexing helpers are called once per render.

- [ ] **Step 4: Separate render state from computed data.**

Compute rows once at page load or after mutation. Expand/collapse, filter and sort callbacks must reuse the view model and redraw only their container. Detail pages must request item-scoped tasks from the review cache rather than regenerate all reviews.

- [ ] **Step 5: Run the complete verification suite.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

Expected: pytest exits 0, diff check emits no output, and `git status` lists only intended plan implementation files plus pre-existing user files.

- [ ] **Step 6: Commit the verification task.**

```bash
git add backend frontend tests
git commit -m "test: verify local catalog and item college coherence"
```

## Final acceptance checklist

- [ ] All seven tasks committed and reviewed locally.
- [ ] SQLite migrations are idempotent and recoverable.
- [ ] Import preview is read-only and rollback restores the previous state.
- [ ] All runtime screens source course/catalog data through SQLite.
- [ ] `/items` displays one row per official item.
- [ ] `/colleges` includes empty colleges and deduplicated global totals.
- [ ] Mastery, evidence, OIC and tasks are item-level and consistent.
- [ ] Paramètres supports local editing, overrides, audit and backups.
- [ ] Full pytest suite passes with fresh output.
- [ ] No pre-existing user files were overwritten or staged unintentionally.
