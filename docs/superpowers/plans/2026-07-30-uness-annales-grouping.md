# UNESS Annales Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group UNESS practice sessions (mDP1/DP1/DP2/SQI1-style sub-parts) under one "annale" row per source URL, sortable by matière/faculté/année/type, with each sub-part still played through the existing Node QCM reader.

**Architecture:** Add a `uness_annales` SQLite table (one row per source URL) and a nullable `annale_id` column on `ai_practice_sessions`. Extend the existing manual-import scan (`import_service.import_verified_directory`) to group files by `source_url` and require a one-time manual `type_annale` tag per new group before import. Rewrite the NiceGUI `/annales` list to read grouped rows, add a new `/annales/{annale_id}` detail page listing sub-parts, and extract the existing QCM session-card actions (open/correction/replay via the Node reader) into a shared component reused by both `qcm_cockpit.py` and the new detail page.

**Tech Stack:** Python 3.11+, SQLite (stdlib `sqlite3` via `backend/core/reviews/local_store.py`), NiceGUI, pytest. No changes to the Node/React QCM app.

## Global Constraints

- `source_url` is the sole identity of a partiel — a second collection of the same URL attaches to the existing `uness_annales` row, never creates a duplicate.
- `type_annale` is always tagged manually by the user at import time; never inferred automatically.
- No new UI for taking a test or viewing a correction — every "Ouvrir"/"Rejouer"/"Voir la correction" action must route through the existing `/qcm-app/?session=<id>` Node reader (falling back to the legacy NiceGUI dialogs only when the Node bundle isn't built, matching the existing `qcm_cockpit.py` behavior).
- Non-UNESS practice sessions are unaffected: `annale_id` stays `NULL` for them, and all existing QCM cockpit behavior must keep passing its current tests unchanged.

---

### Task 1: `uness_annales` table and local_store CRUD

**Files:**
- Modify: `backend/core/reviews/local_store.py:409` (add migration call), and append near `_migrate_ai_practice_v1` (currently ends at line ~434) a new `_migrate_uness_annales()` function.
- Modify: `backend/core/reviews/local_store.py` — add new functions near `create_ai_practice_session`/`get_ai_practice_sessions_history` (around line 1259-1454): `create_uness_annale`, `get_uness_annale_by_source_url`, `get_uness_annale`, `list_uness_annales`, `list_annale_sessions`, `set_session_annale_id`.
- Test: `tests/test_uness_annales_model.py`

**Interfaces:**
- Produces: `local_store.create_uness_annale(*, source_url: str, collected_at: str, faculte: str, niveau: str, annee: int | None, matiere: str, titre: str, type_annale: str) -> int` (returns new `uness_annales.id`, raises `sqlite3.IntegrityError` if `source_url` already exists — callers must check `get_uness_annale_by_source_url` first).
- Produces: `local_store.get_uness_annale_by_source_url(source_url: str) -> dict | None`
- Produces: `local_store.get_uness_annale(annale_id: int) -> dict | None`
- Produces: `local_store.list_uness_annales(*, query: str = "", matiere: str = "", faculte: str = "", annee: int | None = None, type_annale: str = "") -> list[dict]` — each row includes `total_parts`, `completed_parts`, `avg_score` (float or `None`).
- Produces: `local_store.list_annale_sessions(annale_id: int) -> list[dict]` — same row shape as `get_ai_practice_sessions_history` (includes a `status` key: `"pending"` or `"completed"`), filtered to that annale, ordered by `id ASC`.
- Produces: `local_store.set_session_annale_id(session_id: int, annale_id: int) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_uness_annales_model.py`:

```python
"""Tests for the uness_annales grouping table and its local_store CRUD."""

from __future__ import annotations

import sqlite3

import pytest

from backend.core.reviews import local_store
from backend.core.practice.models import (
    PracticeDifficulty,
    PracticeKind,
    PracticeSessionSpec,
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _make_session(course_title: str) -> int:
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        open_questions=0,
        closed_questions=1,
        course_title=course_title,
    )
    question = {
        "kind": "closed",
        "prompt": "Q ?",
        "choices": ["A", "B"],
        "answer": "A",
        "explanation": "Car A.",
    }
    return local_store.create_ai_practice_session(spec=spec, questions=[question], model="uness-verified-local")


def _complete_session(session_id: int, score_percent: float) -> None:
    question_id = local_store.get_ai_practice_session(session_id)[0]["id"]
    local_store.record_ai_practice_attempt(
        session_id=session_id,
        question_id=question_id,
        response="A",
        is_correct=True,
        score_percent=score_percent,
    )


def test_create_and_fetch_annale_by_source_url() -> None:
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=1",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="DFASM1_UE4S7_CT_Gériatrie_080224",
        type_annale="matiere",
    )

    fetched = local_store.get_uness_annale_by_source_url(
        "https://entrainement.uness.fr/annales/course/view.php?id=1"
    )

    assert fetched is not None
    assert fetched["id"] == annale_id
    assert fetched["matiere"] == "GÉRIATRIE"
    assert fetched["type_annale"] == "matiere"


def test_create_annale_rejects_duplicate_source_url() -> None:
    kwargs = dict(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=2",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="NEUROLOGIE",
        titre="DFASM1_UE_Neuro",
        type_annale="matiere",
    )
    local_store.create_uness_annale(**kwargs)

    with pytest.raises(sqlite3.IntegrityError):
        local_store.create_uness_annale(**kwargs)


def test_list_uness_annales_aggregates_sub_part_scores_and_supports_filters() -> None:
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=3",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="DFASM1_UE4S7_CT_Gériatrie_080224",
        type_annale="matiere",
    )
    session_a = _make_session("Gériatrie — mDP1")
    session_b = _make_session("Gériatrie — DP1")
    local_store.set_session_annale_id(session_a, annale_id)
    local_store.set_session_annale_id(session_b, annale_id)
    _complete_session(session_a, 80.0)

    matching = local_store.list_uness_annales(matiere="GÉRIATRIE")
    assert len(matching) == 1
    row = matching[0]
    assert row["id"] == annale_id
    assert row["total_parts"] == 2
    assert row["completed_parts"] == 1
    assert row["avg_score"] == pytest.approx(80.0)

    assert local_store.list_uness_annales(matiere="CARDIOLOGIE") == []
    assert local_store.list_uness_annales(faculte="Faculté de médecine de La Réunion") != []
    assert local_store.list_uness_annales(annee=2025) == []
    assert local_store.list_uness_annales(type_annale="concours_blanc") == []


def test_list_annale_sessions_returns_pending_and_completed_status() -> None:
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=4",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="DFASM1_UE4S7_CT_Gériatrie_080224",
        type_annale="matiere",
    )
    session_a = _make_session("Gériatrie — mDP1")
    session_b = _make_session("Gériatrie — DP1")
    local_store.set_session_annale_id(session_a, annale_id)
    local_store.set_session_annale_id(session_b, annale_id)
    _complete_session(session_a, 80.0)

    rows = local_store.list_annale_sessions(annale_id)

    assert [row["id"] for row in rows] == [session_a, session_b]
    assert rows[0]["status"] == "completed"
    assert rows[1]["status"] == "pending"


def test_ai_practice_session_defaults_to_null_annale_id() -> None:
    session_id = _make_session("QCM classique")
    assert local_store.get_ai_practice_session_summary(session_id)["annale_id"] is None
```

Note: if `local_store.complete_ai_practice_session(session_id, score_percent=...)` does not already exist under that exact name, search the file for the function that sets `completed_at`/`score_percent` on a session (used by the existing QCM completion flow) and use its real name/signature in the test instead — do not invent a signature.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uness_annales_model.py -v`
Expected: FAIL with `AttributeError: module 'backend.core.reviews.local_store' has no attribute 'create_uness_annale'`

- [ ] **Step 3: Add the migration**

In `backend/core/reviews/local_store.py`, change line 409 from:

```python
    _migrate_ai_practice_v1()
    logger.info(f"SQLite initialisé : {DB_PATH}")
```

to:

```python
    _migrate_ai_practice_v1()
    _migrate_uness_annales()
    logger.info(f"SQLite initialisé : {DB_PATH}")
```

Then add, right after the existing `_migrate_ai_practice_v1()` function body (after its closing line, currently ~434):

```python
def _migrate_uness_annales() -> None:
    """Ajoute la table de regroupement des annales UNESS et son lien depuis les sessions."""
    with _conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS uness_annales (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url   TEXT NOT NULL UNIQUE,
                collected_at TEXT NOT NULL,
                faculte      TEXT NOT NULL,
                niveau       TEXT NOT NULL,
                annee        INTEGER,
                matiere      TEXT NOT NULL DEFAULT '',
                titre        TEXT NOT NULL,
                type_annale  TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )"""
        )
        columns = {row[1] for row in con.execute("PRAGMA table_info(ai_practice_sessions)").fetchall()}
        if "annale_id" not in columns:
            con.execute(
                "ALTER TABLE ai_practice_sessions ADD COLUMN annale_id INTEGER "
                "REFERENCES uness_annales(id)"
            )
```

- [ ] **Step 4: Add the CRUD functions**

Add these functions right after `create_ai_practice_session` (after its closing `return session_id`, currently line 1259):

```python
def create_uness_annale(
    *,
    source_url: str,
    collected_at: str,
    faculte: str,
    niveau: str,
    annee: int | None,
    matiere: str,
    titre: str,
    type_annale: str,
) -> int:
    """Create one grouping row for a UNESS partiel. Raises sqlite3.IntegrityError on a duplicate source_url."""
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO uness_annales
               (source_url, collected_at, faculte, niveau, annee, matiere, titre, type_annale, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (source_url, collected_at, faculte, niveau, annee, matiere, titre, type_annale, _now()),
        )
        return int(cur.lastrowid)


def get_uness_annale_by_source_url(source_url: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM uness_annales WHERE source_url = ?", (source_url,)
        ).fetchone()
    return dict(row) if row else None


def get_uness_annale(annale_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM uness_annales WHERE id = ?", (annale_id,)).fetchone()
    return dict(row) if row else None


def list_uness_annales(
    *,
    query: str = "",
    matiere: str = "",
    faculte: str = "",
    annee: int | None = None,
    type_annale: str = "",
) -> list[dict]:
    """List annale groups with aggregated sub-part counts and average completed score."""
    clauses = []
    params: list = []
    if query.strip():
        pattern = f"%{query.strip().lower()}%"
        clauses.append("(LOWER(a.titre) LIKE ? OR LOWER(a.matiere) LIKE ?)")
        params.extend((pattern, pattern))
    if matiere:
        clauses.append("a.matiere = ?")
        params.append(matiere)
    if faculte:
        clauses.append("a.faculte = ?")
        params.append(faculte)
    if annee is not None:
        clauses.append("a.annee = ?")
        params.append(annee)
    if type_annale:
        clauses.append("a.type_annale = ?")
        params.append(type_annale)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn() as con:
        rows = con.execute(
            f"""SELECT a.*,
                       COUNT(s.id) AS total_parts,
                       COALESCE(SUM(CASE WHEN s.completed_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS completed_parts,
                       AVG(CASE WHEN s.completed_at IS NOT NULL THEN s.score_percent END) AS avg_score
                FROM uness_annales a
                LEFT JOIN ai_practice_sessions s ON s.annale_id = a.id
                {where}
                GROUP BY a.id
                ORDER BY a.created_at DESC, a.id DESC""",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def list_annale_sessions(annale_id: int) -> list[dict]:
    """Sub-part sessions for one annale, ordered as imported, with a pending/completed status."""
    with _conn() as con:
        rows = con.execute(
            """SELECT s.*,
                      CASE WHEN s.completed_at IS NULL THEN 'pending' ELSE 'completed' END AS status
               FROM ai_practice_sessions s
               WHERE s.annale_id = ?
               ORDER BY s.id ASC""",
            (annale_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_session_annale_id(session_id: int, annale_id: int) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE ai_practice_sessions SET annale_id = ? WHERE id = ?", (annale_id, session_id)
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uness_annales_model.py -v`
Expected: PASS (5 tests). `get_ai_practice_session_summary` already returns `annale_id` for free since it spreads `SELECT * FROM ai_practice_sessions` — no extra change needed there.

Also apply this same `_isolated_db` fixture shape (patch `DB_PATH` **and** `_DB` to `None`, close and re-null `_DB` on teardown) in every later task's tests — `local_store._conn()` caches a single module-level connection (`_DB`) the first time it's called and ignores `DB_PATH` afterward, so patching `DB_PATH` alone leaks state across tests that share a pytest process (confirmed while implementing this task: without the `_DB` reset, `test_list_uness_annales_aggregates_sub_part_scores_and_supports_filters` saw rows created by earlier tests in the same file).

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_uness_annales_model.py
git commit -m "feat: add uness_annales grouping table and CRUD"
```

---

### Task 2: Group manual imports by source_url and require a type tag

**Files:**
- Modify: `backend/core/uness/import_service.py:55-92` (replace `_exam_fingerprint` through the end of `import_verified_directory` — `import_uness_exam` itself, at lines 299-317, is called unchanged; the new `annale_id` link is set by the caller via `local_store.set_session_annale_id`, not inside it).
- Test: `tests/test_uness_import.py` (extend; check the existing file first for its fixture/import conventions before adding tests — follow its existing `client`/`import_dir` fixture pattern rather than inventing a new one).

**Interfaces:**
- Consumes: `local_store.get_uness_annale_by_source_url`, `local_store.create_uness_annale`, `local_store.set_session_annale_id` from Task 1.
- Produces: `import_service.import_verified_directory(tags: dict[str, str] | None = None) -> dict[str, Any]` — same `{"imported": [...], "skipped": [...], "errors": [...]}` shape as today, plus a new `"pending_tag": [...]` key listing groups needing a tag: `{"source_url": str, "faculte": str, "niveau": str, "annee": int | None, "matiere": str, "titre": str, "files": list[str]}`.

Deviation from the committed spec: the spec listed a separate `list_pending_annale_tags()` read-only preview function. Nothing in this plan's UI flow calls it standalone — Task 3 calls `import_verified_directory()` directly and reads `result["pending_tag"]`, which already surfaces the same groups without a duplicate detection pass. Dropped to avoid dead code; flag this to the user before/after implementing if they specifically wanted a preview-only entry point (e.g. for a future API route).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_uness_import.py` (adapt fixture names to whatever this file already uses for `import_dir`/writing exam JSON — inspect the top of the file first):

```python
def test_scan_reports_a_new_source_url_group_as_pending_tag(import_dir):
    """A never-seen source_url must not import until a type_annale is supplied."""
    payload_a = _exam_payload()
    payload_a["provenance"]["source_url"] = "https://entrainement.uness.fr/annales/course/view.php?id=99"
    payload_a["title"] = "UE Test — mDP1"
    payload_b = _exam_payload()
    payload_b["provenance"]["source_url"] = "https://entrainement.uness.fr/annales/course/view.php?id=99"
    payload_b["title"] = "UE Test — DP1"
    _write_exam(import_dir, "mdp1.json", payload_a)
    _write_exam(import_dir, "dp1.json", payload_b)

    result = import_service.import_verified_directory()

    assert result["imported"] == []
    assert len(result["pending_tag"]) == 1
    group = result["pending_tag"][0]
    assert group["source_url"] == "https://entrainement.uness.fr/annales/course/view.php?id=99"
    assert sorted(group["files"]) == ["dp1.json", "mdp1.json"]
    # Files stay in place, untouched, until tagged.
    assert (import_dir / "mdp1.json").exists()
    assert (import_dir / "dp1.json").exists()


def test_import_with_tag_creates_one_annale_for_both_sub_parts(import_dir):
    payload_a = _exam_payload()
    payload_a["provenance"]["source_url"] = "https://entrainement.uness.fr/annales/course/view.php?id=100"
    payload_a["title"] = "UE Test — mDP1"
    payload_b = _exam_payload()
    payload_b["provenance"]["source_url"] = "https://entrainement.uness.fr/annales/course/view.php?id=100"
    payload_b["title"] = "UE Test — DP1"
    _write_exam(import_dir, "mdp1.json", payload_a)
    _write_exam(import_dir, "dp1.json", payload_b)

    result = import_service.import_verified_directory(
        tags={"https://entrainement.uness.fr/annales/course/view.php?id=100": "matiere"}
    )

    assert result["pending_tag"] == []
    assert len(result["imported"]) == 2
    annale = local_store.get_uness_annale_by_source_url(
        "https://entrainement.uness.fr/annales/course/view.php?id=100"
    )
    assert annale is not None
    assert annale["type_annale"] == "matiere"
    session_ids = [entry["session_id"] for entry in result["imported"]]
    for session_id in session_ids:
        summary = local_store.get_ai_practice_session_summary(session_id)
        assert summary["annale_id"] == annale["id"]


def test_reimporting_same_source_url_attaches_to_existing_annale(import_dir):
    payload = _exam_payload()
    payload["provenance"]["source_url"] = "https://entrainement.uness.fr/annales/course/view.php?id=101"
    _write_exam(import_dir, "part1.json", payload)
    import_service.import_verified_directory(
        tags={"https://entrainement.uness.fr/annales/course/view.php?id=101": "vrai_concours"}
    )
    before = local_store.list_uness_annales()
    assert len(before) == 1

    payload_2 = _exam_payload()
    payload_2["provenance"]["source_url"] = "https://entrainement.uness.fr/annales/course/view.php?id=101"
    payload_2["title"] = payload_2["title"] + " (2)"
    for question in payload_2["questions"]:
        question["id"] = question["id"] + "-second"
    _write_exam(import_dir, "part2.json", payload_2)

    result = import_service.import_verified_directory()

    assert result["pending_tag"] == []
    assert len(result["imported"]) == 1
    after = local_store.list_uness_annales()
    assert len(after) == 1
    assert after[0]["id"] == before[0]["id"]
```

Check the top of `tests/test_uness_import.py` for the exact helper names (`_exam_payload`, `_write_exam`, `import_dir` fixture) already defined there — reuse them verbatim, don't redefine.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uness_import.py -k "pending_tag or one_annale or reimporting" -v`
Expected: FAIL — `import_verified_directory()` currently has no `"pending_tag"` key and no `tags` parameter.

- [ ] **Step 3: Implement grouping in `import_service.py`**

Replace lines 55-92 (`_exam_fingerprint` through the end of `import_verified_directory`) with:

```python
def _exam_fingerprint(exam: UnessExam) -> str:
    import hashlib
    raw = f"{exam.faculty}|{exam.level}|{exam.year}|{exam.title}|" + "|".join(q.id for q in exam.questions)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _annale_group_title(exam: UnessExam) -> str:
    """Recover the shared course title from convert_chatgpt_export.py's '{course} — {part}' convention."""
    return exam.title.rsplit(" — ", 1)[0] if " — " in exam.title else exam.title


def _group_files_by_source_url(paths: list[Path]) -> dict[str, list[tuple[Path, UnessExam]]]:
    groups: dict[str, list[tuple[Path, UnessExam]]] = {}
    for path in paths:
        exam = load_exam(path)
        source_url = str(exam.provenance.get("source_url", "")).strip()
        groups.setdefault(source_url, []).append((path, exam))
    return groups


def import_verified_directory(tags: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate and import all new verified outputs, grouped by partiel, without aborting the batch."""
    tags = tags or {}
    index_path = VERIFIED_DIR / ".imported.json"
    try:
        imported = set(json.loads(index_path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        imported = set()
    result: dict[str, Any] = {"imported": [], "skipped": [], "errors": [], "pending_tag": []}

    for source_url, entries in _group_files_by_source_url(scan_verified_exams()).items():
        annale = local_store.get_uness_annale_by_source_url(source_url) if source_url else None
        if annale is None and source_url:
            type_annale = tags.get(source_url)
            if type_annale is None:
                first_path, first_exam = entries[0]
                result["pending_tag"].append(
                    {
                        "source_url": source_url,
                        "faculte": first_exam.faculty,
                        "niveau": first_exam.level,
                        "annee": first_exam.year,
                        "matiere": str(first_exam.metadata.get("subject", "")),
                        "titre": _annale_group_title(first_exam),
                        "files": [path.name for path, _ in entries],
                    }
                )
                continue
            _, first_exam = entries[0]
            annale_id = local_store.create_uness_annale(
                source_url=source_url,
                collected_at=str(first_exam.provenance.get("collected_at", "")).strip(),
                faculte=first_exam.faculty,
                niveau=first_exam.level,
                annee=first_exam.year,
                matiere=str(first_exam.metadata.get("subject", "")),
                titre=_annale_group_title(first_exam),
                type_annale=type_annale,
            )
            annale = local_store.get_uness_annale(annale_id)

        for path, exam in entries:
            try:
                fingerprint = _exam_fingerprint(exam)
                if fingerprint in imported:
                    result["skipped"].append(path.name)
                    continue
                session_id = import_uness_exam(exam)
                if annale is not None:
                    local_store.set_session_annale_id(session_id, annale["id"])
                imported.add(fingerprint)
                result["imported"].append(
                    {"file": path.name, "session_id": session_id, "disagreements": count_disagreements(exam)}
                )
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                path.replace(ARCHIVE_DIR / path.name)
                collected_at = str(exam.provenance.get("collected_at", "")).strip()
                for candidate in TO_REVIEW_DIR.glob("*.json"):
                    try:
                        source = json.loads(candidate.read_text(encoding="utf-8")).get("source", {})
                    except (OSError, json.JSONDecodeError, AttributeError):
                        continue
                    if collected_at and source.get("collected_at") == collected_at:
                        candidate.replace(ARCHIVE_DIR / f"a_verifier-{candidate.name}")
            except (ValueError, OSError, PermissionError) as exc:
                result["errors"].append({"file": path.name, "error": str(exc)})

    index_path.write_text(json.dumps(sorted(imported), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
```

Note: `load_exam` is called twice per file across `list_pending_annale_tags`/`import_verified_directory` and `_group_files_by_source_url` — this is acceptable for the file counts this pipeline handles (a handful of files per scan), don't add a cache.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uness_import.py -v`
Expected: PASS, including all pre-existing tests in this file (grouping must not break the single-file/no-source_url path already tested there).

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/import_service.py tests/test_uness_import.py
git commit -m "feat: group UNESS imports by source_url and gate on a manual type tag"
```

---

### Task 3: Settings UI — tag pending annale groups before import

**Files:**
- Modify: `frontend/pages/settings_cockpit.py:203-221` (`_scan_verified`).
- Test: `tests/test_settings_uness_import.py` (extend; check existing fixtures first).

**Interfaces:**
- Consumes: `import_service.list_pending_annale_tags()`, `import_service.import_verified_directory(tags=...)` from Task 2.

**Type labels** (reused both here and in Task 5's filter dropdown — define once):

```python
ANNALE_TYPE_LABELS = {
    "matiere": "Matière",
    "concours_blanc": "Concours blanc",
    "vrai_concours": "Vrai concours",
    "edn_complet": "EDN complet",
}
```
Put this in `backend/core/uness/import_service.py` (module level, near the top constants at lines 21-29) so both the settings UI and the annales list page import it from one place.

**Note:** `tests/test_settings_uness_import.py` does not exist yet — this task creates it. This codebase does not spin up a real NiceGUI browser/client for cockpit pages; existing UI tests (e.g. `tests/test_qcm_cockpit_ui.py`) assert on `inspect.getsource(render_function)` for wiring/behavior that would otherwise require a live DOM. Follow that same convention here rather than inventing a rendering harness.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_uness_import.py`:

```python
"""Tests for the UNESS annale-tagging dialog wired into the settings cockpit scan."""

from __future__ import annotations

import inspect

from frontend.pages import settings_cockpit


def test_settings_cockpit_opens_a_tag_dialog_when_scan_reports_pending_groups() -> None:
    source = inspect.getsource(settings_cockpit.render_settings_cockpit)

    assert "_open_tag_dialog" in source
    assert "pending_tag" in source
    assert "ANNALE_TYPE_LABELS" in source


def test_settings_cockpit_passes_chosen_tags_back_into_the_scan() -> None:
    source = inspect.getsource(settings_cockpit.render_settings_cockpit)

    assert "import_verified_directory(tags=" in source


def test_settings_cockpit_lets_the_user_skip_tagging_for_now() -> None:
    source = inspect.getsource(settings_cockpit.render_settings_cockpit)

    assert "Ignorer pour l'instant" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings_uness_import.py -v`
Expected: FAIL — `_open_tag_dialog`/`pending_tag`/`ANNALE_TYPE_LABELS`/`tags=` don't appear in `render_settings_cockpit`'s current source.

- [ ] **Step 3: Implement the tag dialog**

Replace `_scan_verified` (lines 203-221) with:

```python
    def _finalize_scan(tags: dict[str, str] | None = None) -> None:
        result = import_service.import_verified_directory(tags=tags)
        pending = result["pending_tag"]
        if pending:
            _open_tag_dialog(pending)
            return
        imported_count = len(result["imported"])
        error_count = len(result["errors"])
        status.set_text(
            f"Scan terminé : {imported_count} importé(s), "
            f"{len(result['skipped'])} déjà présent(s), {error_count} erreur(s)."
        )
        status.style("color:var(--danger)" if error_count else "color:var(--success)")
        ui.notify(
            f"{imported_count} partiel(s) importé(s)" if not error_count else "Import terminé avec des erreurs",
            type="positive" if not error_count else "warning",
        )

    def _open_tag_dialog(pending: list[dict]) -> None:
        chosen: dict[str, str] = {}
        with ui.dialog() as dialog, ui.card().classes("w-[520px] max-w-[95vw] p-5"):
            ui.label("Nouvelles annales à qualifier").classes("text-lg font-semibold")
            ui.label(
                "Ces partiels n'ont jamais été importés : indique leur type avant de continuer."
            ).classes("text-xs text-slate-500 mb-3")
            for group in pending:
                source_url = group["source_url"]
                chosen[source_url] = "matiere"
                with ui.column().classes("w-full gap-1 mb-3"):
                    ui.label(group["titre"] or source_url).classes("font-semibold text-sm")
                    ui.label(
                        f"{group['matiere'] or '—'} · {group['faculte'] or '—'} · {group['annee'] or '—'} "
                        f"· {len(group['files'])} fichier(s)"
                    ).classes("text-xs text-slate-500")
                    ui.select(
                        import_service.ANNALE_TYPE_LABELS,
                        value="matiere",
                        on_change=lambda e, url=source_url: chosen.__setitem__(url, e.value),
                    ).props("outlined dense").classes("w-full")
            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("Ignorer pour l'instant", on_click=dialog.close).props("flat")
                ui.button(
                    "Valider",
                    on_click=lambda: (dialog.close(), _finalize_scan(tags=chosen)),
                ).props("unelevated color=purple")
        dialog.open()

    def _scan_verified() -> None:
        _finalize_scan()

    ui.button(
        "Scanner les JSON vérifiés",
        icon="fact_check",
        on_click=_scan_verified,
    ).props("unelevated color=purple size=sm rounded").classes("mt-3")
    ui.label("Échange local : UNESS/à_vérifier → UNESS/vérifiés → UNESS/archives").classes("se-uness-status")
```

Add `ANNALE_TYPE_LABELS` to `backend/core/uness/import_service.py` right after the directory constants (after line 29):

```python
ANNALE_TYPE_LABELS = {
    "matiere": "Matière",
    "concours_blanc": "Concours blanc",
    "vrai_concours": "Vrai concours",
    "edn_complet": "EDN complet",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings_uness_import.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/uness/import_service.py frontend/pages/settings_cockpit.py tests/test_settings_uness_import.py
git commit -m "feat: tag new UNESS annale groups with a type before importing"
```

---

### Task 4: Extract the shared session-action component

**Files:**
- Create: `frontend/components/practice_session_card.py`
- Modify: `frontend/pages/qcm_cockpit.py:121-126` (remove local `_open_node_qcm`, import the shared one) and `:501-520` (use the shared action renderer).
- Modify: `tests/test_qcm_cockpit_ui.py:21-25` — `test_qcm_cockpit_prefers_the_node_reader_when_built` currently inspects `qcm_cockpit._open_node_qcm`, which this task deletes.
- Test: `tests/test_practice_session_card.py`

**Interfaces:**
- Produces: `open_node_qcm(session_id: int) -> bool` (moved verbatim from `qcm_cockpit.py`).
- Produces: `render_session_actions(session: dict, *, on_resume, on_correction, on_replay) -> None` — renders the same action buttons as `qcm_cockpit.py`'s current lines 501-520, calling `on_resume(session_id)` / `on_correction(session_id)` / `on_replay(session_id)` depending on `session_action_keys(session)`.

**Note:** follow the same `inspect.getsource` convention already used in `tests/test_qcm_cockpit_ui.py::test_qcm_cockpit_prefers_the_node_reader_when_built` for this kind of check, rather than monkeypatching `pathlib.Path` instance methods (fragile — `Path` instances don't reliably support arbitrary attribute overrides).

- [ ] **Step 1: Write the failing test**

Create `tests/test_practice_session_card.py`:

```python
"""Tests for the shared practice-session action component."""

from __future__ import annotations

import inspect

from frontend.components import practice_session_card


def test_open_node_qcm_prefers_the_node_reader_when_built() -> None:
    source = inspect.getsource(practice_session_card.open_node_qcm)

    assert "qcm-app" in source
    assert "QCM_NODE_DIST.exists()" in source


def test_render_session_actions_dispatches_by_session_action_keys() -> None:
    source = inspect.getsource(practice_session_card.render_session_actions)

    assert "session_action_keys" in source
    assert "on_resume" in source
    assert "on_correction" in source
    assert "on_replay" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_practice_session_card.py -v`
Expected: FAIL — `frontend.components.practice_session_card` does not exist.

- [ ] **Step 3: Create the component**

Create `frontend/components/practice_session_card.py`:

```python
"""Shared session-action rendering reused by the QCM cockpit and the annale detail page."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from nicegui import ui

from frontend.components.qcm_replay import session_action_keys

QCM_NODE_DIST = Path(__file__).parents[2] / "qcm_app" / "dist" / "index.html"


def open_node_qcm(session_id: int) -> bool:
    """Open the approved Node reader when its production bundle is available."""
    if not QCM_NODE_DIST.exists():
        return False
    ui.navigate.to(f"/qcm-app/?session={int(session_id)}")
    return True


def render_session_actions(
    session: dict,
    *,
    on_resume: Callable[[int], None],
    on_correction: Callable[[int], None],
    on_replay: Callable[[int], None],
) -> None:
    """Render the resume/correction/replay buttons valid for this session's current state."""
    session_id = int(session["id"])
    with ui.row().classes("gap-2 flex-wrap mt-2"):
        actions = session_action_keys(session)
        if "resume" in actions:
            ui.button(
                "Reprendre",
                icon="play_arrow",
                on_click=lambda: on_resume(session_id),
            ).props("flat color=primary")
        if "correction" in actions:
            ui.button(
                "Voir la correction",
                icon="fact_check",
                on_click=lambda: on_correction(session_id),
            ).props("flat color=primary")
        if "replay" in actions:
            ui.button(
                "Rejouer",
                icon="replay",
                on_click=lambda: on_replay(session_id),
            ).props("flat")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_practice_session_card.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `qcm_cockpit.py` to the shared component**

In `frontend/pages/qcm_cockpit.py`:

1. Remove the local `_open_node_qcm` function (lines 121-126) and the now-unused `QCM_NODE_DIST` constant (line 51) — the shared component owns both now.
2. Add to the import block (after line 33's `practice_import_panel` import):
   ```python
   from frontend.components.practice_session_card import open_node_qcm, render_session_actions
   ```
3. In `_show_session` (line 386) and `_show_correction` (line 395), replace `_open_node_qcm(session_id)` with `open_node_qcm(session_id)` (both call sites).
4. Replace lines 501-520 (the `with ui.row().classes("gap-2 flex-wrap mt-2"):` block and everything inside it) with:
   ```python
        render_session_actions(
            selected,
            on_resume=_open_selected_session,
            on_correction=_open_selected_correction,
            on_replay=_replay_selected_session,
        )
   ```

- [ ] **Step 6: Update the now-broken existing test**

`tests/test_qcm_cockpit_ui.py:21-25` currently has:

```python
def test_qcm_cockpit_prefers_the_node_reader_when_built():
    source = inspect.getsource(qcm_cockpit._open_node_qcm)

    assert "qcm-app" in source
    assert "QCM_NODE_DIST.exists()" in source
```

`qcm_cockpit._open_node_qcm` no longer exists after Step 5. Replace this test with one confirming `qcm_cockpit.py` now delegates to the shared component. `_show_session` is a closure nested inside `render_qcm_cockpit`, not a module attribute, so `inspect.getsource` must target `render_qcm_cockpit` itself (same target the other tests in this file already use) and check for the delegating call:

```python
def test_qcm_cockpit_delegates_node_reader_check_to_the_shared_component():
    source = inspect.getsource(qcm_cockpit.render_qcm_cockpit)

    assert "open_node_qcm(session_id)" in source
```

- [ ] **Step 7: Run the existing QCM cockpit tests to verify nothing broke**

Run: `.venv/Scripts/python.exe -m pytest tests/test_qcm_cockpit_ui.py tests/test_practice_session_card.py -v`
Expected: PASS — no behavior change, pure extraction.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/practice_session_card.py frontend/pages/qcm_cockpit.py tests/test_practice_session_card.py tests/test_qcm_cockpit_ui.py
git commit -m "refactor: extract shared session-action rendering from the QCM cockpit"
```

---

### Task 5: Rewrite the grouped Annales list

**Files:**
- Modify: `frontend/pages/annales.py` (full rewrite).
- Test: `tests/test_annales_page.py`

**Interfaces:**
- Consumes: `local_store.list_uness_annales(...)` (Task 1), `import_service.ANNALE_TYPE_LABELS` (Task 3).
- Produces: nothing new consumed elsewhere — this is the top-level page.

- [ ] **Step 1: Write the failing test**

Create `tests/test_annales_page.py`:

```python
"""Tests for the grouped Annales list page's filtering logic."""

from __future__ import annotations

import pytest

from backend.core.reviews import local_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _seed_annale(source_url: str, matiere: str, faculte: str, annee: int, type_annale: str) -> int:
    return local_store.create_uness_annale(
        source_url=source_url,
        collected_at="2026-07-30T18:21:37+00:00",
        faculte=faculte,
        niveau="DFASM1",
        annee=annee,
        matiere=matiere,
        titre=f"Titre {matiere}",
        type_annale=type_annale,
    )


def test_annales_list_filters_by_matiere_faculte_annee_and_type() -> None:
    _seed_annale("url-1", "GÉRIATRIE", "Faculté de La Réunion", 2024, "matiere")
    _seed_annale("url-2", "NEUROLOGIE", "Faculté de Paris Saclay", 2025, "concours_blanc")

    from frontend.pages.annales import _filtered_annales

    assert len(_filtered_annales(matiere="GÉRIATRIE")) == 1
    assert len(_filtered_annales(faculte="Faculté de Paris Saclay")) == 1
    assert len(_filtered_annales(annee=2024)) == 1
    assert len(_filtered_annales(type_annale="concours_blanc")) == 1
    assert len(_filtered_annales()) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_annales_page.py -v`
Expected: FAIL — `frontend.pages.annales` has no `_filtered_annales`.

- [ ] **Step 3: Rewrite `frontend/pages/annales.py`**

```python
"""Liste groupée des annales UNESS importées, triable par matière/faculté/année/type."""

from __future__ import annotations

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness.import_service import ANNALE_TYPE_LABELS
from frontend.theme import frame


def _filtered_annales(
    *,
    query: str = "",
    matiere: str = "",
    faculte: str = "",
    annee: int | None = None,
    type_annale: str = "",
) -> list[dict]:
    return local_store.list_uness_annales(
        query=query, matiere=matiere, faculte=faculte, annee=annee, type_annale=type_annale
    )


def _distinct_values(rows: list[dict], key: str) -> list[str]:
    return sorted({str(row[key]) for row in rows if row.get(key)})


@ui.page("/annales")
def annales_page() -> None:
    with frame("Annales"):
        ui.label("Annales UNESS").classes("text-xl font-semibold")
        ui.label("Partiels importés, regroupés par annale").classes("text-sm text-slate-500")

        all_rows = _filtered_annales()
        if not all_rows:
            ui.label("Aucune annale importée pour le moment.").classes("text-sm text-slate-500 mt-6")
            return

        matieres = _distinct_values(all_rows, "matiere")
        facultes = _distinct_values(all_rows, "faculte")
        annees = sorted({int(row["annee"]) for row in all_rows if row.get("annee")})

        with ui.row().classes("w-full gap-3 mt-4 flex-wrap items-end"):
            search = ui.input(label="Recherche").props("outlined dense").classes("w-56")
            matiere_filter = ui.select(
                {"": "Toutes matières", **{m: m for m in matieres}}, value=""
            ).props("outlined dense").classes("w-52")
            faculte_filter = ui.select(
                {"": "Toutes facultés", **{f: f for f in facultes}}, value=""
            ).props("outlined dense").classes("w-56")
            annee_filter = ui.select(
                {"": "Toutes années", **{str(a): str(a) for a in annees}}, value=""
            ).props("outlined dense").classes("w-40")
            type_filter = ui.select(
                {"": "Tous types", **ANNALE_TYPE_LABELS}, value=""
            ).props("outlined dense").classes("w-44")

        rows_column = ui.column().classes("w-full gap-3 mt-4")

        def _render() -> None:
            rows_column.clear()
            rows = _filtered_annales(
                query=str(search.value or ""),
                matiere=str(matiere_filter.value or ""),
                faculte=str(faculte_filter.value or ""),
                annee=int(annee_filter.value) if annee_filter.value else None,
                type_annale=str(type_filter.value or ""),
            )
            with rows_column:
                if not rows:
                    ui.label("Aucune annale ne correspond à ces filtres.").classes("text-sm text-slate-500")
                    return
                for row in rows:
                    annale_id = int(row["id"])
                    total = int(row["total_parts"] or 0)
                    completed = int(row["completed_parts"] or 0)
                    avg_score = row.get("avg_score")
                    score_label = "—" if avg_score is None else f"{float(avg_score):.0f} %"
                    with ui.card().classes("w-full p-4"):
                        with ui.row().classes("w-full items-center justify-between gap-4"):
                            with ui.column().classes("gap-1"):
                                ui.label(str(row["titre"])).classes("font-semibold")
                                ui.label(
                                    f"{row['matiere'] or '—'} · {row['faculte'] or '—'} · "
                                    f"{row['annee'] or '—'} · {ANNALE_TYPE_LABELS.get(row['type_annale'], row['type_annale'])}"
                                ).classes("text-xs text-slate-500")
                                ui.label(
                                    f"{completed}/{total} sous-parties terminées · Score moyen : {score_label}"
                                ).classes("text-xs text-slate-500")
                            ui.button(
                                "Ouvrir",
                                icon="chevron_right",
                                on_click=lambda aid=annale_id: ui.navigate.to(f"/annales/{aid}"),
                            ).props("unelevated color=teal size=sm rounded")

        for control in (search, matiere_filter, faculte_filter, annee_filter, type_filter):
            control.on_value_change(lambda _e=None: _render())
        _render()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_annales_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/annales.py tests/test_annales_page.py
git commit -m "feat: rewrite Annales list grouped by partiel with matière/faculté/année/type filters"
```

---

### Task 6: Annale detail page

**Files:**
- Create: `frontend/pages/annale_detail.py`
- Test: `tests/test_annale_detail_page.py`

**Interfaces:**
- Consumes: `local_store.get_uness_annale(annale_id)`, `local_store.list_annale_sessions(annale_id)` (Task 1); `open_node_qcm`, `render_session_actions` (Task 4); `open_qcm_session`, `open_qcm_correction`, `replay_qcm_session` (existing, from `frontend/components/qcm_replay.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_annale_detail_page.py`:

```python
"""Tests for the annale detail page's data assembly (not full NiceGUI rendering)."""

from __future__ import annotations

import pytest

from backend.core.reviews import local_store
from backend.core.practice.models import PracticeDifficulty, PracticeKind, PracticeSessionSpec


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _make_session(course_title: str) -> int:
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind.QCM,
        total_questions=1,
        closed_questions=1,
        course_title=course_title,
    )
    question = {"kind": "closed", "prompt": "Q ?", "choices": ["A", "B"], "answer": "A", "explanation": "Car A."}
    return local_store.create_ai_practice_session(spec=spec, questions=[question], model="uness-verified-local")


def test_load_annale_detail_returns_annale_and_ordered_sub_parts() -> None:
    from frontend.pages.annale_detail import _load_annale_detail

    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=200",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="Faculté de médecine de La Réunion",
        niveau="DFASM1",
        annee=2024,
        matiere="GÉRIATRIE",
        titre="Gériatrie 2024",
        type_annale="matiere",
    )
    session_a = _make_session("Gériatrie — mDP1")
    session_b = _make_session("Gériatrie — DP1")
    local_store.set_session_annale_id(session_a, annale_id)
    local_store.set_session_annale_id(session_b, annale_id)

    annale, sessions = _load_annale_detail(annale_id)

    assert annale["titre"] == "Gériatrie 2024"
    assert [row["id"] for row in sessions] == [session_a, session_b]


def test_load_annale_detail_returns_none_for_unknown_id() -> None:
    from frontend.pages.annale_detail import _load_annale_detail

    annale, sessions = _load_annale_detail(999999)

    assert annale is None
    assert sessions == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_annale_detail_page.py -v`
Expected: FAIL — `frontend.pages.annale_detail` does not exist.

- [ ] **Step 3: Create `frontend/pages/annale_detail.py`**

```python
"""Détail d'un partiel UNESS : ses sous-parties, jouées via le lecteur Node existant."""

from __future__ import annotations

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness.import_service import ANNALE_TYPE_LABELS
from frontend.components.practice_session_card import open_node_qcm, render_session_actions
from frontend.components.qcm_replay import open_qcm_correction, open_qcm_session, replay_qcm_session
from frontend.theme import frame


def _load_annale_detail(annale_id: int) -> tuple[dict | None, list[dict]]:
    annale = local_store.get_uness_annale(annale_id)
    if annale is None:
        return None, []
    return annale, local_store.list_annale_sessions(annale_id)


@ui.page("/annales/{annale_id}")
def annale_detail_page(annale_id: str) -> None:
    with frame("Annale"):
        try:
            parsed_id = int(annale_id)
        except ValueError:
            ui.label("Identifiant d'annale invalide.").classes("text-sm text-negative")
            return

        annale, sessions = _load_annale_detail(parsed_id)
        if annale is None:
            ui.label("Annale introuvable.").classes("text-sm text-negative")
            ui.button("Retour", icon="arrow_back", on_click=lambda: ui.navigate.to("/annales")).props("flat")
            return

        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-1"):
                ui.label(str(annale["titre"])).classes("text-xl font-semibold")
                ui.label(
                    f"{annale['matiere'] or '—'} · {annale['faculte'] or '—'} · {annale['annee'] or '—'} · "
                    f"{ANNALE_TYPE_LABELS.get(annale['type_annale'], annale['type_annale'])}"
                ).classes("text-sm text-slate-500")
            ui.button("Retour", icon="arrow_back", on_click=lambda: ui.navigate.to("/annales")).props("flat")

        def _show_session(session_id: int) -> None:
            if open_node_qcm(session_id):
                return
            open_qcm_session(session_id, on_complete=lambda _sid: None, on_back=lambda: None)

        def _show_correction(session_id: int) -> None:
            if open_node_qcm(session_id):
                return
            open_qcm_correction(session_id, on_back=lambda: None, on_replay=lambda _sid: None)

        def _replay(session_id: int) -> None:
            replay_qcm_session(session_id)

        with ui.column().classes("w-full gap-3 mt-6"):
            if not sessions:
                ui.label("Aucune sous-partie importée pour cette annale.").classes("text-sm text-slate-500")
            for session in sessions:
                score = session.get("score_percent")
                score_label = "—" if score is None else f"{float(score):.0f} %"
                status_label = "Terminée" if session["status"] == "completed" else "À faire"
                with ui.card().classes("w-full p-4"):
                    ui.label(str(session.get("course_title") or "Sous-partie")).classes("font-semibold")
                    ui.label(f"{session['total_questions']} questions · {status_label} · Score : {score_label}").classes(
                        "text-xs text-slate-500"
                    )
                    render_session_actions(
                        session,
                        on_resume=_show_session,
                        on_correction=_show_correction,
                        on_replay=_replay,
                    )
```

`open_qcm_session`/`open_qcm_correction` already open their own `ui.dialog()` internally (`frontend/components/qcm_replay.py:404`), so no extra dialog wrapper is needed here — the fallback simply delegates to them directly, exactly like `qcm_cockpit.py`'s `_show_session`/`_show_correction` do for the same legacy path.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_annale_detail_page.py -v`
Expected: PASS.

- [ ] **Step 5: Register the page**

Check `main.py` (or wherever `frontend/pages/annales.py` is currently imported so its `@ui.page` decorator registers) and add an identical import line for `frontend.pages.annale_detail` right next to it, so the new `@ui.page("/annales/{annale_id}")` route registers at startup.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/annale_detail.py tests/test_annale_detail_page.py main.py
git commit -m "feat: add annale detail page listing sub-parts via the Node QCM reader"
```

---

### Task 7: Backfill existing sessions

**Files:**
- Create: `scripts/uness/backfill_annales.py`
- Test: `tests/test_backfill_annales.py`

**Interfaces:**
- Consumes: `local_store.get_uness_annale_by_source_url`, `local_store.create_uness_annale`, `local_store.set_session_annale_id`, `local_store.list_uness_annales` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `tests/test_backfill_annales.py`:

```python
"""Tests for the one-off backfill of pre-existing UNESS sessions into uness_annales."""

from __future__ import annotations

import json

import pytest

from backend.core.reviews import local_store
from backend.core.practice.models import PracticeKind, PracticeSessionSpec


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _make_legacy_uness_session(course_title: str, source_url: str) -> int:
    """Simulate a session imported before annale_id existed: metadata only, no annale_id set."""
    spec = PracticeSessionSpec(practice_kind=PracticeKind.QCM, total_questions=1, closed_questions=1, course_title=course_title)
    import_metadata = {
        "uness": {
            "provenance": {"source_url": source_url, "collected_at": "2026-07-30T18:21:37+00:00"},
            "exam": {"faculty": "Faculté de médecine de La Réunion", "level": "DFASM1", "year": 2024, "title": course_title},
        }
    }
    question = {
        "kind": "closed",
        "prompt": "Q ?",
        "choices": ["A", "B"],
        "answer": "A",
        "explanation": "Car A.",
        "import_metadata": import_metadata,
    }
    return local_store.create_ai_practice_session(spec=spec, questions=[question], model="uness-verified-local")


def test_backfill_groups_legacy_sessions_by_source_url_and_prompts_once_per_group(monkeypatch) -> None:
    from scripts.uness.backfill_annales import backfill_annales

    session_a = _make_legacy_uness_session("Gériatrie — mDP1", "https://entrainement.uness.fr/annales/course/view.php?id=29135")
    session_b = _make_legacy_uness_session("Gériatrie — DP1", "https://entrainement.uness.fr/annales/course/view.php?id=29135")

    prompts = iter(["matiere"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(prompts))

    backfill_annales()

    annale = local_store.get_uness_annale_by_source_url(
        "https://entrainement.uness.fr/annales/course/view.php?id=29135"
    )
    assert annale is not None
    assert annale["type_annale"] == "matiere"
    assert local_store.get_ai_practice_session_summary(session_a)["annale_id"] == annale["id"]
    assert local_store.get_ai_practice_session_summary(session_b)["annale_id"] == annale["id"]


def test_backfill_skips_sessions_that_already_have_an_annale_id(monkeypatch) -> None:
    from scripts.uness.backfill_annales import backfill_annales

    session_id = _make_legacy_uness_session("Neuro — DP1", "https://entrainement.uness.fr/annales/course/view.php?id=1")
    annale_id = local_store.create_uness_annale(
        source_url="https://entrainement.uness.fr/annales/course/view.php?id=1",
        collected_at="2026-07-30T18:21:37+00:00",
        faculte="F",
        niveau="DFASM1",
        annee=2024,
        matiere="NEURO",
        titre="Neuro",
        type_annale="vrai_concours",
    )
    local_store.set_session_annale_id(session_id, annale_id)

    monkeypatch.setattr("builtins.input", lambda _prompt: (_ for _ in ()).throw(AssertionError("should not prompt")))

    backfill_annales()  # must not raise, must not prompt

    assert len(local_store.list_uness_annales()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_backfill_annales.py -v`
Expected: FAIL — `scripts.uness.backfill_annales` does not exist.

- [ ] **Step 3: Implement the backfill script**

Create `scripts/uness/backfill_annales.py`:

```python
"""One-off backfill: attach pre-existing UNESS sessions (imported before annale_id existed) to uness_annales."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.core.reviews import local_store  # noqa: E402
from backend.core.uness.import_service import ANNALE_TYPE_LABELS  # noqa: E402


def _session_uness_metadata(session_id: int) -> dict | None:
    """Read the faculty/level/year/source_url buried in the session's first question metadata."""
    session = local_store.get_ai_practice_session(session_id)
    for question in session:
        raw = question.get("import_metadata_json") or question.get("import_metadata")
        metadata = json.loads(raw) if isinstance(raw, str) else (raw or {})
        uness = metadata.get("uness")
        if uness:
            return uness
    return None


def backfill_annales() -> None:
    sessions_without_annale = [
        row
        for row in local_store.get_ai_practice_sessions_history(limit=10_000)
        if str(row.get("model", "")).startswith("uness-") and row.get("annale_id") is None
    ]
    groups: dict[str, list[int]] = {}
    metadata_by_source: dict[str, dict] = {}
    for row in sessions_without_annale:
        uness = _session_uness_metadata(int(row["id"]))
        if not uness:
            continue
        source_url = str(uness.get("provenance", {}).get("source_url", "")).strip()
        if not source_url:
            continue
        groups.setdefault(source_url, []).append(int(row["id"]))
        metadata_by_source.setdefault(source_url, uness)

    for source_url, session_ids in groups.items():
        annale = local_store.get_uness_annale_by_source_url(source_url)
        if annale is None:
            uness = metadata_by_source[source_url]
            exam = uness.get("exam", {})
            print(f"\nAnnale sans type : {exam.get('title', source_url)} ({source_url})")
            for key, label in ANNALE_TYPE_LABELS.items():
                print(f"  {key} : {label}")
            type_annale = input("Type d'annale (matiere/concours_blanc/vrai_concours/edn_complet) : ").strip()
            annale_id = local_store.create_uness_annale(
                source_url=source_url,
                collected_at=str(uness.get("provenance", {}).get("collected_at", "")).strip(),
                faculte=str(exam.get("faculty", "")),
                niveau=str(exam.get("level", "")),
                annee=exam.get("year"),
                matiere=str(exam.get("title", "")),
                titre=str(exam.get("title", "")),
                type_annale=type_annale,
            )
            annale = local_store.get_uness_annale(annale_id)
        for session_id in session_ids:
            local_store.set_session_annale_id(session_id, annale["id"])


if __name__ == "__main__":
    backfill_annales()
```

Note: `_session_uness_metadata` assumes `get_ai_practice_session(session_id)` returns question dicts with either `import_metadata_json` (raw column) or `import_metadata` (already parsed) — check the real function in `local_store.py` before finalizing and adjust the key name to whatever it actually returns; don't guess blindly, grep for `import_metadata` in `local_store.py`'s `get_ai_practice_session` function first.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_backfill_annales.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/uness/backfill_annales.py tests/test_backfill_annales.py
git commit -m "feat: add one-off backfill for pre-existing UNESS sessions into uness_annales"
```

---

### Task 8: Run the backfill and verify end-to-end

**Files:** none (execution only).

- [ ] **Step 1: Run the full test suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass, including every file touched above.

- [ ] **Step 2: Run the backfill against the real local database**

Run: `.venv/Scripts/python.exe scripts/uness/backfill_annales.py`
Expected: prompts once for the Gériatrie 2024 partiel (sessions id 10-13 from the 2026-07-30 import); answer `matiere`.

- [ ] **Step 3: Manually verify in the browser**

Start the app (`python main.py`), open `/annales`: confirm exactly one row for "DFASM1_UE4S7_CT_Gériatrie_080224" (not four), with matière/faculté/année/type filters visible. Filter by the matière and faculté seen, confirm the row still shows. Click it, confirm `/annales/{id}` lists mDP1/DP1/DP2/SQI1 with status/score, and clicking "Ouvrir" on a pending one or "Voir la correction"/"Rejouer" on a completed one navigates to `/qcm-app/?session=<id>`.

- [ ] **Step 4: Inspect the diff for anything unintended**

Run: `git status` and `git diff --stat HEAD~7` (7 commits back to before Task 1) — confirm only the files listed across Tasks 1-7 changed, nothing stray.

- [ ] **Step 5: Final commit if manual verification required fixes**

If Step 3 revealed an issue, fix it, re-run the relevant task's tests, then:
```bash
git add -A -- backend frontend scripts tests
git commit -m "fix: address manual verification findings for annale grouping"
```
