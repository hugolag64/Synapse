# Flux de consolidation long terme (SM-2 étendu) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the bug where declared-level college items (flou/correct/solide) never generate a review task, and add an indefinite "consolidation" flow for items that finish their J3-J30 cycle, using a self-chaining extension of the existing SM-2 engine (grows/shrinks intervals like Anki instead of a fixed cadence).

**Architecture:** New `backend/core/reviews/consolidation.py` module builds virtual `ReviewTask` objects (reusing the existing pydantic model, extended with a `"consolidation"` `review_type` and a `semestre` field) from a pool of eligible courses (declared-only OR finished-J30), backed by new small SQLite helpers in `local_store.py` that bootstrap and advance a self-referencing SM-2 chain per course. A new Planning page tab renders these tasks with Valider/Passer/"Ajouter un cours" actions, reusing the existing `open_session_feedback_dialog` confidence-input dialog as-is.

**Tech Stack:** Python 3.13, NiceGUI (frontend), SQLite (`data/synapse_local.db`), pydantic (ReviewTask), pytest (unittest.TestCase style + `isolated_db` fixture pattern already used in `tests/test_knowledge_store.py`).

## Global Constraints

- No Notion writes for anything in this plan — all new state lives in SQLite (`review_history`, reusing existing table + columns).
- Reuse `open_session_feedback_dialog` (`frontend/pages/dashboard/_dialogs.py:205`) as-is for the confidence-input dialog — do not build a parallel dialog.
- `context` is always `"college"` for this feature (no `"ue"` support) — matches the scope agreed in the design (validated colleges only).
- Do not modify the existing `mark_done()` function in `local_store.py` — it's shared by the J3/J7/J14/J30 pipeline and already covered by tests; consolidation gets its own `mark_consolidation_done()` because it needs ease-factor/repetition state to carry across occurrences with different `task_id`s, which `mark_done()`'s per-`task_id` lookup cannot do.
- Every new SQLite function goes in `backend/core/reviews/local_store.py` (existing pattern: local_store.py is the only file with raw SQL for reviews).
- Tests use the `isolated_db` autouse fixture pattern from `tests/test_knowledge_store.py:8-21` (temp SQLite DB via `monkeypatch`), combined with `unittest.mock.patch('backend.state.store.data_store')` where `data_store.cours` is needed (pattern from `tests/test_review_service.py:21-23`).

---

## File Structure

- **Modify** `backend/core/reviews/local_store.py` — add 6 new functions (SM-2 self-chain primitives). No changes to existing functions.
- **Modify** `backend/core/reviews/models.py` — extend `ReviewType` Literal, add `semestre` field to `ReviewTask`.
- **Create** `backend/core/reviews/consolidation.py` — pool building, eligibility, daily selection, ad-hoc bootstrap. The only file that knows about "what counts as eligible for consolidation."
- **Modify** `backend/core/planning/service.py` — one new thin method `plan_consolidation()`.
- **Modify** `backend/state/store.py` — add `semestre_actuel` default preference.
- **Modify** `frontend/pages/planning.py` — new "Consolidation" tab, card component, 3 actions.
- **Create** `tests/test_consolidation.py` — covers `local_store.py` additions and `consolidation.py` logic.

---

### Task 1: SM-2 self-chaining primitives in `local_store.py`

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_consolidation.py` (new)

**Interfaces:**
- Produces:
  - `is_j_cycle_complete(course_id: str, context: str) -> bool`
  - `get_last_completed_date(course_id: str, context: str, review_type: str) -> Optional[datetime.date]`
  - `get_last_consolidation_state(course_id: str, context: str) -> Optional[sqlite3.Row]`
  - `bootstrap_consolidation(course_id: str, context: str, course_title: str, item_number: str, initial_interval_days: int, at_date: datetime.date) -> None`
  - `mark_consolidation_done(course_id: str, context: str, theoretical_due_date: datetime.date, course_title: str = "", item_number: str = "", confidence: int = 3, difficulty: Optional[str] = None, notes: Optional[str] = None) -> int` (returns the new `next_interval_days`)
  - `get_consolidation_due_date(course_id: str, context: str) -> Optional[datetime.date]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_consolidation.py`:

```python
"""Tests unitaires — consolidation (SM-2 self-chaining) et pool de consolidation."""
import datetime
import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.reviews.local_store as ls
    import backend.core.knowledge.store as ks

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", test_db)
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    ks.init_knowledge_tables()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls


# ── is_j_cycle_complete ──────────────────────────────────────────────────────

def test_j_cycle_incomplet_si_aucune_tache_done():
    assert ls.is_j_cycle_complete("course-1", "college") is False


def test_j_cycle_incomplet_si_3_sur_4():
    for rt in ("J3", "J7", "J14"):
        ls.mark_done(
            task_id=f"course-1_college_{rt}_2026-01-01",
            course_id="course-1", context="college", review_type=rt,
            theoretical_due_date=datetime.date(2026, 1, 1),
        )
    assert ls.is_j_cycle_complete("course-1", "college") is False


def test_j_cycle_complet_si_4_sur_4():
    for rt in ("J3", "J7", "J14", "J30"):
        ls.mark_done(
            task_id=f"course-1_college_{rt}_2026-01-01",
            course_id="course-1", context="college", review_type=rt,
            theoretical_due_date=datetime.date(2026, 1, 1),
        )
    assert ls.is_j_cycle_complete("course-1", "college") is True


def test_j_cycle_ignore_un_autre_contexte():
    for rt in ("J3", "J7", "J14", "J30"):
        ls.mark_done(
            task_id=f"course-1_ue_{rt}_2026-01-01",
            course_id="course-1", context="ue", review_type=rt,
            theoretical_due_date=datetime.date(2026, 1, 1),
        )
    assert ls.is_j_cycle_complete("course-1", "college") is False


# ── get_last_completed_date ──────────────────────────────────────────────────

def test_get_last_completed_date_absent():
    assert ls.get_last_completed_date("course-1", "college", "J30") is None


def test_get_last_completed_date_present():
    ls.mark_done(
        task_id="course-1_college_J30_2026-01-30",
        course_id="course-1", context="college", review_type="J30",
        theoretical_due_date=datetime.date(2026, 1, 30),
    )
    d = ls.get_last_completed_date("course-1", "college", "J30")
    assert d == datetime.date.today()


# ── bootstrap_consolidation ──────────────────────────────────────────────────

def test_bootstrap_consolidation_cree_une_ligne():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    row = ls.get_last_consolidation_state("course-1", "college")
    assert row is not None
    assert row["status"] == "done"
    assert row["next_interval_days"] == 21
    assert row["completed_at"][:10] == "2026-06-01"


def test_bootstrap_consolidation_idempotent():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=14, at_date=datetime.date(2026, 6, 5),
    )
    row = ls.get_last_consolidation_state("course-1", "college")
    # La 2e tentative n'a rien changé (toujours l'amorçage initial).
    assert row["next_interval_days"] == 21
    assert row["completed_at"][:10] == "2026-06-01"


