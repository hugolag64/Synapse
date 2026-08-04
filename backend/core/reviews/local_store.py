"""
local_store.py — Synapse
------------------------
Couche SQLite locale pour les ReviewTasks virtuelles.

Notion  = source de vérité des cours, dates J+X, PDF, statuts globaux.
SQLite  = historique réel des révisions : validations, reports, ignores,
          résultats QCM futurs, sessions de travail.

Aucune connexion réseau dans ce fichier.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path

from loguru import logger

from backend.config.settings import now_local

# ── Emplacement de la base ────────────────────────────────────────────────────
# backend/core/reviews/local_store.py → 4 niveaux vers la racine du projet
_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = _ROOT / "data" / "synapse_local.db"
DB_BACKUP_DIR = _ROOT / "data" / "backups"


# ── Connexion ─────────────────────────────────────────────────────────────────

_DB: sqlite3.Connection | None = None
_DB_LOCK = threading.RLock()


class _LockedConnection:
    """Proxy qui sérialise les transactions de la connexion SQLite partagée."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def __enter__(self):
        _DB_LOCK.acquire()
        try:
            self._connection.__enter__()
        except Exception:
            _DB_LOCK.release()
            raise
        return self._connection

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return self._connection.__exit__(exc_type, exc_value, traceback)
        finally:
            _DB_LOCK.release()

    def execute(self, *args, **kwargs):
        with _DB_LOCK:
            return self._connection.execute(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        with _DB_LOCK:
            return self._connection.executescript(*args, **kwargs)

    def commit(self):
        with _DB_LOCK:
            return self._connection.commit()

    def rollback(self):
        with _DB_LOCK:
            return self._connection.rollback()

    def close(self):
        with _DB_LOCK:
            return self._connection.close()


def _conn() -> _LockedConnection:
    global _DB
    with _DB_LOCK:
        if _DB is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _DB = sqlite3.connect(DB_PATH, check_same_thread=False)
            _DB.row_factory = sqlite3.Row
            _DB.execute("PRAGMA journal_mode=WAL")
            _DB.execute("PRAGMA foreign_keys=ON")
        return _LockedConnection(_DB)


# ── Initialisation ────────────────────────────────────────────────────────────

def backup_database(
    *,
    source_path: Path | None = None,
    backup_dir: Path | None = None,
    keep: int = 7,
    now: datetime.datetime | None = None,
) -> Path | None:
    """Crée une copie SQLite cohérente et conserve les `keep` dernières."""
    source_path = Path(source_path or DB_PATH)
    if not source_path.exists():
        return None

    backup_dir = Path(backup_dir or DB_BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or now_local()).strftime("%Y-%m-%d")
    destination = backup_dir / f"synapse_local-{stamp}.db"
    if destination.exists():
        return destination

    temporary = destination.with_suffix(".db.tmp")
    try:
        source = sqlite3.connect(source_path)
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()
        os.replace(temporary, destination)
        backups = sorted(backup_dir.glob("synapse_local-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
        for old_backup in backups[keep:]:
            old_backup.unlink(missing_ok=True)
        logger.info(f"Sauvegarde SQLite créée : {destination}")
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        logger.exception(f"Échec de la sauvegarde SQLite : {source_path}")
        return None

def init_db() -> None:
    """Crée toutes les tables si elles n'existent pas encore."""
    database_existed = DB_PATH.exists()
    if database_existed:
        backup_database()
    with _conn() as con:
        con.executescript("""
        -- ── Table principale : historique des révisions ──────────────────────
        CREATE TABLE IF NOT EXISTS review_history (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id              TEXT    UNIQUE NOT NULL,
            course_id            TEXT    NOT NULL,
            course_title         TEXT    DEFAULT '',
            item_number          TEXT    DEFAULT '',
            context              TEXT    NOT NULL,
            review_type          TEXT    NOT NULL,
            theoretical_due_date TEXT    NOT NULL,
            effective_due_date   TEXT    NOT NULL,
            status               TEXT    NOT NULL DEFAULT 'todo',
            completed_at         TEXT,
            postponed_to         TEXT,
            postponed_count      INTEGER DEFAULT 0,
            difficulty           TEXT,
            confidence           INTEGER,
            notes                TEXT,
            created_at           TEXT    NOT NULL,
            updated_at           TEXT    NOT NULL
        );

        -- ── Table QCM : résultats EDNpro / Hypocampus ──────────────────────
        CREATE TABLE IF NOT EXISTS qcm_results (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            platform         TEXT    NOT NULL,
            external_id      TEXT,
            course_id        TEXT,
            course_title     TEXT,
            item_number      TEXT,
            date             TEXT    NOT NULL,
            score            REAL,
            total_questions  INTEGER,
            correct_answers  INTEGER,
            wrong_answers    INTEGER,
            weak_tags        TEXT,
            raw_data         TEXT,
            created_at       TEXT    NOT NULL,
            updated_at       TEXT    NOT NULL
        );

        -- ── Table qcm_sessions : historique local des QCM ──────────────────
        CREATE TABLE IF NOT EXISTS qcm_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id        TEXT    NOT NULL,
            course_title     TEXT,
            item_number      TEXT,
            platform         TEXT    NOT NULL,
            session_date     TEXT    NOT NULL,
            score            REAL,
            total_questions  INTEGER,
            errors           TEXT,
            comments         TEXT,
            created_at       TEXT    NOT NULL,
            updated_at       TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_qs_course      ON qcm_sessions(course_id);
        CREATE INDEX IF NOT EXISTS idx_qs_platform    ON qcm_sessions(platform);
        CREATE INDEX IF NOT EXISTS idx_qs_item_date   ON qcm_sessions(item_number, session_date);
        CREATE INDEX IF NOT EXISTS idx_qs_course_date ON qcm_sessions(course_id, session_date DESC);

        CREATE TABLE IF NOT EXISTS ednpro_item_frequency (
            item_number       TEXT PRIMARY KEY,
            priority          TEXT NOT NULL,
            session_count     INTEGER NOT NULL DEFAULT 0,
            question_count    INTEGER NOT NULL DEFAULT 0,
            years_json        TEXT NOT NULL DEFAULT '[]',
            source_url        TEXT NOT NULL DEFAULT '',
            collected_at      TEXT NOT NULL,
            raw_payload_json  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ednpro_frequency_collected
            ON ednpro_item_frequency(collected_at DESC);

        -- ── Questions IA immuables et tentatives rejouables ────────────────
        CREATE TABLE IF NOT EXISTS ai_practice_sessions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id           TEXT NOT NULL DEFAULT '',
            course_title        TEXT NOT NULL DEFAULT '',
            item_number         TEXT NOT NULL DEFAULT '',
            objective_code      TEXT NOT NULL DEFAULT '',
            practice_kind       TEXT NOT NULL,
            total_questions     INTEGER NOT NULL,
            open_questions      INTEGER NOT NULL DEFAULT 0,
            closed_questions    INTEGER NOT NULL DEFAULT 0,
            difficulty          TEXT NOT NULL DEFAULT 'standard',
            model               TEXT NOT NULL DEFAULT '',
            replay_of_session_id INTEGER,
            created_at          TEXT NOT NULL,
            completed_at        TEXT,
            score_percent       REAL,
            mastery_recorded_at TEXT,
            FOREIGN KEY (replay_of_session_id) REFERENCES ai_practice_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS ai_practice_questions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id           TEXT NOT NULL DEFAULT '',
            item_number         TEXT NOT NULL DEFAULT '',
            objective_code      TEXT NOT NULL DEFAULT '',
            practice_kind       TEXT NOT NULL,
            question_kind       TEXT NOT NULL,
            position            INTEGER NOT NULL,
            prompt              TEXT NOT NULL,
            choices_json        TEXT NOT NULL DEFAULT '[]',
            answer              TEXT NOT NULL,
            explanation         TEXT NOT NULL,
            source_refs_json    TEXT NOT NULL DEFAULT '[]',
            import_metadata_json TEXT NOT NULL DEFAULT '{}',
            model               TEXT NOT NULL DEFAULT '',
            question_hash       TEXT NOT NULL,
            created_at          TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_practice_session_questions (
            session_id          INTEGER NOT NULL,
            question_id         INTEGER NOT NULL,
            position            INTEGER NOT NULL,
            PRIMARY KEY (session_id, question_id),
            FOREIGN KEY (session_id) REFERENCES ai_practice_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES ai_practice_questions(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS ai_practice_attempts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL,
            question_id         INTEGER NOT NULL,
            response            TEXT NOT NULL DEFAULT '',
            is_correct           INTEGER,
            score_percent       REAL,
            duration_seconds    INTEGER,
            hints_used          INTEGER NOT NULL DEFAULT 0,
            answered_at         TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES ai_practice_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES ai_practice_questions(id) ON DELETE RESTRICT
        );
        -- ── Items multiples d'une même session (DP transverses) ─────────────
        -- ai_practice_sessions.item_number reste l'item principal (rétro-
        -- compatible) ; cette table liste TOUS les items qu'une session touche,
        -- pour que chacun bénéficie de l'évidence (cf. get_ai_practice_sessions).
        CREATE TABLE IF NOT EXISTS ai_practice_session_items (
            session_id          INTEGER NOT NULL,
            item_number         TEXT NOT NULL,
            PRIMARY KEY (session_id, item_number),
            FOREIGN KEY (session_id) REFERENCES ai_practice_sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ai_practice_session_items_item
            ON ai_practice_session_items(item_number);
        CREATE INDEX IF NOT EXISTS idx_ai_practice_session
            ON ai_practice_session_questions(session_id, position);
        CREATE INDEX IF NOT EXISTS idx_ai_practice_item
            ON ai_practice_questions(item_number, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_ai_practice_attempt_question
            ON ai_practice_attempts(question_id, answered_at DESC);

        CREATE TABLE IF NOT EXISTS imported_practice_cases (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint   TEXT NOT NULL UNIQUE,
            external_id   TEXT NOT NULL DEFAULT '',
            kind          TEXT NOT NULL,
            title         TEXT NOT NULL,
            stem          TEXT NOT NULL,
            item_numbers  TEXT NOT NULL DEFAULT '[]',
            source        TEXT NOT NULL DEFAULT '',
            source_content TEXT NOT NULL DEFAULT '',
            status        TEXT NOT NULL DEFAULT 'ready',
            review_reason TEXT NOT NULL DEFAULT '',
            imported_at   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_imported_cases_status
            ON imported_practice_cases(status);
        CREATE INDEX IF NOT EXISTS idx_imported_cases_items
            ON imported_practice_cases(item_numbers);

        CREATE TABLE IF NOT EXISTS external_results (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            source           TEXT NOT NULL,
            external_id      TEXT NOT NULL,
            session_date     TEXT NOT NULL,
            item_number      TEXT NOT NULL,
            activity_type    TEXT NOT NULL DEFAULT 'QCM',
            score_percent    REAL,
            total_questions  INTEGER,
            rank_a_percent   REAL,
            rank_b_percent   REAL,
            metadata_json    TEXT NOT NULL DEFAULT '{}',
            imported_at      TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            UNIQUE (source, external_id)
        );
        CREATE INDEX IF NOT EXISTS idx_external_results_item_date
            ON external_results(item_number, session_date DESC);

        CREATE TABLE IF NOT EXISTS error_signals (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_number  TEXT NOT NULL,
            category     TEXT NOT NULL,
            occurred_at  TEXT NOT NULL,
            source       TEXT NOT NULL,
            evidence_id  TEXT NOT NULL,
            detail       TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_error_signals_item_date
            ON error_signals(item_number, occurred_at DESC);

        CREATE TABLE IF NOT EXISTS edn_recommendations (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            recommendation_type TEXT NOT NULL,
            item_number       TEXT NOT NULL,
            category          TEXT NOT NULL,
            detail            TEXT NOT NULL,
            evidence_json     TEXT NOT NULL DEFAULT '[]',
            dedupe_key        TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'proposée',
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_edn_recommendations_status
            ON edn_recommendations(status, created_at DESC);

        -- ── Table Télémétrie et Coûts des appels IA ──────────────────────
        CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            task             TEXT NOT NULL,
            model            TEXT NOT NULL,
            input_tokens     INTEGER NOT NULL DEFAULT 0,
            output_tokens    INTEGER NOT NULL DEFAULT 0,
            cost_usd         REAL NOT NULL DEFAULT 0.0,
            duration_ms      REAL,
            error            TEXT,
            context          TEXT,
            created_at       TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_usage_task ON ai_usage_logs(task);
        CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage_logs(created_at DESC);

        CREATE TABLE IF NOT EXISTS imported_practice_questions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id     INTEGER NOT NULL,
            position    INTEGER NOT NULL,
            prompt      TEXT NOT NULL,
            choices     TEXT NOT NULL DEFAULT '[]',
            answer      TEXT NOT NULL,
            explanation TEXT NOT NULL,
            FOREIGN KEY (case_id) REFERENCES imported_practice_cases(id) ON DELETE CASCADE,
            UNIQUE (case_id, position)
        );
        CREATE TABLE IF NOT EXISTS ai_practice_anchors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL UNIQUE,
            label       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            last_seen_at TEXT,
            active      INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (question_id) REFERENCES ai_practice_questions(id) ON DELETE CASCADE
        );

        -- ── Table sessions de travail ─────────────────────────────────────
        CREATE TABLE IF NOT EXISTS study_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id        TEXT    NOT NULL,
            course_title     TEXT,
            item_number      TEXT,
            context          TEXT,
            session_date     TEXT    NOT NULL,
            duration_minutes INTEGER,
            session_type     TEXT    NOT NULL DEFAULT 'révision',
            activity_types   TEXT    DEFAULT '[]',
            confidence       INTEGER,
            difficulty       TEXT,
            qcm_result       TEXT,
            weak_category    TEXT,
            weak_detail      TEXT,
            perceived_mastery INTEGER,
            notes            TEXT,
            created_at       TEXT    NOT NULL,
            updated_at       TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS anki_review_evidence (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key        TEXT    NOT NULL,
            card_id          INTEGER NOT NULL,
            note_id          INTEGER,
            item_number      TEXT    NOT NULL,
            rating           TEXT    NOT NULL,
            reviewed_at      TEXT    NOT NULL,
            interval         INTEGER,
            source_review_id TEXT,
            created_at       TEXT    NOT NULL,
            UNIQUE(event_key, item_number)
        );
        CREATE INDEX IF NOT EXISTS idx_anki_evidence_item_date
            ON anki_review_evidence(item_number, reviewed_at DESC);

        -- Index pour les requêtes courantes
        CREATE INDEX IF NOT EXISTS idx_rh_course  ON review_history(course_id);
        CREATE INDEX IF NOT EXISTS idx_rh_status  ON review_history(status);
        CREATE INDEX IF NOT EXISTS idx_rh_effdate ON review_history(effective_due_date);
        CREATE INDEX IF NOT EXISTS idx_rh_ctx     ON review_history(context);
        CREATE INDEX IF NOT EXISTS idx_ss_course  ON study_sessions(course_id);

        -- ── Table points faibles EDN ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS weak_points (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id         TEXT    NOT NULL,
            course_title      TEXT    DEFAULT '',
            item_number       TEXT    DEFAULT '',
            category          TEXT,
            detail            TEXT    NOT NULL,
            severity          INTEGER DEFAULT 2,
            status            TEXT    NOT NULL DEFAULT 'active',
            source_session_id INTEGER,
            created_at        TEXT    NOT NULL,
            resolved_at       TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_wp_course  ON weak_points(course_id);
        CREATE INDEX IF NOT EXISTS idx_wp_status  ON weak_points(status);

        -- ── Cache local des PDFs détectés ──────────────────────────────────
        CREATE TABLE IF NOT EXISTS pdf_local_cache (
            course_id   TEXT NOT NULL,
            context     TEXT NOT NULL,
            pdf_path    TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            PRIMARY KEY (course_id, context)
        );

        -- ── Suivi import PDF → Notion ─────────────────────────────────────
        -- Mémorise quels (college, item_num) ont déjà été traités pour éviter
        -- de refaire l'appel Notion à chaque démarrage.
        CREATE TABLE IF NOT EXISTS pdf_item_scan (
            college    TEXT    NOT NULL,
            item_num   INTEGER NOT NULL,
            pdf_name   TEXT,
            status     TEXT    NOT NULL DEFAULT 'pending',
            updated_at TEXT    NOT NULL,
            PRIMARY KEY (college, item_num)
        );

        -- ── Routine quotidienne locale ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS routine_items (
            name     TEXT    PRIMARY KEY,
            position INTEGER NOT NULL DEFAULT 0,
            active   INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS routine_checks (
            date      TEXT    NOT NULL,
            item_name TEXT    NOT NULL,
            checked   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, item_name)
        );

        CREATE TABLE IF NOT EXISTS manual_planning_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            course_id TEXT NOT NULL,
            course_title TEXT NOT NULL DEFAULT '',
            item_number TEXT NOT NULL DEFAULT '',
            activity_type TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_manual_planning_date
            ON manual_planning_entries(entry_date);

        -- ── Cache fetch LiSA ─────────────────────────────────────────────
        -- Trace les cours dont les OIC ont déjà été scrapés (même si 0 OIC).
        CREATE TABLE IF NOT EXISTS lisa_oic_cache (
            course_id  TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL
        );

        -- ── Objectifs de Connaissance LiSA ───────────────────────────────
        CREATE TABLE IF NOT EXISTS lisa_oic (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id  TEXT    NOT NULL,
            oic_code   TEXT,
            intitule   TEXT    NOT NULL,
            rang       TEXT    NOT NULL,
            rubrique   TEXT,
            ordre      INTEGER,
            mastered   INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_lisa_oic_course ON lisa_oic(course_id);
        """)
    migrate_study_sessions_v2()
    _migrate_qcm_sessions_v2()
    _migrate_weak_points_v2()
    _migrate_weak_points_from_sessions()
    _migrate_weak_points_obsidian()
    _migrate_review_history_sm2()
    _migrate_course_edges_table()
    _migrate_pending_gap_proposals()
    _migrate_routine_tables()
    _migrate_oic_anythingllm_validation()
    _migrate_ai_practice_v1()
    _migrate_reliable_practice_loop()
    _migrate_uness_annales()
    _migrate_uness_correction_failures()
    _migrate_uness_scanned_catalog()
    logger.info(f"SQLite initialisé : {DB_PATH}")


# ── Helpers internes ──────────────────────────────────────────────────────────

def _now() -> str:
    return now_local().isoformat(timespec="seconds")


def replace_ednpro_item_frequencies(rows: list[dict]) -> int:
    """Replace the complete EDNpro frequency snapshot in one transaction."""
    if not rows:
        raise ValueError("Un snapshot EDNpro ne peut pas être vide")
    with _conn() as con:
        con.execute("DELETE FROM ednpro_item_frequency")
        for row in rows:
            con.execute(
                """INSERT INTO ednpro_item_frequency
                   (item_number, priority, session_count, question_count, years_json,
                    source_url, collected_at, raw_payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(row["item_number"]), str(row.get("priority", "basique")),
                    int(row.get("session_count", 0) or 0), int(row.get("question_count", 0) or 0),
                    json.dumps(list(row.get("years", [])), ensure_ascii=False),
                    str(row.get("source_url", "")), str(row.get("collected_at", "")),
                    row.get("raw_payload_json"),
                ),
            )
    return len(rows)


def _frequency_row(row) -> dict:
    value = dict(row)
    try:
        value["years"] = json.loads(value.pop("years_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        value["years"] = []
    return value


def get_ednpro_item_frequency(item_number: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM ednpro_item_frequency WHERE item_number = ?",
            (str(item_number).strip().removeprefix("ITEM "),),
        ).fetchone()
    return _frequency_row(row) if row else None


def get_ednpro_frequency_snapshot() -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT collected_at, source_url, COUNT(*) AS item_count "
            "FROM ednpro_item_frequency GROUP BY collected_at, source_url "
            "ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_ednpro_practice_questions(item_number: str, limit: int = 100) -> list[dict]:
    """Return imported EDNpro questions tagged with one item for replay."""
    with _conn() as con:
        rows = con.execute(
            """SELECT DISTINCT q.*
               FROM ai_practice_questions q
               JOIN ai_practice_question_items qi ON qi.question_id = q.id
               WHERE qi.item_number = ?
               ORDER BY q.created_at DESC, q.id DESC LIMIT ?""",
            (str(item_number).strip().removeprefix("ITEM "), int(limit)),
        ).fetchall()
    result = []
    for row in rows:
        value = dict(row)
        try:
            metadata = json.loads(value.pop("import_metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        provenance = metadata.get("uness", {}).get("provenance", {}) if isinstance(metadata, dict) else {}
        source = str(metadata.get("source") or provenance.get("source") or "").strip().lower()
        if source != "ednpro":
            continue
        try:
            value["choices"] = json.loads(value.pop("choices_json") or "[]")
            value["source_refs"] = json.loads(value.pop("source_refs_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            continue
        value["import_metadata"] = metadata
        value["item_numbers"] = [str(item_number).strip().removeprefix("ITEM ")]
        result.append(value)
    return result


def upsert_external_result(result) -> str:
    """Insère ou met à jour un résultat externe par clé source/identifiant."""
    now = _now()
    values = (
        str(result.source),
        str(result.external_id),
        result.session_date.isoformat(),
        str(result.item_number),
        str(result.activity_type or "QCM"),
        result.score_percent,
        result.total_questions,
        result.rank_a_percent,
        result.rank_b_percent,
        json.dumps(result.metadata or {}, ensure_ascii=False, sort_keys=True),
    )
    with _conn() as con:
        existing = con.execute(
            "SELECT id FROM external_results WHERE source = ? AND external_id = ?",
            values[:2],
        ).fetchone()
        if existing:
            con.execute(
                """UPDATE external_results SET session_date=?, item_number=?, activity_type=?,
                   score_percent=?, total_questions=?, rank_a_percent=?, rank_b_percent=?,
                   metadata_json=?, updated_at=? WHERE source=? AND external_id=?""",
                values[2:] + (now, values[0], values[1]),
            )
            return "updated"
        con.execute(
            """INSERT INTO external_results
               (source, external_id, session_date, item_number, activity_type,
                score_percent, total_questions, rank_a_percent, rank_b_percent,
                metadata_json, imported_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values + (now, now),
        )
    return "inserted"


def get_external_results(
    *, item_number: str | None = None, source: str | None = None, days: int | None = None
) -> list[dict]:
    clauses = []
    params: list[object] = []
    if item_number:
        clauses.append("item_number = ?")
        params.append(str(item_number).strip().removeprefix("ITEM "))
    if source:
        clauses.append("source = ?")
        params.append(str(source))
    if days is not None:
        cutoff = (now_local().date() - datetime.timedelta(days=int(days))).isoformat()
        clauses.append("session_date >= ?")
        params.append(cutoff)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM external_results{where} ORDER BY session_date DESC, id DESC",
            params,
        ).fetchall()
    result = []
    for row in rows:
        value = dict(row)
        try:
            value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            value["metadata"] = {}
        result.append(value)
    return result


def insert_error_signal(
    item_number: str, category: str, occurred_at: str, source: str, evidence_id: str, detail: str = ""
) -> int:
    with _conn() as con:
        cursor = con.execute(
            """INSERT INTO error_signals
               (item_number, category, occurred_at, source, evidence_id, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(item_number), str(category), str(occurred_at), str(source), str(evidence_id), str(detail), _now()),
        )
    return int(cursor.lastrowid)


def get_error_signals(*, item_number: str | None = None, days: int | None = None) -> list[dict]:
    clauses = []
    params: list[object] = []
    if item_number:
        clauses.append("item_number = ?")
        params.append(str(item_number).strip().removeprefix("ITEM "))
    if days is not None:
        cutoff = (now_local().date() - datetime.timedelta(days=int(days))).isoformat()
        clauses.append("occurred_at >= ?")
        params.append(cutoff)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM error_signals{where} ORDER BY occurred_at DESC, id DESC",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def create_edn_recommendation(
    *, recommendation_type: str, item_number: str, category: str, detail: str,
    evidence_ids: list[str], dedupe_key: str,
) -> int:
    now = _now()
    with _conn() as con:
        cursor = con.execute(
            """INSERT INTO edn_recommendations
               (recommendation_type, item_number, category, detail, evidence_json,
                dedupe_key, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'proposée', ?, ?)""",
            (recommendation_type, item_number, category, detail, json.dumps(evidence_ids), dedupe_key, now, now),
        )
    return int(cursor.lastrowid)


def get_edn_recommendations(*, status: str | None = None) -> list[dict]:
    with _conn() as con:
        if status:
            rows = con.execute(
                "SELECT * FROM edn_recommendations WHERE status = ? ORDER BY created_at DESC, id DESC",
                (status,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM edn_recommendations ORDER BY created_at DESC, id DESC"
            ).fetchall()
    result = []
    for row in rows:
        value = dict(row)
        value["evidence_ids"] = json.loads(value.pop("evidence_json") or "[]")
        result.append(value)
    return result


def get_edn_recommendation(recommendation_id: int) -> dict | None:
    rows = [row for row in get_edn_recommendations() if int(row["id"]) == int(recommendation_id)]
    return rows[0] if rows else None


def update_edn_recommendation(recommendation_id: int, status: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE edn_recommendations SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), int(recommendation_id)),
        )


def _migrate_ai_practice_v1() -> None:
    """Ajoute les colonnes de suivi de maîtrise aux bases existantes."""
    with _conn() as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(ai_practice_sessions)").fetchall()}
        if "mastery_recorded_at" not in columns:
            con.execute("ALTER TABLE ai_practice_sessions ADD COLUMN mastery_recorded_at TEXT")
        if "difficulty" not in columns:
            con.execute("ALTER TABLE ai_practice_sessions ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'standard'")
        question_columns = {
            row[1] for row in con.execute("PRAGMA table_info(ai_practice_questions)").fetchall()
        }
        if "import_metadata_json" not in question_columns:
            con.execute(
                "ALTER TABLE ai_practice_questions "
                "ADD COLUMN import_metadata_json TEXT NOT NULL DEFAULT '{}'"
            )


def _migrate_reliable_practice_loop() -> None:
    """Ajoute le contrat de finalisation et de correction détaillée, sans perte d'historique."""
    with _conn() as con:
        columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(ai_practice_sessions)").fetchall()
        }
        migrations = [
            ("completion_state", "ALTER TABLE ai_practice_sessions ADD COLUMN completion_state TEXT NOT NULL DEFAULT 'draft'"),
            ("score_mode", "ALTER TABLE ai_practice_sessions ADD COLUMN score_mode TEXT NOT NULL DEFAULT ''"),
            ("score_reason", "ALTER TABLE ai_practice_sessions ADD COLUMN score_reason TEXT NOT NULL DEFAULT ''"),
        ]
        for column, statement in migrations:
            if column not in columns:
                con.execute(statement)

        attempt_columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(ai_practice_attempts)").fetchall()
        }
        for column, statement in [
            ("score_mode", "ALTER TABLE ai_practice_attempts ADD COLUMN score_mode TEXT NOT NULL DEFAULT ''"),
            ("score_reason", "ALTER TABLE ai_practice_attempts ADD COLUMN score_reason TEXT NOT NULL DEFAULT ''"),
        ]:
            if column not in attempt_columns:
                con.execute(statement)

        con.executescript("""
            CREATE TABLE IF NOT EXISTS ai_practice_attempt_propositions (
                attempt_id      INTEGER NOT NULL,
                proposition_id  TEXT NOT NULL,
                selected        INTEGER NOT NULL DEFAULT 0,
                expected        INTEGER NOT NULL DEFAULT 0,
                rank            TEXT NOT NULL DEFAULT '',
                points          REAL NOT NULL DEFAULT 0,
                discordance     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (attempt_id, proposition_id),
                FOREIGN KEY (attempt_id) REFERENCES ai_practice_attempts(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS ai_practice_question_items (
                question_id         INTEGER NOT NULL,
                item_number         TEXT NOT NULL,
                oic_code            TEXT NOT NULL DEFAULT '',
                confidence          REAL NOT NULL DEFAULT 1.0,
                source              TEXT NOT NULL DEFAULT 'manual',
                classifier_version  TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (question_id, item_number),
                FOREIGN KEY (question_id) REFERENCES ai_practice_questions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_ai_practice_question_items_item
                ON ai_practice_question_items(item_number);
        """)
        con.execute("""
            UPDATE ai_practice_sessions
            SET completion_state = CASE
                WHEN mastery_recorded_at IS NOT NULL THEN 'recorded'
                WHEN completed_at IS NOT NULL THEN 'scored'
                ELSE 'draft'
            END
            WHERE completion_state IS NULL OR completion_state = '' OR completion_state = 'draft'
        """)
        con.execute("""
            UPDATE ai_practice_sessions
            SET score_mode = 'training'
            WHERE score_percent IS NOT NULL AND (score_mode IS NULL OR score_mode = '')
        """)


def _migrate_uness_annales() -> None:
    """Ajoute la table de regroupement des annales UNESS et son lien depuis les sessions."""
    with _conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS uness_annales (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url   TEXT NOT NULL UNIQUE,
                source       TEXT NOT NULL DEFAULT 'UNESS',
                source_exam_id TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
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
        columns = {row[1] for row in con.execute("PRAGMA table_info(uness_annales)").fetchall()}
        for column, statement in (
            ("source", "ALTER TABLE uness_annales ADD COLUMN source TEXT NOT NULL DEFAULT 'UNESS'"),
            ("source_exam_id", "ALTER TABLE uness_annales ADD COLUMN source_exam_id TEXT NOT NULL DEFAULT ''"),
            ("metadata_json", "ALTER TABLE uness_annales ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"),
        ):
            if column not in columns:
                con.execute(statement)
        columns = {row[1] for row in con.execute("PRAGMA table_info(ai_practice_sessions)").fetchall()}
        if "annale_id" not in columns:
            con.execute(
                "ALTER TABLE ai_practice_sessions ADD COLUMN annale_id INTEGER "
                "REFERENCES uness_annales(id)"
            )
        # Backfill: normalize any source_url stored before URL normalization
        # existed (e.g. a leftover "#section-0" fragment), so a stale row
        # doesn't keep missing lookups against freshly-collected variants of
        # the same course page. Skipped on conflict — a genuine duplicate
        # left as-is is safer than losing one of the two rows silently.
        for row_id, raw_url in con.execute("SELECT id, source_url FROM uness_annales").fetchall():
            normalized = _normalize_uness_source_url(raw_url)
            if normalized != raw_url:
                try:
                    con.execute(
                        "UPDATE uness_annales SET source_url = ? WHERE id = ?", (normalized, row_id)
                    )
                except sqlite3.IntegrityError:
                    pass


_UNESS_RETRY_DELAYS_SECONDS = [30, 120, 600]  # après la 1ère, 2e, 3e tentative


def _migrate_uness_correction_failures() -> None:
    """File d'attente persistante des corrections Gemini en échec (échec total
    ou question manquante) — retry automatique borné + bandeau/badge UI."""
    with _conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS uness_correction_failures (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                bridge_folder   TEXT NOT NULL,
                quiz_title      TEXT NOT NULL,
                collected_at    TEXT NOT NULL,
                error_message   TEXT NOT NULL,
                attempts        INTEGER NOT NULL DEFAULT 0,
                next_retry_at   TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT NOT NULL,
                last_attempt_at TEXT
            )"""
        )


def record_uness_correction_failure(
    *, bridge_folder: str, quiz_title: str, collected_at: str, error_message: str
) -> int:
    """Upsert par (quiz_title, collected_at) : incrémente attempts et repousse
    next_retry_at au lieu de créer une deuxième ligne pour le même quiz qui
    échoue à répétition."""
    from datetime import timedelta

    now = _now()
    with _conn() as con:
        row = con.execute(
            "SELECT id, attempts FROM uness_correction_failures "
            "WHERE quiz_title = ? AND collected_at = ? AND status = 'pending'",
            (quiz_title, collected_at),
        ).fetchone()
        if row is not None:
            attempts = int(row["attempts"]) + 1
            delay = _UNESS_RETRY_DELAYS_SECONDS[min(attempts - 1, len(_UNESS_RETRY_DELAYS_SECONDS) - 1)]
            next_retry_at = (datetime.datetime.fromisoformat(now) + timedelta(seconds=delay)).isoformat()
            con.execute(
                "UPDATE uness_correction_failures SET attempts = ?, next_retry_at = ?, "
                "error_message = ?, bridge_folder = ?, last_attempt_at = ? WHERE id = ?",
                (attempts, next_retry_at, error_message, bridge_folder, now, row["id"]),
            )
            return int(row["id"])
        delay = _UNESS_RETRY_DELAYS_SECONDS[0]
        next_retry_at = (datetime.datetime.fromisoformat(now) + timedelta(seconds=delay)).isoformat()
        cur = con.execute(
            "INSERT INTO uness_correction_failures "
            "(bridge_folder, quiz_title, collected_at, error_message, attempts, "
            "next_retry_at, status, created_at, last_attempt_at) "
            "VALUES (?,?,?,?,1,?,'pending',?,?)",
            (bridge_folder, quiz_title, collected_at, error_message, next_retry_at, now, now),
        )
        return int(cur.lastrowid)


def resolve_uness_correction_failure(quiz_title: str, collected_at: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE uness_correction_failures SET status = 'resolved' "
            "WHERE quiz_title = ? AND collected_at = ? AND status = 'pending'",
            (quiz_title, collected_at),
        )


def get_uness_correction_failure(failure_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM uness_correction_failures WHERE id = ?", (failure_id,)
        ).fetchone()
    return dict(row) if row else None


def list_pending_uness_correction_failures(*, due_only: bool = False) -> list[dict]:
    with _conn() as con:
        if due_only:
            rows = con.execute(
                "SELECT * FROM uness_correction_failures "
                "WHERE status = 'pending' AND attempts < 3 AND next_retry_at <= ? "
                "ORDER BY next_retry_at",
                (_now(),),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM uness_correction_failures WHERE status = 'pending' "
                "ORDER BY created_at DESC"
            ).fetchall()
    return [dict(row) for row in rows]


def count_pending_uness_correction_failures() -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM uness_correction_failures WHERE status = 'pending'"
        ).fetchone()
    return int(row["n"]) if row else 0


def reset_uness_correction_failure_attempts(failure_id: int) -> None:
    """Utilisé par le bouton "Relancer" manuel : redonne 3 tentatives auto
    fraîches plutôt que de laisser l'entrée bloquée si le clic échoue encore."""
    with _conn() as con:
        con.execute(
            "UPDATE uness_correction_failures SET attempts = 0, next_retry_at = ? WHERE id = ?",
            (_now(), failure_id),
        )


# ── API publique — task_id ────────────────────────────────────────────────────

def make_task_id(course_id: str, context: str, review_type: str, due_date: datetime.date) -> str:
    """
    Identifiant stable et unique d'une ReviewTask virtuelle.

    Format : {course_id}_{context}_{review_type}_{due_date_iso}
    Exemple : 256b9fc3-1e69-8055-a266-f7b93ed811ad_college_J7_2026-05-30

    Le due_date dans le task_id est toujours la date THÉORIQUE (Notion),
    jamais la date reportée. Cela permet de retrouver un enregistrement
    même après un report, et de distinguer deux J7 avec des dates différentes
    (si date_1ere_lecture a été modifiée).
    """
    return f"{course_id}_{context}_{review_type}_{due_date.isoformat()}"


# ── API publique — lecture ────────────────────────────────────────────────────

def get_history(task_id: str) -> sqlite3.Row | None:
    """Retourne l'enregistrement SQLite d'une tâche, ou None."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM review_history WHERE task_id = ?", (task_id,)
        ).fetchone()


def get_all_history() -> dict[str, sqlite3.Row]:
    """
    Retourne TOUT l'historique sous la forme {task_id: Row}.
    Appelé une fois par _rebuild_all() pour enrichir les tâches virtuelles.
    """
    with _conn() as con:
        rows = con.execute("SELECT * FROM review_history").fetchall()
    return {row["task_id"]: row for row in rows}


def get_sessions_by_course() -> dict[str, list]:
    """Retourne {course_id: [rows]} pour toutes les study_sessions."""
    with _conn() as con:
        rows = con.execute("SELECT * FROM study_sessions").fetchall()
    result: dict[str, list] = {}
    for row in rows:
        result.setdefault(row["course_id"], []).append(row)
    return result


def get_postpone_counts() -> dict[str, int]:
    """Retourne {course_id: total_postponements} depuis review_history."""
    with _conn() as con:
        rows = con.execute(
            "SELECT course_id, SUM(postponed_count) AS total "
            "FROM review_history GROUP BY course_id"
        ).fetchall()
    return {row["course_id"]: (row["total"] or 0) for row in rows}


def get_all_review_data() -> tuple[dict, dict, dict, set]:
    """
    Single connection, 4 queries batched.
    Remplace les 4 appels séparés dans generate_all_reviews().
    Retourne (history, sessions_map, postpone_map, qcm_done_set).
    """
    with _conn() as con:
        history_rows  = con.execute("SELECT * FROM review_history").fetchall()
        session_rows  = con.execute("SELECT * FROM study_sessions").fetchall()
        postpone_rows = con.execute(
            "SELECT course_id, SUM(postponed_count) AS total "
            "FROM review_history GROUP BY course_id"
        ).fetchall()
        qcm_rows = con.execute(
            "SELECT DISTINCT course_id FROM qcm_sessions"
        ).fetchall()

    history: dict[str, sqlite3.Row] = {r["task_id"]: r for r in history_rows}
    sessions: dict[str, list] = {}
    for r in session_rows:
        sessions.setdefault(r["course_id"], []).append(r)
    postpone: dict[str, int] = {r["course_id"]: (r["total"] or 0) for r in postpone_rows}
    qcm_done: set[str] = {r["course_id"] for r in qcm_rows}
    return history, sessions, postpone, qcm_done


# ── API publique — écriture ───────────────────────────────────────────────────

_SM2_OFFSETS: dict[str, int] = {"J3": 3, "J7": 7, "J14": 14, "J30": 30}
_PREV_REVIEW_TYPE: dict[str, str] = {"J7": "J3", "J14": "J7", "J30": "J14"}


def mark_done(
    task_id: str,
    course_id: str,
    context: str,
    review_type: str,
    theoretical_due_date: datetime.date,
    course_title: str = "",
    item_number: str = "",
    difficulty: str | None = None,
    confidence: int | None = None,
    notes: str | None = None,
    critical_trap: bool = False,
    recurrent_trap: bool = False,
) -> None:
    """
    Marque une révision comme faite.

    Si l'enregistrement n'existe pas encore, il est créé.
    Si il existait (ex : était 'postponed'), il est mis à jour.
    Calcule les valeurs SM-2 (easiness_factor, repetition_count, next_interval_days)
    si confidence est fourni.
    """
    # ── Calcul SM-2 ───────────────────────────────────────────────────────────
    new_ef: float | None = None
    new_rep: int | None = None
    next_interval: int | None = None

    if confidence is not None:
        from backend.core.reviews.sm2 import SM2_INIT_EF, compute_next_interval

        current_ef  = SM2_INIT_EF
        current_rep = 0
        current_interval = _SM2_OFFSETS.get(review_type, 7)

        existing = get_history(task_id)
        if existing:
            current_ef  = existing["easiness_factor"]  or SM2_INIT_EF
            current_rep = existing["repetition_count"] or 0

        next_interval, new_ef = compute_next_interval(
            current_interval_days=current_interval,
            confidence=confidence,
            easiness_factor=current_ef,
            repetition=current_rep,
            critical_trap=critical_trap,
            recurrent_trap=recurrent_trap,
        )
        new_rep = current_rep + 1

    now = _now()
    with _conn() as con:
        con.execute("""
            INSERT INTO review_history
                (task_id, course_id, course_title, item_number, context, review_type,
                 theoretical_due_date, effective_due_date, status,
                 completed_at, difficulty, confidence, notes,
                 easiness_factor, repetition_count, next_interval_days,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,'done',?,?,?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                status             = 'done',
                completed_at       = excluded.completed_at,
                effective_due_date = excluded.effective_due_date,
                postponed_to       = NULL,
                difficulty         = COALESCE(excluded.difficulty,        difficulty),
                confidence         = COALESCE(excluded.confidence,        confidence),
                notes              = COALESCE(excluded.notes,             notes),
                easiness_factor    = COALESCE(excluded.easiness_factor,   easiness_factor),
                repetition_count   = COALESCE(excluded.repetition_count,  repetition_count),
                next_interval_days = COALESCE(excluded.next_interval_days, next_interval_days),
                updated_at         = excluded.updated_at
        """, (
            task_id, course_id, course_title, item_number, context, review_type,
            theoretical_due_date.isoformat(), theoretical_due_date.isoformat(),
            now, difficulty, confidence, notes,
            new_ef, new_rep, next_interval,
            now, now,
        ))


def postpone(
    task_id: str,
    course_id: str,
    context: str,
    review_type: str,
    theoretical_due_date: datetime.date,
    postponed_to: datetime.date,
    course_title: str = "",
    item_number: str = "",
) -> None:
    """
    Reporte une révision à une date ultérieure.

    La date théorique Notion est préservée (theoretical_due_date).
    effective_due_date = postponed_to.
    postponed_count est incrémenté à chaque nouveau report.
    Notion n'est PAS modifié.
    """
    now = _now()
    with _conn() as con:
        con.execute("""
            INSERT INTO review_history
                (task_id, course_id, course_title, item_number, context, review_type,
                 theoretical_due_date, effective_due_date,
                 status, postponed_to, postponed_count, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,'postponed',?,1,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                status          = 'postponed',
                postponed_to    = excluded.postponed_to,
                effective_due_date = excluded.postponed_to,
                postponed_count = postponed_count + 1,
                updated_at      = excluded.updated_at
        """, (
            task_id, course_id, course_title, item_number, context, review_type,
            theoretical_due_date.isoformat(), postponed_to.isoformat(),
            postponed_to.isoformat(), now, now,
        ))


def ignore(
    task_id: str,
    course_id: str,
    context: str,
    review_type: str,
    theoretical_due_date: datetime.date,
    course_title: str = "",
    item_number: str = "",
) -> None:
    """Ignore une révision — elle n'apparaît plus dans le dashboard."""
    now = _now()
    with _conn() as con:
        con.execute("""
            INSERT INTO review_history
                (task_id, course_id, course_title, item_number, context, review_type,
                 theoretical_due_date, effective_due_date,
                 status, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,'ignored',?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                status     = 'ignored',
                updated_at = excluded.updated_at
        """, (
            task_id, course_id, course_title, item_number, context, review_type,
            theoretical_due_date.isoformat(), theoretical_due_date.isoformat(),
            now, now,
        ))


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
) -> datetime.date | None:
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


def get_last_consolidation_state(course_id: str, context: str) -> sqlite3.Row | None:
    """Dernière ligne 'consolidation' done (la plus récente), ou None si jamais amorcée."""
    with _conn() as con:
        return con.execute(
            """SELECT * FROM review_history
               WHERE course_id = ? AND context = ? AND review_type = 'consolidation'
                 AND status = 'done'
               ORDER BY completed_at DESC, id DESC LIMIT 1""",
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

    repetition_count est volontairement seedé à 2 (pas 0) : sm2.compute_next_interval
    a des paliers fixes (3j / 7j) pour repetition 0 et 1, dédiés au cycle J3→J30
    qui démarre toujours "à froid". Ici on démarre déjà avec un intervalle
    mastery-seedé (initial_interval_days) qu'on veut faire croître via l'ease
    factor dès la première vraie validation — pas le réinitialiser à 3 jours.
    Ne PAS "simplifier" ceci en 0 : ça ferait retomber la chaîne consolidation
    sur les paliers fixes du cycle J et annulerait l'intervalle de maîtrise.
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
            SM2_INIT_EF, 2, initial_interval_days,
            now, now,
        ))


def get_consolidation_due_date(course_id: str, context: str) -> datetime.date | None:
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
    difficulty: str | None = None,
    notes: str | None = None,
) -> int:
    """
    Valide une occurrence 'consolidation' et fait progresser la chaîne SM-2.

    Repart de l'état de la DERNIÈRE occurrence complétée (pas de l'occurrence
    courante, qui n'existe pas encore en base tant qu'elle n'a pas de
    completed_at) — sinon l'ease factor et le repetition_count repartiraient
    de zéro à chaque validation, ce qui casserait la croissance des intervalles.

    Retourne le nouvel intervalle (jours), utile pour les tests/logs.
    """
    from backend.core.reviews.sm2 import SM2_INIT_EF, compute_next_interval

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


# ── Migration study_sessions v2 ──────────────────────────────────────────────

def migrate_study_sessions_v2() -> None:
    """Ajoute les colonnes enrichies à study_sessions sur une DB existante."""
    with _conn() as con:
        existing = {
            row["name"]
            for row in con.execute("PRAGMA table_info(study_sessions)").fetchall()
        }
        migrations = [
            ("activity_types",    "ALTER TABLE study_sessions ADD COLUMN activity_types TEXT DEFAULT '[]'"),
            ("qcm_result",        "ALTER TABLE study_sessions ADD COLUMN qcm_result TEXT"),
            ("weak_category",     "ALTER TABLE study_sessions ADD COLUMN weak_category TEXT"),
            ("weak_detail",       "ALTER TABLE study_sessions ADD COLUMN weak_detail TEXT"),
            ("perceived_mastery", "ALTER TABLE study_sessions ADD COLUMN perceived_mastery INTEGER"),
        ]
        for col, sql in migrations:
            if col not in existing:
                con.execute(sql)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_ss_course ON study_sessions(course_id)"
        )


# ── Migration SM-2 columns ────────────────────────────────────────────────────

def _migrate_review_history_sm2() -> None:
    """Ajoute les colonnes SM-2 à review_history (idempotent)."""
    with _conn() as con:
        existing = {
            row["name"]
            for row in con.execute("PRAGMA table_info(review_history)").fetchall()
        }
        migrations = [
            ("easiness_factor",   "ALTER TABLE review_history ADD COLUMN easiness_factor REAL DEFAULT 2.5"),
            ("repetition_count",  "ALTER TABLE review_history ADD COLUMN repetition_count INTEGER DEFAULT 0"),
            ("next_interval_days","ALTER TABLE review_history ADD COLUMN next_interval_days INTEGER"),
        ]
        for col, sql in migrations:
            if col not in existing:
                con.execute(sql)


# ── Migration course_edges table ──────────────────────────────────────────────

def _migrate_course_edges_table() -> None:
    """Crée la table course_edges si absente."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS course_edges (
                source_id  TEXT    NOT NULL,
                target_id  TEXT    NOT NULL,
                weight     REAL    NOT NULL,
                edge_type  TEXT    NOT NULL,
                updated_at TEXT    NOT NULL,
                PRIMARY KEY (source_id, target_id, edge_type)
            );
            CREATE INDEX IF NOT EXISTS idx_ce_source ON course_edges(source_id);
        """)


