# Inférence Gemini des rangs UNESS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatiser la qualification des rangs manquants des questions UNESS avec OIC, persister une file relançable et fournir une validation admin traçable.

**Architecture:** Un module pur construit et parse les lots Gemini. `local_store` persiste les jobs et l’historique. Un runner borné est appelé par la boucle de fond existante, réclame des jobs avec bail et applique les décisions dans les métadonnées de question. FastAPI et le cockpit NiceGUI exposent la file sans créer un nouveau démon.

**Tech Stack:** Python 3.11, SQLite/WAL via `backend.core.reviews.local_store`, FastAPI/Pydantic, NiceGUI, Gemini via `AIService`, pytest.

## Global Constraints

- Ne jamais écraser un rang officiel `A` ou `B`.
- Ne jamais utiliser une inférence Gemini sous `0,85` ou marquée ambiguë pour résoudre automatiquement un rang.
- Ne pas appeler Gemini quand aucun OIC local n’est disponible ; le job devient `needs_oic`.
- Conserver les erreurs et payloads sans secrets, clés API ni URLs signées.
- Modifier uniquement les métadonnées `uness.question.rank*` lors de l’application d’un rang ; l’énoncé, les propositions et la correction officielle restent inchangés.
- Garder les tests indépendants du `data_cache.json` utilisateur et de la clé Gemini réelle.
- Ne pas mélanger les fichiers locaux préexistants du checkout principal avec ce chantier.

---

### Task 1: Contrat pur d’inférence de rang UNESS

**Files:**
- Create: `backend/core/uness/rank_inference.py`
- Modify: `backend/core/ai/routing.py`
- Modify: `backend/core/ai/tasks.py`
- Test: `tests/test_uness_rank_inference.py`

**Interfaces:**
- Produces `UnessRankCandidate`, `build_uness_rank_prompt(item_number, questions, oics)`, `parse_uness_rank_response(text, question_ids)`, and `infer_uness_ranks(prompt, service=None)`.
- Consumes `AITask`, `AIService`, `rank_service.INFERENCE_THRESHOLD`, and question metadata dictionaries.

- [ ] **Step 1: Write failing contract tests**

  Add tests asserting that the prompt includes the item, OIC code/intitulé/rang, question IDs, prompt and choices; that parsing keeps only known IDs, ranks `A`/`B`, confidence in `[0,1]`, non-ambiguous values at or above `0.85`; and that malformed JSON, unknown IDs, `null`, low confidence and ambiguity produce no accepted candidate.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

  Run:

  ```powershell
  pytest -q tests/test_uness_rank_inference.py
  ```

  Expected: import/attribute failures because the new module and task entry point do not exist yet.

- [ ] **Step 3: Implement the minimal pure contract**

  Reuse the existing EDNpro rank-inference conventions but adapt serialization to UNESS metadata (`prompt`, `choices`, `answer`, `explanation`, `item_numbers`). Add `AITask.UNESS_RANK`, route it to `FLASH_LITE`, and make `infer_uness_ranks` call `AIService.generate(..., response_format="json")`.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run:

  ```powershell
  pytest -q tests/test_uness_rank_inference.py
  ```

- [ ] **Step 5: Commit the contract**

  ```powershell
  git add backend/core/uness/rank_inference.py backend/core/ai/routing.py backend/core/ai/tasks.py tests/test_uness_rank_inference.py
  git commit -m "feat: add uness rank inference contract"
  ```

