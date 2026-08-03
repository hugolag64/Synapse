# Fonctionnalités EDN connectées Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relier les données externes, les erreurs, les lacunes, le Flash-Zero, le Tuteur DP et le pilotage Sprint EDN dans le cockpit NiceGUI.

**Architecture:** SQLite reste la source locale de vérité. Les modules métier `backend/core/edn/` parseront les imports,
agrégeront les erreurs et calculeront recommandations/projections ; les écrans NiceGUI consommeront ces services sans
porter de logique métier. Les fonctionnalités Streamlit existantes seront conservées comme références mais ne seront
plus le chemin principal.

**Tech Stack:** Python 3.13, SQLite via `backend.core.reviews.local_store`, pytest, NiceGUI, `PracticeService` et
`FlashZeroService` existants.

## Global Constraints

- SQLite est la source locale de vérité pour résultats, erreurs, lacunes et recommandations.
- La première version F2 accepte CSV/JSON ; les connecteurs automatisés EDNpro/Hypocampus sont hors périmètre.
- Un import répété du même `(source, external_id)` est idempotent.
- F6 suggère une lacune après au moins deux signaux comparables sur le même item ou thème dans les 30 derniers jours.
- Flash-Zero est une tâche Synapse interne unique par jour et par fuseau métier ; aucun événement Google Calendar automatique.
- Les recommandations sont explicables et ne modifient pas silencieusement la maîtrise.
- Une panne IA ou externe ne bloque ni planning ni révisions locales.
- Chaque comportement nouveau suit RED → GREEN → REFACTOR avec un test qui échoue avant le code de production.

---

## File Map

### Files to create

- `backend/core/edn/__init__.py` — exports publics des services EDN.
- `backend/core/edn/external_results.py` — dataclasses, parsing et import idempotent.
- `backend/core/edn/error_profile.py` — catégories et agrégation des signaux d’erreur.
- `backend/core/edn/gap_suggestions.py` — seuil F6, preuves et acceptation/ignorance.
- `backend/core/edn/trajectory.py` — progression, F3 et projections F5.
- `frontend/components/edn_insights_panel.py` — cartes Dashboard Sprint/F3/F4/F5.
- `tests/test_external_results.py` — contrat CSV/JSON et idempotence.
- `tests/test_error_profile.py` — catégories et agrégats F4.
- `tests/test_gap_suggestions.py` — seuil F6 et déduplication.
- `tests/test_edn_trajectory.py` — F3/F5 et fourchettes.
- `tests/test_flash_zero_integration.py` — tâche quotidienne et sélection ciblée.
- `tests/test_dp_tutor.py` — contexte Item/Historique et génération DP.

### Files to modify

- `backend/core/reviews/local_store.py` — migrations et CRUD des tables `external_results`, `error_signals`, `edn_recommendations`.
- `backend/core/practice/flash_zero_service.py` — sélection priorisée par erreurs récentes/répétées.
- `backend/features/daily_routine.py` — création idempotente de la tâche Flash-Zero dans le fuseau métier.
- `backend/core/reviews/recommendation_service.py` — durée et type `flash_zero` dans le budget journalier.
- `backend/core/planning/cockpit_schedule.py` — lecture de la tâche Flash-Zero comme entrée de planning.
- `frontend/pages/dashboard/_cockpit_today.py` — carte Flash-Zero et panneau EDN Insights.
- `frontend/pages/course_detail_cockpit.py` — bouton Tuteur DP dans `_tab_history`.
- `frontend/components/ai_practice_panel.py` — ouverture d’une session DP depuis un contexte Item.
- `frontend/pages/weak_points_cockpit.py` — affichage/acception/ignorance des suggestions F6.
- `frontend/pages/settings_cockpit.py` — import CSV/JSON et rapport de validation.
- `docs/AUDIT_2026-08-03.md` — état livré et reste à faire.

---

### Task 1: Add the external-results import contract

**Files:**
- Create: `backend/core/edn/__init__.py`
- Create: `backend/core/edn/external_results.py`
- Modify: `backend/core/reviews/local_store.py: initialisation SQLite and migrations`
- Create: `tests/test_external_results.py`

