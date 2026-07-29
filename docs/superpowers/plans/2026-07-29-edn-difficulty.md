# Réglage de difficulté EDN Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un niveau de difficulté Standard/EDN/Difficile/Concours aux sessions IA et adapter le prompt, le routage modèle et l’historique.

**Architecture:** Le niveau sera une valeur métier typée dans `PracticeSessionSpec`, transmise au prompt et persistée dans `ai_practice_sessions`. Le routage acceptera le niveau en plus de la tâche, afin de conserver Flash-Lite pour les niveaux courants et de basculer vers Flash pour les niveaux avancés. L’interface existante ajoutera un contrôle visuel compact sans modifier le flux de génération directe.

**Tech Stack:** Python 3.13, dataclasses/StrEnum, SQLite, NiceGUI, pytest, Playwright via navigateur Codex.

## Global Constraints

- `EDN` est le niveau par défaut.
- Les sessions existantes sans niveau sont interprétées comme `Standard`.
- Les sessions rejouées conservent le niveau et les questions originales.
- Les questions ouvertes restent à 0 par défaut.
- Le calcul de score et de maîtrise reste local.

---

### Task 1: Ajouter le type métier et le routage par difficulté

**Files:**
- Modify: `backend/core/practice/models.py`
- Modify: `backend/core/ai/routing.py`
- Test: `tests/test_ai_routing.py`
- Test: `tests/test_ai_practice.py`

**Interfaces:**
- Produces `PracticeDifficulty` with values `STANDARD`, `EDN`, `DIFFICULT`, `CONCOURS`.
- Extends `PracticeSessionSpec` with `difficulty: PracticeDifficulty = PracticeDifficulty.EDN`.
- Extends `model_for_task(task, difficulty=...)` so `DIFFICULT` and `CONCOURS` use `AIModel.FLASH` while `STANDARD` and `EDN` preserve existing task routing.

- [ ] **Step 1: Write failing tests** for the EDN default, enum validation, and advanced routing.
- [ ] **Step 2: Run targeted tests** with `pytest tests/test_ai_routing.py tests/test_ai_practice.py -q` and verify failure.
- [ ] **Step 3: Implement the enum, spec field, validation, and optional routing argument.** Keep `model_for_task(task)` backward compatible.
- [ ] **Step 4: Run the targeted tests** and verify they pass.
- [ ] **Step 5: Commit** with `feat: add EDN practice difficulty model`.

### Task 2: Persist difficulty and include it in generation/replay

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Modify: `backend/core/practice/service.py`
- Test: `tests/test_ai_practice.py`

**Interfaces:**
- `ai_practice_sessions.difficulty` is a non-null text column with `standard` fallback for existing databases.
- `create_ai_practice_session` receives the spec difficulty and stores it.
- `replay_ai_practice_session` copies difficulty exactly.
- `PracticeService` routes with `model_for_task(task, spec.difficulty)` and includes difficulty instructions in `_prompt_for`.

- [ ] **Step 1: Write failing persistence and prompt tests** asserting difficulty storage, replay, and distinct EDN/Concours instructions.
- [ ] **Step 2: Run `pytest tests/test_ai_practice.py -q`** and verify failure.
- [ ] **Step 3: Add the SQLite migration** to add `difficulty` to existing databases and update insert/replay statements.
- [ ] **Step 4: Update prompt construction** with exact constraints for each level while retaining the exact open/closed distribution contract.
- [ ] **Step 5: Run targeted tests** and verify pass.
- [ ] **Step 6: Commit** with `feat: persist practice difficulty and tune generation`.

### Task 3: Add the visual difficulty control to the generation dialog

**Files:**
- Modify: `frontend/components/ai_practice_panel.py`
- Modify: `tests/test_qcm_cockpit_ui.py`
- Modify: `tests/test_ai_practice.py`

**Interfaces:**
- The existing generation dialog exposes a four-option visual toggle bound to `PracticeDifficulty`.
- The default selected value is `EDN`.
- The generated `PracticeSessionSpec` receives the selected difficulty.

- [ ] **Step 1: Write failing UI source tests** for the four labels, EDN default, and spec propagation.
- [ ] **Step 2: Run targeted UI tests** and verify failure.
- [ ] **Step 3: Add the compact toggle** below the practice type and map the selected string to `PracticeDifficulty`.
- [ ] **Step 4: Keep total/open sliders unchanged**, including 0 open questions by default.
- [ ] **Step 5: Run UI tests** and verify pass.
- [ ] **Step 6: Commit** with `feat: add difficulty selector to AI practice UI`.

### Task 4: Expose difficulty in history and verify the full flow

**Files:**
- Modify: `frontend/components/ai_practice_panel.py`
- Modify: `tests/test_ai_practice.py`
- Modify: `tests/test_qcm_cockpit_ui.py`

**Interfaces:**
- History rows show the stored difficulty, with `Standard` fallback for legacy rows.
- Direct generation still opens the answer dialog immediately.

- [ ] **Step 1: Write failing history test** for the difficulty label and legacy fallback.
- [ ] **Step 2: Implement the history label** without changing replay behavior.
- [ ] **Step 3: Run the full suite** with `pytest -q`.
- [ ] **Step 4: Use Playwright** to open the QCM generation dialog, verify `EDN` is selected and open questions show `0`, switch to `Difficile`, generate a minimal session, and verify the answer dialog opens directly.
- [ ] **Step 5: Run `git diff --check` and commit** with `test: verify EDN difficulty generation flow`.
