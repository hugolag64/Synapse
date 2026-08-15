"""Versioned SQLite schema for the local course/item catalog."""

from __future__ import annotations


CATALOG_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE catalog_items (
            id TEXT PRIMARY KEY,
            item_number INTEGER NOT NULL UNIQUE,
            official_title TEXT NOT NULL DEFAULT '',
            local_title TEXT,
            archived_at TEXT,
            provenance TEXT NOT NULL DEFAULT 'official_referential',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE catalog_colleges (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1,
            archived_at TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE catalog_college_aliases (
            college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
            alias TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'official_referential',
            PRIMARY KEY (college_id, alias)
        );
        CREATE TABLE catalog_fiches (
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES catalog_items(id),
            external_notion_id TEXT UNIQUE,
            imported_title TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            archived_at TEXT,
            provenance TEXT NOT NULL DEFAULT 'import',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE catalog_fiche_colleges (
            fiche_id TEXT NOT NULL REFERENCES catalog_fiches(id),
            college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
            source TEXT NOT NULL DEFAULT 'import',
            PRIMARY KEY (fiche_id, college_id)
        );
        CREATE TABLE catalog_official_item_colleges (
            item_id TEXT NOT NULL REFERENCES catalog_items(id),
            college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
            source_acronym TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (item_id, college_id)
        );
        CREATE TABLE catalog_local_overrides (
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES catalog_items(id),
            college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
            action TEXT NOT NULL CHECK(action IN ('add', 'remove')),
            justification TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE catalog_resources (
            id TEXT PRIMARY KEY,
            fiche_id TEXT NOT NULL REFERENCES catalog_fiches(id),
            resource_type TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            checked_at TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE catalog_resource_colleges (
            resource_id TEXT NOT NULL REFERENCES catalog_resources(id),
            college_id TEXT NOT NULL REFERENCES catalog_colleges(id),
            PRIMARY KEY (resource_id, college_id)
        );
        CREATE TABLE catalog_audit_log (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT,
            justification TEXT,
            provenance TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE catalog_import_runs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('dry_run', 'apply', 'rollback')),
            status TEXT NOT NULL,
            backup_path TEXT,
            summary_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX catalog_fiches_item_idx ON catalog_fiches(item_id);
        CREATE INDEX catalog_fiche_colleges_college_idx ON catalog_fiche_colleges(college_id);
        CREATE INDEX catalog_official_item_colleges_college_idx ON catalog_official_item_colleges(college_id);
        """,
    ),
)