# ── get_consolidation_due_date ───────────────────────────────────────────────

def test_get_consolidation_due_date_absent():
    assert ls.get_consolidation_due_date("course-1", "college") is None


def test_get_consolidation_due_date_apres_bootstrap():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    due = ls.get_consolidation_due_date("course-1", "college")
    assert due == datetime.date(2026, 6, 22)


# ── mark_consolidation_done : croissance / décroissance type Anki ──────────

def test_mark_consolidation_done_intervalles_fixes_pour_les_2_premieres_repetitions():
    """compute_next_interval (SM-2 standard) utilise des paliers fixes (3j, 7j)
    pour repetition 0 et 1, quelle que soit la confiance (>= 3/5) — la
    croissance liée à l'ease factor ne démarre qu'à partir de la 3e répétition.
    C'est un comportement existant de sm2.py, pas quelque chose à contourner."""
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    i1 = ls.mark_consolidation_done(
        "course-1", "college", datetime.date(2026, 6, 22), confidence=5,
    )
    assert i1 == 3

    due2 = datetime.date(2026, 6, 22) + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due2, confidence=5)
    assert i2 == 7


def test_mark_consolidation_done_croit_a_partir_de_la_3e_repetition():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    due = datetime.date(2026, 6, 22)
    i1 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i2)
    i3 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    assert i3 > i2  # l'ease factor entre enfin en jeu -> croissance type Anki


def test_mark_consolidation_done_echec_revient_a_un_intervalle_court():
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    due = datetime.date(2026, 6, 22)
    i1 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done("course-1", "college", due, confidence=5)
    due = due + datetime.timedelta(days=i2)
    i3 = ls.mark_consolidation_done("course-1", "college", due, confidence=1)  # échec
    assert i3 <= 3
    assert i3 < i2


def test_mark_consolidation_done_progresse_sur_plusieurs_occurrences():
    """Le repetition_count et l'ease factor doivent survivre d'une occurrence
    à l'autre, malgré des task_id différents à chaque fois (due date différente)."""
    ls.bootstrap_consolidation(
        "course-1", "college", "Mon cours", "42",
        initial_interval_days=21, at_date=datetime.date(2026, 6, 1),
    )
    i1 = ls.mark_consolidation_done(
        "course-1", "college", datetime.date(2026, 6, 22), confidence=5,
    )
    row1 = ls.get_last_consolidation_state("course-1", "college")
    assert row1["repetition_count"] == 1

    due2 = datetime.date(2026, 6, 22) + datetime.timedelta(days=i1)
    i2 = ls.mark_consolidation_done(
        "course-1", "college", due2, confidence=5,
    )
    row2 = ls.get_last_consolidation_state("course-1", "college")
    assert row2["repetition_count"] == 2
    assert i2 >= i1  # confiance haute répétée -> l'intervalle continue de croître ou se stabilise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: FAIL — `AttributeError: module 'backend.core.reviews.local_store' has no attribute 'is_j_cycle_complete'` (and similar for the other new functions).

- [ ] **Step 3: Implement the 6 functions**

In `backend/core/reviews/local_store.py`, add after the `ignore()` function (around line 470, before the "Migration study_sessions v2" section):

```python
# ── API publique — consolidation (SM-2 auto-chaîné) ──────────────────────────

def is_j_cycle_complete(course_id: str, context: str) -> bool:
    """True si les 4 révisions J3/J7/J14/J30 sont toutes marquées done."""
    with _conn() as con:
        rows = con.execute(
            """SELECT DISTINCT review_type FROM review_history
               WHERE course_id = ? AND context = ?
                 AND review_type IN ('J3','J7','J14','J30') AND status = 'done'""",
            (course_id, context),
        ).fetchall()
    done_types = {r["review_type"] for r in rows}
    return done_types == {"J3", "J7", "J14", "J30"}


def get_last_completed_date(
    course_id: str, context: str, review_type: str
) -> Optional[datetime.date]:
    """Date de complétion la plus récente d'un review_type donné, ou None."""
    with _conn() as con:
        row = con.execute(
            """SELECT completed_at FROM review_history
               WHERE course_id = ? AND context = ? AND review_type = ? AND status = 'done'
               ORDER BY completed_at DESC LIMIT 1""",
            (course_id, context, review_type),
        ).fetchone()
    if not row or not row["completed_at"]:
        return None
    return datetime.date.fromisoformat(str(row["completed_at"])[:10])


def get_last_consolidation_state(course_id: str, context: str) -> Optional[sqlite3.Row]:
    """Dernière ligne 'consolidation' done (la plus récente), ou None si jamais amorcée."""
    with _conn() as con:
        return con.execute(
            """SELECT * FROM review_history
               WHERE course_id = ? AND context = ? AND review_type = 'consolidation'
                 AND status = 'done'
               ORDER BY completed_at DESC LIMIT 1""",
            (course_id, context),
        ).fetchone()


def bootstrap_consolidation(
    course_id: str,
    context: str,
    course_title: str,
    item_number: str,
    initial_interval_days: int,
    at_date: datetime.date,
) -> None:
    """
    Amorce la chaîne SM-2 'consolidation' pour un cours, si elle n'existe pas
    déjà. Insère une ligne synthétique 'done' qui sert de premier point
    d'ancrage pour get_consolidation_due_date et mark_consolidation_done.
    Idempotent : ne fait rien si une ligne consolidation existe déjà.
    """
    if get_last_consolidation_state(course_id, context) is not None:
        return

    from backend.core.reviews.sm2 import SM2_INIT_EF

    task_id = make_task_id(course_id, context, "consolidation", at_date)
    now = _now()
    with _conn() as con:
        con.execute("""
            INSERT INTO review_history
                (task_id, course_id, course_title, item_number, context, review_type,
                 theoretical_due_date, effective_due_date, status, completed_at,
                 easiness_factor, repetition_count, next_interval_days,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,'consolidation',?,?,'done',?,?,?,?,?,?)
            ON CONFLICT(task_id) DO NOTHING
        """, (
            task_id, course_id, course_title, item_number, context,
            at_date.isoformat(), at_date.isoformat(), at_date.isoformat(),
            SM2_INIT_EF, 0, initial_interval_days,
            now, now,
        ))


def get_consolidation_due_date(course_id: str, context: str) -> Optional[datetime.date]:
    """Prochaine échéance de consolidation, ou None si jamais amorcée."""
    row = get_last_consolidation_state(course_id, context)
    if not row or not row["completed_at"] or row["next_interval_days"] is None:
        return None
    completed = datetime.date.fromisoformat(str(row["completed_at"])[:10])
    return completed + datetime.timedelta(days=row["next_interval_days"])


def mark_consolidation_done(
    course_id: str,
    context: str,
    theoretical_due_date: datetime.date,
    course_title: str = "",
    item_number: str = "",
    confidence: int = 3,
    difficulty: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """
    Valide une occurrence 'consolidation' et fait progresser la chaîne SM-2.

    Repart de l'état de la DERNIÈRE occurrence complétée (pas de l'occurrence
    courante, qui n'existe pas encore en base tant qu'elle n'a pas de
    completed_at) — sinon l'ease factor et le repetition_count repartiraient
    de zéro à chaque validation, ce qui casserait la croissance des intervalles.

    Retourne le nouvel intervalle (jours), utile pour les tests/logs.
    """
    from backend.core.reviews.sm2 import compute_next_interval, SM2_INIT_EF

    prev = get_last_consolidation_state(course_id, context)
    prev_ef       = (prev["easiness_factor"]   if prev else None) or SM2_INIT_EF
    prev_rep      = (prev["repetition_count"]  if prev else None) or 0
    prev_interval = (prev["next_interval_days"] if prev else None) or 21

    next_interval, new_ef = compute_next_interval(
        current_interval_days=prev_interval,
        confidence=confidence,
        easiness_factor=prev_ef,
        repetition=prev_rep,
    )
    new_rep = prev_rep + 1

    task_id = make_task_id(course_id, context, "consolidation", theoretical_due_date)
    now = _now()
    with _conn() as con:
        con.execute("""
            INSERT INTO review_history
                (task_id, course_id, course_title, item_number, context, review_type,
                 theoretical_due_date, effective_due_date, status, completed_at,
                 confidence, difficulty, notes,
                 easiness_factor, repetition_count, next_interval_days,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,'consolidation',?,?,'done',?,?,?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                status             = 'done',
                completed_at       = excluded.completed_at,
                postponed_to       = NULL,
                confidence         = excluded.confidence,
                difficulty         = excluded.difficulty,
                notes              = excluded.notes,
                easiness_factor    = excluded.easiness_factor,
                repetition_count   = excluded.repetition_count,
                next_interval_days = excluded.next_interval_days,
                updated_at         = excluded.updated_at
        """, (
            task_id, course_id, course_title, item_number, context,
            theoretical_due_date.isoformat(), theoretical_due_date.isoformat(),
            now, confidence, difficulty, notes,
            new_ef, new_rep, next_interval,
            now, now,
        ))
    return next_interval
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: PASS (all tests in the file so far).

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_consolidation.py
git commit -m "feat(reviews): add SM-2 self-chaining primitives for consolidation"
```