# ── API publique — sessions de travail ───────────────────────────────────────

def add_study_session(
    course_id: str,
    course_title: str = "",
    item_number: str = "",
    context: str = "college",
    activity_types: list | None = None,
    duration_minutes: int | None = None,
    confidence: int | None = None,
    difficulty: str | None = None,
    qcm_result: str | None = None,
    weak_category: str | None = None,
    weak_detail: str | None = None,
    perceived_mastery: int | None = None,
    notes: str | None = None,
) -> int:
    """Enregistre une session de travail après validation d'une révision."""
    import json as _json

    types = activity_types or ["révision"]
    session_type = types[0] if types else "révision"
    today = datetime.date.today().isoformat()
    now = _now()

    with _conn() as con:
        cur = con.execute("""
            INSERT INTO study_sessions
                (course_id, course_title, item_number, context, session_date,
                 duration_minutes, session_type, activity_types,
                 confidence, difficulty, qcm_result, weak_category,
                 weak_detail, perceived_mastery, notes, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            course_id, course_title, item_number, context, today,
            duration_minutes, session_type, _json.dumps(types, ensure_ascii=False),
            confidence, difficulty, qcm_result, weak_category,
            weak_detail, perceived_mastery, notes, now, now,
        ))
        session_id: int = cur.lastrowid

    category = (weak_category or "").strip()
    if item_number and category and category.casefold() != "aucune":
        try:
            check_and_propose_recurring_study_feedback(
                item_number=item_number,
                error_type=category,
                new_session_id=session_id,
                course_title=course_title,
                course_id=course_id,
            )
        except Exception as exc:
            logger.warning(f"Recurring study feedback gap (non-bloquant): {exc}")

    return session_id


def delete_study_session(session_id: int) -> None:
    """Supprime une session créée par un workflow qui doit être compensé."""
    import json as _json

    with _conn() as con:
        token = f"study:{int(session_id)}"
        proposals = con.execute(
            "SELECT id, session_ids FROM pending_gap_proposals WHERE status = 'pending'"
        ).fetchall()
        for proposal in proposals:
            try:
                session_ids = _json.loads(proposal["session_ids"] or "[]")
            except (TypeError, ValueError):
                continue
            if token not in session_ids:
                continue
            remaining = [sid for sid in session_ids if sid != token]
            if len(remaining) < RECURRENCE_THRESHOLD:
                con.execute("DELETE FROM pending_gap_proposals WHERE id = ?", (proposal["id"],))
            else:
                con.execute(
                    "UPDATE pending_gap_proposals SET session_ids = ?, occurrence_count = ? WHERE id = ?",
                    (_json.dumps(remaining), len(remaining), proposal["id"]),
                )
        con.execute("DELETE FROM study_sessions WHERE id = ?", (int(session_id),))


def record_manual_review(
    course_id: str,
    course_title: str,
    item_number: str,
    context: str,
    review_date: datetime.date,
    activity_types: list[str],
    duration_minutes: int | None,
    confidence: int | None,
    difficulty: str | None,
    qcm_result: str | None = None,
    weak_category: str | None = None,
    weak_detail: str | None = None,
    notes: str | None = None,
) -> str:
    """Ajoute une séance manuelle dans la timeline et les sessions d'étude."""
    import json as _json

    if not isinstance(review_date, datetime.date):
        raise TypeError("review_date must be a date")
    if confidence is not None and not 1 <= int(confidence) <= 5:
        raise ValueError("confidence must be between 1 and 5")
    types = list(dict.fromkeys(activity_types or ["révision"]))
    session_type = types[0]
    date_str = review_date.isoformat()
    now = _now()
    task_id = f"manual_{course_id}_{date_str}_{uuid.uuid4().hex[:10]}"
    with _conn() as con:
        con.execute(
            """
            INSERT INTO review_history
                (task_id, course_id, course_title, item_number, context, review_type,
                 theoretical_due_date, effective_due_date, status, completed_at,
                 difficulty, confidence, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'manuel', ?, ?, 'done', ?, ?, ?, ?, ?, ?)
            """,
            (task_id, course_id, course_title, item_number, context,
             date_str, date_str, date_str, difficulty, confidence, notes, now, now),
        )
        con.execute(
            """
            INSERT INTO study_sessions
                (course_id, course_title, item_number, context, session_date,
                 duration_minutes, session_type, activity_types, confidence,
                 difficulty, qcm_result, weak_category, weak_detail, notes,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (course_id, course_title, item_number, context, date_str,
             duration_minutes, session_type, _json.dumps(types, ensure_ascii=False),
             confidence, difficulty, qcm_result, weak_category, weak_detail,
             notes, now, now),
        )
    return task_id


def get_manual_review_count(course_id: str) -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM review_history WHERE course_id = ? "
            "AND review_type = 'manuel' AND status = 'done'",
            (course_id,),
        ).fetchone()
    return int(row[0] if row else 0)


def get_manual_reviews_by_course(course_id: str) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            "SELECT * FROM review_history WHERE course_id = ? "
            "AND review_type = 'manuel' AND status = 'done' "
            "ORDER BY completed_at DESC, id DESC",
            (course_id,),
        ).fetchall()


def record_anki_review(
    card_id: int,
    note_id: int | None,
    item_numbers: tuple[str, ...],
    rating: str,
    reviewed_at: datetime.datetime,
    interval: int | None,
    source_review_id: str | None,
) -> str:
    """Enregistre une réponse Anki une seule fois pour chaque item associé."""
    if rating not in {"again", "hard", "good", "easy"}:
        raise ValueError(f"Invalid Anki rating: {rating}")
    timestamp = reviewed_at.isoformat()
    identity = source_review_id or f"{card_id}|{timestamp}|{rating}|{interval or 0}"
    event_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    now = _now()
    normalized_items = tuple(dict.fromkeys(str(item).strip() for item in item_numbers if str(item).strip()))
    with _conn() as con:
        for item_number in normalized_items:
            con.execute(
                """
                INSERT OR IGNORE INTO anki_review_evidence
                    (event_key, card_id, note_id, item_number, rating,
                     reviewed_at, interval, source_review_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_key, int(card_id), note_id, item_number, rating,
                 timestamp, interval, source_review_id, now),
            )
    return event_key


def get_anki_review_evidence(item_number: str | None = None) -> list[sqlite3.Row]:
    with _conn() as con:
        if item_number is None:
            return con.execute(
                "SELECT * FROM anki_review_evidence ORDER BY reviewed_at DESC, id DESC"
            ).fetchall()
        return con.execute(
            "SELECT * FROM anki_review_evidence WHERE item_number = ? "
            "ORDER BY reviewed_at DESC, id DESC",
            (str(item_number),),
        ).fetchall()


# ── Migration depuis l'ancien système JSON ────────────────────────────────────

def migrate_from_done_ids(done_ids: set, courses_map: dict) -> int:
    """
    Migration one-shot depuis data_store.done_review_ids (ancien format JSON).

    Ancien format : "{course_id}_{review_type}"
    Nouveau format : "{course_id}_{context}_{review_type}_{due_date}"

    Paramètres :
        done_ids    : data_store.done_review_ids (set de str)
        courses_map : {course_id: Cours} pour calculer les due_dates
    Retourne le nombre d'enregistrements migrés.
    """
    from datetime import timedelta
    OFFSETS = {"J3": 3, "J7": 7, "J14": 14, "J30": 30}
    migrated = 0

    for old_id in done_ids:
        # Sépare course_id (avec tirets) et review_type par le dernier '_'
        parts = old_id.rsplit("_", 1)
        if len(parts) != 2:
            continue
        course_id, review_type = parts

        if review_type not in OFFSETS:
            # "bonus" ou autre : on ignore silencieusement
            continue

        c = courses_map.get(course_id)
        if not c or not c.date_1ere_lecture:
            continue

        theoretical = c.date_1ere_lecture + timedelta(days=OFFSETS[review_type])
        task_id = make_task_id(course_id, "college", review_type, theoretical)

        try:
            mark_done(
                task_id=task_id,
                course_id=course_id,
                context="college",
                review_type=review_type,
                theoretical_due_date=theoretical,
                course_title=c.title,
                item_number=c.item_number or "",
                notes="Migré depuis done_review_ids JSON",
            )
            migrated += 1
        except Exception as exc:
            logger.warning(f"Migration skip {old_id}: {exc}")

    if migrated:
        logger.success(f"Migration SQLite : {migrated} révision(s) importée(s)")
    return migrated


# ── API publique — QCM Sessions ──────────────────────────────────────────────

def add_qcm_session(
    course_id: str,
    platform: str,
    session_date: str,
    course_title: str = "",
    item_number: str = "",
    score: float | None = None,
    total_questions: int | None = None,
    errors: str | None = None,
    comments: str | None = None,
) -> int:
    """Enregistre une session de QCM locale."""
    now = _now()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO qcm_sessions
                (course_id, course_title, item_number, platform, session_date,
                 score, total_questions, errors, comments, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            course_id, course_title, item_number, platform, session_date,
            score, total_questions, errors, comments, now, now,
        ))
        return cur.lastrowid


