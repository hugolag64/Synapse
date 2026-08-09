# Sprint EDN et reprise d’étude — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fiabiliser les préférences de planification du Sprint EDN et préparer la date de reprise du 20 août sans modifier encore la génération des tâches historiques.

**Architecture:** Les préférences restent stockées dans le cache JSON de `DataStore`, mais leur normalisation et leur écriture groupée sont centralisées. Paramètres devient le point de modification explicite ; le dashboard ne rend la carte Sprint que si la préférence de visibilité est active. La date de reprise est persistée dès maintenant, puis sera consommée par le moteur métier dans le chantier suivant.

**Tech Stack:** Python 3, NiceGUI/Quasar, JSON cache local, pytest, Git.

## Execution status — 9 août 2026

- [x] Task 1 — préférences persistantes Sprint/reprise et normalisation des dates.
- [x] Task 2 — sauvegarde explicite de la planification et masquage/réaffichage dans Paramètres.
- [x] Task 3 — visibilité de la carte Sprint dans Aujourd’hui, sans désactiver ses calculs.
- [x] Task 4 — tests ciblés **13/13**, suite complète **1221/1221**, compilation Python réussie.
- [ ] Vérification manuelle dans l’application Synapse : l’onglet local disponible affichait le
  compagnon Codex, donc cette vérification reste à faire lorsque le serveur Synapse sera ouvert.

Prochaine tranche active : neutraliser de façon non destructive la dette antérieure au 20 août,
en conservant tout l’historique.

## Global Constraints

- Ne pas supprimer ni réécrire l’historique SQLite ou Notion.
- Ne pas modifier visuellement Aujourd’hui, Planning ou la vue thème au-delà de la visibilité du Sprint.
- La date de reprise doit être exactement `2026-08-20` par défaut.
- Après Ctrl+R, `edn_target_date`, `study_resume_date` et `edn_sprint_visible` doivent être restaurés.
- Les préférences invalides doivent conserver leur valeur précédente ou revenir à leur valeur par défaut sûre.
- Chaque tâche se termine par un test ciblé et une mise à jour de `docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md`.

---

### Task 1: Ajouter le modèle de préférences Sprint/reprise

**Files:**
- Modify: `backend/state/store.py:64-94` — valeurs par défaut et normalisation au chargement.
- Modify: `backend/state/store.py:262-269` — écriture groupée des préférences.
- Test: `tests/test_app_timezone.py` — préférences par défaut, validation et round-trip.
- Create: `tests/test_sprint_preferences.py` — cas spécifiques Sprint/reprise.

**Interfaces:**
- Produces `DataStore.set_preferences(values: dict[str, object]) -> None`.
- `DataStore.set_preference(key, value)` reste compatible et délègue à l’écriture normalisée.
- Les clés persistées sont `edn_target_date: str`, `study_resume_date: str` et `edn_sprint_visible: bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_sprint_and_reentry_preferences_have_safe_defaults():
    store = DataStore()
    assert store.preferences["edn_target_date"] == "2026-10-15"
    assert store.preferences["study_resume_date"] == "2026-08-20"
    assert store.preferences["edn_sprint_visible"] is True


def test_set_preferences_validates_dates_and_writes_values(tmp_path, monkeypatch):
    store = DataStore()
    store.CACHE_FILE = str(tmp_path / "cache.json")
    store.set_preferences({
        "edn_target_date": "2026-11-01",
        "study_resume_date": "2026-08-20",
        "edn_sprint_visible": False,
    })
    reloaded = DataStore()
    reloaded.CACHE_FILE = store.CACHE_FILE
    assert reloaded.load_from_disk(force=True) is True
    assert reloaded.preferences["edn_target_date"] == "2026-11-01"
    assert reloaded.preferences["study_resume_date"] == "2026-08-20"
    assert reloaded.preferences["edn_sprint_visible"] is False


def test_invalid_reentry_date_is_rejected():
    store = DataStore()
    with pytest.raises(ValueError):
        store.set_preferences({"study_resume_date": "not-a-date"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sprint_preferences.py tests/test_app_timezone.py -q`

Expected: FAIL because the new preference keys and `set_preferences` do not exist.

- [ ] **Step 3: Implement the minimal preference model**

Add the two defaults to `_get_default_preferences`, normalize both ISO date keys in `_load_preferences`, normalize `edn_sprint_visible` as a boolean, and implement:

```python
def set_preferences(self, values: dict[str, object]) -> None:
    updated = dict(self.preferences)
    for key, value in values.items():
        updated[key] = self._normalize_preference(key, value)
    self.preferences = updated
    self.save_to_disk()
```