---

### Task 2: Extend `ReviewTask` model with `"consolidation"` type and `semestre` field

**Files:**
- Modify: `backend/core/reviews/models.py`
- Test: `tests/test_consolidation.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ReviewType` now includes `"consolidation"`; `ReviewTask.semestre: Optional[str] = None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_consolidation.py`:

```python
# ── ReviewTask accepts review_type="consolidation" + semestre ───────────────

def test_review_task_accepte_consolidation_et_semestre():
    from datetime import date
    from backend.core.reviews.models import ReviewTask

    t = ReviewTask(
        id="x", course_id="c1", course_title="Titre",
        theoretical_due_date=date(2026, 6, 1), due_date=date(2026, 6, 1),
        review_type="consolidation", semestre="Semestre 4",
    )
    assert t.review_type == "consolidation"
    assert t.semestre == "Semestre 4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_consolidation.py::test_review_task_accepte_consolidation_et_semestre -v`
Expected: FAIL — pydantic `ValidationError` on `review_type` (not a permitted literal value).

- [ ] **Step 3: Implement**

In `backend/core/reviews/models.py:15`, change:

```python
ReviewType   = Literal["J3", "J7", "J14", "J30", "bonus", "qcm_error", "manuel"]
```
to:
```python
ReviewType   = Literal["J3", "J7", "J14", "J30", "bonus", "qcm_error", "manuel", "consolidation"]
```

And add a new field in the `ReviewTask` class, right after `mastery_reasons` (around line 71):

```python
    mastery_reasons: List[str] = Field(default_factory=list)

    # Semestre du cours (Notion), utilisé pour pondérer la priorité de consolidation
    semestre: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/models.py tests/test_consolidation.py
git commit -m "feat(reviews): add consolidation review_type and semestre field to ReviewTask"
```

---

### Task 3: `consolidation.py` — pool building and eligibility

**Files:**
- Create: `backend/core/reviews/consolidation.py`
- Test: `tests/test_consolidation.py`

**Interfaces:**
- Consumes: `local_store.is_j_cycle_complete`, `local_store.get_last_completed_date`, `local_store.bootstrap_consolidation`, `local_store.get_consolidation_due_date`, `local_store.get_history`, `local_store.make_task_id` (Task 1); `ReviewTask` with `review_type="consolidation"` (Task 2); `backend.core.reviews.mastery.get_course_mastery`; `backend.core.knowledge.store.get_item_state`; `backend.state.store.data_store.cours`.
- Produces: `get_due_consolidation_tasks(context: str = "college", today: Optional[date] = None) -> list[ReviewTask]`; module constants `INITIAL_INTERVAL_BY_LEVEL: dict[str, int]`, `DEFAULT_INITIAL_INTERVAL: int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_consolidation.py`:

```python
# ── get_due_consolidation_tasks ──────────────────────────────────────────────

from unittest.mock import patch, MagicMock
from datetime import date
from backend.core.notion.models import Cours


def _mock_cours(id, title, college, semestre=None, date_1ere_lecture=None,
                 item_number="1", nb_lectures=0):
    c = MagicMock(spec=Cours)
    c.id = id
    c.title = title
    c.item_number = item_number
    c.college = college
    c.semestre = semestre
    c.date_1ere_lecture = date_1ere_lecture
    c.date_1ere_lecture_ue = None
    c.nb_lectures = nb_lectures
    c.nb_lectures_ue = 0
    c.url_pdf = None
    c.url_pdf_ue = None
    c.agregation_fiche_edn = None
    c.anki = False
    c.qcm_done = False
    c.course_status = "À lire"
    return c


@patch('backend.state.store.data_store')
def test_pool_inclut_item_declare_sans_lecture(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ks.set_item_state("course-1", "flou", context="college", source="triage")
    c = _mock_cours("course-1", "Cours test", ["Cardiovasculaire ❤️"], date_1ere_lecture=None)
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(
        context="college", today=date.today() + datetime.timedelta(days=1),
    )
    assert len(tasks) == 1
    assert tasks[0].review_type == "consolidation"
    assert tasks[0].course_id == "course-1"


@patch('backend.state.store.data_store')
def test_pool_exclut_item_en_cours_de_cycle_j(mock_data_store):
    from backend.core.reviews import consolidation

    ls.mark_done(
        task_id="course-2_college_J3_2026-01-01",
        course_id="course-2", context="college", review_type="J3",
        theoretical_due_date=date(2026, 1, 1),
    )
    c = _mock_cours(
        "course-2", "Cours en cycle", ["Cardiovasculaire ❤️"],
        date_1ere_lecture=date(2025, 12, 1), nb_lectures=1,
    )
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(context="college")
    assert tasks == []


@patch('backend.state.store.data_store')
def test_pool_inclut_item_ayant_fini_j30(mock_data_store):
    from backend.core.reviews import consolidation

    for rt in ("J3", "J7", "J14", "J30"):
        ls.mark_done(
            task_id=f"course-3_college_{rt}_2026-01-01",
            course_id="course-3", context="college", review_type=rt,
            theoretical_due_date=date(2026, 1, 1),
        )
    c = _mock_cours(
        "course-3", "Cours fini", ["Pneumologie 🫁"],
        date_1ere_lecture=date(2025, 12, 1), nb_lectures=4,
    )
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(
        context="college", today=date.today() + datetime.timedelta(days=40),
    )
    assert len(tasks) == 1
    assert tasks[0].course_id == "course-3"


@patch('backend.state.store.data_store')
def test_pool_exclut_item_non_demarre(mock_data_store):
    from backend.core.reviews import consolidation

    c = _mock_cours("course-4", "Jamais touché", ["Dermatologie 🧴"])
    mock_data_store.cours = [c]

    tasks = consolidation.get_due_consolidation_tasks(context="college")
    assert tasks == []


@patch('backend.state.store.data_store')
def test_pool_exclut_item_pas_encore_du(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ks.set_item_state("course-5", "solide", context="college", source="triage")
    c = _mock_cours("course-5", "Cours solide", ["Nutrition 🍔"])
    mock_data_store.cours = [c]

    # Amorcé aujourd'hui avec un intervalle initial de 30j (solide) -> pas dû aujourd'hui.
    tasks = consolidation.get_due_consolidation_tasks(context="college", today=date.today())
    assert tasks == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.reviews.consolidation'`.