**Interfaces:**
- `ExternalResult(source: str, external_id: str, session_date: datetime.date, item_number: str, activity_type: str, score_percent: float | None, total_questions: int | None, rank_a_percent: float | None, rank_b_percent: float | None, metadata: dict)`
- `ImportReport(accepted: int, updated: int, skipped: int, errors: tuple[dict, ...])`
- `parse_external_results(payload: str | bytes, fmt: Literal["csv", "json"]) -> list[ExternalResult]`
- `import_external_results(results: Iterable[ExternalResult], *, store=local_store) -> ImportReport`
- `local_store.upsert_external_result(result: ExternalResult) -> Literal["inserted", "updated"]`
- `local_store.get_external_results(*, item_number: str | None = None, source: str | None = None, days: int | None = None) -> list[dict]`

- [ ] **Step 1: Write the failing parser and idempotence tests**

```python
def test_csv_import_normalizes_rows_and_is_idempotent(tmp_path, monkeypatch):
    from backend.core.edn.external_results import import_external_results, parse_external_results
    from backend.core.reviews import local_store

    payload = "source,external_id,session_date,item_number,activity_type,score_percent\nEDNpro,r-1,2026-08-03,221,QCM,62"
    rows = parse_external_results(payload, "csv")
    assert rows[0].item_number == "221"
    assert import_external_results(rows, store=local_store).accepted == 1
    report = import_external_results(rows, store=local_store)
    assert report.updated == 1
    assert len(local_store.get_external_results()) == 1
```

- [ ] **Step 2: Run `pytest tests/test_external_results.py -q` and verify the expected missing-module or missing-table failure.**
- [ ] **Step 3: Add the migration, strict required-field validation, tolerant optional fields and `ON CONFLICT(source, external_id)` upsert.**
- [ ] **Step 4: Run the test and verify CSV, JSON, invalid-row reporting and duplicate import all pass.**
- [ ] **Step 5: Commit `feat: importer les résultats EDN externes`.**

### Task 2: Build F4 error profiles and F6 gap suggestions

**Files:**
- Create: `backend/core/edn/error_profile.py`
- Create: `backend/core/edn/gap_suggestions.py`
- Modify: `backend/core/reviews/local_store.py: error/recommendation CRUD`
- Create: `tests/test_error_profile.py`
- Create: `tests/test_gap_suggestions.py`

**Interfaces:**
- `ERROR_CATEGORIES: tuple[str, ...] = ("oubli", "raisonnement", "piege_edn", "rang_a", "rang_b", "inattention", "temps", "non_classe")`
- `ErrorSignal(item_number: str, category: str, occurred_at: datetime.date, source: str, evidence_id: str, detail: str = "")`
- `build_error_profile(*, item_number: str | None = None, days: int = 30, store=local_store) -> dict[str, dict]`
- `suggest_gap_candidates(*, item_number: str | None = None, days: int = 30, store=local_store) -> list[dict]`
- `accept_gap_suggestion(suggestion_id: int, *, store=local_store) -> int`
- `ignore_gap_suggestion(suggestion_id: int, *, store=local_store) -> None`

- [ ] **Step 1: Write failing tests for category aggregation and the two-signal threshold.**

```python
def test_repeated_same_category_produces_one_explainable_suggestion(store):
    store.insert_error_signal("221", "oubli", "2026-08-01", "qcm", "q-1", "indication")
    store.insert_error_signal("221", "oubli", "2026-08-02", "qcm", "q-2", "indication")
    suggestions = suggest_gap_candidates(item_number="221", store=store)
    assert len(suggestions) == 1
    assert suggestions[0]["category"] == "oubli"
    assert suggestions[0]["evidence_ids"] == ["q-1", "q-2"]
```