### Task 2: SQLite jobs, claims and audit events

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_uness_rank_jobs_store.py`

**Interfaces:**
- Produces `scan_uness_rank_jobs()`, `list_uness_rank_jobs()`, `get_uness_rank_job(job_id)`, `claim_uness_rank_jobs(limit, worker_id)`, `record_uness_rank_result(...)`, `mark_uness_rank_job_needs_oic(...)`, `accept_uness_rank_job(...)`, `decide_uness_rank_job(...)`, `reject_uness_rank_job(...)`, and `retry_uness_rank_job(...)`.
- Consumes the existing `ai_practice_questions`, `ai_practice_question_items`, `ai_practice_sessions`, `uness_annales`, and `lisa_oic` tables.

- [ ] **Step 1: Write failing persistence tests**

  Use a temporary SQLite database through the existing test fixture pattern. Cover idempotent scanning, exclusion of official ranks, creation of `needs_oic`, atomic claim/lease behavior, expired-lease recovery, result persistence, admin decisions, retry reset, event history, and updating only `uness.question.rank*` metadata.

- [ ] **Step 2: Run the store tests and verify the expected failure**

  ```powershell
  pytest -q tests/test_uness_rank_jobs_store.py
  ```

  Expected: missing table/functions failures.

- [ ] **Step 3: Add the migration and store functions**

  Add `uness_rank_inference_jobs` and `uness_rank_inference_events` in the existing initialization/migration flow. Store JSON fields with `ensure_ascii=False`, use `_conn()` for every transaction, generate a worker lease timestamp, and record every state transition. When applying a decision, load `import_metadata_json`, update only the nested rank fields, write it back atomically, and preserve the previous metadata in the event payload.

- [ ] **Step 4: Run the store tests and verify they pass**

  ```powershell
  pytest -q tests/test_uness_rank_jobs_store.py
  ```

- [ ] **Step 5: Commit persistence**

  ```powershell
  git add backend/core/reviews/local_store.py tests/test_uness_rank_jobs_store.py
  git commit -m "feat: persist uness rank inference jobs"
  ```

### Task 3: Relançable worker et intégration OIC

**Files:**
- Create: `backend/core/uness/rank_job_runner.py`
- Modify: `backend/core/background.py`
- Test: `tests/test_uness_rank_job_runner.py`

**Interfaces:**
- Produces `scan_and_queue_missing_ranks()`, `run_uness_rank_jobs(limit=10)`, and `run_uness_rank_cycle(limit=10)`.
- Consumes the pure prompt/parser contract, `data_store.cours`, `local_store.get_lisa_oic_for_item`, `resolve_rank`, and `infer_uness_ranks`.

- [ ] **Step 1: Write failing worker tests**

  Cover: official rank skipped; missing item skipped; item with no OIC becomes `needs_oic` without calling the AI service; a successful Gemini response becomes `needs_admin` or `resolved` according to the existing threshold contract; low-confidence/ambiguous responses remain `needs_admin`; exceptions become `retry_wait`; and a second cycle does not duplicate jobs.

- [ ] **Step 2: Run the worker tests and verify the expected failure**

  ```powershell
  pytest -q tests/test_uness_rank_job_runner.py
  ```

  Expected: missing module/functions failures.

- [ ] **Step 3: Implement the bounded worker**

  Scan imported UNESS questions from SQLite, resolve item-to-course IDs from `data_store.cours`, fetch OIC context, claim at most `limit` jobs, execute one Gemini batch per item in `asyncio.to_thread`, and record a bounded error without aborting other jobs. Use a stable worker ID and lease expiry. Do not let a missing Gemini key crash the background loop.

- [ ] **Step 4: Add the background hook**

  Call `run_uness_rank_cycle(limit=10)` from `run_background_tasks()` after the existing UNESS correction retry block. Log counts only; never log question contents or raw provider errors.

- [ ] **Step 5: Run worker and regression tests**

  ```powershell
  pytest -q tests/test_uness_rank_inference.py tests/test_uness_rank_jobs_store.py tests/test_uness_rank_job_runner.py tests/test_uness_import.py tests/test_rank_service.py
  ```

- [ ] **Step 6: Commit the worker**

  ```powershell
  git add backend/core/uness/rank_job_runner.py backend/core/background.py tests/test_uness_rank_job_runner.py
  git commit -m "feat: run uness rank inference jobs in background"
  ```

### Task 4: API admin de la file

**Files:**
- Modify: `backend/api/qcm.py`
- Test: `tests/test_uness_rank_admin_api.py`

**Interfaces:**
- Produces `GET /api/qcm/admin/rank-jobs`, `POST /api/qcm/admin/rank-jobs/scan`, `POST /api/qcm/admin/rank-jobs/{job_id}/retry`, `/accept`, `/decide`, and `/reject`.
- Consumes the store service and `RankDecision`; accepts only `A` or `B` for manual decisions and a non-empty reason.

- [ ] **Step 1: Write failing API tests**

  Use the existing FastAPI test fixture to assert pagination/filtering, scan idempotency, 404 for unknown jobs, acceptance of a valid Gemini result, manual `A`/`B` decisions, rejection, retry, and 400 for invalid rank or missing reason.

- [ ] **Step 2: Run the API tests and verify the expected failure**

  ```powershell
  pytest -q tests/test_uness_rank_admin_api.py
  ```

- [ ] **Step 3: Add Pydantic payloads and routes**

  Keep routes thin: validate input, call one store operation, convert expected `ValueError`/missing job to HTTP 400/404, and return counts plus the updated job. The acceptance route must refuse a job without an accepted Gemini rank.

- [ ] **Step 4: Run API tests and the existing QCM API tests**

  ```powershell
  pytest -q tests/test_uness_rank_admin_api.py tests/test_qcm_api_completion.py
  ```

- [ ] **Step 5: Commit the API**

  ```powershell
  git add backend/api/qcm.py tests/test_uness_rank_admin_api.py
  git commit -m "feat: expose uness rank admin queue api"
  ```

### Task 5: Panneau admin NiceGUI

**Files:**
- Create: `frontend/components/uness_rank_admin.py`
- Modify: `frontend/pages/settings_cockpit.py`
- Test: `tests/test_uness_rank_admin_ui.py`

**Interfaces:**
- Produces `render_uness_rank_admin(container=None)` with KPI cards, filters, question/OIC previews, and actions wired to the local API.
- Consumes the API routes from Task 4 and existing NiceGUI settings styling/components.

- [ ] **Step 1: Write failing UI contract tests**

  Assert the component renders the five counters, displays Gemini confidence/source and OIC evidence, labels unresolved ranks as `À valider`, and exposes accept/A/B/reject/retry actions without displaying an official badge for a Gemini result.

- [ ] **Step 2: Run the UI tests and verify the expected failure**

  ```powershell
  pytest -q tests/test_uness_rank_admin_ui.py
  ```

  Expected: missing component/import failures.

- [ ] **Step 3: Implement the compact panel**

  Follow existing `settings_cockpit.py` async button patterns. Keep API calls in a small helper, refresh the list after every mutation, and render question text in a bounded preview. Use source labels `Officiel`, `Gemini`, `Admin` and `Inconnu` consistently.

- [ ] **Step 4: Mount it under the settings diagnostics area**

  Add one expansion titled `RANGS UNESS — VALIDATION` and leave unrelated settings behavior unchanged.

- [ ] **Step 5: Run UI and import tests**

  ```powershell
  pytest -q tests/test_uness_rank_admin_ui.py tests/test_settings_cockpit.py tests/test_uness_rank_admin_api.py
  ```

- [ ] **Step 6: Commit the panel**

  ```powershell
  git add frontend/components/uness_rank_admin.py frontend/pages/settings_cockpit.py tests/test_uness_rank_admin_ui.py
  git commit -m "feat: add uness rank validation panel"
  ```

### Task 6: Vérification, documentation et préparation de livraison

**Files:**
- Modify: `docs/AUDIT_QCM_ANNALES_2026-08-15_SUIVI.md`
- Modify: `docs/superpowers/plans/2026-08-16-uness-rank-inference-admin.md`
- Test: existing targeted backend/frontend suites

- [ ] **Step 1: Update the audit follow-up**

  Move automatic inference/orchestration/admin queue from “reste explicitement à brancher” to “livré”, and leave the other four audit items explicitly open.

- [ ] **Step 2: Run formatting and static checks**

  ```powershell
  python -m compileall -q backend
  git diff --check
  ruff check backend/core/uness/rank_inference.py backend/core/uness/rank_job_runner.py backend/api/qcm.py tests/test_uness_rank_inference.py tests/test_uness_rank_jobs_store.py tests/test_uness_rank_job_runner.py tests/test_uness_rank_admin_api.py
  ```

- [ ] **Step 3: Run the focused backend suite**

  ```powershell
  pytest -q tests/test_uness_rank_inference.py tests/test_uness_rank_jobs_store.py tests/test_uness_rank_job_runner.py tests/test_uness_rank_admin_api.py tests/test_uness_rank_admin_ui.py tests/test_uness_import.py tests/test_uness_normalizer.py tests/test_rank_service.py tests/test_qcm_api_completion.py
  ```

- [ ] **Step 4: Run the frontend checks**

  ```powershell
  npm test -- --run
  npm run build
  ```

- [ ] **Step 5: Review the complete diff and commit documentation**

  ```powershell
  git diff main...HEAD --stat
  git status --short
  git add docs/AUDIT_QCM_ANNALES_2026-08-15_SUIVI.md docs/superpowers/plans/2026-08-16-uness-rank-inference-admin.md
  git commit -m "docs: close uness rank inference audit item"
  ```

- [ ] **Step 6: Report remaining full-suite baseline failures honestly**

  If the full `pytest -q` still reports the known referential/data-cache failures, list them separately from regressions introduced by this feature. Do not add the user’s untracked `data_cache.json` or modify `UNESS/vérifiés/.imported.json` to make the worktree green.