- [ ] **Step 3: Implement `consolidation.py`**

Create `backend/core/reviews/consolidation.py`:

```python
"""
consolidation.py — Synapse
---------------------------
Flux de consolidation long terme : items dont le cycle J3-J30 est terminé,
ou qui ont un niveau déclaré (flou/correct/solide) sans jamais avoir été
suivis dans l'app (lus avant l'existence de Synapse).

Utilise le moteur SM-2 existant, étendu avec un review_type "consolidation"
auto-chaîné (backend.core.reviews.local_store) : l'intervalle s'étire
automatiquement avec la maîtrise plutôt que de suivre un cycle fixe.

Pas d'I/O réseau — data_store.cours est déjà chargé en mémoire.
"""
from __future__ import annotations

import datetime
from typing import Optional

from backend.core.reviews import local_store
from backend.core.reviews.models import ReviewTask
from backend.core.reviews.mastery import get_course_mastery

# Intervalle initial (jours) selon le niveau de maîtrise au moment de l'amorçage.
INITIAL_INTERVAL_BY_LEVEL: dict[str, int] = {
    "critique":          14,
    "fragile":           18,
    "en construction":   18,
    "à consolider":      24,
    "à entraîner":       24,
    "maîtrisé":          30,
}
DEFAULT_INITIAL_INTERVAL = 21

_HIDDEN_STATUSES = {"done", "ignored", "cancelled"}


def _bootstrap_at_date(
    course, context: str, date_ref: Optional[datetime.date], today: datetime.date
) -> datetime.date:
    """Date d'ancrage pour l'amorçage : date de déclaration (item pré-app) ou
    date de complétion du J30 (item ayant fini son cycle)."""
    if date_ref is None:
        from backend.core.knowledge import store as ks
        item_state = ks.get_item_state(course.id, context)
        return item_state.declared_at if item_state else today
    return local_store.get_last_completed_date(course.id, context, "J30") or today


def get_due_consolidation_tasks(
    context: str = "college",
    today: Optional[datetime.date] = None,
) -> list[ReviewTask]:
    """
    Construit les ReviewTask virtuelles 'consolidation' dues aujourd'hui ou
    en retard, pour tous les cours éligibles. Amorce (bootstrap) au passage
    les items nouvellement éligibles qui n'ont pas encore de chaîne SM-2.
    """
    from backend.state.store import data_store

    today = today or datetime.date.today()
    tasks: list[ReviewTask] = []

    for c in data_store.cours:
        date_ref = c.date_1ere_lecture if context == "college" else c.date_1ere_lecture_ue

        mastery = get_course_mastery(c, context=context)
        if mastery.score is None:
            continue

        if date_ref is not None and not local_store.is_j_cycle_complete(c.id, context):
            continue  # encore en cours de cycle J3-J30 normal

        due = local_store.get_consolidation_due_date(c.id, context)
        if due is None:
            at_date = _bootstrap_at_date(c, context, date_ref, today)
            initial = INITIAL_INTERVAL_BY_LEVEL.get(mastery.level, DEFAULT_INITIAL_INTERVAL)
            local_store.bootstrap_consolidation(
                c.id, context, c.title, c.item_number or "", initial, at_date,
            )
            due = local_store.get_consolidation_due_date(c.id, context)
            if due is None:
                continue

        task_id = local_store.make_task_id(c.id, context, "consolidation", due)
        row = local_store.get_history(task_id)
        status = row["status"] if row else "todo"
        if status in _HIDDEN_STATUSES:
            continue

        if status == "postponed" and row["postponed_to"]:
            effective = datetime.date.fromisoformat(row["postponed_to"])
        else:
            effective = due

        if effective > today:
            continue

        days_overdue = (today - effective).days

        tasks.append(ReviewTask(
            id=task_id,
            course_id=c.id,
            course_title=c.title,
            item_number=c.item_number or None,
            college=list(c.college),
            context=context,
            url_pdf=c.url_pdf,
            url_pdf_ue=c.url_pdf_ue,
            agregation_fiche_edn=c.agregation_fiche_edn,
            theoretical_due_date=due,
            due_date=effective,
            review_type="consolidation",
            status=status,
            nb_lectures=c.nb_lectures if context == "college" else c.nb_lectures_ue,
            anki=getattr(c, "anki", False),
            qcm_done=getattr(c, "qcm_done", False),
            course_status=getattr(c, "course_status", "À lire"),
            days_overdue=max(days_overdue, 0),
            mastery_score=mastery.score,
            mastery_level=mastery.level,
            mastery_reasons=mastery.reasons,
            semestre=c.semestre,
        ))

    return tasks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/consolidation.py tests/test_consolidation.py
git commit -m "feat(reviews): build consolidation task pool with J-cycle/declared eligibility"
```

---

### Task 4: Daily selection with diversity cap + semester weighting

**Files:**
- Modify: `backend/core/reviews/consolidation.py`
- Modify: `backend/state/store.py`
- Test: `tests/test_consolidation.py`

**Interfaces:**
- Consumes: `ReviewTask.semestre`, `ReviewTask.mastery_level`, `ReviewTask.days_overdue`, `ReviewTask.college` (Task 2/3); `data_store.preferences` (existing dict).
- Produces: `select_daily(tasks: list[ReviewTask], max_items: int = 6, max_per_college: int = 2) -> tuple[list[ReviewTask], list[ReviewTask]]` (selected, skipped).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_consolidation.py`:

```python
# ── select_daily : diversité + pondération semestre/niveau ─────────────────

