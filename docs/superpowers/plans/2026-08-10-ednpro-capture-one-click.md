# EDNpro One-Click Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make « Capturer une session EDNpro » launch a visible Chromium profile and start capture automatically, then make « Arrêter et importer » stop and import corrected questions without manual PowerShell/CDP commands.

**Architecture:** Keep persistence and import on the Ubuntu Synapse server. Run a small Windows-local agent at user logon; the agent launches a persistent Playwright Chromium context only when `/start` is requested, opens `https://ednpro.app/training-v2`, observes corrected cards, and posts the session to Synapse on `/stop`. The NiceGUI panel calls only the localhost control API and displays actionable local-agent states.

**Tech Stack:** Python 3, NiceGUI, Playwright async API, Chromium persistent contexts, local HTTP server, JSON configuration, Windows Task Scheduler, pytest, SQLite.

## Global Constraints

- Chromium remains visible and user-controlled; the agent never answers QCMs or simulates human behaviour.
- Only questions whose correction is displayed are imported.
- Existing questions are never overwritten; new attempts are retained idempotently.
- The local control API listens only on `127.0.0.1:8876`.
- The server continues to authenticate imports with `EDNPRO_CAPTURE_TOKEN`.
- The capture agent must not print or place the token in URLs or browser DOM.
- The existing `/start`, `/stop`, and `/status` routes remain compatible.

---

### Task 1: Lock down the automatic-agent contract

**Files:**
- Modify: `tests/test_ednpro_qcm_capture_ui.py`
- Modify: `tests/test_ednpro_qcm_capture.py`

**Interfaces:**
- Consumes: existing `open_ednpro_capture_dialog()` and `CaptureBuffer`.
- Produces: regression expectations for automatic `/start`, persistent-agent configuration, browser readiness, and actionable status values.

- [ ] **Step 1: Write failing tests.** Assert that the panel calls `fetch('http://127.0.0.1:8876/start')` when the dialog opens, keeps « Arrêter et importer », includes `https://ednpro.app/training-v2`, and no longer contains « Démarrer la capture ». Add a buffer test asserting `ready → starting → capturing` through `start()` and `mark_browser_ready()`, plus a JSON config-loading test.
- [ ] **Step 2: Run the focused tests to verify failure.**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/test_ednpro_qcm_capture_ui.py tests/test_ednpro_qcm_capture.py -q
  ```
  Expected: FAIL because the current panel requires a manual start button and the agent has no browser/configuration state contract.
- [ ] **Step 3: Commit only the red tests.**
  ```powershell
  git add tests/test_ednpro_qcm_capture_ui.py tests/test_ednpro_qcm_capture.py
  git commit -m "test: specify automatic EDNpro capture lifecycle"
  ```

### Task 2: Make the local agent self-launch Chromium on `/start`

**Files:**
- Modify: `scripts/ednpro/qcm_capture_agent.py`
- Modify: `scripts/ednpro/collector.py` only if the persistent-context helper needs a shared signature adjustment.
- Test: `tests/test_ednpro_qcm_capture.py`

**Interfaces:**
- Consumes: `CaptureBuffer`, `extract_corrected_observation`, and `_post_session()`.
- Produces: `mark_browser_ready()`, `mark_error(message)`, a `status()` payload with `state`, and an async agent loop that creates a persistent context on demand.

- [ ] **Step 1: Add explicit lifecycle states.** Use `ready`, `starting`, `capturing`, `stopping`, `imported`, and `error`. Keep existing status keys for compatibility. `start()` resets observations and sets `starting`; browser readiness sets `capturing`; stopping and import update the state.
- [ ] **Step 2: Refactor browser ownership.** Preserve `--cdp-url` attach mode. Without CDP, do not launch Chromium at agent startup. On the first `/start`, call `playwright.chromium.launch_persistent_context(str(profile_dir), headless=False)`, create/reuse a page, and navigate to `https://ednpro.app/training-v2`. Reuse the context for later captures and convert launch/navigation errors into a visible `error` state.
- [ ] **Step 3: Preserve correction semantics.** Poll only EDNpro pages while active. On stop, take one final DOM snapshot before consuming the session so the last displayed correction is not lost. Post once, retain `last_result`, and expose `imported_questions`.
- [ ] **Step 4: Run and commit.**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/test_ednpro_qcm_capture.py -q
  git add scripts/ednpro/qcm_capture_agent.py scripts/ednpro/collector.py tests/test_ednpro_qcm_capture.py
  git commit -m "feat: launch EDNpro browser on capture start"
  ```

### Task 3: Add persistent local configuration and Windows auto-start

**Files:**
- Modify: `scripts/ednpro/qcm_capture_agent.py`
- Create: `scripts/ednpro/install_capture_agent.ps1`
- Modify: `docs/EDNPRO_QCM_CAPTURE.md`
- Test: `tests/test_ednpro_qcm_capture.py`

**Interfaces:**
- Consumes: CLI overrides `--synapse-url`, `--token`, `--profile-dir`, and `--listen-port`.
- Produces: `--config` JSON loading with CLI precedence and a one-time Windows Task Scheduler installer.

- [ ] **Step 1: Test configuration.** Use a temporary JSON containing server URL, test token, profile path, and port. Assert file values are loaded, explicit CLI values win, and the token is absent from `status()`.
- [ ] **Step 2: Implement config loading.** Add `--config`, defaulting on Windows to `%APPDATA%/Synapse/ednpro-capture-agent.json`. Require server URL and token before serving imports. Never log or return the token.
- [ ] **Step 3: Implement the installer.** `install_capture_agent.ps1` prompts for the token without echoing it, writes the JSON under `%APPDATA%\Synapse`, applies a user-only ACL, registers an idempotent `Synapse EDNpro Capture Agent` logon task, starts it once, and prints only health/status.
- [ ] **Step 4: Update documentation.** Document the one-time installer, the one-time EDNpro login in the dedicated profile, and the normal two-click flow. Keep CDP as a diagnostic fallback only.
- [ ] **Step 5: Run and commit.**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/test_ednpro_qcm_capture.py -q
  git add scripts/ednpro/qcm_capture_agent.py scripts/ednpro/install_capture_agent.ps1 docs/EDNPRO_QCM_CAPTURE.md tests/test_ednpro_qcm_capture.py
  git commit -m "feat: install EDNpro capture agent at Windows logon"
  ```

