"""Idempotent migrations for the local catalog tables."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.state.catalog_schema import CATALOG_MIGRATIONS


_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = _ROOT / "data" / "synapse_local.db"


def _resolve_db_path(db_path: Path | str | None) -> Path:
    if db_path is not None:
        return Path(db_path).expanduser()
    configured = os.getenv("SYNAPSE_TEST_DB_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def catalog_schema_version(db_path: Path | str | None = None) -> int:
    path = _resolve_db_path(db_path)
    if not path.exists():
        return 0
    with sqlite3.connect(path) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'catalog_schema_migrations'"
        ).fetchone()
        if table is None:
            return 0
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM catalog_schema_migrations"
        ).fetchone()
        return int(row[0] or 0)


def ensure_catalog_tables(connection: sqlite3.Connection) -> None:
    """Apply all missing catalog migrations to an open connection."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    current = int(
        connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM catalog_schema_migrations"
        ).fetchone()[0]
        or 0
    )
    for version, sql in CATALOG_MIGRATIONS:
        if version <= current:
            continue
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO catalog_schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, _utc_now()),
        )
        current = version


def run_catalog_migrations(db_path: Path | str | None = None) -> tuple[int, ...]:
    """Create the database if necessary and apply each missing migration once."""
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        before = catalog_schema_version(path)
        ensure_catalog_tables(connection)
        connection.commit()
        after = catalog_schema_version(path)
    return tuple(version for version, _ in CATALOG_MIGRATIONS if before < version <= after)