def _task(course_id, college, days_overdue, mastery_level="fragile", semestre="Semestre 4"):
    from backend.core.reviews.models import ReviewTask
    return ReviewTask(
        id=f"{course_id}_task", course_id=course_id, course_title=course_id,
        college=[college],
        theoretical_due_date=date.today(), due_date=date.today(),
        review_type="consolidation", days_overdue=days_overdue,
        mastery_level=mastery_level, semestre=semestre,
    )


def test_select_daily_respecte_le_plafond_par_college():
    from backend.core.reviews import consolidation

    tasks = [
        _task("c1", "Cardiovasculaire ❤️", 10),
        _task("c2", "Cardiovasculaire ❤️", 9),
        _task("c3", "Cardiovasculaire ❤️", 8),
        _task("c4", "Pneumologie 🫁", 5),
    ]
    selected, skipped = consolidation.select_daily(tasks, max_items=6, max_per_college=2)

    cardio_selected = [t for t in selected if t.college == ["Cardiovasculaire ❤️"]]
    assert len(cardio_selected) == 2
    assert len(skipped) == 1
    assert skipped[0].course_id == "c3"  # le moins prioritaire des 3 cardio


def test_select_daily_respecte_max_items():
    from backend.core.reviews import consolidation

    tasks = [_task(f"c{i}", f"College {i}", 10 - i) for i in range(5)]
    selected, skipped = consolidation.select_daily(tasks, max_items=3, max_per_college=5)
    assert len(selected) == 3
    assert len(skipped) == 2


@patch('backend.state.store.data_store')
def test_select_daily_priorise_semestre_ancien(mock_data_store):
    from backend.core.reviews import consolidation

    mock_data_store.preferences = {"semestre_actuel": "Semestre 7"}
    old = _task("old", "A", days_overdue=5, mastery_level="à consolider", semestre="Semestre 3")
    recent = _task("recent", "B", days_overdue=5, mastery_level="à consolider", semestre="Semestre 7")

    selected, _ = consolidation.select_daily([recent, old], max_items=1, max_per_college=5)
    assert selected[0].course_id == "old"


@patch('backend.state.store.data_store')
def test_select_daily_priorise_niveau_critique(mock_data_store):
    from backend.core.reviews import consolidation

    mock_data_store.preferences = {"semestre_actuel": "Semestre 7"}
    critique = _task("crit", "A", days_overdue=5, mastery_level="critique", semestre="Semestre 7")
    maitrise = _task("mait", "B", days_overdue=5, mastery_level="maîtrisé", semestre="Semestre 7")

    selected, _ = consolidation.select_daily([maitrise, critique], max_items=1, max_per_college=5)
    assert selected[0].course_id == "crit"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: FAIL — `AttributeError: module 'backend.core.reviews.consolidation' has no attribute 'select_daily'`.

- [ ] **Step 3: Implement**

In `backend/state/store.py`, add to `_get_default_preferences()` (near the other defaults, around line 63):

```python
    def _get_default_preferences(self):
        return {
            'dark_mode': False,
            'semestre_actuel': 'Semestre 7',
            # Profile 1 (Standard)
            'pomo_1_work': 25,
```

In `backend/core/reviews/consolidation.py`, add at the top (after `DEFAULT_INITIAL_INTERVAL`):

```python
# Poids semestre : +0.15 par semestre d'écart avec la préférence semestre_actuel.
SEMESTER_GAP_WEIGHT = 0.15

# Poids niveau (multiplicatif — distinct du barème additif de reviews/service.py,
# adapté pour la formule jours_de_retard * poids_semestre * poids_niveau).
MASTERY_WEIGHT: dict[str, float] = {
    "critique":         2.5,
    "fragile":          2.0,
    "en construction":  1.6,
    "à consolider":     1.3,
    "à entraîner":      1.1,
    "maîtrisé":         1.0,
}

MAX_PER_COLLEGE_PER_DAY = 2
MAX_ITEMS_PER_DAY = 6
```

And at the end of the file, add:

```python
def _semestre_num(semestre: Optional[str]) -> Optional[int]:
    if not semestre:
        return None
    digits = "".join(ch for ch in semestre if ch.isdigit())
    return int(digits) if digits else None


def _priority_score(task: ReviewTask) -> float:
    from backend.state.store import data_store

    actuel = _semestre_num(data_store.preferences.get("semestre_actuel")) or 7
    item_sem = _semestre_num(task.semestre)
    gap = max(0, actuel - item_sem) if item_sem is not None else 0
    poids_semestre = 1 + gap * SEMESTER_GAP_WEIGHT
    poids_niveau = MASTERY_WEIGHT.get(task.mastery_level or "", 1.0)
    return max(task.days_overdue, 1) * poids_semestre * poids_niveau


def select_daily(
    tasks: list[ReviewTask],
    max_items: int = MAX_ITEMS_PER_DAY,
    max_per_college: int = MAX_PER_COLLEGE_PER_DAY,
) -> tuple[list[ReviewTask], list[ReviewTask]]:
    """
    Trie les tâches par priorité (ancienneté x semestre x niveau) et
    sélectionne les N premières en plafonnant le nombre par collège, pour
    éviter qu'une seule journée soit monopolisée par un seul collège.
    Le surplus est retourné dans `skipped` (repasse le(s) jour(s) suivant(s),
    sa date d'échéance SM-2 ne changeant pas tant qu'il n'est pas validé).
    """
    scored = sorted(tasks, key=_priority_score, reverse=True)
    selected: list[ReviewTask] = []
    skipped: list[ReviewTask] = []
    college_count: dict[str, int] = {}

    for t in scored:
        primary = t.college[0] if t.college else "?"
        if len(selected) < max_items and college_count.get(primary, 0) < max_per_college:
            selected.append(t)
            college_count[primary] = college_count.get(primary, 0) + 1
        else:
            skipped.append(t)

    return selected, skipped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/consolidation.py backend/state/store.py tests/test_consolidation.py
git commit -m "feat(reviews): daily consolidation selection with college diversity cap"
```

---

### Task 5: Ad-hoc "add a course" bootstrap

**Files:**
- Modify: `backend/core/reviews/consolidation.py`
- Test: `tests/test_consolidation.py`

**Interfaces:**
- Consumes: same as Task 3's helpers, plus `data_store.cours` lookup by id.
- Produces: `get_or_bootstrap_task(course_id: str, context: str = "college") -> Optional[ReviewTask]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_consolidation.py`:

