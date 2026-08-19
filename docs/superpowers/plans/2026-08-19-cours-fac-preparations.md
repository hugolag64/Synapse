# Cours FAC — Préparations automatiques Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Importer les cours FAC contenant des numéros d’items, créer à J-2 ou en rattrapage J-1 les tâches de préparation manquantes dans SQLite, puis déclencher le cycle collège J1/J3/J7/J14/J30 après validation manuelle de la première lecture.

**Architecture:** Une table SQLite course_prep_tasks porte les tâches opérationnelles et une table course_learning_schedule porte l’ancrage local et les dates de révision. Un parseur pur extrait les items des titres Google Calendar ; un service d’orchestration résout chaque item dans le catalogue local et crée les tâches de façon idempotente. La routine quotidienne synchronise les événements et le cockpit du jour affiche les tâches avec raccourci et validation manuelle.

**Tech Stack:** Python 3, SQLite, Pydantic, NiceGUI, Google Calendar API existante, pytest.

## Global Constraints

- SQLite est la source de vérité ; Notion ne doit jamais être relu pour décider de l’état d’une préparation ou d’une date locale.
- Le calendrier FAC est kvj2875m68cng7oeiq6mbfh8k20ha1ru@import.calendar.google.com, libellé FAC.
- Le traitement normal examine les événements à J+2 ; le traitement à J+1 sert de rattrapage automatique.
- Seuls les titres contenant Item ou Items suivi de numéros sont traités ; les numéros d’UE, horaires et salles sont ignorés.
- Le flux cible uniquement le contexte college.
- Les types de préparation sont exactement pdf, obsidian, resume et first_read.
- L’ouverture d’un raccourci ne valide jamais automatiquement la tâche ; la validation est manuelle.
- Le cycle de révision collège est J1, J3, J7, J14, J30, ancré à la date du cours lors de la validation de first_read.
- La contrainte d’idempotence est (course_id, lecture_date, task_type).
- Une panne Google Calendar ou une panne de projection Notion ne doit ni supprimer ni corrompre les données SQLite existantes.
- Chaque tâche d’implémentation suit TDD : test rouge, implémentation minimale, test vert, puis commit ciblé.
- Avant le premier changement et après le dernier : ./.venv/Scripts/python.exe -m pytest -q.

## File Map

- backend/core/prep/models.py — modèles locaux PrepTask, LearningSchedule et types d’action.
- backend/core/prep/store.py — lecture/écriture SQLite des tâches de préparation et du calendrier d’apprentissage.
- backend/core/prep/calendar_parser.py — extraction pure des numéros d’items et des dates d’événements.
- backend/core/prep/service.py — résolution des items, calcul des tâches manquantes et synchronisation idempotente.
- backend/core/reviews/local_store.py — migration et connexion SQLite partagée ; intégration du nouveau schéma.
- backend/core/reviews/service.py et backend/core/reviews/models.py — ajout de J1 et lecture de l’ancrage local.
- backend/state/store.py — source locale des cours et préférence par défaut du calendrier FAC.
- backend/features/daily_routine.py — déclenchement quotidien de la synchronisation FAC.
- frontend/components/course_prep_task_row.py — ligne UI d’une tâche de préparation.
- frontend/pages/dashboard/_cockpit_today.py — bloc Préparations FAC dans la boucle du jour.
- frontend/components/course_quick_actions.py — wrappers publics pour les raccourcis PDF/Obsidian et ouverture de fiche.

---

### Task 0: Baseline et vérification de l’état de départ

**Files:**
- Read: docs/superpowers/specs/2026-08-19-cours-fac-preparations-design.md
- Test: suite existante complète

**Interfaces:**
- Consumes: le dépôt actuel et sa configuration .venv.
- Produces: un résultat de baseline consigné dans la session ; aucun fichier applicatif modifié.

- [ ] **Step 1: Run the complete baseline suite**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest -q
~~~

Expected: la suite termine sans erreur ; noter le nombre exact de tests passés avant toute modification.

- [ ] **Step 2: Check the working tree**

Run:

~~~powershell
git status --short
~~~

Expected: les changements existants sont conservés et aucun fichier utilisateur non lié n’est inclus dans les commits des tâches suivantes.

---

### Task 1: Ajouter le stockage SQLite des préparations et du calendrier local