### Task 4: Make the Synapse panel one-click and observable

**Files:**
- Modify: `frontend/components/ednpro_capture_panel.py`
- Modify: `tests/test_ednpro_qcm_capture_ui.py`

**Interfaces:**
- Consumes: local `GET /start`, `/stop), and `/status).
- Produces: automatic start on dialog open, stop/import action, polling status, relay-unavailable messaging, and a final import summary.

- [ ] **Step 1: Start automatically.** After opening the dialog, call `fetch('http://127.0.0.1:8876/start')`. Remove « Démarrer la capture » and keep « Arrêter et importer » as the only capture action.
- [ ] **Step 2: Poll and map states.** Poll `/status) every second. Map `ready) to « Relais prêt », `starting) to « Ouverture de Chromium… », `capturing) to « Capture active », `stopping) to « Import en cours… », `imported) to the import summary, and `error) to its message. Failed fetches show « Relais local indisponible — lance l’installation Windows une fois. ».
- [ ] **Step 3: Stop and wait.** Call `/stop), disable the stop button, poll until `imported) or `error), notify with `imported_questions) and `new_attempts), and refresh QCM only after the import result.
- [ ] **Step 4: Run and commit.**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/test_ednpro_qcm_capture_ui.py -q
  git add frontend/components/ednpro_capture_panel.py tests/test_ednpro_qcm_capture_ui.py
  git commit -m "feat: make EDNpro capture one click"
  ```

### Task 5: Verify the complete flow and deploy

**Files:**
- Modify: `docs/EDNPRO_QCM_CAPTURE.md) only if verification changes the procedure.
- Test: `tests/test_ednpro_qcm_capture.py`, `tests/test_ednpro_qcm_capture_ui.py`.

- [ ] **Step 1: Run targeted tests.**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/test_ednpro_qcm_capture.py tests/test_ednpro_qcm_capture_ui.py -q
  ```
- [ ] **Step 2: Run the full suite.**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q
  ```
- [ ] **Step 3: Run static checks.**
  ```powershell
  .\.venv\Scripts\python.exe -m compileall -q backend frontend scripts tests
  git diff --check
  ```
- [ ] **Step 4: Human acceptance test.** Run the installer once; open Synapse QCM and click « Capturer une session EDNpro »; confirm Chromium opens and the status becomes « Capture active »; complete one small session; click « Arrêter et importer »; confirm the import summary and server SQLite counts; repeat a known question and confirm content preservation plus a new attempt.
- [ ] **Step 5: Push/deploy.**
  ```powershell
  git push origin main
  ```
  On Ubuntu:
  ```bash
  cd /srv/docker/stacks/synapse
  git pull --ff-only origin main
  docker compose build --pull synapse
  docker compose up -d --force-recreate synapse
  git rev-parse --short HEAD
  ```
