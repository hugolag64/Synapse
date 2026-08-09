# Historique QCM / DP Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le filtre d’état de l’historique rejouable par un toggle QCM/DP et conserver l’action Tuteur DP pour les sessions DP.

**Architecture:** Le cockpit conserve une seule liste de sessions rendue depuis un sous-ensemble filtré par `practice_kind`. Un état local `history_kind` pilote le toggle, tandis que le statut reste une information d’affichage dans chaque ligne. Aucune modification SQLite, de scoring ou de replay n’est nécessaire.

**Tech Stack:** Python 3.11, NiceGUI, pytest, SQLite local existant.

## Global Constraints

- La vue initiale est `QCM`.
- La recherche reste active sur la vue sélectionnée.
- Le statut `À faire / Terminée` n’est plus un filtre de navigation.
- Les actions replay, correction, suppression et Tuteur DP réutilisent les callbacks existants.

---

### Task 1: Contrat de filtrage QCM/DP

**Files:**
- Modify: `frontend/pages/qcm_cockpit.py`
- Test: `tests/test_qcm_cockpit_ui.py`

**Interfaces:**
- Consumes: une liste de sessions avec `practice_kind`.
- Produces: `_filter_replayable_history(sessions, practice_kind)` retournant les sessions du type demandé, avec les types vides traités comme QCM.

- [ ] **Step 1: Write the failing test**

```python
def test_replayable_history_filter_returns_only_selected_kind():
    sessions = [
        {"id": 1, "practice_kind": "QCM"},
        {"id": 2, "practice_kind": "DP"},
        {"id": 3, "practice_kind": ""},
    ]

    assert [row["id"] for row in qcm_cockpit._filter_replayable_history(sessions, "QCM")] == [1, 3]
    assert [row["id"] for row in qcm_cockpit._filter_replayable_history(sessions, "DP")] == [2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_qcm_cockpit_ui.py::test_replayable_history_filter_returns_only_selected_kind -q`

Expected: FAIL because `_filter_replayable_history` does not yet exist.

- [ ] **Step 3: Write minimal implementation**

```python
def _filter_replayable_history(sessions: list[dict], practice_kind: str) -> list[dict]:
    selected = str(practice_kind or "QCM").strip().casefold()
    return [
        session for session in sessions
        if (str(session.get("practice_kind") or "QCM").strip().casefold() == selected)
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_qcm_cockpit_ui.py::test_replayable_history_filter_returns_only_selected_kind -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_qcm_cockpit_ui.py frontend/pages/qcm_cockpit.py
git commit -m "refactor: filter replay history by practice kind"
```

### Task 2: Toggle UI et intégration de la liste

**Files:**
- Modify: `frontend/pages/qcm_cockpit.py`
- Test: `tests/test_qcm_cockpit_ui.py`

**Interfaces:**
- Consumes: `_filter_replayable_history` et les callbacks de session existants.
- Produces: un toggle NiceGUI `QCM / DP`, une liste unique filtrée, et une action Tuteur DP quand le type actif est DP.

- [ ] **Step 1: Write the failing test**

```python
def test_qcm_cockpit_uses_qcm_dp_toggle_instead_of_status_filter():
    source = inspect.getsource(qcm_cockpit.render_qcm_cockpit)

    assert '"QCM": "QCM"' in source
    assert '"DP": "DP"' in source
    assert "history_kind" in source
    assert "HISTORY_STATUS_OPTIONS" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_qcm_cockpit_ui.py::test_qcm_cockpit_uses_qcm_dp_toggle_instead_of_status_filter -q`

Expected: FAIL because the cockpit still creates and reads the status toggle.

- [ ] **Step 3: Write minimal implementation**

Replace the status state with:

```python
history_kind = ui.toggle({"QCM": "QCM", "DP": "DP"}, value="QCM").props(
    "spread no-caps unelevated dense"
).classes("w-full mt-2")
```

Read the selected kind in `_replayable_history`, filter the loaded sessions,
and render one list. Keep the DP button and selected-session Tuteur DP action.

- [ ] **Step 4: Run focused and full tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_qcm_cockpit_ui.py tests/test_qcm_cockpit_replay.py tests/test_qcm_cockpit_persistence.py -q`

Expected: all focused tests pass. Then run `.venv\Scripts\python.exe -m pytest -q` and verify no regression.

- [ ] **Step 5: Commit**

```bash
git add tests/test_qcm_cockpit_ui.py frontend/pages/qcm_cockpit.py
git commit -m "feat: switch replay history between QCM and DP"
```

### Task 3: Documentation and deployment record

**Files:**
- Modify: `docs/superpowers/specs/2026-08-09-qcm-dp-history-design.md`
- Modify: `DEPLOYMENT_SESSION_2026-08-09.md`

- [ ] **Step 1: Record the final toggle behavior and test counts.**
- [ ] **Step 2: Commit and push the documentation.**
- [ ] **Step 3: Deploy with the documented homeserver command and perform Chromium QA on `/qcm`.**