**Files:**
- Create: backend/core/prep/__init__.py
- Create: backend/core/prep/models.py
- Create: backend/core/prep/store.py
- Modify: backend/core/reviews/local_store.py dans init_db() et les migrations idempotentes
- Test: tests/test_course_prep_store.py

**Interfaces:**
- Consumes: _conn() et _now() de backend.core.reviews.local_store ; datetime.date.
- Produces:
  - PrepTaskType = Literal["pdf", "obsidian", "resume", "first_read"].
  - PrepTaskStatus = Literal["todo", "done", "cancelled"].
  - PrepTask avec id: int, course_id: str, item_number: str, lecture_date: date, calendar_event_id: str, calendar_title: str, task_type: PrepTaskType, status: PrepTaskStatus, created_at: str, updated_at: str, completed_at: str | None.
  - LearningSchedule avec course_id, context, first_read_date, j1_date, j3_date, j7_date, j14_date, j30_date.
  - list_prep_tasks(day: date | None = None, statuses: tuple[str, ...] = ("todo",)) -> list[PrepTask].
  - upsert_prep_task(course_id: str, item_number: str, lecture_date: date, calendar_event_id: str, calendar_title: str, task_type: PrepTaskType) -> PrepTask.
  - update_prep_task_status(task_id: int, status: PrepTaskStatus) -> PrepTask.
  - get_learning_schedule(course_id: str, context: str = "college") -> LearningSchedule | None.
  - save_learning_schedule(course_id: str, first_read_date: date, context: str = "college") -> LearningSchedule.
  - move_pending_prep_tasks(calendar_event_id: str, lecture_date: date, calendar_title: str) -> int.
  - cancel_pending_prep_tasks(calendar_event_id: str) -> int.

- [ ] **Step 1: Write failing schema/API tests**

Use the existing temporary SQLite fixture:

~~~python
def test_prep_task_is_idempotent_by_course_date_and_type():
    first = upsert_prep_task("course-1", "363", date(2026, 8, 28), "event-1", "Item 363", "pdf")
    second = upsert_prep_task("course-1", "363", date(2026, 8, 28), "event-1", "Item 363", "pdf")
    assert first.id == second.id
    assert len(list_prep_tasks(date(2026, 8, 28), ("todo",))) == 1


def test_schedule_persists_all_review_dates():
    schedule = save_learning_schedule("course-1", date(2026, 8, 28))
    assert schedule.j1_date == date(2026, 8, 29)
    assert schedule.j3_date == date(2026, 8, 31)
    assert schedule.j7_date == date(2026, 9, 4)
    assert schedule.j14_date == date(2026, 9, 11)
    assert schedule.j30_date == date(2026, 9, 27)
~~~

Also cover status transitions, completed_at, pending-task move, cancellation, and missing schedule.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_store.py -q
~~~

Expected: FAIL because the new package, tables, and APIs do not exist.

- [ ] **Step 3: Add the idempotent SQLite tables**

Add migrations equivalent to:

~~~sql
CREATE TABLE IF NOT EXISTS course_prep_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    item_number TEXT NOT NULL DEFAULT '',
    lecture_date TEXT NOT NULL,
    calendar_event_id TEXT NOT NULL DEFAULT '',
    calendar_title TEXT NOT NULL DEFAULT '',
    task_type TEXT NOT NULL CHECK (task_type IN ('pdf', 'obsidian', 'resume', 'first_read')),
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'done', 'cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(course_id, lecture_date, task_type)
);

CREATE TABLE IF NOT EXISTS course_learning_schedule (
    course_id TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT 'college',
    first_read_date TEXT NOT NULL,
    j1_date TEXT NOT NULL,
    j3_date TEXT NOT NULL,
    j7_date TEXT NOT NULL,
    j14_date TEXT NOT NULL,
    j30_date TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(course_id, context)
);
~~~

Keep the migration idempotent and call it from init_db() after the existing routine migrations.

- [ ] **Step 4: Implement the store functions**

Use INSERT ... ON CONFLICT(course_id, lecture_date, task_type) DO UPDATE for provenance fields while preserving status and completed_at. update_prep_task_status must reject unknown statuses, set completed_at only for done, and clear it only when moving back to todo.

- [ ] **Step 5: Run focused tests to verify pass**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_store.py -q
~~~

Expected: all store tests pass.

- [ ] **Step 6: Commit**

~~~powershell
git add backend/core/prep backend/core/reviews/local_store.py tests/test_course_prep_store.py
git commit -m "feat: add sqlite storage for course preparation tasks"
~~~