- [ ] **Step 2: Run the two test files and verify they fail because the tables/services are absent.**
- [ ] **Step 3: Add normalized signal storage, deterministic grouping, 30-day filtering and active-suggestion deduplication.**
- [ ] **Step 4: Make acceptance call `add_weak_point_full` with the evidence detail and make ignore trace the decision without deleting signals.**
- [ ] **Step 5: Run both files and verify profile counts, `non_classe`, threshold and deduplication.**
- [ ] **Step 6: Commit `feat: profiler les erreurs et proposer les lacunes`.**

### Task 3: Connect Flash-Zero to the morning planning flow

**Files:**
- Modify: `backend/core/practice/flash_zero_service.py`
- Modify: `backend/features/daily_routine.py`
- Modify: `backend/core/reviews/local_store.py: manual planning activity validation and daily lookup`
- Modify: `backend/core/reviews/recommendation_service.py`
- Modify: `backend/core/planning/cockpit_schedule.py`
- Modify: `frontend/pages/dashboard/_cockpit_today.py`
- Create: `tests/test_flash_zero_integration.py`

**Interfaces:**
- `FlashZeroService.get_morning_quiz(count: int = 10, *, item_number: str | None = None) -> list[FlashZeroQuestion]`
- `local_store.ensure_daily_flash_zero(entry_date: datetime.date, *, timezone_name: str) -> dict`
- `local_store.get_daily_flash_zero(entry_date: datetime.date, *, timezone_name: str) -> dict | None`
- `build_flash_zero_priority(signals: Iterable[dict], today: datetime.date) -> list[str]`

- [ ] **Step 1: Write failing tests proving repeated/recent signals are selected first and only one daily task is created.**
- [ ] **Step 2: Run `pytest tests/test_flash_zero_integration.py -q` and verify the current service returns only shuffled canonical questions and the planning store rejects `flash_zero`.**
- [ ] **Step 3: Add deterministic priority ordering before canonical fallback, permit `flash_zero` as an internal activity, and make `ensure_daily_flash_zero` idempotent by business date/timezone.**
- [ ] **Step 4: Add a five-minute morning card in the Dashboard that opens the existing quiz path and marks the internal task complete after finishing.**
- [ ] **Step 5: Run the integration tests and the existing planning/dashboard tests.**
- [ ] **Step 6: Commit `feat: intégrer flash-zero au planning du matin`.**