def get_qcm_sessions_by_course(course_id: str) -> list[sqlite3.Row]:
    """Retourne l'historique des QCM pour un cours donné, du plus récent au plus ancien."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM qcm_sessions WHERE course_id = ? ORDER BY session_date DESC, created_at DESC",
            (course_id,)
        ).fetchall()


def get_qcm_done_course_ids() -> set[str]:
    """Retourne l'ensemble des course_id ayant au moins une session de QCM."""
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT course_id FROM qcm_sessions").fetchall()
    return {row["course_id"] for row in rows}


# ── API publique — questions IA rejouables ──────────────────────────────────

def _ai_question_hash(question: dict) -> str:
    import json as _json
    payload = {
        "kind": getattr(question.get("kind"), "value", question.get("kind", "")),
        "prompt": str(question.get("prompt", "")).strip(),
        "choices": list(question.get("choices") or []),
        "answer": str(question.get("answer", "")).strip(),
        "explanation": str(question.get("explanation", "")).strip(),
    }
    return hashlib.sha256(
        _json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def create_ai_practice_session(*, spec, questions: list[dict], model: str) -> int:
    """Crée une session et conserve chaque question comme version immuable."""
    import json as _json
    now = _now()
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO ai_practice_sessions
               (course_id, course_title, item_number, objective_code, practice_kind,
               total_questions, open_questions, closed_questions, difficulty, model, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                spec.course_id, spec.course_title, spec.item_number, spec.objective_code,
                spec.practice_kind.value, spec.total_questions, spec.open_questions,
                spec.closed_questions, spec.difficulty.value, model, now,
            ),
        )
        session_id = int(cur.lastrowid)
        for position, question in enumerate(questions, start=1):
            kind = getattr(question.get("kind"), "value", question.get("kind", ""))
            cur = con.execute(
                """INSERT INTO ai_practice_questions
                   (course_id, item_number, objective_code, practice_kind, question_kind,
                    position, prompt, choices_json, answer, explanation, source_refs_json,
                    import_metadata_json, model, question_hash, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    spec.course_id, spec.item_number, spec.objective_code,
                    spec.practice_kind.value, kind, position,
                    question["prompt"], _json.dumps(list(question.get("choices") or []), ensure_ascii=False),
                    question["answer"], question["explanation"],
                    _json.dumps(list(question.get("source_refs") or []), ensure_ascii=False),
                    _json.dumps(dict(question.get("import_metadata") or {}), ensure_ascii=False),
                    model, _ai_question_hash(question), now,
                ),
            )
            con.execute(
                "INSERT INTO ai_practice_session_questions(session_id, question_id, position) VALUES (?,?,?)",
                (session_id, int(cur.lastrowid), position),
            )
            question_item_numbers = tuple(dict.fromkeys(
                str(item).strip() for item in question.get("item_numbers", ()) if str(item).strip()
            ))
            if (
                not question_item_numbers
                and spec.item_number
                and question.get("allow_session_item_fallback", True)
            ):
                question_item_numbers = (spec.item_number,)
            for question_item in question_item_numbers:
                con.execute(
                    """INSERT OR IGNORE INTO ai_practice_question_items
                       (question_id, item_number, confidence, source, classifier_version)
                       VALUES (?,?,?,?,?)""",
                    (
                        int(cur.lastrowid), question_item,
                        float(question.get("item_classification_confidence", 1.0)),
                        str(question.get("item_classification_source") or "rule"),
                        str(question.get("item_classifier_version") or "session-primary-v1"),
                    ),
                )
        item_numbers = tuple(dict.fromkeys(
            n for n in (spec.item_numbers or ((spec.item_number,) if spec.item_number else ()))
            if n
        ))
        for item_number in item_numbers:
            con.execute(
                "INSERT OR IGNORE INTO ai_practice_session_items(session_id, item_number) VALUES (?,?)",
                (session_id, item_number),
            )
    return session_id


def _normalize_uness_source_url(source_url: str) -> str:
    """Collapse cosmetic URL differences (fragment, trailing slash, whitespace)
    that don't change which UNESS course page is being referenced. Without
    this, the same partiel collected once with a "#section-0" anchor and once
    without silently creates two annale rows instead of one — the second one
    an orphan with no sessions ever attached to it."""
    from urllib.parse import urlsplit, urlunsplit

    cleaned = (source_url or "").strip()
    if not cleaned:
        return cleaned
    parts = urlsplit(cleaned)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), parts.query, ""))


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
    source: str = "UNESS",
    source_exam_id: str = "",
    metadata_json: str = "{}",
) -> int:
    """Create one grouping row for a UNESS partiel. Raises sqlite3.IntegrityError on a duplicate source_url."""
    source_url = _normalize_uness_source_url(source_url)
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO uness_annales
               (source_url, source, source_exam_id, metadata_json, collected_at, faculte, niveau,
                annee, matiere, titre, type_annale, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                source_url, source, source_exam_id, metadata_json, collected_at, faculte, niveau,
                annee, matiere, titre, type_annale, _now(),
            ),
        )
        return int(cur.lastrowid)


def update_uness_annale(
    annale_id: int,
    *,
    titre: str | None = None,
    faculte: str | None = None,
    matiere: str | None = None,
    annee: int | None = None,
) -> None:
    """Patch a UNESS annale's editable metadata (rename, or correct fields the
    automatic import couldn't extract). Only non-None arguments are updated."""
    updates = {
        "titre": titre,
        "faculte": faculte,
        "matiere": matiere,
        "annee": annee,
    }
    fields = {key: value for key, value in updates.items() if value is not None}
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with _conn() as con:
        con.execute(
            f"UPDATE uness_annales SET {assignments} WHERE id = ?",
            (*fields.values(), annale_id),
        )


def get_uness_annale_by_source_url(source_url: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM uness_annales WHERE source_url = ?",
            (_normalize_uness_source_url(source_url),),
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


def delete_uness_annale(annale_id: int) -> bool:
    """Delete an annale and every imported sub-part session under it."""
    with _conn() as con:
        exists = con.execute("SELECT 1 FROM uness_annales WHERE id = ?", (annale_id,)).fetchone()
        if exists is None:
            return False
        session_ids = [
            row[0]
            for row in con.execute(
                "SELECT id FROM ai_practice_sessions WHERE annale_id = ?", (annale_id,)
            ).fetchall()
        ]
        for session_id in session_ids:
            con.execute("DELETE FROM ai_practice_sessions WHERE id = ?", (session_id,))
        con.execute("DELETE FROM uness_annales WHERE id = ?", (annale_id,))
        return True


def _migrate_uness_scanned_catalog() -> None:
    with _conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS uness_scanned_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT UNIQUE NOT NULL,
                faculte TEXT NOT NULL,
                matiere TEXT NOT NULL,
                annee INTEGER,
                titre TEXT NOT NULL,
                quiz_count INTEGER DEFAULT 0,
                total_questions INTEGER,
                is_single_dp INTEGER DEFAULT 0,
                scanned_at TEXT NOT NULL,
                status TEXT DEFAULT 'available'
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_uness_scanned_matiere ON uness_scanned_catalog(matiere)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_uness_scanned_faculte ON uness_scanned_catalog(faculte)"
        )


def upsert_scanned_catalog_annale(
    *,
    source_url: str,
    faculte: str,
    matiere: str,
    annee: int | None,
    titre: str,
    quiz_count: int = 0,
    total_questions: int | None = None,
    is_single_dp: bool = False,
) -> None:
    """Insert or update a scanned UNESS exam in the local SQLite catalog."""
    source_url = _normalize_uness_source_url(source_url)
    with _conn() as con:
        con.execute(
            """INSERT INTO uness_scanned_catalog
               (source_url, faculte, matiere, annee, titre, quiz_count, total_questions, is_single_dp, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_url) DO UPDATE SET
                   faculte = excluded.faculte,
                   matiere = excluded.matiere,
                   annee = excluded.annee,
                   titre = excluded.titre,
                   quiz_count = excluded.quiz_count,
                   total_questions = excluded.total_questions,
                   is_single_dp = excluded.is_single_dp,
                   scanned_at = excluded.scanned_at""",
            (
                source_url,
                faculte,
                matiere,
                annee,
                titre,
                quiz_count,
                total_questions,
                1 if is_single_dp else 0,
                _now(),
            ),
        )


def list_scanned_catalog_annales(
    *,
    matiere: str = "",
    faculte: str = "",
    only_unimported: bool = False,
) -> list[dict]:
    """List scanned UNESS catalog exams, optionally filtered by subject, faculty, or import status."""
    clauses = []
    params: list = []

    if matiere.strip():
        clauses.append("c.matiere = ?")
        params.append(matiere.strip())
    if faculte.strip():
        clauses.append("c.faculte = ?")
        params.append(faculte.strip())
    if only_unimported:
        clauses.append("a.id IS NULL")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _conn() as con:
        rows = con.execute(
            f"""SELECT c.*,
                       CASE WHEN a.id IS NOT NULL THEN 1 ELSE 0 END AS is_imported
                FROM uness_scanned_catalog c
                LEFT JOIN uness_annales a ON a.source_url = c.source_url
                {where}
                ORDER BY c.quiz_count DESC, CASE WHEN c.annee IS NULL THEN 0 ELSE c.annee END DESC, c.titre ASC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def mark_scanned_annale_imported(source_url: str) -> None:
    source_url = _normalize_uness_source_url(source_url)
    with _conn() as con:
        con.execute(
            "UPDATE uness_scanned_catalog SET status = 'imported' WHERE source_url = ?",
            (source_url,),
        )


def list_annale_sessions(annale_id: int) -> list[dict]:
    """Sub-part sessions for one annale, grouping by root session to show the latest attempt."""
    with _conn() as con:
        # Get all root sessions (imported sub-parts with replay_of_session_id IS NULL)
        roots = con.execute(
            """SELECT s.*
               FROM ai_practice_sessions s
               WHERE s.annale_id = ? AND s.replay_of_session_id IS NULL
               ORDER BY s.id ASC""",
            (annale_id,),
        ).fetchall()
        
        result = []
        for root in roots:
            root_dict = dict(root)
            root_id = root_dict["id"]
            # Find the most recent session in this chain (either root or latest replay)
            latest = con.execute(
                """SELECT s.*,
                          CASE WHEN s.completed_at IS NULL THEN 'pending' ELSE 'completed' END AS status
                   FROM ai_practice_sessions s
                   WHERE s.id = ? OR s.replay_of_session_id = ?
                   ORDER BY s.id DESC LIMIT 1""",
                (root_id, root_id),
            ).fetchone()
            if latest:
                result.append(dict(latest))
            else:
                root_dict["status"] = "completed" if root_dict.get("completed_at") else "pending"
                result.append(root_dict)
    return result


def set_session_annale_id(session_id: int, annale_id: int) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE ai_practice_sessions SET annale_id = ? WHERE id = ?", (annale_id, session_id)
        )


def replay_ai_practice_session(session_id: int) -> int:
    """Crée une nouvelle tentative sur exactement les mêmes questions."""
    with _conn() as con:
        source = con.execute(
            "SELECT * FROM ai_practice_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if source is None:
            raise ValueError(f"Session IA introuvable : {session_id}")
        rows = con.execute(
            "SELECT question_id, position FROM ai_practice_session_questions WHERE session_id = ? ORDER BY position",
            (session_id,),
        ).fetchall()
        if not rows:
            raise ValueError(f"Session IA sans questions rejouables : {session_id}")
        now = _now()
        cur = con.execute(
            """INSERT INTO ai_practice_sessions
               (course_id, course_title, item_number, objective_code, practice_kind,
                total_questions, open_questions, closed_questions, difficulty, model,
                annale_id, replay_of_session_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(source[key] for key in (
                "course_id", "course_title", "item_number", "objective_code",
                "practice_kind", "total_questions", "open_questions", "closed_questions",
                "difficulty", "model", "annale_id",
            )) + (session_id, now),
        )
        new_id = int(cur.lastrowid)
        con.executemany(
            "INSERT INTO ai_practice_session_questions(session_id, question_id, position) VALUES (?,?,?)",
            [(new_id, row["question_id"], row["position"]) for row in rows],
        )
    return new_id


def set_ai_practice_session_items(session_id: int, item_number: str, item_numbers) -> None:
    """Renseigne item_number après-coup sur une session déjà importée (session +
    ses questions) et remplace intégralement sa liste multi-items — utilisé par
    le script de rattrapage (scripts/backfill_uness_item_numbers.py) et par la
    passe de correction des classifications sur-larges
    (scripts/refine_uness_overbroad_items.py). Remplace plutôt qu'accumule :
    une reclassification doit pouvoir corriger une liste trop large, pas
    l'étendre."""
    with _conn() as con:
        con.execute("UPDATE ai_practice_sessions SET item_number = ? WHERE id = ?", (item_number, session_id))
        con.execute(
            """UPDATE ai_practice_questions SET item_number = ?
               WHERE id IN (SELECT question_id FROM ai_practice_session_questions WHERE session_id = ?)""",
            (item_number, session_id),
        )
        con.execute("DELETE FROM ai_practice_session_items WHERE session_id = ?", (session_id,))
        for n in dict.fromkeys(x for x in item_numbers if x):
            con.execute(
                "INSERT OR IGNORE INTO ai_practice_session_items(session_id, item_number) VALUES (?,?)",
                (session_id, n),
            )


def get_dp_count_by_item() -> dict[str, int]:
    """Nombre de DP distincts couvrant chaque item EDN (item principal OU
    secondaire d'un DP transverse) — sert au panneau « Couverture DP par
    item » (Paramètres) pour repérer les items sans cas personnalisé à créer
    manuellement plutôt qu'à l'aveugle."""
    with _conn() as con:
        rows = con.execute(
            """SELECT item_number, COUNT(DISTINCT session_id) AS n FROM (
                   SELECT id AS session_id, item_number FROM ai_practice_sessions
                   WHERE practice_kind = 'DP' AND TRIM(COALESCE(item_number, '')) != ''
                   UNION ALL
                   SELECT i.session_id, i.item_number FROM ai_practice_session_items i
                   JOIN ai_practice_sessions s ON s.id = i.session_id
                   WHERE s.practice_kind = 'DP'
               )
               GROUP BY item_number"""
        ).fetchall()
    return {row["item_number"]: row["n"] for row in rows}


def get_ai_practice_sessions(*, item_number: str = "", course_id: str = "", limit: int = 50) -> list:
    """Retourne les sessions IA, plus récentes en premier.

    `item_number` matche à la fois l'item principal (colonne historique) et
    tout item secondaire d'un DP transverse (table ai_practice_session_items) —
    un DP tagué sur les items 218 et 334 compte comme évidence pour les deux.
    """
    clauses, params = [], []
    if item_number:
        clauses.append(
            "(item_number = ? OR id IN (SELECT session_id FROM ai_practice_session_items WHERE item_number = ?))"
        )
        params.extend((item_number, item_number))
    if course_id:
        clauses.append("course_id = ?")
        params.append(course_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn() as con:
        return con.execute(
            f"SELECT * FROM ai_practice_sessions {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()


def delete_pending_ai_practice_session(session_id: int) -> bool:
    """Supprime une session IA encore à faire, sans toucher aux questions immuables."""
    with _conn() as con:
        session = con.execute(
            "SELECT completed_at, score_percent FROM ai_practice_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None or session["completed_at"] is not None or session["score_percent"] is not None:
            return False
        con.execute("DELETE FROM ai_practice_sessions WHERE id = ?", (session_id,))
    return True


def delete_ai_practice_session(session_id: int) -> bool:
    """Supprime une session IA de l'historique, terminée ou non."""
    with _conn() as con:
        cur = con.execute("DELETE FROM ai_practice_sessions WHERE id = ?", (session_id,))
    return cur.rowcount > 0


def get_ai_practice_session(session_id: int) -> list:
    """Retourne les questions d'une session avec toutes leurs tentatives."""
    import json as _json
    with _conn() as con:
        rows = con.execute(
            """SELECT q.*, sq.position AS session_position
               FROM ai_practice_session_questions sq
               JOIN ai_practice_questions q ON q.id = sq.question_id
               WHERE sq.session_id = ? ORDER BY sq.position""",
            (session_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["choices"] = _json.loads(item.pop("choices_json") or "[]")
            item["source_refs"] = _json.loads(item.pop("source_refs_json") or "[]")
            item["import_metadata"] = _json.loads(item.pop("import_metadata_json") or "{}")
            for key in ("uness", "correction"):
                if key in item["import_metadata"]:
                    item[key] = item["import_metadata"][key]
            attempts = con.execute(
                """SELECT * FROM ai_practice_attempts
                   WHERE session_id = ? AND question_id = ?
                     AND TRIM(COALESCE(response, '')) NOT IN ('', '[]')
                   ORDER BY answered_at DESC""",
                (session_id, row["id"]),
            ).fetchall()
            item["attempts"] = [dict(attempt) for attempt in attempts]
            result.append(item)
    return result


def get_ai_practice_session_summary(session_id: int) -> dict | None:
    """Retourne les metadonnees et la derniere tentative de chaque question."""
    with _conn() as con:
        session = con.execute(
            "SELECT * FROM ai_practice_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            return None
        latest = con.execute(
            """SELECT a.*, sq.position AS question_position
               FROM ai_practice_attempts a
               JOIN ai_practice_session_questions sq
                 ON sq.session_id = a.session_id AND sq.question_id = a.question_id
               JOIN (
                 SELECT question_id, MAX(id) AS max_id
                 FROM ai_practice_attempts
                 WHERE session_id = ?
                   AND TRIM(COALESCE(response, '')) NOT IN ('', '[]')
                 GROUP BY question_id
               ) latest ON latest.max_id = a.id
               WHERE a.session_id = ? ORDER BY sq.position""",
            (session_id, session_id),
        ).fetchall()

    latest_attempts = [dict(row) for row in latest]
    scored_count = sum(attempt["score_percent"] is not None for attempt in latest_attempts)
    correct_count = sum(attempt["is_correct"] == 1 for attempt in latest_attempts)
    incorrect_count = sum(attempt["is_correct"] == 0 for attempt in latest_attempts)
    return {
        **dict(session),
        "answered_count": len(latest_attempts),
        "scored_count": scored_count,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "unanswered_count": max(0, session["total_questions"] - len(latest_attempts)),
        "latest_attempts": latest_attempts,
    }


def get_ai_practice_sessions_history(
    limit: int = 100, query: str = "", status: str = "all", exclude_uness: bool = False
) -> list[dict]:
    """Retourne l'historique borne des sessions avec leurs compteurs.

    `exclude_uness` drops sessions attached to a UNESS annale (`annale_id` set) —
    those already have their own dedicated view under /annales and would otherwise
    clutter the regular QCM history."""
    clauses = []
    params: list = []
    if query.strip():
        pattern = f"%{query.strip().lower()}%"
        clauses.append("(LOWER(s.course_title) LIKE ? OR LOWER(s.item_number) LIKE ?)")
        params.extend((pattern, pattern))
    if status == "pending":
        clauses.append("s.completed_at IS NULL")
    elif status == "completed":
        clauses.append("s.completed_at IS NOT NULL")
    if exclude_uness:
        clauses.append("s.annale_id IS NULL")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(0, limit))
    with _conn() as con:
        rows = con.execute(
            f"""WITH latest AS (
                    SELECT a.session_id, a.question_id, a.is_correct, a.score_percent,
                           a.duration_seconds
                    FROM ai_practice_attempts a
                    JOIN (
                        SELECT session_id, question_id, MAX(id) AS max_id
                        FROM ai_practice_attempts
                        WHERE TRIM(COALESCE(response, '')) NOT IN ('', '[]')
                        GROUP BY session_id, question_id
                    ) current ON current.max_id = a.id
                )
                SELECT s.*, COUNT(latest.question_id) AS answered_count,
                       COUNT(latest.score_percent) AS scored_count,
                       COALESCE(SUM(CASE WHEN latest.is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct_count,
                       COALESCE(SUM(CASE WHEN latest.is_correct = 0 THEN 1 ELSE 0 END), 0) AS incorrect_count,
                       MAX(0, s.total_questions - COUNT(latest.question_id)) AS unanswered_count,
                       SUM(latest.duration_seconds) AS duration_seconds,
                       EXISTS (
                           SELECT 1
                           FROM ai_practice_session_questions sq
                           WHERE sq.session_id = s.id
                       ) AS has_questions,
                       CASE WHEN s.completed_at IS NULL THEN 'pending' ELSE 'completed' END AS status
                FROM ai_practice_sessions s
                LEFT JOIN latest ON latest.session_id = s.id
                {where}
                GROUP BY s.id
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?""",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_ai_practice_failure_streak(session_id: int, threshold: float = 70.0) -> int:
    """Compte les sessions terminées sous le seuil, jusqu'à la dernière session donnée."""
    with _conn() as con:
        current = con.execute(
            "SELECT course_id, item_number, created_at FROM ai_practice_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if current is None:
            return 0
        rows = con.execute(
            """SELECT score_percent FROM ai_practice_sessions
               WHERE course_id = ? AND item_number = ? AND completed_at IS NOT NULL
               ORDER BY created_at DESC, id DESC""",
            (current["course_id"], current["item_number"]),
        ).fetchall()
    streak = 0
    for row in rows:
        if row["score_percent"] is None or float(row["score_percent"]) >= threshold:
            break
        streak += 1
    return streak


def get_ai_practice_history(*, item_number: str, limit: int = 100) -> list:
    """Historique consultable d'un ITEM, questions et réponses incluses."""
    with _conn() as con:
        sessions = con.execute(
            """SELECT id, created_at, completed_at, practice_kind, model, difficulty,
                      score_percent
               FROM ai_practice_sessions
               WHERE item_number = ?
               ORDER BY id DESC LIMIT ?""",
            (item_number, limit),
        ).fetchall()
    history = []
    for session in sessions:
        history.append({"session": dict(session), "questions": get_ai_practice_session(session["id"])})
    return history


def record_ai_practice_attempt(
    *, session_id: int, question_id: int, response: str,
    is_correct: bool | None = None, score_percent: float | None = None,
    duration_seconds: int | None = None, hints_used: int = 0, finalize_session: bool = True,
    score_mode: str = "", score_reason: str = "",
) -> int:
    """Enregistre une réponse sans modifier l'énoncé ni sa correction."""
    now = _now()
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO ai_practice_attempts
               (session_id, question_id, response, is_correct, score_percent,
                duration_seconds, hints_used, answered_at, score_mode, score_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session_id, question_id, response, None if is_correct is None else int(is_correct),
             score_percent, duration_seconds, hints_used, now, score_mode, score_reason),
        )
        if score_percent is not None and finalize_session:
            avg = con.execute(
                "SELECT AVG(score_percent) FROM ai_practice_attempts WHERE session_id = ? AND score_percent IS NOT NULL",
                (session_id,),
            ).fetchone()[0]
            con.execute(
                "UPDATE ai_practice_sessions SET score_percent = ?, completed_at = ? WHERE id = ?",
                (avg, now, session_id),
            )
        return int(cur.lastrowid)


def replace_ai_practice_attempt_propositions(attempt_id: int, propositions: list[dict]) -> None:
    """Remplace la correction détaillée d'une tentative de manière idempotente."""
    with _conn() as con:
        con.execute("DELETE FROM ai_practice_attempt_propositions WHERE attempt_id = ?", (attempt_id,))
        for row in propositions:
            con.execute(
                """INSERT INTO ai_practice_attempt_propositions
                   (attempt_id, proposition_id, selected, expected, rank, points, discordance)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    attempt_id,
                    str(row.get("proposition_id") or ""),
                    int(bool(row.get("selected"))),
                    int(bool(row.get("expected"))),
                    str(row.get("rank") or ""),
                    float(row.get("points") or 0),
                    str(row.get("discordance") or ""),
                ),
            )


def get_ai_practice_attempt_propositions(attempt_id: int) -> list[dict]:
    import json as _json

    with _conn() as con:
        rows = [dict(row) for row in con.execute(
            """SELECT proposition_id, selected, expected, rank, points, discordance
               FROM ai_practice_attempt_propositions
               WHERE attempt_id = ? ORDER BY proposition_id""",
            (attempt_id,),
        ).fetchall()]
        question = con.execute(
            """SELECT q.choices_json
               FROM ai_practice_attempts a
               JOIN ai_practice_questions q ON q.id = a.question_id
               WHERE a.id = ?""",
            (attempt_id,),
        ).fetchone()

    try:
        choices = _json.loads(question["choices_json"] or "[]") if question else []
    except (TypeError, ValueError):
        choices = []
    proposition_texts = {}
    for index, choice in enumerate(choices):
        if isinstance(choice, dict):
            proposition_id = str(choice.get("id") or choice.get("label") or chr(ord("A") + index)).upper()
            text = str(choice.get("text") or choice.get("texte") or choice.get("label") or proposition_id)
        else:
            proposition_id = chr(ord("A") + index)
            text = str(choice)
        proposition_texts[proposition_id] = text
    return [
        {**row, "text": proposition_texts.get(str(row["proposition_id"]).upper(), "")}
        for row in rows
    ]


def get_ai_practice_question_items(question_id: int) -> list[dict]:
    with _conn() as con:
        return [dict(row) for row in con.execute(
            """SELECT item_number, oic_code, confidence, source, classifier_version
               FROM ai_practice_question_items WHERE question_id = ?
               ORDER BY item_number""",
            (question_id,),
        ).fetchall()]


def finalize_ai_practice_session(session_id: int) -> dict | None:
    """Score une session complète une seule fois, sans laisser les effets annexes la bloquer."""
    with _conn() as con:
        session = con.execute(
            "SELECT * FROM ai_practice_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            return None
        latest = con.execute(
            """SELECT a.* FROM ai_practice_attempts a
               JOIN (
                 SELECT question_id, MAX(id) AS max_id
                 FROM ai_practice_attempts
                 WHERE session_id = ?
                   AND TRIM(COALESCE(response, '')) NOT IN ('', '[]')
                 GROUP BY question_id
               ) latest ON latest.max_id = a.id
               WHERE a.session_id = ?""",
            (session_id, session_id),
        ).fetchall()
        question_rows = con.execute(
            """SELECT question_id, position FROM ai_practice_session_questions
               WHERE session_id = ? ORDER BY position""",
            (session_id,),
        ).fetchall()
        latest_by_question = {int(row["question_id"]): row for row in latest}
        missing_positions = [
            int(question["position"])
            for question in question_rows
            if question["question_id"] not in latest_by_question
            or latest_by_question[question["question_id"]]["score_percent"] is None
        ]
        scored = [row["score_percent"] for row in latest if row["score_percent"] is not None]
        state = str(session["completion_state"] or "draft")
        if missing_positions or state in {"scored", "recorded"}:
            updated = session
        else:
            score = round(sum(scored) / len(scored), 2)
            attempt_modes = {str(row["score_mode"] or "") for row in latest}
            score_mode = "edn" if attempt_modes == {"edn"} else "training"
            score_reason = next(
                (str(row["score_reason"] or "") for row in latest if row["score_reason"]),
                "" if score_mode == "edn" else "Score d'entraînement non calibré EDN.",
            )
            con.execute(
                """UPDATE ai_practice_sessions
                   SET score_percent = ?, completed_at = ?, completion_state = 'scored',
                       score_mode = ?, score_reason = ?
                   WHERE id = ?""",
                (score, _now(), score_mode, score_reason, session_id),
            )
            updated = con.execute(
                "SELECT * FROM ai_practice_sessions WHERE id = ?", (session_id,)
            ).fetchone()

    result = {
        **dict(updated),
        "answered_count": len(latest),
        "scored_count": len(scored),
        "missing_positions": missing_positions,
    }
    if missing_positions or str(updated["completion_state"] or "draft") != "scored":
        return result

    # Traitement secondaire : aucune erreur de lacune ne peut annuler le score.
    for attempt in latest:
        if attempt["score_percent"] is None or float(attempt["score_percent"]) >= 50.0:
            continue
        try:
            with _conn() as con:
                question = con.execute(
                    "SELECT prompt FROM ai_practice_questions WHERE id = ?",
                    (attempt["question_id"],),
                ).fetchone()
                failures = con.execute(
                    """SELECT COUNT(*) AS count FROM ai_practice_attempts
                       WHERE question_id = ? AND score_percent < 50.0""",
                    (attempt["question_id"],),
                ).fetchone()["count"]
            if failures >= 2:
                prompt = str(question["prompt"] if question else f"Question {attempt['question_id']}")[:120]
                add_weak_point(
                    course_id=str(updated["course_id"] or ""),
                    detail=f"Lacune récurrente (2 échecs) : {prompt}",
                    course_title=str(updated["course_title"] or ""),
                    item_number=str(updated["item_number"] or ""),
                    category=f"Item {updated['item_number']}" if updated["item_number"] else "Annale UNESS",
                    severity=3,
                    source_session_id=session_id,
                )
        except Exception:
            logger.exception("Détection de lacune non bloquante pour la session {}", session_id)
    return result


def mark_ai_practice_mastery_recorded(session_id: int) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE ai_practice_sessions SET mastery_recorded_at = ? WHERE id = ?",
            (_now(), session_id),
        )


# ── Statistiques ─────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """
    Retourne des statistiques sur la base SQLite locale.
    Utilisé par la page Settings pour afficher l'état de la base.
    """
    try:
        with _conn() as con:
            nb_reviews  = con.execute("SELECT COUNT(*) FROM review_history").fetchone()[0]
            nb_done     = con.execute("SELECT COUNT(*) FROM review_history WHERE status='done'").fetchone()[0]
            nb_postponed= con.execute("SELECT COUNT(*) FROM review_history WHERE status='postponed'").fetchone()[0]
            nb_ignored  = con.execute("SELECT COUNT(*) FROM review_history WHERE status='ignored'").fetchone()[0]
            nb_qcm      = con.execute("SELECT COUNT(*) FROM qcm_results").fetchone()[0]
            nb_sessions = con.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
            last_done_row = con.execute(
                "SELECT completed_at FROM review_history WHERE status='done' ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
            last_done = last_done_row[0] if last_done_row else None
        return {
            "db_path":      str(DB_PATH),
            "db_exists":    DB_PATH.exists(),
            "db_size_kb":   round(DB_PATH.stat().st_size / 1024, 1) if DB_PATH.exists() else 0,
            "nb_reviews":   nb_reviews,
            "nb_done":      nb_done,
            "nb_postponed": nb_postponed,
            "nb_ignored":   nb_ignored,
            "nb_qcm":       nb_qcm,
            "nb_sessions":  nb_sessions,
            "last_done":    last_done,
        }
    except Exception as e:
        return {"error": str(e), "db_path": str(DB_PATH), "db_exists": DB_PATH.exists()}


# ── Lecture des sessions de travail ──────────────────────────────────────────

def get_recent_study_sessions(limit: int = 50) -> list:
    """Retourne les dernières séances, tri décroissant par date puis heure."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM study_sessions ORDER BY session_date DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


# ── Planifications manuelles du cockpit Planning ─────────────────────────────

_MANUAL_PLANNING_ACTIVITY_TYPES = {"revision", "lecture", "qcm", "lacune", "flash_zero"}


def create_manual_planning_entry(
    entry_date: datetime.date,
    course_id: str,
    course_title: str,
    item_number: str,
    activity_type: str,
    duration_minutes: int,
) -> dict:
    """Persist a local planning intention without touching review state."""
    if activity_type not in _MANUAL_PLANNING_ACTIVITY_TYPES:
        raise ValueError(f"Type d'activité invalide: {activity_type}")
    duration = int(duration_minutes)
    if duration <= 0:
        raise ValueError("La durée doit être positive")
    date_iso = entry_date.isoformat() if isinstance(entry_date, datetime.date) else str(entry_date)
    created_at = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as con:
        cursor = con.execute(
            """INSERT INTO manual_planning_entries
               (entry_date, course_id, course_title, item_number, activity_type,
                duration_minutes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (date_iso, str(course_id), course_title or "", item_number or "",
             activity_type, duration, created_at),
        )
        row = con.execute(
            "SELECT * FROM manual_planning_entries WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def get_manual_planning_entries(
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[dict]:
    start_iso = start_date.isoformat() if isinstance(start_date, datetime.date) else str(start_date)
    end_iso = end_date.isoformat() if isinstance(end_date, datetime.date) else str(end_date)
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM manual_planning_entries
               WHERE entry_date >= ? AND entry_date <= ?
               ORDER BY entry_date, created_at, id""",
            (start_iso, end_iso),
        ).fetchall()
    return [dict(row) for row in rows]


def ensure_daily_flash_zero(entry_date: datetime.date, *, timezone_name: str) -> dict:
    """Crée la tâche Flash-Zero du jour une seule fois par fuseau métier."""
    course_id = f"flash-zero:{timezone_name}"
    date_iso = entry_date.isoformat() if isinstance(entry_date, datetime.date) else str(entry_date)
    with _conn() as con:
        existing = con.execute(
            """SELECT * FROM manual_planning_entries
               WHERE entry_date = ? AND activity_type = 'flash_zero' AND course_id = ?
               ORDER BY id LIMIT 1""",
            (date_iso, course_id),
        ).fetchone()
    if existing:
        return dict(existing)
    return create_manual_planning_entry(
        entry_date=entry_date,
        course_id=course_id,
        course_title="Flash-Zero du matin",
        item_number="",
        activity_type="flash_zero",
        duration_minutes=5,
    )


def get_daily_flash_zero(entry_date: datetime.date, *, timezone_name: str) -> dict | None:
    course_id = f"flash-zero:{timezone_name}"
    return next(
        (
            row for row in get_manual_planning_entries(entry_date, entry_date)
            if row["activity_type"] == "flash_zero" and row["course_id"] == course_id
        ),
        None,
    )


def complete_daily_flash_zero(entry_date: datetime.date, *, timezone_name: str) -> None:
    date_iso = entry_date.isoformat() if isinstance(entry_date, datetime.date) else str(entry_date)
    item_name = f"flash_zero:{timezone_name}"
    with _conn() as con:
        con.execute(
            """INSERT INTO routine_checks(date, item_name, checked) VALUES (?, ?, 1)
               ON CONFLICT(date, item_name) DO UPDATE SET checked = 1""",
            (date_iso, item_name),
        )


def is_daily_flash_zero_complete(entry_date: datetime.date, *, timezone_name: str) -> bool:
    date_iso = entry_date.isoformat() if isinstance(entry_date, datetime.date) else str(entry_date)
    with _conn() as con:
        row = con.execute(
            "SELECT checked FROM routine_checks WHERE date = ? AND item_name = ?",
            (date_iso, f"flash_zero:{timezone_name}"),
        ).fetchone()
    return bool(row and row["checked"])


def dismiss_daily_flash_zero(entry_date: datetime.date, *, timezone_name: str) -> None:
    date_iso = entry_date.isoformat() if isinstance(entry_date, datetime.date) else str(entry_date)
    item_name = f"flash_zero_dismissed:{timezone_name}"
    with _conn() as con:
        con.execute(
            """INSERT INTO routine_checks(date, item_name, checked) VALUES (?, ?, 1)
               ON CONFLICT(date, item_name) DO UPDATE SET checked = 1""",
            (date_iso, item_name),
        )


def is_daily_flash_zero_dismissed(entry_date: datetime.date, *, timezone_name: str) -> bool:
    date_iso = entry_date.isoformat() if isinstance(entry_date, datetime.date) else str(entry_date)
    with _conn() as con:
        row = con.execute(
            "SELECT checked FROM routine_checks WHERE date = ? AND item_name = ?",
            (date_iso, f"flash_zero_dismissed:{timezone_name}"),
        ).fetchone()
    return bool(row and row["checked"])


def delete_manual_planning_entry(entry_id: int) -> bool:
    with _conn() as con:
        cursor = con.execute("DELETE FROM manual_planning_entries WHERE id = ?", (int(entry_id),))
    return cursor.rowcount > 0


def get_weekly_study_stats(days: int = 7) -> dict:
    """
    Statistiques agrégées sur une période.

    days=0 → toutes les sessions (pas de filtre de date).

    activity_minutes : la durée COMPLÈTE de la séance est attribuée à CHAQUE
    activité de la liste (pas divisée). Ex : 30 min avec [révision, qcm]
    → révision+=30, qcm+=30. Choix délibéré : reflète le temps passé sur
    chaque discipline, peu importe la répartition exacte inconnue.
    """
    import json as _json

    with _conn() as con:
        if days > 0:
            cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
            rows = con.execute(
                "SELECT * FROM study_sessions WHERE session_date >= ?", (cutoff,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM study_sessions").fetchall()

    total_minutes = 0
    confidences: list[int] = []
    activity_counts: dict[str, int] = {}
    activity_minutes: dict[str, int] = {}
    difficulty_counts: dict[str, int] = {}
    qcm_result_counts: dict[str, int] = {}
    weak_count = 0

    for row in rows:
        dur = row["duration_minutes"] or 0
        total_minutes += dur

        if row["confidence"]:
            confidences.append(int(row["confidence"]))

        try:
            types = _json.loads(row["activity_types"] or "[]")
            if not types:
                types = [row["session_type"] or "révision"]
        except Exception:
            types = [row["session_type"] or "révision"]

        for act in types:
            k = act.lower().strip()
            if k:
                activity_counts[k] = activity_counts.get(k, 0) + 1
                activity_minutes[k] = activity_minutes.get(k, 0) + dur

        if row["difficulty"]:
            d = row["difficulty"].lower().strip()
            difficulty_counts[d] = difficulty_counts.get(d, 0) + 1

        if row["qcm_result"]:
            q = row["qcm_result"].lower().strip()
            qcm_result_counts[q] = qcm_result_counts.get(q, 0) + 1

        wd = (row["weak_detail"] or "").strip()
        wc = (row["weak_category"] or "").strip()
        qr = (row["qcm_result"] or "").lower()
        if wd or (wc and wc.lower() not in ("aucune", "")) or qr in ("raté", "rate"):
            weak_count += 1

    avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else None

    return {
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 1),
        "session_count": len(rows),
        "activity_counts": activity_counts,
        "activity_minutes": activity_minutes,
        "average_confidence": avg_conf,
        "difficulty_counts": difficulty_counts,
        "qcm_result_counts": qcm_result_counts,
        "weak_count": weak_count,
    }


def get_active_weak_points(limit: int = 100) -> list:
    """Séances avec points faibles depuis study_sessions (source historique)."""
    with _conn() as con:
        return con.execute("""
            SELECT course_id, course_title, item_number, session_date,
                   weak_category, weak_detail, qcm_result, confidence, difficulty, created_at
            FROM study_sessions
            WHERE (weak_detail IS NOT NULL AND TRIM(weak_detail) != '')
               OR (weak_category IS NOT NULL AND TRIM(weak_category) != ''
                   AND LOWER(TRIM(weak_category)) NOT IN ('aucune'))
               OR LOWER(qcm_result) IN ('raté', 'rate')
            ORDER BY session_date DESC, created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


def get_course_session_summary(course_id: str) -> dict:
    """Résume l'historique de séances d'un cours. Utilisé pour la fiche détail."""
    import json as _json

    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM study_sessions WHERE course_id = ? ORDER BY session_date DESC",
            (course_id,),
        ).fetchall()

    if not rows:
        return {
            "session_count": 0, "total_minutes": 0, "average_confidence": None,
            "last_session_date": None, "weak_points": [], "activity_counts": {},
        }

    total_min = sum(r["duration_minutes"] or 0 for r in rows)
    confs = [r["confidence"] for r in rows if r["confidence"]]
    avg_conf = round(sum(confs) / len(confs), 2) if confs else None
    act_counts: dict[str, int] = {}
    weak_pts: list[dict] = []

    for r in rows:
        try:
            types = _json.loads(r["activity_types"] or "[]") or [r["session_type"] or "révision"]
        except Exception:
            types = [r["session_type"] or "révision"]
        for t in types:
            k = t.lower().strip()
            if k:
                act_counts[k] = act_counts.get(k, 0) + 1
        wd = (r["weak_detail"] or "").strip()
        wc = (r["weak_category"] or "").strip()
        if wd or (wc and wc.lower() not in ("aucune", "")):
            weak_pts.append({
                "category": wc or None,
                "detail": wd or f"Point faible : {wc}",
                "session_date": r["session_date"],
                "confidence": r["confidence"],
            })

    return {
        "session_count": len(rows),
        "total_minutes": total_min,
        "average_confidence": avg_conf,
        "last_session_date": rows[0]["session_date"],
        "weak_points": weak_pts,
        "activity_counts": act_counts,
    }


# ── Table weak_points — gestion dédiée ───────────────────────────────────────

def init_weak_points_table() -> None:
    """Crée la table weak_points (appelée dans init_db, idempotente)."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS weak_points (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id         TEXT    NOT NULL,
                course_title      TEXT    DEFAULT '',
                item_number       TEXT    DEFAULT '',
                category          TEXT,
                detail            TEXT    NOT NULL,
                severity          INTEGER DEFAULT 2,
                status            TEXT    NOT NULL DEFAULT 'active',
                source_session_id INTEGER,
                created_at        TEXT    NOT NULL,
                resolved_at       TEXT
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_wp_course ON weak_points(course_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_wp_status ON weak_points(status)")


def add_weak_point(
    course_id: str,
    detail: str,
    course_title: str = "",
    item_number: str = "",
    category: str | None = None,
    severity: int = 2,
    source_session_id: int | None = None,
) -> int:
    """Enregistre un point faible. Retourne l'id inséré."""
    now = _now()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO weak_points
                (course_id, course_title, item_number, category, detail,
                 severity, status, source_session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (course_id, course_title, item_number, category, detail,
               severity, source_session_id, now))
        return cur.lastrowid


def resolve_weak_point(weak_point_id: int) -> None:
    """Marque un point faible comme résolu."""
    with _conn() as con:
        con.execute(
            "UPDATE weak_points SET status='résolue', resolved_at=? WHERE id=?",
            (_now(), weak_point_id),
        )


def get_unresolved_weak_points(limit: int = 100) -> list:
    """
    Retourne les points faibles actifs avec données de session (JOIN).
    Colonnes : id, course_id, course_title, item_number, category, detail,
               severity, created_at, confidence, difficulty, session_date.
    """
    with _conn() as con:
        return con.execute("""
            SELECT wp.id, wp.course_id, wp.course_title, wp.item_number,
                   wp.category, wp.detail, wp.severity, wp.created_at,
                   ss.confidence, ss.difficulty, ss.session_date
            FROM weak_points wp
            LEFT JOIN study_sessions ss ON ss.id = wp.source_session_id
            WHERE wp.status = 'active'
            ORDER BY wp.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


def _migrate_qcm_sessions_v2() -> None:
    """
    Migration douce : ajoute les colonnes Phase C à qcm_sessions.
    Idempotente — ne touche pas aux données existantes.
    """
    with _conn() as con:
        existing = {
            row["name"]
            for row in con.execute("PRAGMA table_info(qcm_sessions)").fetchall()
        }
        migrations = [
            ("session_type",    "ALTER TABLE qcm_sessions ADD COLUMN session_type TEXT DEFAULT 'QCM'"),
            ("score_raw",       "ALTER TABLE qcm_sessions ADD COLUMN score_raw TEXT"),
            ("score_percent",   "ALTER TABLE qcm_sessions ADD COLUMN score_percent REAL"),
            ("correct_answers", "ALTER TABLE qcm_sessions ADD COLUMN correct_answers INTEGER"),
            ("wrong_answers",   "ALTER TABLE qcm_sessions ADD COLUMN wrong_answers INTEGER"),
            ("difficulty",      "ALTER TABLE qcm_sessions ADD COLUMN difficulty TEXT"),
            ("error_types",     "ALTER TABLE qcm_sessions ADD COLUMN error_types TEXT DEFAULT '[]'"),
        ]
        for col, sql in migrations:
            if col not in existing:
                con.execute(sql)
        # Rétro-compat : si score existe mais score_percent vide, copier
        con.execute("""
            UPDATE qcm_sessions
            SET score_percent = score
            WHERE score_percent IS NULL AND score IS NOT NULL
        """)


def _migrate_weak_points_v2() -> None:
    """
    Migration douce : ajoute les colonnes manquantes à weak_points
    et normalise les statuts 'resolved' → 'résolue'.
    Idempotente.
    """
    with _conn() as con:
        existing = {
            row["name"]
            for row in con.execute("PRAGMA table_info(weak_points)").fetchall()
        }
        migrations = [
            ("source_type",      "ALTER TABLE weak_points ADD COLUMN source_type TEXT DEFAULT 'manuel'"),
            ("last_reviewed_at", "ALTER TABLE weak_points ADD COLUMN last_reviewed_at TEXT"),
            ("recurrence_count", "ALTER TABLE weak_points ADD COLUMN recurrence_count INTEGER DEFAULT 0"),
        ]
        for col, sql in migrations:
            if col not in existing:
                con.execute(sql)
        # Normaliser 'resolved' → 'résolue'
        con.execute("UPDATE weak_points SET status='résolue' WHERE status='resolved'")
        # Corriger les lacunes sans statut (bug add_weak_point pre-fix)
        con.execute("UPDATE weak_points SET status='active' WHERE status IS NULL OR status=''")


def _migrate_weak_points_from_sessions() -> None:
    """
    Migration one-shot : alimente weak_points depuis study_sessions existantes.
    Ne s'exécute que si la table weak_points est vide (premier démarrage après ajout).
    """
    with _conn() as con:
        count = con.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]
        if count > 0:
            return

        rows = con.execute("""
            SELECT id, course_id, course_title, item_number,
                   weak_category, weak_detail, created_at
            FROM study_sessions
            WHERE (weak_detail IS NOT NULL AND TRIM(weak_detail) != '')
               OR (weak_category IS NOT NULL AND TRIM(weak_category) != ''
                   AND LOWER(TRIM(weak_category)) NOT IN ('aucune'))
        """).fetchall()

        now = _now()
        migrated = 0
        for row in rows:
            detail = (row["weak_detail"] or "").strip()
            cat = (row["weak_category"] or "").strip()
            if not detail:
                if not cat or cat.lower() == "aucune":
                    continue
                detail = f"Point faible : {cat}"
            con.execute("""
                INSERT INTO weak_points
                    (course_id, course_title, item_number, category, detail,
                     source_session_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row["course_id"], row["course_title"] or "", row["item_number"] or "",
                cat or None, detail, row["id"], row["created_at"] or now,
            ))
            migrated += 1

    if migrated:
        logger.info(f"Migration weak_points : {migrated} point(s) importé(s) depuis study_sessions")


# ── API étendue — weak_points (Phase D) ──────────────────────────────────────

# Statuts valides
WEAK_POINT_STATUSES = ("active", "à revoir", "résolue", "récurrente")

# Catégories standards
WEAK_POINT_CATEGORIES = [
    "Diagnostic", "Clinique", "Examens complémentaires", "Traitement",
    "Complications", "Physiopathologie", "Urgence", "Contre-indication",
    "Piège EDN", "Valeur chiffrée", "Raisonnement", "Inattention", "Autre",
]

# Types de source
WEAK_POINT_SOURCE_TYPES = ("qcm", "séance", "note", "manuel")


def add_weak_point_full(
    course_id: str,
    detail: str,
    course_title: str = "",
    item_number: str = "",
    category: str | None = None,
    severity: int = 2,
    source_type: str = "manuel",
    source_session_id: int | None = None,
) -> int:
    """
    Ajoute une lacune avec tous les champs Phase D.
    Retourne l'id inséré.
    """
    now = _now()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO weak_points
                (course_id, course_title, item_number, category, detail,
                 severity, status, source_type, source_session_id,
                 recurrence_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, 0, ?)
        """, (
            course_id, course_title, item_number, category, detail,
            severity, source_type, source_session_id, now,
        ))
        return cur.lastrowid


def get_all_weak_points_table(
    status_filter: str | None = None,
    limit: int = 200,
) -> list:
    """
    Retourne les lacunes de la table weak_points, avec infos de session jointe.

    status_filter : 'active' | 'à revoir' | 'résolue' | 'récurrente' | None (tout)
    """
    with _conn() as con:
        if status_filter:
            rows = con.execute("""
                SELECT wp.*,
                       ss.session_date AS session_date,
                       ss.confidence   AS session_confidence,
                       ss.difficulty   AS session_difficulty
                FROM weak_points wp
                LEFT JOIN study_sessions ss ON ss.id = wp.source_session_id
                WHERE wp.status = ?
                ORDER BY wp.severity DESC, wp.created_at DESC
                LIMIT ?
            """, (status_filter, limit)).fetchall()
        else:
            rows = con.execute("""
                SELECT wp.*,
                       ss.session_date AS session_date,
                       ss.confidence   AS session_confidence,
                       ss.difficulty   AS session_difficulty
                FROM weak_points wp
                LEFT JOIN study_sessions ss ON ss.id = wp.source_session_id
                ORDER BY wp.severity DESC, wp.created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
    return rows


def get_critical_weak_points_count() -> int:
    """Retourne le nombre de lacunes actives avec severity >= 4."""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM weak_points WHERE status='active' AND severity >= 4"
        ).fetchone()
    return row[0] if row else 0


def update_weak_point_status(weak_point_id: int, status: str) -> None:
    """
    Change le statut d'une lacune.
    status ∈ ('active', 'à revoir', 'résolue', 'récurrente')
    """
    now = _now()
    resolved_at = now if status == "résolue" else None
    with _conn() as con:
        con.execute("""
            UPDATE weak_points
            SET status      = ?,
                resolved_at = CASE WHEN ? = 'résolue' THEN ? ELSE resolved_at END
            WHERE id = ?
        """, (status, status, resolved_at, weak_point_id))


def update_weak_point_obsidian(wp_id: int, obsidian_path: str, obsidian_uri: str) -> None:
    """Lie une lacune Synapse à sa note Obsidian (après création depuis Synapse)."""
    with _conn() as con:
        con.execute(
            "UPDATE weak_points SET obsidian_path=?, obsidian_uri=? WHERE id=?",
            (obsidian_path, obsidian_uri, wp_id),
        )


def update_weak_point_obsidian_path(wp_id: int, obsidian_path: str) -> None:
    """Met à jour le chemin obsidian_path après un déplacement de fichier."""
    with _conn() as con:
        con.execute(
            "UPDATE weak_points SET obsidian_path=? WHERE id=?",
            (obsidian_path, wp_id),
        )


def mark_weak_point_reviewed(weak_point_id: int) -> None:
    """Met à jour last_reviewed_at."""
    with _conn() as con:
        con.execute(
            "UPDATE weak_points SET last_reviewed_at = ? WHERE id = ?",
            (_now(), weak_point_id),
        )


def update_weak_point_severity(weak_point_id: int, severity: int) -> None:
    """Change la sévérité (1-5)."""
    with _conn() as con:
        con.execute(
            "UPDATE weak_points SET severity = ? WHERE id = ?",
            (max(1, min(5, severity)), weak_point_id),
        )


def increment_recurrence(weak_point_id: int) -> None:
    """Incrémente recurrence_count et passe status à 'récurrente'."""
    with _conn() as con:
        con.execute("""
            UPDATE weak_points
            SET recurrence_count = recurrence_count + 1,
                status = 'récurrente'
            WHERE id = ?
        """, (weak_point_id,))


def delete_weak_point(weak_point_id: int) -> None:
    """Supprime définitivement une lacune."""
    with _conn() as con:
        con.execute("DELETE FROM weak_points WHERE id = ?", (weak_point_id,))


def get_weak_points_for_course(course_id: str) -> list:
    """Retourne toutes les lacunes actives/à revoir d'un cours."""
    with _conn() as con:
        return con.execute("""
            SELECT * FROM weak_points
            WHERE course_id = ? AND status NOT IN ('résolue')
            ORDER BY severity DESC, created_at DESC
        """, (course_id,)).fetchall()


# ── API étendue — QCM sessions (Phase C) ─────────────────────────────────────

QCM_PLATFORMS     = ("EDNpro", "Hypocampus", "ChatGPT", "Gemini")
QCM_SESSION_TYPES = ("QCM", "DP", "KFP", "Annales")
QCM_ERROR_TYPES   = ("connaissance", "raisonnement", "inattention", "stratégie EDN")
QCM_PASS_THRESHOLD = 70.0    # % en dessous duquel c'est raté
RECURRENCE_THRESHOLD = 2     # sessions min avec le même error_type sur un même item pour déclencher une proposition


def add_qcm_session_full(
    platform: str,
    session_date: str,
    course_id: str = "",
    course_title: str = "",
    item_number: str = "",
    session_type: str = "QCM",
    score_raw: str | None = None,
    score_percent: float | None = None,
    total_questions: int | None = None,
    correct_answers: int | None = None,
    wrong_answers: int | None = None,
    difficulty: str | None = None,
    error_types: list | None = None,
    comments: str | None = None,
) -> int:
    """
    Enregistre un résultat QCM complet (Phase C).
    Retourne l'id inséré.
    """
    import json as _json
    now = _now()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO qcm_sessions
                (course_id, course_title, item_number, platform, session_date,
                 session_type, score, score_raw, score_percent,
                 total_questions, correct_answers, wrong_answers,
                 difficulty, error_types, comments, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            course_id, course_title, item_number, platform, session_date,
            session_type, score_percent, score_raw, score_percent,
            total_questions, correct_answers, wrong_answers,
            difficulty,
            _json.dumps(error_types or [], ensure_ascii=False),
            comments, now, now,
        ))
        sid: int = cur.lastrowid

    if error_types and item_number:
        try:
            check_and_propose_recurring_gaps(
                item_number=item_number,
                error_types=error_types,
                new_session_id=sid,
                course_title=course_title,
                course_id=course_id,
            )
        except Exception as _gap_err:
            logger.warning(f"check_and_propose_recurring_gaps (non-bloquant): {_gap_err}")

    return sid


def get_qcm_sessions_all(
    limit: int = 100,
    platform: str | None = None,
    course_id: str | None = None,
) -> list:
    """Retourne les sessions QCM triées du plus récent au plus ancien."""
    with _conn() as con:
        if platform and course_id:
            rows = con.execute("""
                SELECT * FROM qcm_sessions
                WHERE platform = ? AND course_id = ?
                ORDER BY session_date DESC, created_at DESC LIMIT ?
            """, (platform, course_id, limit)).fetchall()
        elif platform:
            rows = con.execute("""
                SELECT * FROM qcm_sessions
                WHERE platform = ?
                ORDER BY session_date DESC, created_at DESC LIMIT ?
            """, (platform, limit)).fetchall()
        elif course_id:
            rows = con.execute("""
                SELECT * FROM qcm_sessions
                WHERE course_id = ?
                ORDER BY session_date DESC, created_at DESC LIMIT ?
            """, (course_id, limit)).fetchall()
        else:
            rows = con.execute("""
                SELECT * FROM qcm_sessions
                ORDER BY session_date DESC, created_at DESC LIMIT ?
            """, (limit,)).fetchall()
    return rows


def get_qcm_summary_for_course(course_id: str) -> dict:
    """
    Résumé QCM pour un cours :
      count, avg_score, last_score, last_date, passed, failed
    """
    with _conn() as con:
        rows = con.execute("""
            SELECT score_percent, session_date FROM qcm_sessions
            WHERE course_id = ? AND score_percent IS NOT NULL
            ORDER BY session_date DESC
        """, (course_id,)).fetchall()

    if not rows:
        return {
            "count": 0, "avg_score": None, "last_score": None,
            "last_date": None, "passed": 0, "failed": 0,
        }

    scores = [r["score_percent"] for r in rows]
    avg    = round(sum(scores) / len(scores), 1)
    passed = sum(1 for s in scores if s >= QCM_PASS_THRESHOLD)

    return {
        "count":      len(rows),
        "avg_score":  avg,
        "last_score": rows[0]["score_percent"],
        "last_date":  rows[0]["session_date"],
        "passed":     passed,
        "failed":     len(rows) - passed,
    }


def get_global_qcm_stats() -> dict:
    """Stats QCM globales pour la bannière de la page QCM."""
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM qcm_sessions").fetchone()[0]
        rows  = con.execute(
            "SELECT score_percent, platform FROM qcm_sessions WHERE score_percent IS NOT NULL"
        ).fetchall()

    if not rows:
        return {
            "total": total, "avg_score": None, "pass_rate": None,
            "ednpro_count": 0, "hypocampus_count": 0, "failed_count": 0,
        }

    scores = [r["score_percent"] for r in rows]
    avg    = round(sum(scores) / len(scores), 1)
    passed = sum(1 for s in scores if s >= QCM_PASS_THRESHOLD)
    ednpro = sum(1 for r in rows if r["platform"] == "EDNpro")
    hypoc  = sum(1 for r in rows if r["platform"] == "Hypocampus")

    return {
        "total":            total,
        "avg_score":        avg,
        "pass_rate":        round(passed / len(scores) * 100) if scores else None,
        "ednpro_count":     ednpro,
        "hypocampus_count": hypoc,
        "failed_count":     len(scores) - passed,
    }


def delete_qcm_session(session_id: int) -> None:
    """Supprime définitivement une session QCM."""
    with _conn() as con:
        con.execute("DELETE FROM qcm_sessions WHERE id = ?", (session_id,))


def delete_qcm_sessions_for_item(item_number: str) -> int:
    """Supprime toutes les sessions QCM liées à un item_number. Retourne le nombre supprimé."""
    with _conn() as con:
        cur = con.execute("DELETE FROM qcm_sessions WHERE item_number = ?", (item_number,))
        return cur.rowcount


def delete_qcm_sessions_for_college(course_title: str) -> int:
    """Supprime les sessions college-level (sans item_number) pour un collège donné."""
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM qcm_sessions WHERE (item_number IS NULL OR item_number = '') AND course_title = ?",
            (course_title,),
        )
        return cur.rowcount


def qcm_session_exists(
    platform: str,
    session_date: str,
    course_title: str,
    score_percent,
) -> bool:
    """Vérifie si une session identique existe déjà (déduplication à l'import)."""
    with _conn() as con:
        if score_percent is None:
            row = con.execute(
                """SELECT 1 FROM qcm_sessions
                   WHERE platform = ? AND session_date = ? AND course_title = ?
                     AND score_percent IS NULL
                   LIMIT 1""",
                (platform, session_date, course_title),
            ).fetchone()
        else:
            row = con.execute(
                """SELECT 1 FROM qcm_sessions
                   WHERE platform = ? AND session_date = ? AND course_title = ?
                     AND ABS(COALESCE(score_percent, -1) - ?) < 0.01
                   LIMIT 1""",
                (platform, session_date, course_title, float(score_percent)),
            ).fetchone()
    return row is not None


# ── Croisement QCM ↔ Dashboard (Phase E2) ────────────────────────────────────

def get_qcm_last_scores_by_course() -> dict[str, dict]:
    """
    Batch : pour chaque cours avec au moins 1 QCM enregistré, retourne
    le dernier score + tendance (comparaison avec le score précédent).

    Retourne : {course_id: {last_score, last_raw, trend, trend_color, platform}}
      trend       : '↑' | '↓' | '→' | None (si une seule session)
      trend_color : 'green' | 'red' | 'slate'

    Utilise ROW_NUMBER() (SQLite 3.25+) pour ne récupérer que les 2 dernières
    sessions par cours directement en SQL — évite le plein-table scan Python.
    """
    with _conn() as con:
        rows = con.execute("""
            SELECT course_id, score_percent, score_raw, platform, rn
            FROM (
                SELECT course_id, score_percent, score_raw, platform,
                       ROW_NUMBER() OVER (
                           PARTITION BY course_id
                           ORDER BY session_date DESC, id DESC
                       ) AS rn
                FROM qcm_sessions
                WHERE course_id != '' AND course_id IS NOT NULL
                  AND score_percent IS NOT NULL
            )
            WHERE rn <= 2
            ORDER BY course_id, rn
        """).fetchall()

    by_course: dict[str, list] = {}
    for r in rows:
        by_course.setdefault(r["course_id"], []).append(dict(r))

    result: dict[str, dict] = {}
    for cid, sessions in by_course.items():
        last     = sessions[0]   # rn=1 → le plus récent
        prev     = sessions[1] if len(sessions) > 1 else None
        last_pct = last["score_percent"]
        if prev:
            diff   = last_pct - prev["score_percent"]
            trend  = "↑" if diff > 2 else ("↓" if diff < -2 else "→")
            t_col  = "green" if diff > 2 else ("red" if diff < -2 else "slate")
        else:
            trend, t_col = None, "slate"
        result[cid] = {
            "last_score":  last_pct,
            "last_raw":    last.get("score_raw") or f"{last_pct}%",
            "trend":       trend,
            "trend_color": t_col,
            "platform":    last["platform"],
        }
    return result


get_qcm_latest_by_course = get_qcm_last_scores_by_course


def get_active_lacunes_count_by_course() -> dict[str, int]:
    """
    Batch : pour chaque cours, retourne le nombre de lacunes non résolues
    (statuts 'active', 'à revoir', 'récurrente').
    """
    with _conn() as con:
        rows = con.execute("""
            SELECT course_id, COUNT(*) AS cnt
            FROM weak_points
            WHERE status IN ('active', 'à revoir', 'récurrente')
              AND course_id != '' AND course_id IS NOT NULL
            GROUP BY course_id
        """).fetchall()
    return {r["course_id"]: r["cnt"] for r in rows}


def get_qcm_trend_for_course(course_id: str) -> dict:
    """
    Tendance QCM pour un cours précis (2 dernières sessions).
    Retourne : {last_score, last_raw, prev_score, trend, trend_color}
    """
    with _conn() as con:
        rows = con.execute("""
            SELECT score_percent, score_raw, session_date
            FROM qcm_sessions
            WHERE course_id = ? AND score_percent IS NOT NULL
            ORDER BY session_date DESC, id DESC
            LIMIT 2
        """, (course_id,)).fetchall()

    if not rows:
        return {"last_score": None, "last_raw": None, "prev_score": None,
                "trend": None, "trend_color": "slate"}

    last_pct = rows[0]["score_percent"]
    prev_pct = rows[1]["score_percent"] if len(rows) > 1 else None

    if prev_pct is not None:
        diff   = last_pct - prev_pct
        trend  = "↑" if diff > 2 else ("↓" if diff < -2 else "→")
        t_col  = "green" if diff > 2 else ("red" if diff < -2 else "slate")
    else:
        trend, t_col = None, "slate"

    return {
        "last_score":  last_pct,
        "last_raw":    rows[0]["score_raw"] or f"{last_pct}%",
        "prev_score":  prev_pct,
        "trend":       trend,
        "trend_color": t_col,
    }


def get_active_lacunes_for_course(course_id: str) -> list:
    """Lacunes non résolues (active / à revoir / récurrente) pour un cours."""
    with _conn() as con:
        return con.execute("""
            SELECT * FROM weak_points
            WHERE course_id = ?
              AND status IN ('active', 'à revoir', 'récurrente')
            ORDER BY severity DESC, created_at DESC
        """, (course_id,)).fetchall()


def get_open_lacunes_count() -> int:
    """Nb total de lacunes non résolues (toutes sévérités)."""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM weak_points WHERE status != 'résolue'"
        ).fetchone()
    return row[0] if row else 0


def get_streak_days() -> int:
    """
    Nombre de jours consécutifs de révisions.
    La série est maintenue si aujourd'hui OU hier est le jour le plus récent
    (évite de casser le streak à minuit avant que l'utilisateur ait révisé).
    """
    import datetime as _dt

    with _conn() as con:
        rows = con.execute("""
            SELECT DISTINCT DATE(completed_at) AS day
            FROM review_history
            WHERE status = 'done' AND completed_at IS NOT NULL
            ORDER BY day DESC
        """).fetchall()

    if not rows:
        return 0

    today = _dt.date.today()
    yesterday = today - _dt.timedelta(days=1)

    try:
        days = [_dt.date.fromisoformat(r[0]) for r in rows if r[0]]
    except Exception:
        return 0

    if not days or days[0] < yesterday:
        return 0

    streak = 0
    expected = days[0]
    for day in days:
        if day == expected:
            streak += 1
            expected -= _dt.timedelta(days=1)
        else:
            break

    return streak


# ── Migration Obsidian (Phase H) ──────────────────────────────────────────────

def _migrate_weak_points_obsidian() -> None:
    """
    Migration douce : ajoute les colonnes Obsidian à weak_points.
    Idempotente — ne touche pas aux données existantes.
    Colonnes ajoutées :
      synapse_id     : identifiant stable pour les lacunes Obsidian
      obsidian_path  : chemin absolu de la note (slashes, compatible Windows)
      obsidian_uri   : obsidian://open?vault=...&file=...
      obsidian_title : titre H1 ou frontmatter de la note
      college        : collège extrait du frontmatter Obsidian
      raw_frontmatter: dump JSON du frontmatter complet
    """
    with _conn() as con:
        existing = {
            row["name"]
            for row in con.execute("PRAGMA table_info(weak_points)").fetchall()
        }
        migrations = [
            ("synapse_id",      "ALTER TABLE weak_points ADD COLUMN synapse_id TEXT"),
            ("obsidian_path",   "ALTER TABLE weak_points ADD COLUMN obsidian_path TEXT"),
            ("obsidian_uri",    "ALTER TABLE weak_points ADD COLUMN obsidian_uri TEXT"),
            ("obsidian_title",  "ALTER TABLE weak_points ADD COLUMN obsidian_title TEXT"),
            ("college",         "ALTER TABLE weak_points ADD COLUMN college TEXT"),
            ("raw_frontmatter", "ALTER TABLE weak_points ADD COLUMN raw_frontmatter TEXT"),
        ]
        for col, sql in migrations:
            if col not in existing:
                con.execute(sql)
        # Index partiel unique sur synapse_id (SQLite 3.8.9+)
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wp_synapse_id "
            "ON weak_points(synapse_id) WHERE synapse_id IS NOT NULL"
        )
    logger.debug("Migration weak_points Obsidian appliquée.")


# ── API Obsidian — weak_points ────────────────────────────────────────────────

def get_weak_point_by_synapse_id(synapse_id: str) -> sqlite3.Row | None:
    """Retourne la lacune dont le synapse_id correspond, ou None."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM weak_points WHERE synapse_id = ?",
            (synapse_id,),
        ).fetchone()


def upsert_weak_point_from_obsidian(
    synapse_id: str,
    obsidian_path: str,
    obsidian_uri: str,
    obsidian_title: str,
    detail: str,
    severity: int,
    status: str,
    source: str,
    college: str,
    course_id: str,
    course_title: str,
    item_number: str,
    raw_frontmatter: str,
    created_at: str | None = None,
    resolved_at: str | None = None,
) -> int:
    """
    Insert or update une lacune provenant d'Obsidian.

    Utilise synapse_id comme clé d'idempotence.
    Retourne l'id SQLite de la ligne (INTEGER).

    - Si la lacune existe déjà  → UPDATE des champs (pas d'ID change).
    - Si elle n'existe pas      → INSERT avec synapse_id.
    - N'écrase jamais le status si l'utilisateur l'a changé manuellement
      depuis Synapse ET que l'Obsidian n'a pas été modifié
      (comportement : Obsidian est source de vérité pour le statut).
    """
    now  = _now()
    when = created_at or now

    # resolved_at : mettre à jour seulement si status devient 'résolue'
    resolved = resolved_at if (status == "résolue" and resolved_at) else None

    sev_clamped = max(1, min(5, severity))

    with _conn() as con:
        existing = con.execute(
            "SELECT id, resolved_at FROM weak_points WHERE synapse_id = ?",
            (synapse_id,),
        ).fetchone()

        if existing:
            # ── UPDATE ─────────────────────────────────────────────────────
            # resolved_at : on ne réécrit que si le nouveau status est résolue
            new_resolved = resolved if (status == "résolue" and resolved) else existing["resolved_at"]
            con.execute("""
                UPDATE weak_points SET
                    course_id       = ?,
                    course_title    = ?,
                    item_number     = ?,
                    detail          = ?,
                    severity        = ?,
                    status          = ?,
                    source_type     = ?,
                    college         = ?,
                    obsidian_path   = ?,
                    obsidian_uri    = ?,
                    obsidian_title  = ?,
                    raw_frontmatter = ?,
                    resolved_at     = ?
                WHERE synapse_id = ?
            """, (
                course_id, course_title, item_number,
                detail, sev_clamped, status, source, college,
                obsidian_path, obsidian_uri, obsidian_title,
                raw_frontmatter, new_resolved,
                synapse_id,
            ))
            return existing["id"]
        else:
            # ── INSERT ─────────────────────────────────────────────────────
            cur = con.execute("""
                INSERT INTO weak_points
                    (synapse_id, course_id, course_title, item_number,
                     detail, severity, status, source_type, college,
                     obsidian_path, obsidian_uri, obsidian_title,
                     raw_frontmatter, created_at, resolved_at, recurrence_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                synapse_id, course_id, course_title, item_number,
                detail, sev_clamped, status, source, college,
                obsidian_path, obsidian_uri, obsidian_title,
                raw_frontmatter, when, resolved,
            ))
            return cur.lastrowid


def get_active_critical_weak_points(severity_threshold: int = 4) -> list:
    """
    Retourne les lacunes actives/à revoir/récurrentes avec severity >= threshold.

    Critères :
      - status IN ('active', 'à revoir', 'récurrente')
      - severity >= severity_threshold (défaut : 4)

    Usage principal : remontée dans le dashboard (Phase I).
    """
    with _conn() as con:
        return con.execute("""
            SELECT * FROM weak_points
            WHERE status IN ('active', 'à revoir', 'récurrente')
              AND severity >= ?
            ORDER BY severity DESC, created_at DESC
        """, (severity_threshold,)).fetchall()


def get_review_history_by_course(course_id: str) -> list:
    """Retourne l'historique de révisions (validées/reportées/ignorées) pour un cours."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM review_history WHERE course_id = ? ORDER BY effective_due_date DESC",
            (course_id,),
        ).fetchall()


def get_bounded_week_stats(monday: datetime.date, sunday: datetime.date) -> dict:
    """
    Stats d'une semaine bornée (lundi → dimanche).
    Utilisé par la page 'Ma Progression' onglet Semaine.
    """
    import json as _json
    mon_s = monday.isoformat()
    sun_s = sunday.isoformat()

    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM study_sessions WHERE session_date >= ? AND session_date <= ?",
            (mon_s, sun_s),
        ).fetchall()

        lacunes_added = con.execute(
            "SELECT COUNT(*) FROM weak_points "
            "WHERE DATE(created_at) >= ? AND DATE(created_at) <= ?",
            (mon_s, sun_s),
        ).fetchone()[0]

        lacunes_resolved = con.execute(
            "SELECT COUNT(*) FROM weak_points WHERE status='résolue' "
            "AND resolved_at IS NOT NULL "
            "AND DATE(resolved_at) >= ? AND DATE(resolved_at) <= ?",
            (mon_s, sun_s),
        ).fetchone()[0]

        qcm_rows = con.execute(
            "SELECT score_percent, session_date FROM qcm_sessions "
            "WHERE session_date >= ? AND session_date <= ? AND score_percent IS NOT NULL",
            (mon_s, sun_s),
        ).fetchall()

        reviews_done = con.execute(
            "SELECT COUNT(*) FROM review_history WHERE status='done' "
            "AND DATE(completed_at) >= ? AND DATE(completed_at) <= ?",
            (mon_s, sun_s),
        ).fetchone()[0]

    total_min = sum(r["duration_minutes"] or 0 for r in rows)
    confs = [r["confidence"] for r in rows if r["confidence"]]
    avg_conf = round(sum(confs) / len(confs), 1) if confs else None
    act_counts: dict[str, int] = {}
    for row in rows:
        try:
            types = _json.loads(row["activity_types"] or "[]") or [row["session_type"] or "révision"]
        except Exception:
            types = [row["session_type"] or "révision"]
        for t in types:
            k = t.lower().strip()
            if k:
                act_counts[k] = act_counts.get(k, 0) + 1

    qcm_scores = [r["score_percent"] for r in qcm_rows]
    avg_qcm = round(sum(qcm_scores) / len(qcm_scores), 1) if qcm_scores else None

    return {
        "total_min":        total_min,
        "session_count":    len(rows),
        "unique_days":      len({r["session_date"] for r in rows}),
        "avg_conf":         avg_conf,
        "lecture_count":    act_counts.get("lecture", 0),
        "revision_count":   act_counts.get("révision", 0) + reviews_done,
        "anki_count":       act_counts.get("anki", 0),
        "video_count":      act_counts.get("vidéo", 0) + act_counts.get("video", 0),
        "fiche_count":      act_counts.get("fiche", 0),
        "qcm_count":        len(qcm_rows),
        "avg_qcm":          avg_qcm,
        "lacunes_added":    lacunes_added,
        "lacunes_resolved": lacunes_resolved,
        "reviews_done":     reviews_done,
    }


def get_lacunes_a_revoir(limit: int = 50) -> list:
    """Retourne les lacunes dont le statut est 'à revoir' ou 'récurrente'."""
    with _conn() as con:
        return con.execute("""
            SELECT * FROM weak_points
            WHERE status IN ('à revoir', 'récurrente')
            ORDER BY severity DESC, created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


# ── F1 — Graphe sémantique : persistance SQLite ───────────────────────────────

def save_graph_to_db(graph: dict) -> None:
    """Persiste toutes les arêtes du graphe sémantique dans course_edges."""
    now = _now()
    with _conn() as con:
        con.execute("DELETE FROM course_edges")
        con.executemany(
            "INSERT OR REPLACE INTO course_edges (source_id, target_id, weight, edge_type, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (e.source_id, e.target_id, e.weight, e.edge_type, now)
                for edges in graph.values()
                for e in edges
            ],
        )
    logger.debug(f"graph: {sum(len(v) for v in graph.values())} arêtes sauvegardées")


def load_graph_from_db() -> dict:
    """
    Recharge le graphe depuis SQLite.
    Retourne {source_id: [CourseEdge]}.
    """
    from collections import defaultdict

    from backend.core.graph.models import CourseEdge

    with _conn() as con:
        rows = con.execute("SELECT * FROM course_edges").fetchall()

    graph: dict = defaultdict(list)
    for r in rows:
        graph[r["source_id"]].append(
            CourseEdge(r["source_id"], r["target_id"], r["weight"], r["edge_type"])
        )
    return dict(graph)


# ── F2 — SM-2 : date effective pour la prochaine révision ────────────────────

def get_sm2_effective_date(
    course_id: str,
    context: str,
    review_type: str,
) -> datetime.date | None:
    """
    Retourne la date effective SM-2 calculée depuis la révision précédente.

    Ex : si J3 a été validé avec next_interval_days=5,
    retourne completed_at_date + 5 pour le J7.
    Retourne None si pas de données SM-2 disponibles.
    """
    prev_type = _PREV_REVIEW_TYPE.get(review_type)
    if not prev_type:
        return None

    with _conn() as con:
        row = con.execute("""
            SELECT completed_at, next_interval_days
            FROM review_history
            WHERE course_id = ? AND context = ? AND review_type = ?
              AND status = 'done' AND next_interval_days IS NOT NULL
            ORDER BY completed_at DESC
            LIMIT 1
        """, (course_id, context, prev_type)).fetchone()

    if not row:
        return None

    try:
        completed = datetime.date.fromisoformat(str(row["completed_at"])[:10])
        return completed + datetime.timedelta(days=int(row["next_interval_days"]))
    except (TypeError, ValueError):
        return None


def get_all_sm2_effective_dates() -> dict[tuple[str, str, str], datetime.date]:
    """
    Charge TOUTES les dates SM-2 en une seule requête.

    Retourne un dict {(course_id, context, review_type): date} où review_type
    est le type SUIVANT (ex: la clé 'J7' indique la date effective calculée
    pour la révision J7, issue du J3 précédent validé avec SM-2).

    Utilisé par generate_reviews() pour éviter N×M connexions SQLite.
    """
    # On récupère pour chaque (course_id, context, review_type) le last completed
    # avec next_interval_days, puis on calcule la date cible.
    with _conn() as con:
        rows = con.execute("""
            SELECT course_id, context, review_type, completed_at, next_interval_days
            FROM review_history
            WHERE status = 'done' AND next_interval_days IS NOT NULL
            ORDER BY course_id, context, review_type, completed_at DESC
        """).fetchall()

    # On ne garde que la révision la plus récente par (course_id, context, review_type)
    # (les doublons sont éliminés car triés DESC et on prend le premier rencontré)
    seen: set[tuple[str, str, str]] = set()
    result: dict[tuple[str, str, str], datetime.date] = {}

    for row in rows:
        key_prev = (row["course_id"], row["context"], row["review_type"])
        if key_prev in seen:
            continue
        seen.add(key_prev)

        # Le type SUIVANT dans la séquence SM-2
        next_type: str | None = None
        for nxt, prv in _PREV_REVIEW_TYPE.items():
            if prv == row["review_type"]:
                next_type = nxt
                break

        if next_type is None:
            continue  # J30 n'a pas de type suivant dans notre séquence

        try:
            completed = datetime.date.fromisoformat(str(row["completed_at"])[:10])
            sm2_date = completed + datetime.timedelta(days=int(row["next_interval_days"]))
            key_next = (row["course_id"], row["context"], next_type)
            # Ne surcharge pas si déjà calculé depuis une révision plus récente
            if key_next not in result:
                result[key_next] = sm2_date
        except (TypeError, ValueError):
            continue

    return result


# ── F3 — Pièges EDN : upsert dans weak_points ────────────────────────────────

def upsert_auto_detected_trap(
    course_id: str,
    course_title: str = "",
    item_number: str = "",
    detail: str = "",
    severity: int = 4,
    obsidian_path: str = "",
) -> int:
    """
    Crée ou ignore un piège EDN auto-détecté dans weak_points.
    Idempotent sur (course_id, category='Piège EDN', detail).
    Retourne l'id de la ligne.
    """
    now = _now()
    with _conn() as con:
        existing = con.execute("""
            SELECT id FROM weak_points
            WHERE course_id = ? AND category = 'Piège EDN'
              AND source_type = 'auto_detection' AND detail = ?
        """, (course_id, detail)).fetchone()

        if existing:
            return int(existing["id"])

        cur = con.execute("""
            INSERT INTO weak_points
                (course_id, course_title, item_number, category, detail,
                 severity, status, source_type, obsidian_path, created_at)
            VALUES (?, ?, ?, 'Piège EDN', ?, ?, 'active', 'auto_detection', ?, ?)
        """, (course_id, course_title, item_number, detail, severity, obsidian_path, now))
        return int(cur.lastrowid)


# ── Sprint 2 — Propositions de lacunes récurrentes ───────────────────────────

def _migrate_pending_gap_proposals() -> None:
    """Crée la table pending_gap_proposals si absente (idempotent)."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS pending_gap_proposals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                item_number      TEXT    NOT NULL,
                error_type       TEXT    NOT NULL,
                course_title     TEXT    DEFAULT '',
                course_id        TEXT    DEFAULT '',
                session_ids      TEXT    DEFAULT '[]',
                occurrence_count INTEGER DEFAULT 2,
                created_at       TEXT    NOT NULL,
                expires_at       TEXT    NOT NULL,
                status           TEXT    NOT NULL DEFAULT 'pending'
            );
            CREATE INDEX IF NOT EXISTS idx_pgp_item
                ON pending_gap_proposals(item_number);
            CREATE INDEX IF NOT EXISTS idx_pgp_status
                ON pending_gap_proposals(status);
        """)


def check_and_propose_recurring_gaps(
    item_number: str,
    error_types: list[str],
    new_session_id: int,
    course_title: str = "",
    course_id: str = "",
) -> list[int]:
    """
    Appelé après chaque insertion de session QCM.
    Pour chaque error_type, si le même type apparaît sur item_number
    dans ≥ RECURRENCE_THRESHOLD sessions distinctes, crée ou met à jour
    une proposition pending_gap_proposals.
    Retourne la liste des proposal IDs créés ou mis à jour.
    """
    import datetime as _dt
    import json as _json

    if not item_number or not error_types:
        return []

    proposal_ids: list[int] = []
    now = _now()
    expires_at = (
        _dt.date.fromisoformat(now[:10]) + _dt.timedelta(days=14)
    ).isoformat()

    with _conn() as con:
        for error_type in error_types:
            # Compte les sessions antérieures avec le même item + error_type
            # json_each() évite le LIKE '%...%' (full-table scan sur error_types TEXT/JSON)
            prior_rows = con.execute(
                "SELECT DISTINCT qs.id FROM qcm_sessions qs, json_each(qs.error_types) je "
                "WHERE qs.item_number = ? AND je.value = ? AND qs.id != ?",
                (item_number, error_type, new_session_id),
            ).fetchall()

            total_count = len(prior_rows) + 1  # inclut la session courante
            if total_count < RECURRENCE_THRESHOLD:
                continue

            all_session_ids = {
                *(f"qcm:{r['id']}" for r in prior_rows),
                f"qcm:{new_session_id}",
            }

            # Vérifier si une proposition pending existe déjà
            existing = con.execute(
                "SELECT id, session_ids FROM pending_gap_proposals "
                "WHERE item_number = ? AND error_type = ? AND status = 'pending'",
                (item_number, error_type),
            ).fetchone()

            if existing:
                old_sids = _json.loads(existing["session_ids"] or "[]")
                tagged_old_sids = {
                    sid if isinstance(sid, str) and ":" in sid else f"qcm:{sid}"
                    for sid in old_sids
                }
                merged = sorted(tagged_old_sids | all_session_ids)
                con.execute(
                    "UPDATE pending_gap_proposals "
                    "SET occurrence_count = ?, session_ids = ? WHERE id = ?",
                    (total_count, _json.dumps(merged), existing["id"]),
                )
                proposal_ids.append(existing["id"])
            else:
                cur = con.execute(
                    "INSERT INTO pending_gap_proposals "
                    "(item_number, error_type, course_title, course_id, "
                    " session_ids, occurrence_count, created_at, expires_at, status) "
                    "VALUES (?,?,?,?,?,?,?,?,'pending')",
                    (
                        item_number, error_type, course_title, course_id,
                        _json.dumps(sorted(all_session_ids)), total_count,
                        now, expires_at,
                    ),
                )
                proposal_ids.append(cur.lastrowid)

    return proposal_ids


def check_and_propose_recurring_study_feedback(
    item_number: str,
    error_type: str,
    new_session_id: int,
    course_title: str = "",
    course_id: str = "",
) -> list[int]:
    """Propose une lacune seulement après répétition d'un signal de session."""
    import datetime as _dt
    import json as _json

    normalized_error_type = error_type.strip()
    if not item_number or not normalized_error_type:
        return []

    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT id FROM study_sessions "
            "WHERE item_number = ? "
            "AND LOWER(TRIM(weak_category)) = LOWER(TRIM(?))",
            (item_number, normalized_error_type),
        ).fetchall()

        source_session_ids = {f"study:{row['id']}" for row in rows}
        source_session_ids.add(f"study:{new_session_id}")
        occurrence_count = len(source_session_ids)
        if occurrence_count < RECURRENCE_THRESHOLD:
            return []

        existing = con.execute(
            "SELECT id, session_ids FROM pending_gap_proposals "
            "WHERE item_number = ? AND error_type = ? AND status = 'pending'",
            (item_number, normalized_error_type),
        ).fetchone()
        if existing:
            old_sids = _json.loads(existing["session_ids"] or "[]")
            tagged_old_sids = {
                sid if isinstance(sid, str) and ":" in sid else f"qcm:{sid}"
                for sid in old_sids
            }
            merged = sorted(tagged_old_sids | source_session_ids)
            con.execute(
                "UPDATE pending_gap_proposals "
                "SET occurrence_count = ?, session_ids = ? WHERE id = ?",
                (len(merged), _json.dumps(merged), existing["id"]),
            )
            return [existing["id"]]

        now = _now()
        expires_at = (_dt.date.fromisoformat(now[:10]) + _dt.timedelta(days=14)).isoformat()
        cur = con.execute(
            "INSERT INTO pending_gap_proposals "
            "(item_number, error_type, course_title, course_id, session_ids, "
            "occurrence_count, created_at, expires_at, status) "
            "VALUES (?,?,?,?,?,?,?,?,'pending')",
            (
                item_number,
                normalized_error_type,
                course_title,
                course_id,
                _json.dumps(sorted(source_session_ids)),
                occurrence_count,
                now,
                expires_at,
            ),
        )
        return [cur.lastrowid]


def get_pending_proposals(limit: int = 50) -> list:
    """Retourne les propositions de lacunes récurrentes en attente (non expirées)."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    with _conn() as con:
        return con.execute(
            "SELECT * FROM pending_gap_proposals "
            "WHERE status = 'pending' AND expires_at >= ? "
            "ORDER BY occurrence_count DESC, created_at DESC LIMIT ?",
            (today, limit),
        ).fetchall()


def get_pending_proposals_count() -> int:
    """Retourne le nombre de propositions en attente non expirées."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM pending_gap_proposals "
            "WHERE status = 'pending' AND expires_at >= ?",
            (today,),
        ).fetchone()
    return row[0] if row else 0


def accept_gap_proposal(proposal_id: int, course_id: str = "") -> int:
    """
    Accepte une proposition : crée le weak_point récurrent et marque 'accepted'.
    Retourne le wp_id créé.
    """
    with _conn() as con:
        proposal = con.execute(
            "SELECT * FROM pending_gap_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()

    if not proposal:
        raise ValueError(f"Proposition {proposal_id} introuvable")

    count       = proposal["occurrence_count"]
    item_number = proposal["item_number"]
    error_type  = proposal["error_type"]
    course_title = proposal["course_title"] or ""
    cid         = course_id or proposal["course_id"] or "—"

    detail = (
        f"Erreur récurrente ({error_type}) — {count} sessions · Item {item_number}"
        if item_number
        else f"Erreur récurrente ({error_type}) — {count} sessions"
    )

    # Sévérité : 2 sessions→3, 3→4, 4+→5
    severity = min(5, max(3, count + 1))

    # Catégorie déduite du type d'erreur connu
    _category_map = {
        "raisonnement":  "Raisonnement",
        "inattention":   "Inattention",
        "stratégie EDN": "Piège EDN",
    }
    category = _category_map.get(error_type)

    wp_id = add_weak_point_full(
        course_id=cid,
        detail=detail,
        course_title=course_title,
        item_number=item_number,
        category=category,
        severity=severity,
        source_type="error_type_recurrence",
    )

    with _conn() as con:
        con.execute(
            "UPDATE weak_points SET status='récurrente', recurrence_count=? WHERE id=?",
            (count, wp_id),
        )
        con.execute(
            "UPDATE pending_gap_proposals SET status='accepted' WHERE id=?",
            (proposal_id,),
        )

    return wp_id


def dismiss_gap_proposal(proposal_id: int) -> None:
    """Rejette une proposition sans créer de weak_point."""
    with _conn() as con:
        con.execute(
            "UPDATE pending_gap_proposals SET status='dismissed' WHERE id=?",
            (proposal_id,),
        )


def expire_old_gap_proposals() -> int:
    """Passe à 'expired' les propositions dont expires_at est dépassé. Retourne le nombre."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    with _conn() as con:
        cur = con.execute(
            "UPDATE pending_gap_proposals SET status='expired' "
            "WHERE status='pending' AND expires_at < ?",
            (today,),
        )
    return cur.rowcount


# ── Sprint 3 — Stats par item EDN ─────────────────────────────────────────────

def get_item_stats(limit: int = 300) -> list[dict]:
    """
    Vue agrégée par item EDN depuis qcm_sessions.
    Toutes plateformes et périodes confondues.
    Retourne une liste triée par taux de réussite croissant (les plus difficiles en premier).
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT item_number, MAX(course_title) AS course_title, "
            "COUNT(*) AS session_count, "
            "AVG(score_percent) AS avg_score, "
            "SUM(CASE WHEN score_percent >= ? THEN 1 ELSE 0 END) AS pass_count, "
            "SUM(CASE WHEN score_percent < ?  THEN 1 ELSE 0 END) AS fail_count, "
            "MAX(session_date) AS last_date "
            "FROM qcm_sessions "
            "WHERE item_number IS NOT NULL AND TRIM(item_number) != '' "
            "  AND score_percent IS NOT NULL "
            "GROUP BY item_number "
            "ORDER BY avg_score ASC "
            "LIMIT ?",
            (QCM_PASS_THRESHOLD, QCM_PASS_THRESHOLD, limit),
        ).fetchall()

        recurring_items = {
            r["item_number"]
            for r in con.execute(
                "SELECT DISTINCT item_number FROM weak_points "
                "WHERE status='récurrente' "
                "  AND item_number IS NOT NULL AND TRIM(item_number) != ''"
            ).fetchall()
        }

        pending_items = {
            r["item_number"]
            for r in con.execute(
                "SELECT DISTINCT item_number FROM pending_gap_proposals "
                "WHERE status='pending'"
            ).fetchall()
        }

        # 2 derniers scores par item pour la tendance
        trend_rows = con.execute(
            "SELECT item_number, score_percent FROM qcm_sessions "
            "WHERE item_number IS NOT NULL AND TRIM(item_number) != '' "
            "  AND score_percent IS NOT NULL "
            "ORDER BY item_number, session_date DESC, id DESC"
        ).fetchall()

    trend_map: dict[str, list[float]] = {}
    for r in trend_rows:
        itn = r["item_number"]
        if itn not in trend_map:
            trend_map[itn] = []
        if len(trend_map[itn]) < 2:
            trend_map[itn].append(r["score_percent"])

    result: list[dict] = []
    for r in rows:
        itn = r["item_number"]
        scores = trend_map.get(itn, [])
        trend = trend_color = None
        if len(scores) >= 2:
            diff = scores[0] - scores[1]
            if diff > 2:
                trend, trend_color = "↑", "text-green-500"
            elif diff < -2:
                trend, trend_color = "↓", "text-red-500"
            else:
                trend, trend_color = "→", "text-slate-400"

        result.append({
            "item_number":          itn,
            "course_title":         r["course_title"] or "—",
            "session_count":        r["session_count"],
            "avg_score":            round(r["avg_score"], 1) if r["avg_score"] is not None else None,
            "pass_count":           r["pass_count"] or 0,
            "fail_count":           r["fail_count"] or 0,
            "last_date":            r["last_date"] or "",
            "trend":                trend,
            "trend_color":          trend_color or "text-slate-400",
            "has_recurring_gap":    itn in recurring_items,
            "has_pending_proposal": itn in pending_items,
        })

    return result


# ── PDF Zéro-Friction : cache local ───────────────────────────────────────────

def get_pdf_cache(course_id: str, context: str) -> str | None:
    """
    Retourne le chemin du PDF mis en cache pour (course_id, context).
    Si pas de cache, retourne None.

    Paramètres :
        course_id : identifiant du cours
        context   : 'college' ou 'ue'

    Retourne :
        str : chemin absolu du PDF
        None : pas d'entrée en cache
    """
    with _conn() as con:
        row = con.execute(
            "SELECT pdf_path FROM pdf_local_cache WHERE course_id = ? AND context = ?",
            (course_id, context),
        ).fetchone()
    return row["pdf_path"] if row else None


def get_all_pdf_cache() -> dict[tuple[str, str], str]:
    """
    Retourne tout le cache PDF en une seule requête : {(course_id, context): pdf_path}.
    À utiliser au préchargement (des centaines de cours) au lieu d'appeler
    get_pdf_cache() par cours/contexte (évite ~2 requêtes SQLite par cours).
    """
    with _conn() as con:
        rows = con.execute("SELECT course_id, context, pdf_path FROM pdf_local_cache").fetchall()
    return {(row["course_id"], row["context"]): row["pdf_path"] for row in rows}


def set_pdf_cache(course_id: str, context: str, pdf_path: str) -> None:
    """
    Enregistre ou remplace le chemin du PDF pour (course_id, context).
    Idempotent : appeler plusieurs fois avec la même clé (course_id, context)
    ne crée qu'une seule ligne.

    Paramètres :
        course_id : identifiant du cours
        context   : 'college' ou 'ue'
        pdf_path  : chemin absolu du PDF
    """
    detected_at = datetime.date.today().isoformat()
    with _conn() as con:
        con.execute("""
            INSERT OR REPLACE INTO pdf_local_cache
                (course_id, context, pdf_path, detected_at)
            VALUES (?, ?, ?, ?)
        """, (course_id, context, pdf_path, detected_at))


def cleanup_pdf_cache() -> int:
    """
    Supprime les entrées de pdf_local_cache dont le fichier n'existe plus sur disque.
    Appelée au démarrage (Phase A) pour nettoyer les chemins stale.

    Retourne :
        int : nombre d'entrées supprimées
    """
    with _conn() as con:
        rows = con.execute("SELECT course_id, context, pdf_path FROM pdf_local_cache").fetchall()
        stale = [(row["course_id"], row["context"]) for row in rows if not os.path.isfile(row["pdf_path"])]
        if stale:
            con.executemany(
                "DELETE FROM pdf_local_cache WHERE course_id = ? AND context = ?", stale,
            )
    return len(stale)


# ── API publique — pdf_item_scan ─────────────────────────────────────────────

def get_processed_pdf_items() -> set[tuple[str, int]]:
    """Retourne les (college, item_num) dont le status est 'created' ou 'existing'."""
    rows = _conn().execute(
        "SELECT college, item_num FROM pdf_item_scan WHERE status IN ('created', 'existing')"
    ).fetchall()
    return {(r["college"], r["item_num"]) for r in rows}


def upsert_pdf_scan(college: str, item_num: int, status: str, pdf_name: str | None = None) -> None:
    """Insère ou met à jour un résultat de scan PDF."""
    with _conn() as con:
        con.execute(
            """
            INSERT INTO pdf_item_scan (college, item_num, pdf_name, status, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(college, item_num) DO UPDATE SET
                pdf_name   = excluded.pdf_name,
                status     = excluded.status,
                updated_at = excluded.updated_at
            """,
            (college, item_num, pdf_name, status, _now()),
        )


def reset_pdf_scan() -> int:
    """Supprime toutes les entrées pdf_item_scan (force rescan). Retourne le nb supprimé."""
    with _conn() as con:
        cur = con.execute("DELETE FROM pdf_item_scan")
        return cur.rowcount


def get_pdf_scan_stats() -> dict:
    """Retourne {'created': N, 'existing': N, 'failed': N, 'total': N}."""
    rows = _conn().execute(
        "SELECT status, COUNT(*) AS n FROM pdf_item_scan GROUP BY status"
    ).fetchall()
    stats: dict[str, int] = {"created": 0, "existing": 0, "failed": 0, "total": 0}
    for r in rows:
        s = r["status"]
        if s in stats:
            stats[s] = r["n"]
        stats["total"] += r["n"]
    return stats


# ── Migration Routine tables ──────────────────────────────────────────────────

def _migrate_routine_tables() -> None:
    """Insère les items de routine par défaut si la table est vide."""
    with _conn() as con:
        count = con.execute("SELECT COUNT(*) FROM routine_items").fetchone()[0]
        if count == 0:
            con.executemany(
                "INSERT OR IGNORE INTO routine_items (name, position) VALUES (?, ?)",
                [('Révision', 0), ('QCM', 1), ('Sport', 2), ('Musique', 3), ('Anki', 4)],
            )


def _migrate_oic_anythingllm_validation() -> None:
    """
    Migration douce : ajoute oic_level à lisa_oic et crée/met à niveau oic_attempts.
    Idempotente — ne touche pas aux données existantes (sauf reconstruction de table
    nécessaire pour ajouter ON DELETE CASCADE à une table déjà créée sans cascade).
    """
    with _conn() as con:
        existing = {
            row["name"]
            for row in con.execute("PRAGMA table_info(lisa_oic)").fetchall()
        }
        if "oic_level" not in existing:
            con.execute("ALTER TABLE lisa_oic ADD COLUMN oic_level INTEGER NOT NULL DEFAULT 0")
        if "active" not in existing:
            con.execute("ALTER TABLE lisa_oic ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

        table_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='oic_attempts'"
        ).fetchone() is not None

        has_cascade = False
        if table_exists:
            fk_rows = con.execute("PRAGMA foreign_key_list(oic_attempts)").fetchall()
            has_cascade = any(
                row["table"] == "lisa_oic" and (row["on_delete"] or "").upper() == "CASCADE"
                for row in fk_rows
            )

        if not table_exists:
            con.executescript("""
                CREATE TABLE oic_attempts (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    oic_id         INTEGER NOT NULL REFERENCES lisa_oic(id) ON DELETE CASCADE,
                    session_score  INTEGER NOT NULL,
                    questions_json TEXT    NOT NULL,
                    attempted_at   TEXT    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_oic_attempts_oic ON oic_attempts(oic_id);
            """)
        elif not has_cascade:
            con.executescript("""
                CREATE TABLE oic_attempts_new (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    oic_id         INTEGER NOT NULL REFERENCES lisa_oic(id) ON DELETE CASCADE,
                    session_score  INTEGER NOT NULL,
                    questions_json TEXT    NOT NULL,
                    attempted_at   TEXT    NOT NULL
                );
                INSERT INTO oic_attempts_new (id, oic_id, session_score, questions_json, attempted_at)
                    SELECT id, oic_id, session_score, questions_json, attempted_at FROM oic_attempts;
                DROP TABLE oic_attempts;
                ALTER TABLE oic_attempts_new RENAME TO oic_attempts;
                CREATE INDEX IF NOT EXISTS idx_oic_attempts_oic ON oic_attempts(oic_id);
            """)


# ── API publique — Routine quotidienne ───────────────────────────────────────

def get_routine_items() -> list[str]:
    """Retourne les noms des items de routine actifs, triés par position."""
    rows = _conn().execute(
        "SELECT name FROM routine_items WHERE active = 1 ORDER BY position"
    ).fetchall()
    return [r["name"] for r in rows]


def get_routine_checks(date_str: str) -> dict[str, bool]:
    """Retourne {item_name: checked} pour une date ('YYYY-MM-DD')."""
    rows = _conn().execute(
        "SELECT item_name, checked FROM routine_checks WHERE date = ?",
        (date_str,),
    ).fetchall()
    return {r["item_name"]: bool(r["checked"]) for r in rows}


def set_routine_check(date_str: str, item_name: str, checked: bool) -> None:
    """Upsert l'état coché d'un item de routine pour une date donnée."""
    with _conn() as con:
        con.execute(
            "INSERT INTO routine_checks (date, item_name, checked) VALUES (?, ?, ?) "
            "ON CONFLICT(date, item_name) DO UPDATE SET checked = excluded.checked",
            (date_str, item_name, 1 if checked else 0),
        )


# ── API LiSA OIC ──────────────────────────────────────────────────────────────

def get_lisa_oic(course_id: str) -> list | None:
    """
    Retourne les OIC d'un cours depuis le cache SQLite.
    - None  : jamais fetchés (afficher spinner + scraper)
    - []    : fetchés mais aucun OIC trouvé sur LiSA
    - [...]  : liste de sqlite3.Row
    """
    with _conn() as con:
        cached = con.execute(
            "SELECT 1 FROM lisa_oic_cache WHERE course_id = ?", (course_id,)
        ).fetchone()
        if cached is None:
            return None
        return con.execute(
            "SELECT * FROM lisa_oic WHERE course_id = ? AND active = 1 ORDER BY rang, ordre",
            (course_id,),
        ).fetchall()


def upsert_lisa_oic(course_id: str, oics: list[dict]) -> None:
    """
    Réconcilie les OIC d'un cours dans SQLite.
    Préserve l'identité, mastered, le niveau et les tentatives des codes existants.
    Marque le cours comme fetché même si oics=[].
    """
    today = datetime.date.today().isoformat()
    with _conn() as con:
        # Désactiver les codes absents de la réponse sans supprimer leurs tentatives.
        con.execute("UPDATE lisa_oic SET active = 0 WHERE course_id = ?", (course_id,))
        saved_state: dict[str, sqlite3.Row] = {
            row["oic_code"]: row
            for row in con.execute(
                "SELECT id, oic_code, mastered, oic_level FROM lisa_oic WHERE course_id = ? AND oic_code IS NOT NULL",
                (course_id,),
            ).fetchall()
        }
        # Mettre à jour les codes existants ou insérer les nouveaux.
        for oic in oics:
            code = oic.get("oic_code") or ""
            prev = saved_state.get(code) if code else None
            mastered = prev["mastered"] if prev is not None else 0
            oic_level = prev["oic_level"] if prev is not None else 0
            if prev is not None:
                con.execute(
                    """UPDATE lisa_oic SET intitule = ?, rang = ?, rubrique = ?,
                       ordre = ?, mastered = ?, oic_level = ?, fetched_at = ?, active = 1
                       WHERE id = ?""",
                    (
                        oic.get("intitule", ""), oic.get("rang", "A"),
                        oic.get("rubrique", ""), oic.get("ordre", 0),
                        mastered, oic_level, today, prev["id"],
                    ),
                )
            else:
                con.execute(
                    """INSERT INTO lisa_oic
                       (course_id, oic_code, intitule, rang, rubrique, ordre, mastered, oic_level, fetched_at, active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        course_id, code or None, oic.get("intitule", ""),
                        oic.get("rang", "A"), oic.get("rubrique", ""),
                        oic.get("ordre", 0), mastered, oic_level, today,
                    ),
                )
        # Marquer comme fetché
        con.execute(
            "INSERT OR REPLACE INTO lisa_oic_cache (course_id, fetched_at) VALUES (?, ?)",
            (course_id, today),
        )


def toggle_lisa_oic_mastery(oic_id: int) -> bool:
    """
    Bascule mastered 0↔1 pour un OIC.
    Retourne le nouvel état (True = maîtrisé).
    Retourne False si l'OIC est introuvable.
    """
    with _conn() as con:
        row = con.execute(
            "SELECT mastered FROM lisa_oic WHERE id = ?", (oic_id,)
        ).fetchone()
        if row is None:
            return False
        new_val = 0 if row["mastered"] else 1
        con.execute(
            "UPDATE lisa_oic SET mastered = ? WHERE id = ?", (new_val, oic_id)
        )
        return bool(new_val)


def save_oic_attempt(oic_id: int, session_score: int, questions_json: str) -> int:
    """
    Enregistre une tentative d'évaluation OIC. Retourne l'id inséré.

    Une tentative à OIC_SUCCESS_SCORE ou au-dessus marque l'OIC comme maîtrisé.
    Un échec ultérieur ne le démarque pas : la réussite est acquise, c'est la
    dégradation de la maîtrise de l'item qui porte l'oubli.
    """
    from backend.core.knowledge.models import OIC_SUCCESS_SCORE

    with _conn() as con:
        cur = con.execute(
            """INSERT INTO oic_attempts (oic_id, session_score, questions_json, attempted_at)
               VALUES (?, ?, ?, ?)""",
            (oic_id, session_score, questions_json, _now()),
        )
        if session_score >= OIC_SUCCESS_SCORE:
            con.execute("UPDATE lisa_oic SET mastered = 1 WHERE id = ?", (oic_id,))
        return cur.lastrowid


def get_oic_attempts(oic_id: int, limit: int = 10) -> list:
    """Retourne les tentatives d'un OIC, les plus récentes en premier."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM oic_attempts WHERE oic_id = ? ORDER BY id DESC LIMIT ?",
            (oic_id, limit),
        ).fetchall()


def update_oic_level(oic_id: int, new_level: int) -> None:
    """Met à jour le niveau de maîtrise progressif d'un OIC."""
    with _conn() as con:
        con.execute("UPDATE lisa_oic SET oic_level = ? WHERE id = ?", (new_level, oic_id))


def import_practice_batch(batch) -> dict[str, int]:
    """Importe une banque DP/KFP et ignore les cas déjà présents."""
    import json

    inserted = duplicates = needs_review = 0
    with _conn() as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(imported_practice_cases)").fetchall()}
        if "source_content" not in columns:
            con.execute("ALTER TABLE imported_practice_cases ADD COLUMN source_content TEXT NOT NULL DEFAULT ''")
        for case in batch.cases:
            existing = con.execute(
                "SELECT id FROM imported_practice_cases WHERE fingerprint = ?",
                (case.fingerprint,),
            ).fetchone()
            if existing:
                duplicates += 1
                continue
            cur = con.execute(
                """INSERT INTO imported_practice_cases
                   (fingerprint, external_id, kind, title, stem, item_numbers,
                   source, source_content, status, review_reason, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (case.fingerprint, case.external_id, case.kind, case.title, case.stem,
                 json.dumps(case.item_numbers), batch.source, getattr(batch, "raw_text", ""),
                 case.status, case.review_reason, _now()),
            )
            for position, question in enumerate(case.questions, start=1):
                con.execute(
                    """INSERT INTO imported_practice_questions
                       (case_id, position, prompt, choices, answer, explanation)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (cur.lastrowid, position, question.prompt,
                     json.dumps(question.choices, ensure_ascii=False), question.answer,
                     question.explanation),
                )
            inserted += 1
            needs_review += case.status == "needs_review"
    return {"inserted": inserted, "duplicates": duplicates, "needs_review": needs_review}


def _imported_case_rows(rows):
    import json

    result = []
    for row in rows:
        item = dict(row)
        item["item_numbers"] = json.loads(item["item_numbers"] or "[]")
        result.append(item)
    return result


def get_imported_practice_cases(*, item_number: str | None = None, limit: int = 100) -> list:
    import json

    with _conn() as con:
        if item_number:
            rows = con.execute(
                "SELECT * FROM imported_practice_cases WHERE item_numbers LIKE ? "
                "ORDER BY imported_at DESC LIMIT ?",
                (f'%"{item_number}"%', limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM imported_practice_cases ORDER BY imported_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = _imported_case_rows(rows)
        for case in result:
            questions = con.execute(
                "SELECT * FROM imported_practice_questions WHERE case_id = ? ORDER BY position",
                (case["id"],),
            ).fetchall()
            for question in questions:
                item = dict(question)
                item["choices"] = json.loads(item["choices"] or "[]")
                case.setdefault("questions", []).append(item)
        return result


def get_import_review_queue(limit: int = 100) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM imported_practice_cases WHERE status = 'needs_review' "
            "ORDER BY imported_at DESC LIMIT ?", (limit,),
        ).fetchall()
        return _imported_case_rows(rows)


def get_random_imported_practice_cases(*, item_number: str | None = None, limit: int = 10) -> list:
    """Retourne des cas locaux aléatoires, filtrables par ITEM."""
    with _conn() as con:
        if item_number:
            rows = con.execute(
                "SELECT * FROM imported_practice_cases WHERE status = 'ready' AND item_numbers LIKE ? "
                "ORDER BY RANDOM() LIMIT ?", (f'%"{item_number}"%', limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM imported_practice_cases WHERE status = 'ready' "
                "ORDER BY RANDOM() LIMIT ?", (limit,),
            ).fetchall()
        return _imported_case_rows(rows)


def set_ai_practice_anchor(question_id: int, label: str = "") -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT id FROM ai_practice_anchors WHERE question_id = ?", (question_id,)
        ).fetchone()
        if row:
            con.execute("UPDATE ai_practice_anchors SET active = 1, label = ? WHERE id = ?", (label, row["id"]))
            return row["id"]
        cur = con.execute(
            "INSERT INTO ai_practice_anchors (question_id, label, created_at) VALUES (?, ?, ?)",
            (question_id, label, _now()),
        )
        return cur.lastrowid


def remove_ai_practice_anchor(question_id: int) -> None:
    with _conn() as con:
        con.execute("UPDATE ai_practice_anchors SET active = 0 WHERE question_id = ?", (question_id,))


def get_ai_practice_anchors(*, item_number: str | None = None, limit: int = 100) -> list:
    with _conn() as con:
        query = """SELECT a.*, q.prompt, q.answer, q.explanation, q.item_number
                   FROM ai_practice_anchors a
                   JOIN ai_practice_questions q ON q.id = a.question_id
                   WHERE a.active = 1"""
        params: list = []
        if item_number:
            query += " AND q.item_number = ?"
            params.append(item_number)
        query += " ORDER BY a.created_at DESC LIMIT ?"
        params.append(limit)
        return con.execute(query, params).fetchall()


def record_ai_usage(
    task: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_ms: float | None = None,
    error: str | None = None,
    context: str | None = None,
) -> int:
    """Enregistre un appel IA dans la table ai_usage_logs."""
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO ai_usage_logs
               (task, model, input_tokens, output_tokens, cost_usd, duration_ms, error, context, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task, model, input_tokens, output_tokens, cost_usd, duration_ms, error, context, _now()),
        )
        return cur.lastrowid


def get_ai_usage_summary(limit: int = 50) -> dict:
    """Retourne les métriques cumulées d'utilisation IA et la liste des derniers appels."""
    with _conn() as con:
        summary_row = con.execute(
            """SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
                COALESCE(SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END), 0) AS total_errors
               FROM ai_usage_logs"""
        ).fetchone()

        recent_rows = con.execute(
            """SELECT * FROM ai_usage_logs ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

        by_task_rows = con.execute(
            """SELECT task,
                      COUNT(*) AS calls,
                      SUM(input_tokens + output_tokens) AS tokens,
                      SUM(cost_usd) AS cost
               FROM ai_usage_logs
               GROUP BY task
               ORDER BY cost DESC"""
        ).fetchall()

        by_context_rows = con.execute(
            """SELECT COALESCE(context, task) AS context,
                      task,
                      COUNT(*) AS calls,
                      SUM(input_tokens + output_tokens) AS tokens,
                      SUM(cost_usd) AS cost
               FROM ai_usage_logs
               GROUP BY COALESCE(context, task)
               ORDER BY cost DESC"""
        ).fetchall()

    return {
        "summary": dict(summary_row) if summary_row else {},
        "recent_calls": [dict(r) for r in recent_rows],
        "by_task": [dict(r) for r in by_task_rows],
        "by_context": [dict(r) for r in by_context_rows],
    }


def get_item_pedagogical_history(item_number: str) -> list[dict]:
    """
    Retourne l'historique pédagogique centralisé d'un item (Annales UNESS, QCM, DP/KFP).
    Inclut les scores, rangs (A vs B) et la typologie des erreurs (Rang A, Piège, Diag Diff, Temps).
    """
    clean_item = str(item_number or "").strip()
    if not clean_item:
        return []

    history: list[dict] = []
    with _conn() as con:
        # 1. Sessions pratiques / Annales UNESS / DP IA
        rows_ai = con.execute(
            """SELECT * FROM ai_practice_sessions 
               WHERE item_number = ? OR item_number LIKE ?
               ORDER BY created_at DESC LIMIT 30""",
            (clean_item, f"%{clean_item}%")
        ).fetchall()
        for r in rows_ai:
            r_dict = dict(r)
            score_p = r_dict.get("score_percent")
            err_cat = "rang_a" if (score_p is not None and score_p < 50.0) else None
            history.append({
                "id": f"ai_{r_dict['id']}",
                "date": (r_dict.get("completed_at") or r_dict.get("created_at") or "")[:10],
                "type": "Annale UNESS" if r_dict.get("annale_id") else "DP / KFP IA",
                "title": r_dict.get("title") or f"Session {r_dict['id']}",
                "score_percent": score_p,
                "rank": r_dict.get("rank") or "A",
                "error_category": r_dict.get("error_category") or err_cat,
                "annale_id": r_dict.get("annale_id"),
            })

        # 2. Résultats QCM locaux
        rows_qcm = con.execute(
            """SELECT * FROM qcm_results
               WHERE course_id LIKE ?
               ORDER BY session_date DESC LIMIT 20""",
            (f"%{clean_item}%",)
        ).fetchall()
        for r in rows_qcm:
            r_dict = dict(r)
            history.append({
                "id": f"qcm_{r_dict.get('id', 0)}",
                "date": (r_dict.get("session_date") or "")[:10],
                "type": "Entraînement QCM",
                "title": f"QCM {r_dict.get('session_type', 'standard')}",
                "score_percent": r_dict.get("score_percent"),
                "rank": "A",
                "error_category": r_dict.get("error_category"),
                "annale_id": None,
            })

    return sorted(history, key=lambda x: str(x.get("date") or ""), reverse=True)


# ── Auto-init à l'import ──────────────────────────────────────────────────────
try:
    init_db()
except Exception as _e:
    logger.error(f"Impossible d'initialiser SQLite: {_e}")