---

### Task 2: Implémenter le parseur pur des titres FAC

**Files:**
- Create: backend/core/prep/calendar_parser.py
- Test: tests/test_course_prep_calendar_parser.py

**Interfaces:**
- Consumes: titre d’événement et payload Google Calendar.
- Produces:
  - extract_item_numbers(summary: str) -> list[str].
  - event_start_date(event: dict, timezone: tzinfo) -> date | None.
  - event_is_cancelled(event: dict) -> bool.

- [ ] **Step 1: Write failing parser tests**

~~~python
def test_extracts_one_item():
    assert extract_item_numbers("UE2.S7 Médecine Légale - Item 13") == ["13"]


def test_extracts_and_deduplicates_multiple_items():
    assert extract_item_numbers("UE7.S7 Orthopédie - items 363, 362, 334, 365, 363") == ["363", "362", "334", "365"]


def test_does_not_parse_ue_time_or_room_numbers():
    assert extract_item_numbers("UE7.S7 Orthopédie - De 07:45 à 09:45 C017") == []


def test_ignores_title_without_explicit_item_keyword():
    assert extract_item_numbers("UE14 LCA - Introduction") == []
~~~

Add cases for Item 13 et 14, accented text, empty titles, all-day events, and cancelled events.

- [ ] **Step 2: Run parser tests to verify failure**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_calendar_parser.py -q
~~~

Expected: FAIL because calendar_parser.py is absent.

- [ ] **Step 3: Implement the parser**

Match only the token items? with a word boundary, then consume a bounded sequence of decimal numbers separated by commas, semicolons, or et. Do not scan the rest of the title for numbers. Preserve first-seen order and normalize each number to its integer string form.

For the event date, read event["start"]["dateTime"] or event["start"]["date"]; convert date-times into the application timezone before taking .date().

- [ ] **Step 4: Run parser tests to verify pass**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_calendar_parser.py -q
~~~

Expected: all parser tests pass.

- [ ] **Step 5: Commit**

~~~powershell
git add backend/core/prep/calendar_parser.py tests/test_course_prep_calendar_parser.py
git commit -m "feat: parse item numbers from faculty calendar titles"
~~~

---

### Task 3: Enregistrer automatiquement le calendrier FAC

**Files:**
- Modify: backend/core/planning/calendar_sources.py
- Modify: backend/state/store.py:_get_default_preferences
- Test: tests/test_planning_calendar_sources.py
- Test: tests/test_planning_calendar_actions.py

**Interfaces:**
- Consumes: existing planning_calendar_sources preference and GoogleCalendarService.get_events_for_day.
- Produces:
  - FAC_CALENDAR_ID and FAC_CALENDAR_LABEL constants.
  - default_calendar_sources() -> list[dict] returning the FAC source.
  - Existing user preference values remain authoritative when present; an explicit empty list still means the user removed the source.

- [ ] **Step 1: Add failing source tests**

~~~python
def test_default_calendar_sources_contains_fac_calendar():
    assert default_calendar_sources() == [{
        "id": "kvj2875m68cng7oeiq6mbfh8k20ha1ru@import.calendar.google.com",
        "label": "FAC",
    }]
~~~

Extend the existing fake multi-calendar test to assert that the FAC ID is fetched when the default preference is used and that its events receive _synapse_source_label == "FAC".

- [ ] **Step 2: Run focused tests to verify failure**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_planning_calendar_sources.py tests/test_planning_calendar_actions.py -q
~~~

Expected: FAIL because the default FAC source is not defined.

- [ ] **Step 3: Add the default source without overwriting explicit preferences**

Set the default preference to default_calendar_sources(). Preserve the existing _load_preferences merge behavior so an existing saved planning_calendar_sources list, including an explicit empty list, is not overwritten. Keep the existing .env and settings-panel sources working.

- [ ] **Step 4: Run focused tests to verify pass**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_planning_calendar_sources.py tests/test_planning_calendar_actions.py -q
~~~

Expected: all source and multi-calendar tests pass.

- [ ] **Step 5: Commit**

~~~powershell
git add backend/core/planning/calendar_sources.py backend/state/store.py tests/test_planning_calendar_sources.py tests/test_planning_calendar_actions.py
git commit -m "feat: register faculty calendar as a default source"
~~~

---

### Task 4: Construire le service de synchronisation des préparations

