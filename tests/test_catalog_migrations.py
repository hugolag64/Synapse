from __future__ import annotations

import sqlite3

from backend.state.catalog_migrations import catalog_schema_version, run_catalog_migrations


def test_catalog_migration_creates_versioned_item_and_fiche_tables(tmp_path):
    db_path = tmp_path / "synapse.sqlite"

    applied = run_catalog_migrations(db_path)

    assert applied
    assert catalog_schema_version(db_path) >= 1
    tables = sqlite3.connect(db_path).execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {row[0] for row in tables}
    assert {
        "catalog_items",
        "catalog_colleges",
        "catalog_fiches",
        "catalog_fiche_colleges",
        "catalog_archived_courses",
    } <= names


def test_catalog_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "synapse.sqlite"

    first = run_catalog_migrations(db_path)
    second = run_catalog_migrations(db_path)

    assert first
    assert second == ()