### Task 4: Add the Tuteur DP to Item History

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py:_tab_history`
- Modify: `frontend/components/ai_practice_panel.py`
- Modify: `backend/core/practice/service.py` only if context needs a typed DP entry point
- Create: `tests/test_dp_tutor.py`

**Interfaces:**
- `build_dp_tutor_context(*, item_number: str, dp_session: dict, errors: list[dict], gaps: list[dict]) -> str`
- `PracticeService.create_tutor_dp_session(*, item_number: str, course_id: str, course_title: str, dossier_context: str, errors: list[dict], gap_details: list[str], total_questions: int = 5) -> int`
- `render_dp_tutor_action(item_number: str, dp_session: dict, refresh: Callable[[], None]) -> None`

- [ ] **Step 1: Write failing tests for context composition and a `PracticeKind.DP` session using the selected dossier.**
- [ ] **Step 2: Run `pytest tests/test_dp_tutor.py -q` and verify the context builder/session entry point is absent.**
- [ ] **Step 3: Implement the context builder with explicit dossier, item, error and gap sections; call `PracticeService` with `context=` and the existing EDN difficulty.**
- [ ] **Step 4: Add the action beside compatible DP entries in `_tab_history`, persist the generated session and refresh the history.**
- [ ] **Step 5: Run Item cockpit and practice tests.**
- [ ] **Step 6: Commit `feat: ajouter le tuteur DP dans l historique Item`.**

### Task 5: Enrich Sprint Countdown with F5 projections

**Files:**
- Create: `backend/core/edn/trajectory.py`
- Modify: `backend/core/planning/sprint_countdown.py`
- Create: `frontend/components/edn_insights_panel.py`
- Modify: `frontend/pages/dashboard/_cockpit_today.py`
- Create: `tests/test_edn_trajectory.py`

**Interfaces:**
- `ProgressSnapshot(covered_items: int, total_items: int, average_mastery: float | None, overdue_reviews: int, remaining_reviews: int, recent_items_per_week: float, recent_minutes_per_day: float)`
- `ProjectionScenario(name: str, projected_coverage: float, projected_mastery: float | None, remaining_items: int, confidence: str)`
- `build_progress_snapshot(*, courses: list, tasks: list, history: dict, as_of: datetime.date) -> ProgressSnapshot`
- `project_to_exam(snapshot: ProgressSnapshot, *, target_date: datetime.date, daily_capacity_minutes: int) -> tuple[ProjectionScenario, ...]`

- [ ] **Step 1: Write failing tests for prudent/central/ambitious scenarios and zero/negative capacity handling.**
- [ ] **Step 2: Run `pytest tests/test_edn_trajectory.py -q` and verify the trajectory module is absent.**
- [ ] **Step 3: Implement a 28-day throughput baseline, bounded coverage percentages and three named scenarios without pretending to predict ranking.**
- [ ] **Step 4: Extend `SprintConfig` with the progress fields needed by the card while preserving existing phase/ratio tests.**
- [ ] **Step 5: Render the card in the Dashboard with `business_today()` and the configured timezone; degrade to the countdown alone when data is unavailable.**
- [ ] **Step 6: Run trajectory, sprint and dashboard tests.**
- [ ] **Step 7: Commit `feat: afficher la trajectoire EDN dans le sprint countdown`.**

### Task 6: Add F3 potential-of-gain ranking and F2 import UI

**Files:**
- Modify: `backend/core/edn/trajectory.py`
- Modify: `frontend/components/edn_insights_panel.py`
- Modify: `frontend/pages/settings_cockpit.py`
- Create: `tests/test_edn_gain_priority.py`

**Interfaces:**
- `rank_gain_potential(*, items: Iterable[dict], available_minutes: int | None = None) -> list[dict]`
- `render_external_result_import(on_import: Callable[[], None]) -> None`

- [ ] **Step 1: Write failing tests showing higher EDN importance, larger mastery gap, repeated errors and lower effort rank above low-impact items.**
- [ ] **Step 2: Run the new test and verify `rank_gain_potential` is absent.**
- [ ] **Step 3: Implement a bounded relative score and explanatory factors; keep it consultative and deterministic.**
- [ ] **Step 4: Add CSV/JSON upload and pasted-text input to Settings, show accepted/updated/skipped/error counts, and do not save invalid rows.**
- [ ] **Step 5: Add the gain-priority list to the EDN Insights panel and link each row to the Item view.**
- [ ] **Step 6: Run import, trajectory and Settings tests.**
- [ ] **Step 7: Commit `feat: afficher le potentiel de gain et importer les résultats`.**

### Task 7: Expose F6 suggestions and complete documentation

**Files:**
- Modify: `frontend/pages/weak_points_cockpit.py`
- Modify: `frontend/pages/course_detail_cockpit.py`
- Modify: `docs/AUDIT_2026-08-03.md`
- Create or modify: focused UI contract tests under `tests/`

- [ ] **Step 1: Write failing source/contract tests for Create/Ignore actions and the Item History Tuteur DP action.**
- [ ] **Step 2: Run the focused UI tests and verify the actions are not present.**
- [ ] **Step 3: Render suggestion evidence, call acceptance/ignore services, and refresh without duplicating active gaps.**
- [ ] **Step 4: Add the Item History link to the selected DP and preserve the current timeline/error typography.**
- [ ] **Step 5: Update the audit with delivered F2–F6/Phase 5 behavior, import format and remaining automated connectors.**
- [ ] **Step 6: Run `pytest -q`, `python -m compileall -q backend frontend`, and `git diff --check`.**
- [ ] **Step 7: Commit `feat: brancher les fonctionnalités EDN isolées`.**

## Verification Gate

Before claiming completion, run the full suite from a clean working tree and record the exact result. The final
report must distinguish implementation failures from the two known external dependency warnings, link the audit and
list any connector or Google Calendar work intentionally left outside this tranche.