**Files:**
- Create: backend/core/prep/service.py
- Modify: backend/core/knowledge/course_aliases.py only if a public canonical-item helper is required by tests
- Test: tests/test_course_prep_service.py

**Interfaces:**
- Consumes: extract_item_numbers, event_start_date, event_is_cancelled, data_store.cours, and the store functions from Task 1.
- Produces:
  - PrepSyncReport(created: int, moved: int, cancelled: int, unresolved_items: tuple[str, ...]).
  - missing_task_types(course, lecture_date: date) -> tuple[PrepTaskType, ...].
  - sync_preparation_events(events: list[dict], courses: list, today: date) -> PrepSyncReport.
  - async sync_fac_preparations(today: date | None = None) -> PrepSyncReport, which fetches today+1 and today+2 from calendar_service and passes the combined events to the pure synchronizer.
  - complete_first_read_prep(task: PrepTask, course) -> LearningSchedule, which persists the lecture-date anchor and marks the preparation task done.

- [ ] **Step 1: Write failing orchestration tests**

Use small Pydantic Cours fixtures and monkeypatch the store functions:

~~~python
def test_missing_task_types_only_contains_unfinished_actions(course_without_resources):
    assert missing_task_types(course_without_resources, date(2026, 8, 28)) == (
        "pdf", "obsidian", "resume", "first_read"
    )


def test_existing_course_state_suppresses_corresponding_tasks(course_with_pdf_obsidian_resume_and_read):
    assert missing_task_types(course_with_pdf_obsidian_resume_and_read, date(2026, 8, 28)) == ()


def test_sync_is_idempotent_between_j_minus_2_and_j_minus_1(sample_event, course_without_resources, monkeypatch):
    first = sync_preparation_events([sample_event], [course_without_resources], date(2026, 8, 26))
    second = sync_preparation_events([sample_event], [course_without_resources], date(2026, 8, 27))
    assert first.created == 4
    assert second.created == 0
~~~

Also test multiple items, duplicate item numbers, unresolved items, cancelled events, moved pending events, and an already populated date_1ere_lecture.

- [ ] **Step 2: Run service tests to verify failure**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_service.py -q
~~~

Expected: FAIL because the orchestration service is absent.

- [ ] **Step 3: Implement item resolution and missing-action calculation**

Resolve an item against the canonical college course already present in the local course list. Use normalized_item and canonical_course_for_item from backend.core.knowledge.course_aliases so duplicate fiche records for an item produce one course target. Use the local course fields url_pdf, obsidian_uri, resume_done, and date_1ere_lecture to derive missing actions.

- [ ] **Step 4: Implement idempotent event synchronization**

For each active event in today+1/today+2:

1. parse item numbers;
2. resolve each number;
3. call upsert_prep_task once per missing action;
4. preserve existing task status and completion timestamp;
5. record unresolved item numbers in the report.

For a cancelled event, call cancel_pending_prep_tasks(event_id). For a moved event, call move_pending_prep_tasks before creating newly missing action rows. Never delete a task row.

- [ ] **Step 5: Implement the async calendar adapter**

Fetch exactly today + timedelta(days=1) and today + timedelta(days=2) using the existing calendar_service.get_events_for_day. Catch GoogleCalendarAuthError and other fetch errors, log them, and return an empty non-failing report without mutating local tasks.

- [ ] **Step 6: Run service tests to verify pass**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_service.py -q
~~~

Expected: all orchestration tests pass.

- [ ] **Step 7: Commit**

~~~powershell
git add backend/core/prep/service.py tests/test_course_prep_service.py
git commit -m "feat: synchronize faculty course preparation tasks"
~~~

---

### Task 5: Brancher la validation de première lecture sur le cycle local J1–J30

**Files:**
- Modify: backend/core/reviews/models.py
- Modify: backend/core/reviews/service.py
- Modify: backend/core/reviews/local_store.py
- Modify: frontend/pages/todo_cockpit.py
- Test: tests/test_review_generation.py
- Test: tests/test_review_service.py
- Test: tests/test_course_prep_store.py

**Interfaces:**
- Consumes: LearningSchedule, save_learning_schedule, and existing ReviewTask generation/history.
- Produces:
  - ReviewType accepts "J1".
  - REVIEW_OFFSETS == {"J1": 1, "J3": 3, "J7": 7, "J14": 14, "J30": 30}.
  - local_store._SM2_OFFSETS and _PREV_REVIEW_TYPE include J1 and the J1→J3 transition.
  - college review generation reads course_learning_schedule before legacy course fields.

