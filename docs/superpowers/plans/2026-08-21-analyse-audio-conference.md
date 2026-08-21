# Analyse Batch audio des dossiers UNESS post-conférence — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dès qu'une conférence DFASM1 liée à son dossier UNESS a un audio uploadé, soumettre
automatiquement un job Gemini Batch (audio + snapshot du dossier) qui propose, par question,
l'item EDN manquant, le rang A/B manquant et un avis de validité de la correction officielle
éclairé par l'audio — sans jamais écraser une donnée officielle UNESS.

**Architecture:** un worker de fond (même cadence que `rank_job_runner.py`, appelé depuis
`background.py`) scanne les conférences éligibles, crée un job `conference_analysis_jobs`,
uploade l'audio via la Gemini File API, soumet un job `batchGenerateContent`, puis poll et
applique le résultat validé dans trois destinations séparées : `ai_practice_question_items`
(item), `ai_practice_questions.import_metadata_json` via `_apply_rank_metadata` (rang), et deux
nouvelles tables append-only `conference_analyses`/`conference_question_analysis` (validité
éclairée par l'audio — jamais fusionnée avec `verdict_ia`).

**Tech Stack:** Python 3.11, `requests` (REST brut, pas de SDK Gemini), SQLite (`sqlite3`),
NiceGUI, Loguru, pytest.

## Global Constraints

- Aucune donnée officielle UNESS (`reponse_uness`, item officiel, rang officiel) n'est jamais
  écrasée par un résultat Gemini.
- L'analyse conférence utilise exclusivement l'API Gemini Batch (`batchGenerateContent` /
  `/v1beta/batches`), jamais `generateContent` synchrone.
- Le déclenchement est automatique dès que `conferences.audio_path` ET
  `conferences.uness_session_id` sont renseignés — pas de bouton manuel pour le déclenchement
  initial ; un bouton « Relancer » n'est visible que sur un job `failed`/`needs_admin`.
- La validité de la correction éclairée par l'audio est une annotation consultable uniquement :
  elle ne modifie jamais automatiquement `UnessProposition.statut` ni `reponse_finale`.
- L'audio et son contenu ne doivent jamais apparaître dans les logs applicatifs ni dans
  `ai_usage_logs` — seuls chemin local et hash sont conservés.
- Une resoumission est idempotente : `idempotency_key = sha256(conference_id:uness_session_id:audio_hash:model_id:prompt_version)`
  bloque toute resoumission tant qu'un job avec la même clé existe déjà.
- La boucle de fond ne doit jamais bloquer le thread NiceGUI (`asyncio.to_thread`, comme
  `_run_pending_uness_rank_jobs` dans `backend/core/background.py`).
- Suivre les conventions déjà en place dans `backend/core/reviews/local_store.py` : chaque
  fonction mutante fait `with _conn() as con: con.execute(...); row = con.execute("SELECT ...").fetchone(); return dict(row)`, migrations en `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN` guardé par `PRAGMA table_info`.

---

### Task 1 : Schéma SQLite et CRUD de base

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_local_store_conference_analysis.py`

**Interfaces:**
- Produces: `set_conference_audio(conference_id: int, *, audio_path: str, audio_hash: str) -> dict`,
  `create_conference_analysis_job(*, conference_id: int, uness_session_id: int, model_id: str, idempotency_key: str, prompt_version: str) -> dict`,
  `get_conference_analysis_job(job_id: int) -> dict | None`,
  `list_conferences_eligible_for_analysis() -> list[dict]`,
  `claim_pending_conference_analysis_jobs(*, limit: int = 5, worker_id: str = "conference-analysis-worker") -> list[dict]`,
  `mark_conference_analysis_job_submitted(job_id: int, *, provider_job_name: str, next_poll_at: str) -> dict`,
  `list_conference_analysis_jobs_due_for_poll(*, limit: int = 10) -> list[dict]`,
  `mark_conference_analysis_job_polled(job_id: int, *, next_poll_at: str) -> dict`,
  `complete_conference_analysis_job(job_id: int, *, status: str, result_path: str) -> dict`,
  `fail_conference_analysis_job(job_id: int, *, error: str) -> dict`,
  `record_conference_analysis(*, conference_id: int, uness_session_id: int, batch_job_id: int, model_id: str, prompt_version: str, summary_text: str) -> dict`,
  `record_conference_question_analysis(*, conference_analysis_id: int, question_id: int, verdict: str, confidence: float | None, rationale: str, transcript_excerpt: str) -> None`,
  `apply_conference_item_classification(question_id: int, item_number: str, *, confidence: float, rationale: str) -> bool`,
  `apply_conference_rank_result(question_id: int, *, rank: str, confidence: float, evidence: list[str], rationale: str) -> bool`.

- [ ] **Step 1: Write the failing test for schema + audio setter**

```python
# tests/test_local_store_conference_analysis.py
import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "conf-analysis.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _make_conference(local_store):
    return local_store.upsert_conference(
        date=__import__("datetime").date(2026, 9, 1),
        theme_raw="Cardiologie",
        match_status="matched",
        college_name="Cardiologie",
        source_file="planning.xlsx",
    )


def test_set_conference_audio_stores_path_and_hash(isolated_db):
    _, conf = _make_conference(isolated_db)
    updated = isolated_db.set_conference_audio(
        conf["id"], audio_path="data/conferences/audio/1.mp3", audio_hash="abc123"
    )
    assert updated["audio_path"] == "data/conferences/audio/1.mp3"
    assert updated["audio_hash"] == "abc123"
    assert updated["audio_uploaded_at"]


def test_create_conference_analysis_job_is_idempotent(isolated_db):
    _, conf = _make_conference(isolated_db)
    job1 = isolated_db.create_conference_analysis_job(
        conference_id=conf["id"], uness_session_id=42, model_id="gemini-flash",
        idempotency_key="key-1", prompt_version="v1",
    )
    job2 = isolated_db.create_conference_analysis_job(
        conference_id=conf["id"], uness_session_id=42, model_id="gemini-flash",
        idempotency_key="key-1", prompt_version="v1",
    )
    assert job1["id"] == job2["id"]
    assert job1["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_store_conference_analysis.py -v`
Expected: FAIL — `AttributeError: module 'local_store' has no attribute 'set_conference_audio'`
(la table `conferences` n'a pas encore de colonne `audio_path`).

- [ ] **Step 3: Add migration for `conferences` audio columns and the three new tables**

In `backend/core/reviews/local_store.py`, add a new migration function right after
`_migrate_conferences_table` (around line 6746), following the exact `PRAGMA table_info` +
guarded `ALTER TABLE` idiom already used for `uness_annales` (lines 1253–1257) and the exact
job-table shape already used for `uness_rank_inference_jobs` (lines 2666–2716):

```python
def _migrate_conference_analysis() -> None:
    with _conn() as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(conferences)").fetchall()}
        for name, ddl in [
            ("audio_path", "ALTER TABLE conferences ADD COLUMN audio_path TEXT NOT NULL DEFAULT ''"),
            ("audio_uploaded_at", "ALTER TABLE conferences ADD COLUMN audio_uploaded_at TEXT NOT NULL DEFAULT ''"),
            ("audio_hash", "ALTER TABLE conferences ADD COLUMN audio_hash TEXT NOT NULL DEFAULT ''"),
        ]:
            if name not in columns:
                con.execute(ddl)

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS conference_analysis_jobs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                conference_id       INTEGER NOT NULL REFERENCES conferences(id) ON DELETE CASCADE,
                uness_session_id    INTEGER NOT NULL REFERENCES uness_annales(id) ON DELETE CASCADE,
                status              TEXT NOT NULL DEFAULT 'pending',
                model_id            TEXT NOT NULL DEFAULT '',
                provider_job_name   TEXT NOT NULL DEFAULT '',
                idempotency_key     TEXT NOT NULL UNIQUE,
                prompt_version      TEXT NOT NULL DEFAULT '',
                audio_file_uri      TEXT NOT NULL DEFAULT '',
                attempts            INTEGER NOT NULL DEFAULT 0,
                locked_at           TEXT,
                worker_id           TEXT,
                submitted_at        TEXT,
                completed_at        TEXT,
                last_polled_at      TEXT,
                next_poll_at        TEXT NOT NULL,
                result_path         TEXT NOT NULL DEFAULT '',
                last_error          TEXT NOT NULL DEFAULT '',
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conference_analysis_jobs_status
                ON conference_analysis_jobs(status, next_poll_at);
            CREATE INDEX IF NOT EXISTS idx_conference_analysis_jobs_conf
                ON conference_analysis_jobs(conference_id);

            CREATE TABLE IF NOT EXISTS conference_analyses (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                conference_id       INTEGER NOT NULL REFERENCES conferences(id) ON DELETE CASCADE,
                uness_session_id    INTEGER NOT NULL REFERENCES uness_annales(id) ON DELETE CASCADE,
                batch_job_id        INTEGER NOT NULL REFERENCES conference_analysis_jobs(id) ON DELETE CASCADE,
                model_id            TEXT NOT NULL DEFAULT '',
                prompt_version      TEXT NOT NULL DEFAULT '',
                summary_text        TEXT NOT NULL DEFAULT '',
                created_at          TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conference_analyses_conf
                ON conference_analyses(conference_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS conference_question_analysis (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                conference_analysis_id  INTEGER NOT NULL REFERENCES conference_analyses(id) ON DELETE CASCADE,
                question_id             INTEGER NOT NULL REFERENCES ai_practice_questions(id) ON DELETE CASCADE,
                verdict                 TEXT NOT NULL,
                confidence              REAL,
                rationale               TEXT NOT NULL DEFAULT '',
                transcript_excerpt      TEXT NOT NULL DEFAULT '',
                created_at              TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conference_question_analysis_question
                ON conference_question_analysis(question_id);
            CREATE INDEX IF NOT EXISTS idx_conference_question_analysis_analysis
                ON conference_question_analysis(conference_analysis_id);
            """
        )
```

Register it in `init_db()` right after the `_migrate_conferences_table()` call (around line 659):

```python
    _migrate_conferences_table()
    _migrate_conference_analysis()
```

- [ ] **Step 4: Add `set_conference_audio` and the job CRUD functions**

Add after `set_conference_uness_session` (around line 6902), following the exact
mutate-then-select shape used throughout the file:

```python
def set_conference_audio(conference_id: int, *, audio_path: str, audio_hash: str) -> dict:
    """Enregistre l'audio uploadé pour une conférence déjà liée à un dossier UNESS."""
    now = _now()
    with _conn() as con:
        con.execute(
            """UPDATE conferences
               SET audio_path = ?, audio_hash = ?, audio_uploaded_at = ?, updated_at = ?
               WHERE id = ?""",
            (str(audio_path), str(audio_hash), now, now, int(conference_id)),
        )
        row = con.execute("SELECT * FROM conferences WHERE id = ?", (int(conference_id),)).fetchone()
    if row is None:
        raise ValueError(f"Conférence introuvable: {conference_id}")
    return dict(row)


def list_conferences_eligible_for_analysis() -> list[dict]:
    """Conférences avec audio + dossier liés, sans job actif pour le hash audio courant."""
    with _conn() as con:
        rows = con.execute(
            """SELECT c.* FROM conferences c
               WHERE c.uness_session_id IS NOT NULL AND c.audio_hash != ''
                 AND NOT EXISTS (
                     SELECT 1 FROM conference_analysis_jobs j
                     WHERE j.conference_id = c.id
                       AND j.status IN ('pending', 'submitted', 'running', 'succeeded')
                       AND j.idempotency_key LIKE c.audio_hash || ':%'
                 )"""
        ).fetchall()
        return [dict(row) for row in rows]


def create_conference_analysis_job(
    *, conference_id: int, uness_session_id: int, model_id: str, idempotency_key: str, prompt_version: str,
) -> dict:
    now = _now()
    with _conn() as con:
        con.execute(
            """INSERT OR IGNORE INTO conference_analysis_jobs
               (conference_id, uness_session_id, model_id, idempotency_key, prompt_version,
                next_poll_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (int(conference_id), int(uness_session_id), str(model_id), str(idempotency_key),
             str(prompt_version), now, now, now),
        )
        row = con.execute(
            "SELECT * FROM conference_analysis_jobs WHERE idempotency_key = ?", (str(idempotency_key),)
        ).fetchone()
    return dict(row)


def get_conference_analysis_job(job_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM conference_analysis_jobs WHERE id = ?", (int(job_id),)
        ).fetchone()
    return dict(row) if row is not None else None


def claim_pending_conference_analysis_jobs(
    *, limit: int = 5, worker_id: str = "conference-analysis-worker", lease_seconds: int = 900,
) -> list[dict]:
    now = _now()
    expired = (
        datetime.datetime.now().astimezone() - datetime.timedelta(seconds=max(1, lease_seconds))
    ).isoformat(timespec="seconds")
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM conference_analysis_jobs
               WHERE status = 'pending' AND (locked_at IS NULL OR locked_at <= ?)
               ORDER BY created_at ASC LIMIT ?""",
            (expired, max(1, int(limit))),
        ).fetchall()
        claimed_ids = [int(row["id"]) for row in rows]
        for job_id in claimed_ids:
            con.execute(
                "UPDATE conference_analysis_jobs SET locked_at = ?, worker_id = ?, updated_at = ? WHERE id = ?",
                (now, worker_id, now, job_id),
            )
    return [get_conference_analysis_job(job_id) for job_id in claimed_ids]


def mark_conference_analysis_job_submitted(job_id: int, *, provider_job_name: str, next_poll_at: str) -> dict:
    now = _now()
    with _conn() as con:
        con.execute(
            """UPDATE conference_analysis_jobs
               SET status = 'submitted', provider_job_name = ?, submitted_at = ?,
                   next_poll_at = ?, locked_at = NULL, worker_id = NULL, updated_at = ?
               WHERE id = ?""",
            (str(provider_job_name), now, str(next_poll_at), now, int(job_id)),
        )
    return get_conference_analysis_job(job_id)


def list_conference_analysis_jobs_due_for_poll(*, limit: int = 10) -> list[dict]:
    now = _now()
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM conference_analysis_jobs
               WHERE status IN ('submitted', 'running') AND next_poll_at <= ?
               ORDER BY next_poll_at ASC LIMIT ?""",
            (now, max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_conference_analysis_job_polled(job_id: int, *, next_poll_at: str) -> dict:
    now = _now()
    with _conn() as con:
        con.execute(
            """UPDATE conference_analysis_jobs
               SET status = 'running', last_polled_at = ?, next_poll_at = ?, updated_at = ?
               WHERE id = ?""",
            (now, str(next_poll_at), now, int(job_id)),
        )
    return get_conference_analysis_job(job_id)


def complete_conference_analysis_job(job_id: int, *, status: str, result_path: str) -> dict:
    if status not in {"succeeded", "partial", "needs_admin"}:
        raise ValueError("Statut de complétion invalide")
    now = _now()
    with _conn() as con:
        con.execute(
            """UPDATE conference_analysis_jobs
               SET status = ?, result_path = ?, completed_at = ?, updated_at = ?
               WHERE id = ?""",
            (status, str(result_path), now, now, int(job_id)),
        )
    return get_conference_analysis_job(job_id)


def fail_conference_analysis_job(job_id: int, *, error: str) -> dict:
    now = _now()
    with _conn() as con:
        con.execute(
            """UPDATE conference_analysis_jobs
               SET status = 'failed', last_error = ?, completed_at = ?, updated_at = ?
               WHERE id = ?""",
            (str(error or "")[:500], now, now, int(job_id)),
        )
    return get_conference_analysis_job(job_id)
```

- [ ] **Step 5: Add analysis/question-analysis recorders and result appliers**

```python
def record_conference_analysis(
    *, conference_id: int, uness_session_id: int, batch_job_id: int,
    model_id: str, prompt_version: str, summary_text: str,
) -> dict:
    now = _now()
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO conference_analyses
               (conference_id, uness_session_id, batch_job_id, model_id, prompt_version, summary_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (int(conference_id), int(uness_session_id), int(batch_job_id),
             str(model_id), str(prompt_version), str(summary_text), now),
        )
        row = con.execute(
            "SELECT * FROM conference_analyses WHERE id = ?", (int(cur.lastrowid),)
        ).fetchone()
    return dict(row)


def record_conference_question_analysis(
    *, conference_analysis_id: int, question_id: int, verdict: str,
    confidence: float | None, rationale: str, transcript_excerpt: str,
) -> None:
    if verdict not in {"concordant", "desaccord", "incertain"}:
        raise ValueError(f"Verdict de conférence inconnu: {verdict}")
    with _conn() as con:
        con.execute(
            """INSERT INTO conference_question_analysis
               (conference_analysis_id, question_id, verdict, confidence, rationale, transcript_excerpt, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (int(conference_analysis_id), int(question_id), verdict, confidence,
             str(rationale or "")[:500], str(transcript_excerpt or "")[:1000], _now()),
        )


def apply_conference_item_classification(
    question_id: int, item_number: str, *, confidence: float, rationale: str,
) -> bool:
    """N'ajoute l'item que si la question n'en a aucun (officiel ou déjà classifié)."""
    existing = get_ai_practice_question_items(question_id)
    if existing:
        return False
    with _conn() as con:
        con.execute(
            """INSERT OR IGNORE INTO ai_practice_question_items
               (question_id, item_number, confidence, source, classifier_version)
               VALUES (?, ?, ?, 'gemini_conference', 'conference-analysis-v1')""",
            (int(question_id), str(item_number).strip(), float(confidence)),
        )
    return True


def apply_conference_rank_result(
    question_id: int, *, rank: str, confidence: float, evidence: list[str], rationale: str,
) -> bool:
    """Réutilise _apply_rank_metadata : lève déjà si un rang officiel existe."""
    with _conn() as con:
        try:
            _apply_rank_metadata(
                con, question_id=question_id, rank=rank, source="gemini_conference",
                confidence=confidence, evidence=evidence, rationale=rationale,
            )
        except ValueError:
            return False
    return True
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_local_store_conference_analysis.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_local_store_conference_analysis.py
git commit -m "feat(conferences): schema and CRUD for post-conference audio analysis jobs"
```

---

### Task 2 : Upload et validation de l'audio

**Files:**
- Create: `backend/core/conferences/audio_service.py`
- Test: `tests/test_conference_audio_service.py`

**Interfaces:**
- Consumes: `local_store.set_conference_audio(conference_id, *, audio_path, audio_hash) -> dict`
  (Task 1), `local_store.get_conference(conference_id) -> dict | None` (existing).
- Produces: `save_conference_audio(conference_id: int, *, filename: str, content: bytes) -> dict`
  raising `ValueError` on invalid input; `AUDIO_DIR: Path`; `MAX_AUDIO_BYTES: int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conference_audio_service.py
import datetime

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "audio-service.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


@pytest.fixture
def conference(isolated_db):
    _, conf = isolated_db.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="Cardiologie", match_status="matched",
        college_name="Cardiologie", source_file="planning.xlsx",
    )
    return conf


def test_save_conference_audio_writes_file_and_hash(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")

    result = audio_service.save_conference_audio(
        conference["id"], filename="correction.mp3", content=b"fake-mp3-bytes",
    )

    assert result["audio_path"].endswith(".mp3")
    saved = tmp_path / "audio" / f"{conference['id']}.mp3"
    assert saved.read_bytes() == b"fake-mp3-bytes"
    assert result["audio_hash"] == audio_service.hash_bytes(b"fake-mp3-bytes")


def test_save_conference_audio_rejects_unsupported_format(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")

    with pytest.raises(ValueError, match="format"):
        audio_service.save_conference_audio(
            conference["id"], filename="correction.pdf", content=b"not-audio",
        )


def test_save_conference_audio_rejects_empty_file(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")

    with pytest.raises(ValueError, match="vide"):
        audio_service.save_conference_audio(conference["id"], filename="correction.mp3", content=b"")


def test_save_conference_audio_rejects_too_large_file(tmp_path, monkeypatch, conference):
    from backend.core.conferences import audio_service
    monkeypatch.setattr(audio_service, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(audio_service, "MAX_AUDIO_BYTES", 10)

    with pytest.raises(ValueError, match="volumineux"):
        audio_service.save_conference_audio(
            conference["id"], filename="correction.mp3", content=b"0123456789ABCDEF",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conference_audio_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.conferences.audio_service'`

- [ ] **Step 3: Write the implementation**

```python
# backend/core/conferences/audio_service.py
"""Upload et validation de l'enregistrement audio d'une conférence."""
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.core.reviews import local_store

AUDIO_DIR = Path("data/conferences/audio")
MAX_AUDIO_BYTES = 300 * 1024 * 1024  # 300 Mo
_ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".wav"}


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_conference_audio(conference_id: int, *, filename: str, content: bytes) -> dict:
    """Valide, sauvegarde sur disque et enregistre l'audio d'une conférence.

    Lève ValueError (rien n'est écrit) si le format est inconnu, le fichier
    vide ou trop volumineux.
    """
    if local_store.get_conference(conference_id) is None:
        raise ValueError(f"Conférence introuvable: {conference_id}")

    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Format audio non supporté: {suffix or '(aucun)'}")
    if not content:
        raise ValueError("Le fichier audio est vide")
    if len(content) > MAX_AUDIO_BYTES:
        raise ValueError(f"Fichier audio trop volumineux (> {MAX_AUDIO_BYTES // (1024*1024)} Mo)")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    target = AUDIO_DIR / f"{conference_id}{suffix}"
    target.write_bytes(content)

    audio_hash = hash_bytes(content)
    return local_store.set_conference_audio(
        conference_id, audio_path=str(target), audio_hash=audio_hash,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_conference_audio_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/conferences/audio_service.py tests/test_conference_audio_service.py
git commit -m "feat(conferences): validate and store uploaded conference audio"
```

---

### Task 3 : Client REST Gemini File API + Batch API

**Files:**
- Create: `backend/core/ai/batch_client.py`
- Test: `tests/test_conference_batch_client.py`

**Interfaces:**
- Consumes: `settings.gemini_api_key`, `settings.gemini_timeout_seconds` (existing,
  `backend/config/settings.py`), `_redact_provider_secrets` pattern from `gemini_client.py`.
- Produces: `upload_audio_file(path: Path, *, api_key: str | None = None, timeout: float | None = None) -> UploadedFile`,
  `create_batch_job(model_id: str, request_body: dict, *, api_key=None, timeout=None) -> BatchJobHandle`,
  `get_batch_job(job_name: str, *, api_key=None, timeout=None) -> BatchJobStatus`,
  `download_batch_results(responses_file_name: str, *, api_key=None, timeout=None) -> bytes`.
  Dataclasses `UploadedFile(uri: str, name: str, mime_type: str)`,
  `BatchJobHandle(name: str)`,
  `BatchJobStatus(name: str, done: bool, state: str, inlined_responses: list | None, responses_file_name: str | None, error: str | None)`.

This module talks to the real Gemini REST endpoints documented at
`https://ai.google.dev/gemini-api/docs/batch-mode` and
`https://ai.google.dev/gemini-api/docs/generate-content/file-input-methods`:
resumable upload (`POST /upload/v1beta/files` then `PUT` to the returned
`X-Goog-Upload-URL`), `POST /v1beta/models/{model}:batchGenerateContent`,
`GET /v1beta/{job_name}` (long-running-operation shape: `done`, `metadata.state`,
`response.inlinedResponses` / `response.responsesFile`, `error`), and
`GET /download/v1beta/{responses_file_name}:download?alt=media`.

- [ ] **Step 1: Write the failing tests (all network calls mocked via `requests`)**

```python
# tests/test_conference_batch_client.py
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


def test_upload_audio_file_does_resumable_upload_and_returns_uri(tmp_path):
    from backend.core.ai import batch_client

    audio = tmp_path / "correction.mp3"
    audio.write_bytes(b"fake-audio-bytes")

    start_response = Mock(headers={"X-Goog-Upload-URL": "https://upload.example/session-1"})
    start_response.raise_for_status = Mock()
    finalize_response = Mock()
    finalize_response.raise_for_status = Mock()
    finalize_response.json.return_value = {
        "file": {"uri": "files/abc123", "name": "files/abc123", "mimeType": "audio/mpeg"}
    }

    with patch("backend.core.ai.batch_client.requests.post", side_effect=[start_response, finalize_response]) as mock_post:
        result = batch_client.upload_audio_file(audio, api_key="fake-key", timeout=30)

    assert result.uri == "files/abc123"
    assert result.mime_type == "audio/mpeg"
    start_call, finalize_call = mock_post.call_args_list
    assert start_call.kwargs["headers"]["X-Goog-Upload-Command"] == "start"
    assert finalize_call.args[0] == "https://upload.example/session-1"


def test_create_batch_job_posts_batch_generate_content(tmp_path):
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {"name": "batches/job-1"}

    with patch("backend.core.ai.batch_client.requests.post", return_value=response) as mock_post:
        handle = batch_client.create_batch_job(
            "gemini-flash", {"batch": {"display_name": "conf-1"}}, api_key="fake-key", timeout=30,
        )

    assert handle.name == "batches/job-1"
    assert "gemini-flash:batchGenerateContent" in mock_post.call_args.args[0]


def test_get_batch_job_parses_succeeded_state_with_inlined_responses():
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "name": "batches/job-1",
        "done": True,
        "metadata": {"state": "JOB_STATE_SUCCEEDED"},
        "response": {"inlinedResponses": [{"response": {"text": "ok"}}]},
    }

    with patch("backend.core.ai.batch_client.requests.get", return_value=response):
        status = batch_client.get_batch_job("batches/job-1", api_key="fake-key", timeout=30)

    assert status.done is True
    assert status.state == "JOB_STATE_SUCCEEDED"
    assert status.inlined_responses == [{"response": {"text": "ok"}}]
    assert status.responses_file_name is None


def test_get_batch_job_parses_failed_state():
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "name": "batches/job-1", "done": True,
        "metadata": {"state": "JOB_STATE_FAILED"},
        "error": {"message": "quota exceeded"},
    }

    with patch("backend.core.ai.batch_client.requests.get", return_value=response):
        status = batch_client.get_batch_job("batches/job-1", api_key="fake-key", timeout=30)

    assert status.state == "JOB_STATE_FAILED"
    assert status.error == "quota exceeded"


def test_download_batch_results_returns_bytes():
    from backend.core.ai import batch_client

    response = Mock()
    response.raise_for_status = Mock()
    response.content = b'{"key": "q1", "response": {}}\n'

    with patch("backend.core.ai.batch_client.requests.get", return_value=response) as mock_get:
        content = batch_client.download_batch_results("files/results-1", api_key="fake-key", timeout=30)

    assert content == b'{"key": "q1", "response": {}}\n'
    assert "files/results-1:download" in mock_get.call_args.args[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conference_batch_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.ai.batch_client'`

- [ ] **Step 3: Write the implementation**

```python
# backend/core/ai/batch_client.py
"""Transport HTTP minimal vers la Gemini File API et Batch API (REST brut)."""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

import requests

from backend.config.settings import settings
from backend.core.ai.gemini_client import GeminiClientError, _redact_provider_secrets

_UPLOAD_BASE = "https://generativelanguage.googleapis.com/upload/v1beta/files"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DOWNLOAD_BASE = "https://generativelanguage.googleapis.com/download/v1beta"


@dataclass(frozen=True)
class UploadedFile:
    uri: str
    name: str
    mime_type: str


@dataclass(frozen=True)
class BatchJobHandle:
    name: str


@dataclass(frozen=True)
class BatchJobStatus:
    name: str
    done: bool
    state: str
    inlined_responses: list | None
    responses_file_name: str | None
    error: str | None


def _resolve(api_key: str | None, timeout: float | None) -> tuple[str, float]:
    key = settings.gemini_api_key if api_key is None else api_key
    if not key:
        raise GeminiClientError("Aucune clé Gemini configurée")
    return key, (settings.gemini_timeout_seconds if timeout is None else timeout)


def upload_audio_file(path: Path, *, api_key: str | None = None, timeout: float | None = None) -> UploadedFile:
    """Upload resumable d'un fichier audio via la Gemini File API."""
    key, effective_timeout = _resolve(api_key, timeout)
    content = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"

    try:
        start = requests.post(
            _UPLOAD_BASE,
            headers={
                "x-goog-api-key": key,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(content)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": path.name}},
            timeout=effective_timeout,
        )
        start.raise_for_status()
        upload_url = start.headers.get("X-Goog-Upload-URL") or start.headers.get("x-goog-upload-url")
        if not upload_url:
            raise GeminiClientError("Gemini n'a pas renvoyé d'URL d'upload")

        finalize = requests.post(
            upload_url,
            headers={
                "x-goog-api-key": key,
                "Content-Length": str(len(content)),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            data=content,
            timeout=effective_timeout,
        )
        finalize.raise_for_status()
        payload = finalize.json()["file"]
    except GeminiClientError:
        raise
    except Exception as exc:
        raise GeminiClientError(f"Upload audio Gemini échoué : {_redact_provider_secrets(str(exc))}") from exc

    return UploadedFile(uri=payload["uri"], name=payload["name"], mime_type=payload.get("mimeType", mime_type))


def create_batch_job(
    model_id: str, request_body: dict, *, api_key: str | None = None, timeout: float | None = None,
) -> BatchJobHandle:
    key, effective_timeout = _resolve(api_key, timeout)
    url = f"{_API_BASE}/models/{model_id}:batchGenerateContent"
    try:
        response = requests.post(
            url, headers={"x-goog-api-key": key}, json=request_body, timeout=effective_timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise GeminiClientError(f"Création du job Batch échouée : {_redact_provider_secrets(str(exc))}") from exc
    return BatchJobHandle(name=data["name"])


def get_batch_job(job_name: str, *, api_key: str | None = None, timeout: float | None = None) -> BatchJobStatus:
    key, effective_timeout = _resolve(api_key, timeout)
    url = f"{_API_BASE}/{job_name}"
    try:
        response = requests.get(url, headers={"x-goog-api-key": key}, timeout=effective_timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise GeminiClientError(f"Consultation du job Batch échouée : {_redact_provider_secrets(str(exc))}") from exc

    metadata = data.get("metadata") or {}
    response_payload = data.get("response") or {}
    error_payload = data.get("error") or {}
    return BatchJobStatus(
        name=data.get("name", job_name),
        done=bool(data.get("done", False)),
        state=str(metadata.get("state", "")),
        inlined_responses=response_payload.get("inlinedResponses"),
        responses_file_name=response_payload.get("responsesFile"),
        error=error_payload.get("message"),
    )


def download_batch_results(
    responses_file_name: str, *, api_key: str | None = None, timeout: float | None = None,
) -> bytes:
    key, effective_timeout = _resolve(api_key, timeout)
    url = f"{_DOWNLOAD_BASE}/{responses_file_name}:download?alt=media"
    try:
        response = requests.get(url, headers={"x-goog-api-key": key}, timeout=effective_timeout)
        response.raise_for_status()
    except Exception as exc:
        raise GeminiClientError(f"Téléchargement des résultats Batch échoué : {_redact_provider_secrets(str(exc))}") from exc
    return response.content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_conference_batch_client.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/ai/batch_client.py tests/test_conference_batch_client.py
git commit -m "feat(ai): add Gemini File API and Batch API REST client"
```

---

### Task 4 : Construction du prompt et validation du contrat de réponse

**Files:**
- Create: `backend/core/conferences/analysis_prompt.py`
- Test: `tests/test_conference_analysis_prompt.py`

**Interfaces:**
- Consumes: `backend.core.uness.item_classifier.candidate_items_for_college(college_label: str) -> list[dict]`
  (existing), `local_store.get_lisa_oic_for_item(item_number, course_ids) -> list[dict]` (existing),
  `backend.core.practice.rank_service.INFERENCE_THRESHOLD` (existing, `= 0.85`).
- Produces: `ConferenceQuestionSnapshot` (dataclass), `build_conference_analysis_request(*, audio_file: UploadedFile, college_label: str, questions: list[ConferenceQuestionSnapshot]) -> dict` (request body for `create_batch_job`), `ConferenceQuestionResult` (dataclass), `ConferenceAnalysisResult` (dataclass with `summary: str`, `questions: dict[str, ConferenceQuestionResult]`), `parse_conference_analysis_response(raw_text: str, *, known_question_ids: set[str], candidate_items: dict[str, set[str]]) -> ConferenceAnalysisResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conference_analysis_prompt.py
import json

from backend.core.conferences.analysis_prompt import (
    ConferenceQuestionSnapshot,
    build_conference_analysis_request,
    parse_conference_analysis_response,
)
from backend.core.ai.batch_client import UploadedFile


def test_build_conference_analysis_request_includes_audio_and_snapshot():
    audio = UploadedFile(uri="files/abc", name="files/abc", mime_type="audio/mpeg")
    questions = [
        ConferenceQuestionSnapshot(
            question_id="q1", enonce="Quel est le traitement de première intention ?",
            official_answer="Bêtabloquant", official_item="", official_rank="",
        )
    ]
    body = build_conference_analysis_request(
        audio_file=audio, college_label="Cardiologie", questions=questions,
    )
    contents = body["batch"]["input_config"]["requests"]["requests"][0]["request"]["contents"]
    parts = contents[0]["parts"]
    assert {"file_data": {"mime_type": "audio/mpeg", "file_uri": "files/abc"}} in parts
    assert any("q1" in part.get("text", "") for part in parts)


def test_parse_conference_analysis_response_keeps_only_candidate_items():
    raw = json.dumps({
        "summary": "Cours sur l'insuffisance cardiaque.",
        "questions": [
            {
                "question_id": "q1", "item_numbers": ["ITEM 232"], "item_confidence": 0.9,
                "item_rationale": "cité explicitement",
                "rank": "A", "rank_confidence": 0.9, "rank_rationale": "cours de rang A",
                "verdict": "concordant", "verdict_confidence": 0.8,
                "verdict_rationale": "le professeur confirme la réponse",
                "transcript_excerpt": "00:12:30 - ...",
            },
            {
                "question_id": "q2", "item_numbers": ["ITEM 999"], "item_confidence": 0.95,
                "item_rationale": "hors référentiel",
                "rank": "B", "rank_confidence": 0.9, "rank_rationale": "",
                "verdict": "incertain", "verdict_confidence": 0.4, "verdict_rationale": "",
                "transcript_excerpt": "",
            },
        ],
    })
    result = parse_conference_analysis_response(
        raw,
        known_question_ids={"q1", "q2"},
        candidate_items={"q1": {"ITEM 232", "ITEM 233"}, "q2": {"ITEM 1"}},
    )
    assert result.summary == "Cours sur l'insuffisance cardiaque."
    assert result.questions["q1"].item_number == "ITEM 232"
    # q2 : item proposé hors liste candidate -> rejeté, jamais inventé
    assert result.questions["q2"].item_number == ""
    assert result.questions["q2"].item_needs_admin is True


def test_parse_conference_analysis_response_ignores_unknown_question_ids():
    raw = json.dumps({"summary": "", "questions": [
        {"question_id": "ghost", "item_numbers": [], "item_confidence": 0, "item_rationale": "",
         "rank": "", "rank_confidence": 0, "rank_rationale": "",
         "verdict": "incertain", "verdict_confidence": 0, "verdict_rationale": "", "transcript_excerpt": ""},
    ]})
    result = parse_conference_analysis_response(raw, known_question_ids={"q1"}, candidate_items={"q1": set()})
    assert result.questions == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conference_analysis_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.conferences.analysis_prompt'`

- [ ] **Step 3: Write the implementation**

```python
# backend/core/conferences/analysis_prompt.py
"""Construction du prompt Batch et validation du contrat de réponse pour
l'analyse audio-informée d'un dossier UNESS post-conférence."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from loguru import logger

from backend.core.ai.batch_client import UploadedFile
from backend.core.practice.rank_service import INFERENCE_THRESHOLD

PROMPT_VERSION = "conference-analysis-v1"
_VALID_VERDICTS = {"concordant", "desaccord", "incertain"}


@dataclass(frozen=True)
class ConferenceQuestionSnapshot:
    question_id: str
    enonce: str
    official_answer: str
    official_item: str
    official_rank: str


@dataclass(frozen=True)
class ConferenceQuestionResult:
    item_number: str = ""
    item_confidence: float = 0.0
    item_rationale: str = ""
    item_needs_admin: bool = False
    rank: str = ""
    rank_confidence: float = 0.0
    rank_rationale: str = ""
    rank_needs_admin: bool = False
    verdict: str = "incertain"
    verdict_confidence: float = 0.0
    verdict_rationale: str = ""
    transcript_excerpt: str = ""


@dataclass(frozen=True)
class ConferenceAnalysisResult:
    summary: str = ""
    questions: dict[str, ConferenceQuestionResult] = field(default_factory=dict)


_INSTRUCTIONS = """Tu analyses l'enregistrement audio d'une conférence de médecine et le
dossier UNESS travaillé le même jour. Pour chaque question listée ci-dessous, réponds en
te basant sur ce que dit le professeur dans l'audio :
- item_numbers : uniquement des numéros pris dans la liste "items candidats" fournie pour
  la question ; jamais un numéro hors de cette liste ; laisse vide si absent officiellement
  ET non identifiable avec certitude.
- rank : "A", "B" ou vide si non identifiable.
- verdict : "concordant" si l'audio confirme la correction officielle, "desaccord" si
  l'audio la contredit, "incertain" sinon.
Ne modifie jamais un item ou un rang déjà marqué "officiel" ci-dessous — propose seulement
pour les champs marqués manquants. Réponds en JSON strict :
{"summary": "...", "questions": [{"question_id": "...", "item_numbers": [...],
"item_confidence": 0-1, "item_rationale": "...", "rank": "A|B|", "rank_confidence": 0-1,
"rank_rationale": "...", "verdict": "concordant|desaccord|incertain", "verdict_confidence": 0-1,
"verdict_rationale": "...", "transcript_excerpt": "..."}]}"""


def build_conference_analysis_request(
    *, audio_file: UploadedFile, college_label: str, questions: list[ConferenceQuestionSnapshot],
) -> dict:
    lines = [_INSTRUCTIONS, f"\nCollège : {college_label}\n"]
    for question in questions:
        lines.append(
            f"- question_id={question.question_id} | énoncé: {question.enonce} | "
            f"réponse officielle: {question.official_answer or '(absente)'} | "
            f"item officiel: {question.official_item or '(absent)'} | "
            f"rang officiel: {question.official_rank or '(absent)'}"
        )
    text_prompt = "\n".join(lines)

    parts = [
        {"file_data": {"mime_type": audio_file.mime_type, "file_uri": audio_file.uri}},
        {"text": text_prompt},
    ]
    return {
        "batch": {
            "display_name": f"conference-analysis-{college_label}",
            "input_config": {
                "requests": {
                    "requests": [
                        {
                            "request": {
                                "contents": [{"parts": parts}],
                                "generation_config": {"responseMimeType": "application/json"},
                            },
                            "metadata": {"key": "conference-analysis"},
                        }
                    ]
                }
            },
        }
    }


def parse_conference_analysis_response(
    raw_text: str, *, known_question_ids: set[str], candidate_items: dict[str, set[str]],
) -> ConferenceAnalysisResult:
    try:
        payload = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError) as exc:
        logger.warning(f"Réponse d'analyse conférence invalide (JSON) : {exc}")
        return ConferenceAnalysisResult()

    summary = str(payload.get("summary") or "").strip()
    results: dict[str, ConferenceQuestionResult] = {}

    for entry in payload.get("questions") or []:
        question_id = str(entry.get("question_id") or "").strip()
        if question_id not in known_question_ids:
            continue

        allowed_items = candidate_items.get(question_id, set())
        proposed_items = [str(n).strip() for n in (entry.get("item_numbers") or [])]
        kept_item = next((n for n in proposed_items if n in allowed_items), "")
        item_needs_admin = bool(proposed_items) and not kept_item

        rank = str(entry.get("rank") or "").strip().upper()
        rank_confidence = float(entry.get("rank_confidence") or 0.0)
        rank_needs_admin = rank in {"A", "B"} and rank_confidence < INFERENCE_THRESHOLD
        if rank not in {"A", "B"}:
            rank = ""

        verdict = str(entry.get("verdict") or "incertain").strip().lower()
        if verdict not in _VALID_VERDICTS:
            verdict = "incertain"

        results[question_id] = ConferenceQuestionResult(
            item_number=kept_item,
            item_confidence=float(entry.get("item_confidence") or 0.0),
            item_rationale=str(entry.get("item_rationale") or "").strip(),
            item_needs_admin=item_needs_admin,
            rank=rank,
            rank_confidence=rank_confidence,
            rank_rationale=str(entry.get("rank_rationale") or "").strip(),
            rank_needs_admin=rank_needs_admin,
            verdict=verdict,
            verdict_confidence=float(entry.get("verdict_confidence") or 0.0),
            verdict_rationale=str(entry.get("verdict_rationale") or "").strip(),
            transcript_excerpt=str(entry.get("transcript_excerpt") or "").strip(),
        )

    return ConferenceAnalysisResult(summary=summary, questions=results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_conference_analysis_prompt.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/conferences/analysis_prompt.py tests/test_conference_analysis_prompt.py
git commit -m "feat(conferences): build Batch prompt and validate its response contract"
```

---

### Task 5 : Worker de fond (scan, soumission, polling, application)

**Files:**
- Create: `backend/core/conferences/analysis_job_runner.py`
- Test: `tests/test_conference_analysis_job_runner.py`

**Interfaces:**
- Consumes: everything produced by Tasks 1, 3, 4, plus `local_store.get_conference(id)`,
  `local_store.get_uness_annale(id)` (existing — used by `link_conference_to_uness_session`),
  and needs read access to a dossier's questions; add one more `local_store` helper this task
  introduces itself (`list_uness_annale_questions_for_analysis`, see Step 3).
- Produces: `scan_and_queue_conference_analyses() -> int`,
  `submit_pending_conference_analysis_jobs(*, limit=5, client=None) -> dict[str, int]`,
  `poll_running_conference_analysis_jobs(*, limit=10, client=None) -> dict[str, int]`,
  `run_conference_analysis_cycle(*, client=None) -> dict[str, int]`.

- [ ] **Step 1: Add the missing local_store read helper first (small, standalone)**

`ai_practice_questions` rows for a dossier are reachable via
`ai_practice_sessions.annale_id` (used already in `scan_uness_rank_jobs`, local_store.py line
~2815-2824). Add this helper right after `scan_uness_rank_jobs` (around line 2865, after its
closing):

```python
def list_uness_annale_questions_for_analysis(annale_id: int) -> list[dict]:
    """Questions d'un dossier UNESS avec leur snapshot officiel, pour l'analyse conférence."""
    with _conn() as con:
        rows = con.execute(
            """SELECT q.id AS question_id, q.prompt, q.answer, q.item_number,
                      q.import_metadata_json
               FROM ai_practice_questions q
               JOIN ai_practice_session_questions sq ON sq.question_id = q.id
               JOIN ai_practice_sessions s ON s.id = sq.session_id
               WHERE s.annale_id = ?""",
            (int(annale_id),),
        ).fetchall()
    results = []
    for row in rows:
        try:
            metadata = json.loads(row["import_metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        question_meta = (metadata.get("uness") or {}).get("question") or {}
        results.append({
            "question_id": row["question_id"],
            "prompt": row["prompt"],
            "answer": row["answer"],
            "official_item": row["item_number"] or "",
            "official_rank": str(question_meta.get("rank") or ""),
        })
    return results
```

Write and run its test first:

```python
# add to tests/test_local_store_conference_analysis.py
def test_list_uness_annale_questions_for_analysis(isolated_db):
    now = isolated_db._now()
    with isolated_db._conn() as con:
        con.execute(
            "INSERT INTO ai_practice_questions (id, practice_kind, question_kind, position, prompt, answer, explanation, question_hash, created_at) "
            "VALUES (1, 'QCM', 'CLOSED', 1, 'Enonce', 'Reponse', '', 'hash1', ?)", (now,),
        )
        con.execute(
            "INSERT INTO ai_practice_sessions (id, practice_kind, total_questions, annale_id, created_at) "
            "VALUES (1, 'QCM', 1, 77, ?)", (now,),
        )
        con.execute("INSERT INTO ai_practice_session_questions (session_id, question_id, position) VALUES (1, 1, 1)")
    result = isolated_db.list_uness_annale_questions_for_analysis(77)
    assert result == [{"question_id": 1, "prompt": "Enonce", "answer": "Reponse", "official_item": "", "official_rank": ""}]
```

Run: `pytest tests/test_local_store_conference_analysis.py::test_list_uness_annale_questions_for_analysis -v`
Expected: FAIL, then implement Step above, then PASS. Commit this helper on its own:

```bash
git add backend/core/reviews/local_store.py tests/test_local_store_conference_analysis.py
git commit -m "feat(conferences): read a dossier's questions for conference analysis"
```

- [ ] **Step 2: Write the failing tests for the job runner**

```python
# tests/test_conference_analysis_job_runner.py
import datetime
import json
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from backend.core.reviews import local_store
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "job-runner.db")
    monkeypatch.setattr(local_store, "_DB", None)
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    monkeypatch.setattr(local_store, "_DB", None)


def _seed_conference_with_dossier(local_store, *, with_audio=True):
    now = local_store._now()
    with local_store._conn() as con:
        con.execute(
            "INSERT INTO uness_annales (id, source_url, faculte, niveau, annee, matiere, titre, type_annale, collected_at) "
            "VALUES (77, 'https://uness.example/77', 'F', 'DFASM1', 2026, 'Cardiologie', 'Titre', 'annale', ?)", (now,),
        )
        con.execute(
            "INSERT INTO ai_practice_questions (id, practice_kind, question_kind, position, prompt, answer, explanation, question_hash, created_at) "
            "VALUES (1, 'QCM', 'CLOSED', 1, 'Enonce', 'Reponse', '', 'hash1', ?)", (now,),
        )
        con.execute(
            "INSERT INTO ai_practice_sessions (id, practice_kind, total_questions, annale_id, created_at) "
            "VALUES (1, 'QCM', 1, 77, ?)", (now,),
        )
        con.execute("INSERT INTO ai_practice_session_questions (session_id, question_id, position) VALUES (1, 1, 1)")
    _, conf = local_store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="Cardiologie", match_status="matched",
        college_name="Cardiologie", source_file="planning.xlsx",
    )
    local_store.set_conference_uness_session(conf["id"], 77)
    if with_audio:
        local_store.set_conference_audio(conf["id"], audio_path="data/conferences/audio/1.mp3", audio_hash="hash-abc")
    return local_store.get_conference(conf["id"])


def test_scan_creates_one_pending_job_per_eligible_conference(isolated_db):
    from backend.core.conferences import analysis_job_runner
    _seed_conference_with_dossier(isolated_db)
    created = analysis_job_runner.scan_and_queue_conference_analyses()
    assert created == 1
    jobs = isolated_db.list_conference_analysis_jobs_due_for_poll(limit=10)
    assert jobs == []  # still pending, not yet submitted/polled


def test_scan_skips_conference_without_audio(isolated_db):
    from backend.core.conferences import analysis_job_runner
    _seed_conference_with_dossier(isolated_db, with_audio=False)
    assert analysis_job_runner.scan_and_queue_conference_analyses() == 0


def test_submit_pending_jobs_uploads_audio_and_creates_batch_job(tmp_path, isolated_db, monkeypatch):
    from backend.core.conferences import analysis_job_runner
    from backend.core.ai.batch_client import UploadedFile, BatchJobHandle

    conf = _seed_conference_with_dossier(isolated_db)
    audio_path = tmp_path / "1.mp3"
    audio_path.write_bytes(b"fake")
    isolated_db.set_conference_audio(conf["id"], audio_path=str(audio_path), audio_hash="hash-abc")
    analysis_job_runner.scan_and_queue_conference_analyses()

    client = Mock()
    client.upload_audio_file.return_value = UploadedFile(uri="files/abc", name="files/abc", mime_type="audio/mpeg")
    client.create_batch_job.return_value = BatchJobHandle(name="batches/job-1")

    counts = analysis_job_runner.submit_pending_conference_analysis_jobs(client=client)

    assert counts["submitted"] == 1
    client.upload_audio_file.assert_called_once()
    client.create_batch_job.assert_called_once()
    jobs = isolated_db.list_conference_analysis_jobs_due_for_poll(limit=10)
    assert len(jobs) == 1
    assert jobs[0]["provider_job_name"] == "batches/job-1"


def test_poll_applies_result_without_overwriting_nothing_official(isolated_db, monkeypatch):
    from backend.core.conferences import analysis_job_runner
    from backend.core.ai.batch_client import BatchJobStatus

    conf = _seed_conference_with_dossier(isolated_db)
    job = isolated_db.create_conference_analysis_job(
        conference_id=conf["id"], uness_session_id=77, model_id="gemini-flash",
        idempotency_key="hash-abc:key", prompt_version="v1",
    )
    isolated_db.mark_conference_analysis_job_submitted(job["id"], provider_job_name="batches/job-1", next_poll_at=isolated_db._now())

    response_payload = {
        "summary": "Résumé de la conférence.",
        "questions": [{
            "question_id": "1", "item_numbers": ["ITEM 232"], "item_confidence": 0.9,
            "item_rationale": "cité", "rank": "A", "rank_confidence": 0.9, "rank_rationale": "rang A",
            "verdict": "concordant", "verdict_confidence": 0.9, "verdict_rationale": "confirmé",
            "transcript_excerpt": "00:05:00",
        }],
    }
    client = Mock()
    client.get_batch_job.return_value = BatchJobStatus(
        name="batches/job-1", done=True, state="JOB_STATE_SUCCEEDED",
        inlined_responses=[{"response": {"candidates": [{"content": {"parts": [{"text": json.dumps(response_payload)}]}}]}}],
        responses_file_name=None, error=None,
    )
    monkeypatch.setattr(
        "backend.core.conferences.analysis_job_runner.candidate_items_for_college",
        lambda label: [{"item": "ITEM 232"}],
    )

    counts = analysis_job_runner.poll_running_conference_analysis_jobs(client=client)

    assert counts["succeeded"] == 1
    updated_job = isolated_db.get_conference_analysis_job(job["id"])
    assert updated_job["status"] == "succeeded"
    items = isolated_db.get_ai_practice_question_items(1)
    assert items[0]["item_number"] == "ITEM 232"
    assert items[0]["source"] == "gemini_conference"
    with isolated_db._conn() as con:
        usage_rows = con.execute("SELECT task, model, context FROM ai_usage_logs").fetchall()
    assert usage_rows[0]["task"] == "conference_analysis"
    assert "batch" in usage_rows[0]["context"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_conference_analysis_job_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.conferences.analysis_job_runner'`

- [ ] **Step 4: Write the implementation**

```python
# backend/core/conferences/analysis_job_runner.py
"""Worker de fond : scan des conférences éligibles, soumission, polling et
application du résultat de l'analyse Batch audio-informée."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from loguru import logger

from backend.core.ai import batch_client
from backend.core.ai.gemini_client import GeminiClientError
from backend.core.conferences.analysis_prompt import (
    PROMPT_VERSION,
    ConferenceQuestionSnapshot,
    build_conference_analysis_request,
    parse_conference_analysis_response,
)
from backend.core.reviews import local_store
from backend.core.uness.item_classifier import candidate_items_for_college

_MODEL_ID = "gemini-flash-lite"
_POLL_INTERVAL_SECONDS = 900  # 15 min, borné par le cycle de fond (5 min)


def _idempotency_key(conference_id: int, uness_session_id: int, audio_hash: str) -> str:
    raw = f"{audio_hash}:{conference_id}:{uness_session_id}:{_MODEL_ID}:{PROMPT_VERSION}"
    return f"{audio_hash}:{hashlib.sha256(raw.encode()).hexdigest()}"


def scan_and_queue_conference_analyses() -> int:
    created = 0
    for conference in local_store.list_conferences_eligible_for_analysis():
        key = _idempotency_key(conference["id"], conference["uness_session_id"], conference["audio_hash"])
        job = local_store.create_conference_analysis_job(
            conference_id=conference["id"],
            uness_session_id=conference["uness_session_id"],
            model_id=_MODEL_ID,
            idempotency_key=key,
            prompt_version=PROMPT_VERSION,
        )
        if job["status"] == "pending":
            created += 1
    return created


def submit_pending_conference_analysis_jobs(*, limit: int = 5, client=None) -> dict[str, int]:
    client = client or batch_client
    counts = {"claimed": 0, "submitted": 0, "failed": 0}
    for job in local_store.claim_pending_conference_analysis_jobs(limit=limit):
        counts["claimed"] += 1
        try:
            conference = local_store.get_conference(job["conference_id"])
            annale = local_store.get_uness_annale(job["uness_session_id"])
            questions = local_store.list_uness_annale_questions_for_analysis(job["uness_session_id"])
            if not questions:
                raise GeminiClientError("Dossier UNESS sans question importée")

            uploaded = client.upload_audio_file(Path(conference["audio_path"]))
            snapshots = [
                ConferenceQuestionSnapshot(
                    question_id=str(q["question_id"]), enonce=q["prompt"], official_answer=q["answer"],
                    official_item=q["official_item"], official_rank=q["official_rank"],
                )
                for q in questions
            ]
            request_body = build_conference_analysis_request(
                audio_file=uploaded, college_label=annale.get("matiere", ""), questions=snapshots,
            )
            handle = client.create_batch_job(_MODEL_ID, request_body)
            next_poll = (
                datetime.datetime.now().astimezone() + datetime.timedelta(seconds=_POLL_INTERVAL_SECONDS)
            ).isoformat(timespec="seconds")
            local_store.mark_conference_analysis_job_submitted(
                job["id"], provider_job_name=handle.name, next_poll_at=next_poll,
            )
            counts["submitted"] += 1
        except Exception as exc:  # noqa: BLE001 - une conférence en échec ne bloque pas les autres
            logger.warning(f"Soumission de l'analyse conférence {job['id']} échouée : {exc}")
            local_store.fail_conference_analysis_job(job["id"], error=str(exc))
            counts["failed"] += 1
    return counts


def _extract_response_text(status: batch_client.BatchJobStatus) -> str:
    if status.inlined_responses:
        parts = status.inlined_responses[0]["response"]["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    if status.responses_file_name:
        raw = batch_client.download_batch_results(status.responses_file_name)
        first_line = raw.splitlines()[0]
        payload = json.loads(first_line)
        parts = payload["response"]["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    raise GeminiClientError("Job Batch terminé sans résultat exploitable")


def _apply_result(job: dict, questions: list[dict], response_text: str) -> str:
    known_ids = {str(q["question_id"]) for q in questions}
    college_label = (local_store.get_uness_annale(job["uness_session_id"]) or {}).get("matiere", "")
    candidates = {c["item"] for c in candidate_items_for_college(college_label)}
    candidate_items_by_question = {qid: candidates for qid in known_ids}

    parsed = parse_conference_analysis_response(
        response_text, known_question_ids=known_ids, candidate_items=candidate_items_by_question,
    )

    analysis = local_store.record_conference_analysis(
        conference_id=job["conference_id"], uness_session_id=job["uness_session_id"],
        batch_job_id=job["id"], model_id=job["model_id"], prompt_version=job["prompt_version"],
        summary_text=parsed.summary,
    )

    any_needs_admin = False
    for question_id_str, result in parsed.questions.items():
        question_id = int(question_id_str)
        if result.item_number and not result.item_needs_admin:
            local_store.apply_conference_item_classification(
                question_id, result.item_number,
                confidence=result.item_confidence, rationale=result.item_rationale,
            )
        elif result.item_needs_admin:
            any_needs_admin = True

        if result.rank and not result.rank_needs_admin:
            local_store.apply_conference_rank_result(
                question_id, rank=result.rank, confidence=result.rank_confidence,
                evidence=[], rationale=result.rank_rationale,
            )
        elif result.rank_needs_admin:
            any_needs_admin = True

        local_store.record_conference_question_analysis(
            conference_analysis_id=analysis["id"], question_id=question_id,
            verdict=result.verdict, confidence=result.verdict_confidence,
            rationale=result.verdict_rationale, transcript_excerpt=result.transcript_excerpt,
        )

    if not parsed.questions:
        return "failed"
    if any_needs_admin:
        return "needs_admin"
    if len(parsed.questions) < len(known_ids):
        return "partial"
    return "succeeded"


def _log_batch_usage(job: dict, status: "batch_client.BatchJobStatus") -> None:
    """Trace le coût dans ai_usage_logs sans nouvelle colonne : le mode batch et le job
    Batch Gemini sont portés par `context` (JSON), pas par le schéma existant, pour éviter
    d'étendre ai_usage_logs pour ce seul chantier (cf. section 5 de la spec)."""
    usage = {}
    if status.inlined_responses:
        usage = status.inlined_responses[0].get("response", {}).get("usageMetadata", {})
    local_store.record_ai_usage(
        task="conference_analysis",
        model=job["model_id"],
        input_tokens=int(usage.get("promptTokenCount") or 0),
        output_tokens=int(usage.get("candidatesTokenCount") or 0),
        cost_usd=0.0,  # pas de registre de prix Batch/audio dans ce chantier (YAGNI, cf. spec §5)
        context=json.dumps({
            "execution_mode": "batch", "conference_id": job["conference_id"],
            "batch_job_id": job["id"], "provider_job_name": job["provider_job_name"],
        }),
    )


def poll_running_conference_analysis_jobs(*, limit: int = 10, client=None) -> dict[str, int]:
    client = client or batch_client
    counts = {"polled": 0, "succeeded": 0, "partial": 0, "needs_admin": 0, "not_ready": 0, "failed": 0}
    for job in local_store.list_conference_analysis_jobs_due_for_poll(limit=limit):
        counts["polled"] += 1
        try:
            status = client.get_batch_job(job["provider_job_name"])
            if not status.done:
                next_poll = (
                    datetime.datetime.now().astimezone() + datetime.timedelta(seconds=_POLL_INTERVAL_SECONDS)
                ).isoformat(timespec="seconds")
                local_store.mark_conference_analysis_job_polled(job["id"], next_poll_at=next_poll)
                counts["not_ready"] += 1
                continue
            if status.state == "JOB_STATE_FAILED":
                raise GeminiClientError(status.error or "Job Batch en échec")

            response_text = _extract_response_text(status)
            questions = local_store.list_uness_annale_questions_for_analysis(job["uness_session_id"])
            final_status = _apply_result(job, questions, response_text)
            local_store.complete_conference_analysis_job(job["id"], status=final_status, result_path="")
            _log_batch_usage(job, status)
            counts[final_status] += 1
        except Exception as exc:  # noqa: BLE001 - isole une conférence en échec des autres
            logger.warning(f"Analyse conférence {job['id']} : {exc}")
            local_store.fail_conference_analysis_job(job["id"], error=str(exc))
            counts["failed"] += 1
    return counts


def run_conference_analysis_cycle(*, client=None) -> dict[str, int]:
    created = scan_and_queue_conference_analyses()
    submitted = submit_pending_conference_analysis_jobs(client=client)
    polled = poll_running_conference_analysis_jobs(client=client)
    return {"created": created, **{f"submit_{k}": v for k, v in submitted.items()}, **{f"poll_{k}": v for k, v in polled.items()}}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_conference_analysis_job_runner.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/core/conferences/analysis_job_runner.py tests/test_conference_analysis_job_runner.py
git commit -m "feat(conferences): background worker for the audio-informed Batch analysis"
```

---

### Task 6 : Enregistrement dans la boucle de fond

**Files:**
- Modify: `backend/core/background.py`
- Test: `tests/test_background_conference_analysis.py`

**Interfaces:**
- Consumes: `backend.core.conferences.analysis_job_runner.run_conference_analysis_cycle() -> dict[str, int]` (Task 5).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_background_conference_analysis.py
import asyncio
from unittest.mock import patch


def test_run_pending_conference_analysis_calls_cycle_without_blocking():
    from backend.core.background import _run_pending_conference_analysis

    with patch(
        "backend.core.conferences.analysis_job_runner.run_conference_analysis_cycle",
        return_value={"created": 1, "submit_submitted": 1, "poll_succeeded": 0},
    ) as mock_cycle:
        asyncio.run(_run_pending_conference_analysis())

    mock_cycle.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_background_conference_analysis.py -v`
Expected: FAIL — `ImportError: cannot import name '_run_pending_conference_analysis'`

- [ ] **Step 3: Add the wrapper and register it in the loop**

In `backend/core/background.py`, add right after `_run_pending_uness_rank_jobs` (around line 456),
mirroring its exact shape:

```python
async def _run_pending_conference_analysis() -> None:
    """Run the conference audio-analysis Batch cycle without blocking the sync loop."""
    try:
        from backend.core.conferences.analysis_job_runner import run_conference_analysis_cycle

        result = await asyncio.to_thread(run_conference_analysis_cycle)
        if result.get("created") or result.get("submit_submitted") or result.get("poll_succeeded"):
            logger.info(
                "Analyse conférence : {} créées, {} soumises, {} réussies, {} en échec",
                result.get("created", 0), result.get("submit_submitted", 0),
                result.get("poll_succeeded", 0), result.get("submit_failed", 0) + result.get("poll_failed", 0),
            )
    except Exception as exc:
        logger.warning(f"Analyse conférence ignorée : {exc}")
```

Register the call in the main loop right after `await _run_pending_uness_rank_jobs()` (around
line 152):

```python
        await _run_pending_uness_rank_jobs()
        await _run_pending_conference_analysis()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_background_conference_analysis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/background.py tests/test_background_conference_analysis.py
git commit -m "feat(conferences): schedule the audio-analysis Batch cycle in the background loop"
```

---

### Task 7 : Interface — upload audio, statut du job, panneau d'analyse

**Files:**
- Modify: `frontend/components/conferences_admin.py`
- Test: `tests/test_conferences_admin_audio.py`

**Interfaces:**
- Consumes: `backend.core.conferences.audio_service.save_conference_audio` (Task 2),
  `local_store.list_conferences(match_status="matched")` (existing),
  `local_store.get_conference_analysis_job`-family (Task 1),
  `local_store.list_conferences_eligible_for_analysis` is not used here directly — the UI needs
  a new read helper for "linked conferences with their latest job status", added in Step 1.

- [ ] **Step 1: Add a local_store read helper for linked-conference rows**

```python
# backend/core/reviews/local_store.py — after list_conferences_eligible_for_analysis
def list_linked_conferences_with_analysis_status() -> list[dict]:
    """Conférences déjà liées à un dossier UNESS, avec le statut du dernier job d'analyse."""
    with _conn() as con:
        rows = con.execute(
            """SELECT c.*,
                      (SELECT j.status FROM conference_analysis_jobs j
                       WHERE j.conference_id = c.id ORDER BY j.created_at DESC LIMIT 1) AS analysis_status,
                      (SELECT j.id FROM conference_analysis_jobs j
                       WHERE j.conference_id = c.id ORDER BY j.created_at DESC LIMIT 1) AS analysis_job_id
               FROM conferences c
               WHERE c.uness_session_id IS NOT NULL
               ORDER BY c.date DESC"""
        ).fetchall()
    return [dict(row) for row in rows]
```

Test (append to `tests/test_local_store_conference_analysis.py`):

```python
def test_list_linked_conferences_with_analysis_status(isolated_db):
    _, conf = _make_conference(isolated_db)
    isolated_db.set_conference_uness_session(conf["id"], 77)
    rows = isolated_db.list_linked_conferences_with_analysis_status()
    assert len(rows) == 1
    assert rows[0]["analysis_status"] is None
```

Run: `pytest tests/test_local_store_conference_analysis.py::test_list_linked_conferences_with_analysis_status -v`
— expect FAIL then PASS after adding the function above. Commit:

```bash
git add backend/core/reviews/local_store.py tests/test_local_store_conference_analysis.py
git commit -m "feat(conferences): list linked conferences with their analysis status"
```

- [ ] **Step 2: Write the failing UI test**

`conferences_admin.py` renders inside `ui.row`/`ui.column` contexts tied to a NiceGUI page — its
existing tests (if any) exercise the pure functions, not a live client. Follow that same
pattern: test the new render helper's *data selection*, not NiceGUI internals.

```python
# tests/test_conferences_admin_audio.py
from unittest.mock import Mock, patch


def test_render_linked_conferences_calls_upload_service_on_upload(monkeypatch):
    from frontend.components import conferences_admin

    fake_event = Mock()
    fake_event.name = "correction.mp3"
    fake_event.content.read.return_value = b"fake-audio"

    with patch(
        "frontend.components.conferences_admin.audio_service.save_conference_audio"
    ) as mock_save:
        conferences_admin._handle_audio_upload(conference_id=5, event=fake_event)

    mock_save.assert_called_once_with(5, filename="correction.mp3", content=b"fake-audio")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_conferences_admin_audio.py -v`
Expected: FAIL — `AttributeError: module 'conferences_admin' has no attribute '_handle_audio_upload'`

- [ ] **Step 4: Implement the upload handler and the linked-conference render section**

Add the import and the handler near the top of `frontend/components/conferences_admin.py`
(alongside the existing `from backend.core.conferences import service` import):

```python
from backend.core.conferences import audio_service
from backend.core.reviews import local_store
```

```python
def _handle_audio_upload(*, conference_id: int, event) -> None:
    try:
        content = event.content.read()
        audio_service.save_conference_audio(conference_id, filename=event.name, content=content)
        ui.notify("Audio enregistré, l'analyse démarrera automatiquement.", type="positive")
    except ValueError as exc:
        ui.notify(str(exc), type="negative")
    except Exception as exc:  # noqa: BLE001 - retour utilisateur, ne doit jamais planter la page
        logger.error(f"Upload audio conférence échoué : {exc}")
        ui.notify("Erreur lors de l'enregistrement de l'audio.", type="negative")


_STATUS_LABELS = {
    None: "Pas d'analyse",
    "pending": "En attente",
    "submitted": "Soumis",
    "running": "En cours",
    "succeeded": "Terminé",
    "partial": "Partiel",
    "needs_admin": "À valider",
    "failed": "Échec",
}


def _render_linked_conference(row: dict) -> None:
    with ui.row().classes("w-full items-center gap-2"):
        ui.label(f"{row['date']} — {row['theme_raw']}").classes("text-sm flex-1")
        ui.badge(_STATUS_LABELS.get(row["analysis_status"], row["analysis_status"])).classes("text-xs")
        if not row["audio_path"]:
            ui.upload(
                on_upload=lambda e, conf_id=row["id"]: _handle_audio_upload(conference_id=conf_id, event=e),
                max_files=1, auto_upload=True,
            ).props("accept='audio/*' flat bordered dense").classes("w-56")
        if row["analysis_status"] in {"failed", "needs_admin"}:
            def _retry(conf_id=row["id"]) -> None:
                from backend.core.conferences.analysis_job_runner import scan_and_queue_conference_analyses
                scan_and_queue_conference_analyses()
                ui.notify("Nouvelle analyse mise en file.", type="positive")
                _render_body()

            ui.button("Relancer l'analyse", on_click=_retry).props("outline color=orange size=sm")
```

Call it from `_render_body()` (around line 44), right after the existing pending-links section:

```python
    for row in local_store.list_linked_conferences_with_analysis_status():
        _render_linked_conference(row)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_conferences_admin_audio.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/conferences_admin.py tests/test_conferences_admin_audio.py
git commit -m "feat(conferences): audio upload, analysis status badge and retry in the admin panel"
```

- [ ] **Step 7: Manual verification in the running app**

Run: `pytest -q` (full suite, non-regression) then start the app and check
Réglages → Conférences : a conference already linked to a dossier shows an upload control; after
uploading a small test mp3, the row shows "En attente" without further action, and a
"Relancer l'analyse" button appears only after a job reaches `failed`/`needs_admin`.

---

## Self-Review Notes

- **Spec coverage**: déclenchement auto (Task 5+7), upload manuel (Task 2+7), Batch obligatoire
  (Task 3+5), non-écrasement de l'officiel (Task 1's `apply_conference_rank_result` reuses
  `_apply_rank_metadata`'s existing guard; Task 4's parser drops out-of-candidate items;
  `apply_conference_item_classification` only writes when zero items exist), annotation
  consultable non auto-appliquée (Task 1's `conference_analyses`/`conference_question_analysis`
  tables, never touching `UnessProposition`), statuts de job (Task 1 schema), idempotence
  (Task 5's `_idempotency_key` + Task 1's `INSERT OR IGNORE ... UNIQUE(idempotency_key)`), audio
  jamais loggé (Task 2/3 never pass raw bytes to `logger`), badge de statut + relance manuelle
  (Task 7), traçabilité du coût/mode d'exécution sans double-comptage (Task 5's `_log_batch_usage`,
  reusing the existing `record_ai_usage`/`context` column rather than extending the schema — a
  deliberate simplification of spec §5's fuller telemetry design, justified by YAGNI since no
  Batch pricing registry exists yet) — all ten acceptance criteria from the spec map to a task above.
- **Placeholder scan**: no TBD/TODO; every step has runnable code including its test.
- **Type consistency checked**: `ConferenceQuestionSnapshot`/`ConferenceQuestionResult`/
  `ConferenceAnalysisResult` (Task 4) are consumed with the same field names in Task 5's
  `_apply_result`; `UploadedFile`/`BatchJobHandle`/`BatchJobStatus` (Task 3) are consumed
  identically in Task 5; `local_store` function names introduced in Task 1 (`create_conference_analysis_job`, `claim_pending_conference_analysis_jobs`, etc.) match their call sites in Task 5 and Task 7 exactly.
- **Scope check**: single vertical slice (conference dossiers only), no change to the general
  UNESS annale import pipeline, no generic `ai_batch_jobs` table — consistent with the approved
  design's Approach A.
