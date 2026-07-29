# Refonte Linear du retour de séance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le grand modal NiceGUI de retour de séance par un panneau compact et contextuel, cohérent avec le handoff Linear, sans modifier les traitements de maîtrise.

**Architecture:** Conserver `open_session_feedback_dialog` comme point d'entrée partagé et son callback de validation. Refaire la composition NiceGUI dans `frontend/pages/dashboard/_dialogs.py` avec une hiérarchie de panneau, des contrôles textuels compacts et des champs conditionnels. Ajouter des tests de contrat sur les décisions de rendu qui peuvent être vérifiées sans lancer une session navigateur.

**Tech Stack:** Python, NiceGUI/Quasar, pytest, composants et services Synapse existants.

## Global Constraints

- Le panneau reçoit et affiche explicitement l'item issu de `ReviewTask`.
- Les champs QCM/DP/KFP ne sont visibles que lorsque l'activité correspondante est sélectionnée.
- La section « Détails avancés » est repliée par défaut.
- Les calculs de maîtrise, la planification et les callbacks existants restent inchangés.
- Les couleurs et espacements suivent les tokens du dossier `design_handoff_synapse_refonte`.
- Aucun emoji ne doit être nécessaire pour comprendre la confiance.

---

### Task 1: Isoler les décisions de présentation testables

**Files:**
- Create: `frontend/components/session_feedback_ui.py`
- Test: `tests/test_session_feedback_ui.py`

**Interfaces:**
- Produces `default_feedback_state(task, initial_duration_minutes, manual_date) -> dict`.
- Produces `activity_label(activity_id) -> str`.
- Produces `confidence_label(value) -> str`.
- Produces `qcm_activity_ids() -> frozenset[str]`.

- [x] **Step 1: Write the failing tests**

```python
def test_default_state_prefills_qcm_error_context():
    state = default_feedback_state(_task(review_type="qcm_error"), None, None)
    assert state["activity_types"] == ["qcm", "correction"]
    assert state["qcm_result"] == "raté"


def test_confidence_labels_are_understandable_without_emoji():
    assert confidence_label(1) == "Très incertain"
    assert confidence_label(5) == "Très solide"


def test_qcm_fields_are_limited_to_qcm_activities():
    assert qcm_activity_ids() == frozenset({"qcm", "dp_kfp"})
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_session_feedback_ui.py -q`

Expected: FAIL because `frontend.components.session_feedback_ui` does not exist.

- [x] **Step 3: Write minimal implementation**

Extract only the deterministic defaults and labels from `_dialogs.py`; do not move NiceGUI code or alter the callback contract.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_session_feedback_ui.py -q`

Expected: PASS.

### Task 2: Recomposer le panneau de retour de séance

**Files:**
- Modify: `frontend/pages/dashboard/_dialogs.py:205-500`
- Test: `tests/test_knowledge_session_dialog_gating.py`

**Interfaces:**
- Keeps `open_session_feedback_dialog(task, card, validate_fn, initial_duration_minutes=None, manual_date=None)` unchanged.
- Calls `validate_fn` with the existing keyword arguments.
- Keeps the `knowledge_store.set_item_state(..., source="reprise")` behavior unchanged.

- [x] **Step 1: Add a source-level regression test for the new structure**

```python
def test_session_feedback_uses_linear_panel_structure():
    source = Path("frontend/pages/dashboard/_dialogs.py").read_text(encoding="utf-8")
    assert "Comment s'est passée cette séance ?" in source
    assert "Détails avancés" in source
    assert "Valider la séance" in source
    assert "Très incertain" in source
    assert "emoji" not in source.lower()
```

- [x] **Step 2: Run the regression test to verify it fails**

Run: `python -m pytest tests/test_knowledge_session_dialog_gating.py -q`

Expected: FAIL on the missing new copy/structure assertions while the existing knowledge tests continue to pass.

- [x] **Step 3: Replace the old dialog composition**

Implement a compact `ui.dialog`/panel with:

- header containing `RETOUR DE SÉANCE`, `task.item_number`, `task.label`, and compact item links when available;
- summary row for activity, duration, result and confidence;
- compact activity selection with one active state, defaulted from the task context;
- duration presets and custom duration;
- text confidence scale 1–5 and difficulty selection;
- conditional QCM/DP result block;
- collapsed `Détails avancés` expansion containing error category and note;
- optional item situating block, preserving the existing gate;
- consequence sentence and `Annuler` / `Valider la séance` footer.

Use the existing `state_fb` fields and submit logic. Keep the visual layer in the existing NiceGUI file for this first pass to avoid an unnecessary architectural migration.

- [x] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_session_feedback_ui.py tests/test_knowledge_session_dialog_gating.py tests/test_session_feedback.py -q`

Expected: PASS with no regressions in feedback forwarding or knowledge gating.

### Task 3: Verify integration and visual constraints

**Files:**
- Modify: `tests/test_session_feedback.py` only if a missing preserved contract is discovered.

- [x] **Step 1: Run the full Python test suite**

Run: `python -m pytest -q`

Expected: exit code 0.

- [x] **Step 2: Run a syntax/import check**

Run: `python -m compileall frontend/components/session_feedback_ui.py frontend/pages/dashboard/_dialogs.py`

Expected: exit code 0 with no syntax errors.

- [x] **Step 3: Inspect the final diff**

Run: `git diff --check; git diff --stat; git status --short`

Expected: no whitespace errors; only the feedback UI, its focused tests, and the plan/spec files are changed.

- [ ] **Step 4: Manually verify the three key flows**

Open the cockpit and verify:

1. standard revision: only essential fields are visible and details are collapsed;
2. QCM/DP: result controls appear and the item/session links remain available;
3. failed validation: the panel closes only after the existing callback succeeds and the item mastery path remains intact.