- [ ] **Step 1: Write failing J1 and local-anchor tests**

~~~python
def test_review_offsets_include_j1():
    assert REVIEW_OFFSETS == {"J1": 1, "J3": 3, "J7": 7, "J14": 14, "J30": 30}


def test_local_schedule_is_used_when_course_object_has_no_first_read_date(monkeypatch, course):
    save_learning_schedule(course.id, date(2026, 8, 28))
    course.date_1ere_lecture = None
    tasks = generate_for_courses([course])
    assert {task.review_type for task in tasks} == {"J1", "J3", "J7", "J14", "J30"}
~~~

Update existing cycle-completion tests to require all five review types and add a test that J1’s theoretical date is the anchor plus one day.

- [ ] **Step 2: Run review tests to verify failure**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_review_generation.py tests/test_review_service.py -q
~~~

Expected: FAIL because J1 and the local schedule lookup are absent.

- [ ] **Step 3: Add J1 to the review model and constants**

Update the ReviewType literal, REVIEW_OFFSETS, local_store._SM2_OFFSETS, _PREV_REVIEW_TYPE, is_j_cycle_complete, and the UI cycle list. Keep existing J3/J7/J14/J30 task IDs stable.

- [ ] **Step 4: Make local schedule the college anchor**

In ReviewService.generate_reviews, read get_learning_schedule(c.id, "college"). Use its first_read_date when present, then fall back to the existing course field only for legacy records. For college jalon dates, use the schedule’s j1_date through j30_date before any legacy Notion-derived dates. Do not alter UE generation behavior.

- [ ] **Step 5: Connect first-read completion to schedule persistence**

Add a service function:

~~~python
def complete_first_read_prep(task: PrepTask, course) -> LearningSchedule:
    """Persist course-date anchor and return J1/J3/J7/J14/J30 dates."""
~~~

It must call save_learning_schedule(course.id, task.lecture_date, context="college"), then mark the preparation task done in the same user action. The task’s completion timestamp remains the actual click time; the schedule anchor remains the lecture date.

- [ ] **Step 6: Run review tests to verify pass**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_review_generation.py tests/test_review_service.py tests/test_course_prep_store.py -q
~~~

Expected: all updated review and schedule tests pass, including legacy J3/J7/J14/J30 cases.

- [ ] **Step 7: Commit**

~~~powershell
git add backend/core/reviews/models.py backend/core/reviews/service.py backend/core/reviews/local_store.py frontend/pages/todo_cockpit.py tests/test_review_generation.py tests/test_review_service.py tests/test_course_prep_store.py
git commit -m "feat: add local J1 to J30 learning schedule"
~~~

---

### Task 6: Déclencher la synchronisation dans la routine quotidienne

**Files:**
- Modify: backend/features/daily_routine.py
- Test: tests/test_daily_routine_fac_sync.py

**Interfaces:**
- Consumes: sync_fac_preparations(today) from Task 4.
- Produces: a daily routine that attempts FAC synchronization on every invocation, including when _routine_date already equals today.

- [ ] **Step 1: Write failing routine tests**

~~~python
@pytest.mark.asyncio
async def test_daily_routine_syncs_fac_before_same_day_short_circuit(monkeypatch):
    calls = []
    async def fake_sync(today):
        calls.append(today)
    monkeypatch.setattr(daily_routine, "business_today", lambda: date(2026, 8, 26))
    monkeypatch.setattr(daily_routine, "sync_fac_preparations", fake_sync)
    monkeypatch.setitem(daily_routine.data_store.preferences, "_routine_date", "2026-08-26")
    await daily_routine.run_daily_routine()
    assert calls == [date(2026, 8, 26)]
~~~

Also test that a sync exception is logged and does not prevent the existing daily page maintenance.

- [ ] **Step 2: Run routine tests to verify failure**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_daily_routine_fac_sync.py -q
~~~

Expected: FAIL because the routine does not call the FAC service.

- [ ] **Step 3: Integrate the non-blocking sync**

Call await sync_fac_preparations(today) after computing today and before the _routine_date early return. Wrap it in a narrow try/except that logs the failure and leaves the existing Notion daily-page behavior unchanged.

- [ ] **Step 4: Run routine tests to verify pass**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_daily_routine_fac_sync.py tests/test_flash_zero_integration.py -q
~~~

Expected: all routine tests pass.

- [ ] **Step 5: Commit**