`set_preference` must call `set_preferences({key: value})` so existing callers keep the same persistence behavior.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sprint_preferences.py tests/test_app_timezone.py -q`

Expected: PASS.

- [ ] **Step 5: Update the roadmap status**

In `docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md`, add a short status line under Chantier 1 stating that the preference model now persists the EDN target date, the study reentry date and Sprint visibility. Keep the task-filtering behavior marked as pending.

- [ ] **Step 6: Commit**

```bash
git add backend/state/store.py tests/test_app_timezone.py tests/test_sprint_preferences.py docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md
git commit -m "feat: persist sprint and study reentry preferences"
```

### Task 2: Add explicit save and hide/show controls in Settings

**Files:**
- Modify: `frontend/pages/settings_cockpit.py:177-197` — planification EDN controls.
- Test: `tests/test_settings_sprint_preferences.py` — source-level contract for labels, handler and keys.

**Interfaces:**
- The settings screen reads `data_store.preferences` into draft inputs.
- The save handler calls `data_store.set_preferences(...)` once with the three planning values.
- The visibility control writes `edn_sprint_visible` and exposes a way to restore the card.

- [ ] **Step 1: Write the failing tests**

```python
def test_settings_exposes_explicit_planning_save_and_reentry_date():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert "Date de reprise" in source
    assert "Enregistrer la planification" in source
    assert "study_resume_date" in source
    assert "set_preferences" in source


def test_settings_exposes_sprint_visibility_control():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")
    assert "edn_sprint_visible" in source
    assert "Masquer le Sprint" in source
    assert "Réafficher le Sprint" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_settings_sprint_preferences.py -q`

Expected: FAIL because the new labels and preference keys are absent from the settings page.

- [ ] **Step 3: Implement the explicit settings flow**

Render the existing EDN target date beside a new date input initialized from `study_resume_date`. Add a primary save button whose handler validates both dates, reads the current visibility state, calls `data_store.set_preferences` once, and displays `Planification enregistrée`. Add a compact hide/show control for the Sprint card that persists `edn_sprint_visible` immediately and displays the opposite action after the change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_settings_sprint_preferences.py -q`

Expected: PASS.

- [ ] **Step 5: Update the roadmap status**

Update Chantier 1 with the completed Settings behavior and state that review-task neutralization remains pending.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/settings_cockpit.py tests/test_settings_sprint_preferences.py docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md
git commit -m "feat: add explicit sprint planning controls"
```

### Task 3: Gate the Sprint card without disabling its calculations

**Files:**
- Modify: `frontend/pages/dashboard/_cockpit_today.py:239-303,482-490` — pass the visibility preference to rendering.
- Modify: `frontend/components/edn_insights_panel.py:105-153` — optional hide control contract.
- Test: `tests/test_edn_insights_ui.py` — visibility gate and unchanged model calculation.

**Interfaces:**
- `SprintCountdownService.get_sprint_status(...)` remains unchanged.
- The dashboard still computes `edn_status` when the card is hidden.
- The renderer is called only when `edn_sprint_visible` is true, or it receives an explicit visibility flag.

- [ ] **Step 1: Write the failing tests**

```python
def test_dashboard_reads_sprint_visibility_preference():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert "edn_sprint_visible" in source


def test_sprint_status_model_is_still_computed_when_visibility_is_configurable():
    source = Path("frontend/pages/dashboard/_cockpit_today.py").read_text(encoding="utf-8")
    assert "SprintCountdownService" in source
    assert "get_sprint_status" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_edn_insights_ui.py -q`

Expected: FAIL because the dashboard does not read the visibility preference.

- [ ] **Step 3: Implement the visibility gate**

Keep the existing status/projection calculation intact. Wrap only the `render_edn_insights_panel(...)` call in the visibility condition and provide the hide action that persists the preference and refreshes the dashboard.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_edn_insights_ui.py -q`

Expected: PASS.

- [ ] **Step 5: Update the roadmap status**

Mark Sprint persistence and hide/show as complete in Chantier 1. Keep the global reentry filter and future planning aggregation as the next pending slice.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/dashboard/_cockpit_today.py frontend/components/edn_insights_panel.py tests/test_edn_insights_ui.py docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md
git commit -m "feat: allow hiding the sprint card"
```

### Task 4: Full verification checkpoint

**Files:**
- Verify: all files from Tasks 1–3.
- Update: `docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md`.

- [ ] **Step 1: Run the focused suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sprint_preferences.py tests/test_settings_sprint_preferences.py tests/test_edn_insights_ui.py tests/test_phase5_edn.py -q`

Expected: PASS.

- [ ] **Step 2: Run the complete suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`

Expected: all pre-existing tests plus the new tests pass.

- [ ] **Step 3: Perform the manual browser check**

Verify in Settings: edit the EDN target date, edit the reentry date, save once, reload the page, confirm both values remain, hide the Sprint card, reload the dashboard, confirm it is absent, return to Settings, restore it, and confirm it reappears. Confirm the underlying `SprintCountdownService` still exposes the same target date and phase.

- [ ] **Step 4: Update the roadmap status**

Record the focused suite, full suite and manual browser verification in `docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md`, then write the next slice as the active item: non-destructive neutralization of pre-20 August review debt.

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP_UX_ALGORITHMES_2026-08-09.md
git commit -m "docs: record sprint preferences verification"
```