```python
# ── get_or_bootstrap_task (ajout manuel d'un cours) ─────────────────────────

@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_cree_la_chaine_si_absente(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.reviews import consolidation

    ks.set_item_state("course-6", "correct", context="college", source="triage")
    c = _mock_cours("course-6", "Cours ajouté", ["Infectiologie 🦠"])
    mock_data_store.cours = [c]

    task = consolidation.get_or_bootstrap_task("course-6", context="college")
    assert task is not None
    assert task.course_id == "course-6"
    assert task.review_type == "consolidation"
    assert ls.get_last_consolidation_state("course-6", "college") is not None


@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_reutilise_chaine_existante(mock_data_store):
    from backend.core.reviews import consolidation

    ls.bootstrap_consolidation(
        "course-7", "college", "Déjà amorcé", "1",
        initial_interval_days=21, at_date=date(2026, 1, 1),
    )
    c = _mock_cours("course-7", "Déjà amorcé", ["Neurologie 🧠"])
    mock_data_store.cours = [c]

    task = consolidation.get_or_bootstrap_task("course-7", context="college")
    assert task.theoretical_due_date == date(2026, 1, 22)


@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_none_si_cours_introuvable(mock_data_store):
    from backend.core.reviews import consolidation

    mock_data_store.cours = []
    assert consolidation.get_or_bootstrap_task("nope", context="college") is None


@patch('backend.state.store.data_store')
def test_get_or_bootstrap_task_none_si_jamais_demarre(mock_data_store):
    from backend.core.reviews import consolidation

    c = _mock_cours("course-8", "Jamais commencé", ["Nutrition 🍔"])
    mock_data_store.cours = [c]
    assert consolidation.get_or_bootstrap_task("course-8", context="college") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: FAIL — `AttributeError: module 'backend.core.reviews.consolidation' has no attribute 'get_or_bootstrap_task'`.

- [ ] **Step 3: Implement**

In `backend/core/reviews/consolidation.py`, add at the end:

```python
def get_or_bootstrap_task(course_id: str, context: str = "college") -> Optional[ReviewTask]:
    """
    Retourne la ReviewTask 'consolidation' d'un cours choisi manuellement
    ("j'ai travaillé ce cours aujourd'hui"), en amorçant sa chaîne SM-2 si
    elle n'existe pas encore. due_date est forcée à aujourd'hui — l'utilisateur
    choisit de le traiter maintenant, indépendamment de sa vraie échéance.
    Retourne None si le cours est introuvable ou jamais démarré (mastery.score is None).
    """
    from backend.state.store import data_store

    course = next((c for c in data_store.cours if c.id == course_id), None)
    if course is None:
        return None

    mastery = get_course_mastery(course, context=context)
    if mastery.score is None:
        return None

    today = datetime.date.today()
    due = local_store.get_consolidation_due_date(course.id, context)
    if due is None:
        date_ref = course.date_1ere_lecture if context == "college" else course.date_1ere_lecture_ue
        at_date = _bootstrap_at_date(course, context, date_ref, today)
        initial = INITIAL_INTERVAL_BY_LEVEL.get(mastery.level, DEFAULT_INITIAL_INTERVAL)
        local_store.bootstrap_consolidation(
            course.id, context, course.title, course.item_number or "", initial, at_date,
        )
        due = local_store.get_consolidation_due_date(course.id, context) or today

    task_id = local_store.make_task_id(course.id, context, "consolidation", due)
    return ReviewTask(
        id=task_id,
        course_id=course.id,
        course_title=course.title,
        item_number=course.item_number or None,
        college=list(course.college),
        context=context,
        url_pdf=course.url_pdf,
        url_pdf_ue=course.url_pdf_ue,
        agregation_fiche_edn=course.agregation_fiche_edn,
        theoretical_due_date=due,
        due_date=today,
        review_type="consolidation",
        status="todo",
        nb_lectures=course.nb_lectures if context == "college" else course.nb_lectures_ue,
        anki=getattr(course, "anki", False),
        qcm_done=getattr(course, "qcm_done", False),
        course_status=getattr(course, "course_status", "À lire"),
        days_overdue=0,
        mastery_score=mastery.score,
        mastery_level=mastery.level,
        mastery_reasons=mastery.reasons,
        semestre=course.semestre,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/consolidation.py tests/test_consolidation.py
git commit -m "feat(reviews): ad-hoc bootstrap for manually-added consolidation courses"
```

---

### Task 6: `PlanningService.plan_consolidation()`

**Files:**
- Modify: `backend/core/planning/service.py`
- Test: `tests/test_consolidation.py`

**Interfaces:**
- Consumes: `consolidation.get_due_consolidation_tasks`, `consolidation.select_daily` (Tasks 3-4).
- Produces: `PlanningService.plan_consolidation(self, max_items: int = 6, max_per_college: int = 2) -> tuple[list[ReviewTask], list[ReviewTask]]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_consolidation.py`:

```python
# ── PlanningService.plan_consolidation ───────────────────────────────────────

@patch('backend.state.store.data_store')
def test_plan_consolidation_retourne_selection_et_surplus(mock_data_store):
    import backend.core.knowledge.store as ks
    from backend.core.planning.service import planning_service

    mock_data_store.preferences = {"semestre_actuel": "Semestre 7"}
    ks.set_item_state("course-9", "flou", context="college", source="triage")
    c = _mock_cours("course-9", "Cours plan", ["Cardiovasculaire ❤️"])
    mock_data_store.cours = [c]

    selected, skipped = planning_service.plan_consolidation(
        max_items=6, max_per_college=2,
    )
    assert len(selected) == 1
    assert skipped == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_consolidation.py::test_plan_consolidation_retourne_selection_et_surplus -v`
Expected: FAIL — `AttributeError: 'PlanningService' object has no attribute 'plan_consolidation'`.

- [ ] **Step 3: Implement**

In `backend/core/planning/service.py`, add a new method to `PlanningService`, right after `plan_week` (before the "Singleton" section, around line 235):

```python
    # ── plan_consolidation ───────────────────────────────────────────────────

    def plan_consolidation(
        self,
        max_items: int = 6,
        max_per_college: int = 2,
    ):
        """
        Sélection du jour pour le flux de consolidation long terme (items
        ayant fini leur cycle J3-J30, ou déclarés flou/correct/solide sans
        avoir jamais été suivis dans l'app). Retourne (selected, skipped).
        """
        from backend.core.reviews import consolidation

        tasks = consolidation.get_due_consolidation_tasks()
        return consolidation.select_daily(
            tasks, max_items=max_items, max_per_college=max_per_college,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_consolidation.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add backend/core/planning/service.py tests/test_consolidation.py
git commit -m "feat(planning): add plan_consolidation() to PlanningService"
```

---

### Task 7: Planning page — "Consolidation" tab with Valider/Passer/Tout reporter

**Files:**
- Modify: `frontend/pages/planning.py`

**Interfaces:**
- Consumes: `planning_service.plan_consolidation()` (Task 6); `local_store.mark_consolidation_done`, `local_store.postpone`, `local_store.add_study_session` (Task 1 + existing); `open_session_feedback_dialog` from `frontend/pages/dashboard/_dialogs.py:205`; `ReviewTask` fields `.label`, `.mastery_level`, `.days_overdue`, `.id`, `.course_id`, `.course_title`, `.item_number`, `.context`, `.theoretical_due_date`.
- Produces: a third "Consolidation" mode on the Planning page. No new public functions — purely additive UI in `planning_page()`.

This task has no automated test (no precedent in the project for testing NiceGUI pages directly — same call made in the `2026-07-02-college-en-retard-badge-design.md` spec). Verify manually per the steps at the end of this task.

- [ ] **Step 1: Add the import and card component**

In `frontend/pages/planning.py`, add to the imports at the top (after the existing `from backend.core.google.calendar_service import calendar_service` line):

```python
from backend.core.reviews import consolidation
from backend.core.reviews.local_store import mark_consolidation_done, postpone as postpone_task, add_study_session
from backend.core.reviews.models import ReviewTask
from frontend.pages.dashboard._dialogs import open_session_feedback_dialog
```

Add a new card component, after `_slot_card` (around line 119, before "Dialog export Google Calendar"):

```python
# ── Composant ConsolidationCard ────────────────────────────────────────────

def _consolidation_card(task: ReviewTask, on_validate, on_postpone):
    """Carte d'un item du flux de consolidation, avec actions Valider/Passer."""
    with ui.card().classes(
        "w-full p-0 rounded-xl border-l-4 border-l-cyan-500 "
        "border-y border-r border-slate-100 dark:border-slate-800 "
        "shadow-sm hover:shadow-md transition-all overflow-hidden"
    ) as card:
        with ui.row().classes("items-center gap-3 px-3 py-2.5 w-full"):
            ui.icon("history_edu", size="sm").classes("text-cyan-500 shrink-0")

            with ui.column().classes("flex-1 gap-0 min-w-0"):
                ui.label(task.label).classes(
                    "text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug"
                ).style(
                    "overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                ).tooltip(task.label)
                sub_parts = []
                if task.mastery_level:
                    sub_parts.append(f"niveau {task.mastery_level}")
                if task.days_overdue > 0:
                    sub_parts.append(f"{task.days_overdue}j de retard")
                ui.label(" · ".join(sub_parts) or "à consolider").classes(
                    "text-[11px] text-slate-500 dark:text-slate-400"
                )

            with ui.row().classes("items-center gap-1 shrink-0"):
                ui.button("Passer", on_click=lambda: on_postpone(task)).props(
                    "flat dense size=sm color=slate"
                )
                ui.button("Valider", icon="check", on_click=lambda t=task, c=card: on_validate(t, c)).props(
                    "unelevated dense size=sm color=cyan"
                )
    return card
```

- [ ] **Step 2: Wire the tab state, validate/postpone handlers, and render function**

In `planning_page()`, change the mode toggle section. Locate the existing block:

```python
            # Toggle Journée / Semaine
            with ui.element("div").classes(
                "flex rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700"
            ):
                btn_day = ui.button("Journée", icon="today").props(
                    "unelevated size=sm color=indigo"
                ).classes("rounded-none")
                btn_week = ui.button("Semaine", icon="date_range").props(
                    "flat size=sm color=slate"
                ).classes("rounded-none")
```

Replace it with:

```python
            # Toggle Journée / Semaine / Consolidation
            with ui.element("div").classes(
                "flex rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700"
            ):
                btn_day = ui.button("Journée", icon="today").props(
                    "unelevated size=sm color=indigo"
                ).classes("rounded-none")
                btn_week = ui.button("Semaine", icon="date_range").props(
                    "flat size=sm color=slate"
                ).classes("rounded-none")
                btn_consolidation = ui.button("Consolidation", icon="history_edu").props(
                    "flat size=sm color=slate"
                ).classes("rounded-none")
```

Update `_set_day` / `_set_week` and add `_set_consolidation` right after them:

```python
            def _set_day():
                mode_state["value"] = "day"
                btn_day.props("unelevated color=indigo")
                btn_week.props("flat color=slate")
                btn_consolidation.props("flat color=slate")
                plan_container.clear()

            def _set_week():
                mode_state["value"] = "week"
                btn_day.props("flat color=slate")
                btn_week.props("unelevated color=indigo")
                btn_consolidation.props("flat color=slate")
                plan_container.clear()

            def _set_consolidation():
                mode_state["value"] = "consolidation"
                btn_day.props("flat color=slate")
                btn_week.props("flat color=slate")
                btn_consolidation.props("unelevated color=indigo")
                plan_container.clear()

            btn_day.on("click", _set_day)
            btn_week.on("click", _set_week)
            btn_consolidation.on("click", _set_consolidation)
```

(This replaces the existing two-line `btn_day.on(...)` / `btn_week.on(...)` block — add the `btn_consolidation.on(...)` line alongside them.)

Now add the consolidation branch. In `_planifier()`, after the existing `if mode_state["value"] == "day": ... else: ...` (week branch), change the structure to a 3-way branch. Replace:

```python
                if mode_state["value"] == "day":
```

with:

```python
                if mode_state["value"] == "consolidation":
                    async def _refresh_consolidation():
                        selected, _skipped = planning_service.plan_consolidation()
                        plan_container.clear()
                        with plan_container:
                            _render_consolidation(selected)

                    async def _do_mark_consolidation(
                        t: ReviewTask, card,
                        activity_types=None, duration_minutes=None,
                        confidence=None, difficulty=None, qcm_result=None,
                        weak_category=None, weak_detail=None,
                    ) -> None:
                        mark_consolidation_done(
                            course_id=t.course_id, context=t.context,
                            theoretical_due_date=t.theoretical_due_date,
                            course_title=t.course_title, item_number=t.item_number or "",
                            confidence=confidence or 3, difficulty=difficulty,
                        )
                        add_study_session(
                            course_id=t.course_id, course_title=t.course_title,
                            item_number=t.item_number or "", context=t.context,
                            activity_types=activity_types or ["révision"],
                            duration_minutes=duration_minutes, confidence=confidence,
                            difficulty=difficulty, qcm_result=qcm_result,
                            weak_category=weak_category, weak_detail=weak_detail,
                        )
                        ui.notify(f"✓ Consolidé : {t.course_title}", type="positive")
                        await _refresh_consolidation()

                    def _on_validate(t: ReviewTask, card) -> None:
                        open_session_feedback_dialog(t, card, _do_mark_consolidation)

                    async def _on_postpone(t: ReviewTask, days: int = 7) -> None:
                        postpone_task(
                            task_id=t.id, course_id=t.course_id, context=t.context,
                            review_type="consolidation",
                            theoretical_due_date=t.theoretical_due_date,
                            postponed_to=datetime.date.today() + datetime.timedelta(days=days),
                            course_title=t.course_title, item_number=t.item_number or "",
                        )
                        ui.notify(f"Reporté : {t.course_title}", type="info")
                        await _refresh_consolidation()

                    def _render_consolidation(tasks: list[ReviewTask]) -> None:
                        if not tasks:
                            with ui.column().classes("w-full items-center py-8 gap-2 text-slate-400"):
                                ui.icon("check_circle_outline", size="xl").classes("text-green-400")
                                ui.label("Rien à consolider aujourd'hui.").classes("text-sm")
                            return

                        with ui.row().classes("items-center justify-between w-full mb-2"):
                            ui.label(f"{len(tasks)} item(s) à consolider").classes(
                                "text-xs font-bold text-cyan-600 uppercase tracking-wider"
                            )

                            async def _postpone_all():
                                for t in list(tasks):
                                    await _on_postpone(t)

                            ui.button("Tout reporter", icon="skip_next", on_click=_postpone_all).props(
                                "flat dense size=sm color=slate"
                            )

                        for t in tasks:
                            _consolidation_card(t, _on_validate, _on_postpone)

                    await _refresh_consolidation()

                elif mode_state["value"] == "day":
```

And change the final `else:` (week branch) to `else:  # "week"` (no functional change, just keep it as the fallback branch of the now-3-way if/elif/else).

- [ ] **Step 3: Manual verification**

1. Launch the app (`python main.py` or the project's usual entry point), open the Planning page.
2. Click "Consolidation" — with at least one of the 9 validated colleges having items, at least one card should appear (verifies the original bug fix: declared items now produce a task).
3. Click "Valider" on a card, set confidence to 4-5, submit — card list refreshes, item disappears (not due again for a while).
4. Re-open a Python shell or check `data/synapse_local.db` (`sqlite3 data/synapse_local.db "select next_interval_days from review_history where review_type='consolidation' order by completed_at desc limit 1"`) — interval should be longer than the initial one for that mastery level.
5. Click "Passer" on another card — it disappears from today's list.
6. With 2+ cards visible, click "Tout reporter" — all disappear.
7. Confirm the "Journée" and "Semaine" tabs still work unaffected (regression check).

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/planning.py
git commit -m "feat(planning): add Consolidation tab with Valider/Passer/Tout reporter"
```

---

### Task 8: "Ajouter un cours" ad-hoc search

**Files:**
- Modify: `frontend/pages/planning.py`

**Interfaces:**
- Consumes: `consolidation.get_or_bootstrap_task` (Task 5); `data_store.cours` (search fallback, same pattern as `frontend/components/command_palette.py:40-53`).
- Produces: a search input inside the Consolidation tab that adds an ad-hoc card.

- [ ] **Step 1: Add the search helper and UI**

In `frontend/pages/planning.py`, inside the `if mode_state["value"] == "consolidation":` block from Task 7, add a search function and input, right before the `_render_consolidation(tasks)` definition:

```python
                    def _search_courses(query: str) -> list:
                        q = query.strip()
                        if len(q) < 2:
                            return []
                        try:
                            from backend.core.search.service import search_index
                            hits = search_index.search(q, limit=8, score_cutoff=50)
                            return [c for c, _ in hits]
                        except Exception:
                            q_low = q.lower()
                            return [
                                c for c in data_store.cours
                                if q_low in c.title.lower()
                                or (c.item_number and q_low in c.item_number)
                            ][:8]

                    async def _add_course_worked(course_id: str) -> None:
                        task = consolidation.get_or_bootstrap_task(course_id, context="college")
                        if task is None:
                            ui.notify("Cours introuvable ou jamais commencé.", type="warning")
                            return
                        dummy_card = ui.card()  # cible d'animation pour le dialogue existant
                        dummy_card.set_visibility(False)
                        open_session_feedback_dialog(task, dummy_card, _do_mark_consolidation)
```

- [ ] **Step 2: Wire the search input into `_render_consolidation`**

Modify `_render_consolidation` (from Task 7) to add the search bar above the task list. Replace:

```python
                    def _render_consolidation(tasks: list[ReviewTask]) -> None:
                        if not tasks:
```

with:

```python
                    def _render_consolidation(tasks: list[ReviewTask]) -> None:
                        with ui.row().classes("items-center gap-2 w-full mb-3"):
                            search_input = ui.input(
                                placeholder="Ajouter un cours travaillé aujourd'hui…"
                            ).props("outlined dense clearable").classes("flex-1")
                            results_container = ui.column().classes("w-full gap-1")

                            def _on_search(e):
                                results_container.clear()
                                hits = _search_courses(e.value or "")
                                with results_container:
                                    for c in hits:
                                        label = f"ITEM {c.item_number} – {c.title}" if c.item_number else c.title
                                        ui.button(
                                            label,
                                            on_click=lambda cid=c.id: _add_course_worked(cid),
                                        ).props("flat dense align=left size=sm color=slate").classes(
                                            "w-full justify-start normal-case"
                                        )

                            search_input.on("update:model-value", _on_search)

                        if not tasks:
```

- [ ] **Step 3: Manual verification**

1. On the Consolidation tab, type at least 2 characters of a course title in the new search field — matching courses appear as buttons below.
2. Click a result for a course that already has an active declared level or finished J30 — the validation dialog opens directly.
3. Submit with a confidence rating — verify (same DB check as Task 7 step 4) that a new `consolidation` row was created/advanced for that course, even though it wasn't in today's original list.
4. Try searching for a course that was never started (`mastery.score is None`) — clicking it should show the "Cours introuvable ou jamais commencé." warning instead of crashing.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/planning.py
git commit -m "feat(planning): add ad-hoc course search to Consolidation tab"
```

---

## Self-Review Notes

**Spec coverage:**
- Bug fix (declared items never generate a task) → Task 3 (`get_due_consolidation_tasks` includes declared-only items) + Task 7 manual verification step 2.
- SM-2 self-chaining "consolidation" type → Task 1 (`bootstrap_consolidation`, `mark_consolidation_done`, `get_consolidation_due_date`) + Task 2 (`ReviewType` extension).
- Unified global pool (declared OR finished-J30) → Task 3.
- Semester + mastery-level weighting → Task 4.
- Diversity cap per college → Task 4 (`select_daily`).
- UI tab → Task 7.
- Autoéval modulating frequency → Task 7 (`_do_mark_consolidation` passes `confidence` into `mark_consolidation_done`, reusing the existing dialog).
- "Passer"/"Tout reporter" → Task 7.
- "Ajouter un cours travaillé" → Task 8.
- `semestre_actuel` preference → Task 4.

**Deviation from the committed design doc (noted for the record):** the design doc mentions routing consolidation items through `PlannedSlot`/`SLOT_META` like the Journée/Semaine tabs. During planning this turned out to be the wrong fit — `PlannedSlot` drops the `task_id`/`theoretical_due_date` fields needed for Valider/Passer, and the Calendar-export use case `PlannedSlot` exists for doesn't apply to this tab. The plan instead renders `ReviewTask` objects directly with a dedicated card component. Functionally equivalent, simpler, and the spec's diversity/priority/UI-tab intent is unchanged.

**Placeholder scan:** no TBD/TODO; every step has complete code.

**Type consistency:** `ReviewTask.semestre` (Task 2) is populated at every `ReviewTask(...)` construction site added in this plan (Tasks 3, 5) — checked. `select_daily`'s signature (Task 4) matches the call in `plan_consolidation` (Task 6). `_consolidation_card`'s `on_validate`/`on_postpone` callback signatures (Task 7) match `_on_validate`/`_on_postpone`'s definitions in the same task.