~~~powershell
git add backend/features/daily_routine.py tests/test_daily_routine_fac_sync.py
git commit -m "feat: run faculty preparation sync from daily routine"
~~~

---

### Task 7: Ajouter les préparations FAC à la boucle du jour

**Files:**
- Create: frontend/components/course_prep_task_row.py
- Modify: frontend/pages/dashboard/_cockpit_today.py
- Modify: frontend/components/course_quick_actions.py
- Test: tests/test_course_prep_task_row.py
- Test: tests/test_todo_cockpit_ui.py

**Interfaces:**
- Consumes: PrepTask, list_prep_tasks, update_prep_task_status, complete_first_read_prep, and local course resolution.
- Produces:
  - action_label(task_type: PrepTaskType) -> str.
  - render_course_prep_task(task: PrepTask, course, on_open, on_validate) -> None.
  - open_course_prep_action(course, task_type, refresh_fn, client) -> None in course_quick_actions.py.

- [ ] **Step 1: Write failing component tests**

~~~python
def test_action_labels_are_stable():
    assert action_label("pdf") == "Lier le PDF"
    assert action_label("obsidian") == "Créer la fiche Obsidian"
    assert action_label("resume") == "Faire le résumé"
    assert action_label("first_read") == "Faire une première lecture"
~~~

Add a source-level UI test asserting that _cockpit_today.py renders Préparations FAC, Raccourci, and Valider.

- [ ] **Step 2: Run UI tests to verify failure**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_task_row.py tests/test_todo_cockpit_ui.py -q
~~~

Expected: FAIL because the component and dashboard block are absent.

- [ ] **Step 3: Expose action-specific shortcut wrappers**

Implement open_course_prep_action as follows:

~~~python
if task_type == "pdf":
    open_pdf_wizard(course, "college", refresh_fn, client)
elif task_type == "obsidian":
    open_link_note_dialog(course, refresh_fn)
else:
    ui.navigate.to(f"/cours/{course.id}")
~~~

The resume and first_read actions open the course detail page; they do not mark the task done.

- [ ] **Step 4: Render the preparation block and validation callbacks**

In _cockpit_today.py, load list_prep_tasks(business_today(), ("todo",)) during _fetch() and render a dedicated Préparations FAC card before the spaced-repetition queue. Resolve each task’s course locally, render the action row, and on validation:

~~~python
if task.task_type == "first_read":
    complete_first_read_prep(task, course)
else:
    update_prep_task_status(task.id, "done")
_full_rebuild()
~~~

An unresolved course must render as an unavailable row with the stored item number and no action button; it must not crash the dashboard.

- [ ] **Step 5: Run UI tests to verify pass**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_task_row.py tests/test_todo_cockpit_ui.py -q
~~~

Expected: all component and source-level UI tests pass.

- [ ] **Step 6: Commit**

~~~powershell
git add frontend/components/course_prep_task_row.py frontend/components/course_quick_actions.py frontend/pages/dashboard/_cockpit_today.py tests/test_course_prep_task_row.py tests/test_todo_cockpit_ui.py
git commit -m "feat: show faculty preparation tasks in today cockpit"
~~~

---

### Task 8: Vérification d’intégration et non-régression

**Files:**
- Modify: tests created by Tasks 1–7 only if a failing integration exposes an actual contract mismatch.
- Test: full repository suite.

**Interfaces:**
- Consumes: all public interfaces from Tasks 1–7.
- Produces: verified feature with no unrelated staged files and a final test result.

- [ ] **Step 1: Run the focused feature suite**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_course_prep_store.py tests/test_course_prep_calendar_parser.py tests/test_planning_calendar_sources.py tests/test_planning_calendar_actions.py tests/test_course_prep_service.py tests/test_review_generation.py tests/test_review_service.py tests/test_daily_routine_fac_sync.py tests/test_course_prep_task_row.py tests/test_todo_cockpit_ui.py -q
~~~

Expected: all feature tests pass.

- [ ] **Step 2: Run the complete suite**

Run:

~~~powershell
./.venv/Scripts/python.exe -m pytest -q
~~~

Expected: no regression in existing calendar, course-detail, Obsidian, review, dashboard, or planning tests.

- [ ] **Step 3: Inspect the final diff and working tree**

Run:

~~~powershell
git status --short
git log --oneline -10
~~~

Expected: only the intentionally committed feature files are included in the feature commits; existing user changes remain untouched.
