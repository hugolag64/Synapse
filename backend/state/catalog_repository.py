"""Persistence boundary for the local item/college catalog."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.state.catalog_migrations import run_catalog_migrations


@dataclass(frozen=True)
class CatalogItem:
    id: str
    item_number: int
    official_title: str
    local_title: str | None
    archived_at: str | None

    @property
    def title(self) -> str:
        return self.local_title or self.official_title


@dataclass(frozen=True)
class CatalogFiche:
    id: str
    item_id: str
    external_notion_id: str | None
    imported_title: str
    archived_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CatalogRepository:
    """Small transaction-per-operation repository over catalog tables."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path is not None else None
        run_catalog_migrations(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        path = self.db_path
        if path is None:
            from backend.state.catalog_migrations import DEFAULT_DB_PATH

            path = DEFAULT_DB_PATH
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def count_items(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0])

    def count_fiches(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM catalog_fiches").fetchone()[0])

    def count_archived_courses(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute("SELECT COUNT(*) FROM catalog_archived_courses").fetchone()[0]
            )

    def get_item_by_number(self, item_number: int) -> CatalogItem | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, item_number, official_title, local_title, archived_at
                FROM catalog_items WHERE item_number = ?
                """,
                (item_number,),
            ).fetchone()
        return self._item(row) if row else None

    def list_items(self, include_archived: bool = False) -> list[CatalogItem]:
        where = "" if include_archived else " WHERE archived_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, item_number, official_title, local_title, archived_at
                FROM catalog_items
                """ + where + " ORDER BY item_number"
            ).fetchall()
        return [self._item(row) for row in rows]

    def list_fiches(self, item_id: str, include_archived: bool = False) -> list[CatalogFiche]:
        where = "" if include_archived else " AND archived_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, item_id, external_notion_id, imported_title, archived_at
                FROM catalog_fiches WHERE item_id = ?
                """ + where + " ORDER BY created_at, id",
                (item_id,),
            ).fetchall()
        return [self._fiche(row) for row in rows]

    def list_colleges_for_item(self, item_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.name
                FROM catalog_colleges c
                JOIN catalog_official_item_colleges link ON link.college_id = c.id
                WHERE link.item_id = ?
                UNION
                SELECT c.name
                FROM catalog_colleges c
                JOIN catalog_fiche_colleges link ON link.college_id = c.id
                JOIN catalog_fiches f ON f.id = link.fiche_id
                WHERE f.item_id = ? AND f.archived_at IS NULL
                ORDER BY name
                """,
                (item_id, item_id),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def upsert_item(self, *, item_id: str, item_number: int, title: str, provenance: str) -> None:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO catalog_items
                    (id, item_number, official_title, provenance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_number) DO UPDATE SET
                    official_title = excluded.official_title,
                    provenance = excluded.provenance,
                    updated_at = excluded.updated_at
                """,
                (item_id, item_number, title, provenance, now, now),
            )

    def upsert_college(self, *, college_id: str, name: str, source: str) -> None:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO catalog_colleges
                    (id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (college_id, name, now, now),
            )
            actual_id = connection.execute(
                "SELECT id FROM catalog_colleges WHERE name = ?", (name,)
            ).fetchone()[0]
            connection.execute(
                """
                INSERT OR IGNORE INTO catalog_college_aliases(college_id, alias, source)
                VALUES (?, ?, ?)
                """,
                (actual_id, name, source),
            )

    def add_official_college(self, *, item_id: str, college_name: str, source_acronym: str) -> None:
        with self._connect() as connection:
            college_id = connection.execute(
                "SELECT id FROM catalog_colleges WHERE name = ?", (college_name,)
            ).fetchone()[0]
            connection.execute(
                """
                INSERT OR IGNORE INTO catalog_official_item_colleges
                    (item_id, college_id, source_acronym)
                VALUES (?, ?, ?)
                """,
                (item_id, college_id, source_acronym),
            )

    def upsert_fiche(
        self,
        *,
        fiche_id: str,
        item_id: str,
        external_notion_id: str,
        title: str,
        payload: dict,
        archived_at: str | None = None,
    ) -> None:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO catalog_fiches
                    (id, item_id, external_notion_id, imported_title, payload_json, archived_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    item_id = excluded.item_id,
                    external_notion_id = excluded.external_notion_id,
                    imported_title = excluded.imported_title,
                    payload_json = excluded.payload_json,
                    archived_at = excluded.archived_at,
                    updated_at = excluded.updated_at
                """,
                (fiche_id, item_id, external_notion_id, title, json.dumps(payload, ensure_ascii=False), archived_at, now, now),
            )

    def link_fiche_college(self, *, fiche_id: str, college_name: str, source: str) -> None:
        with self._connect() as connection:
            college_id = connection.execute(
                "SELECT id FROM catalog_colleges WHERE name = ?", (college_name,)
            ).fetchone()[0]
            connection.execute(
                """
                INSERT OR IGNORE INTO catalog_fiche_colleges(fiche_id, college_id, source)
                VALUES (?, ?, ?)
                """,
                (fiche_id, college_id, source),
            )

    def upsert_resource(
        self,
        *,
        resource_id: str,
        fiche_id: str,
        resource_type: str,
        title: str,
        url: str,
        college_names: list[str],
    ) -> None:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO catalog_resources
                    (id, fiche_id, resource_type, title, url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    updated_at = excluded.updated_at
                """,
                (resource_id, fiche_id, resource_type, title, url, now, now),
            )
            for college_name in college_names:
                college_id = connection.execute(
                    "SELECT id FROM catalog_colleges WHERE name = ?", (college_name,)
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT OR IGNORE INTO catalog_resource_colleges(resource_id, college_id)
                    VALUES (?, ?)
                    """,
                    (resource_id, college_id),
                )

    def insert_archived_course(self, *, course_id: str, title: str, payload: dict, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO catalog_archived_courses
                    (id, external_notion_id, title, payload_json, archive_reason, archived_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (course_id, course_id, title, json.dumps(payload, ensure_ascii=False), reason, _now()),
            )

    def create_import_run(self, *, run_id: str, source: str, mode: str, status: str, backup_path: str | None, summary: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO catalog_import_runs
                    (id, source, mode, status, backup_path, summary_json, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, source, mode, status, backup_path, json.dumps(summary, ensure_ascii=False), _now(), _now()),
            )

    @staticmethod
    def _item(row: sqlite3.Row) -> CatalogItem:
        return CatalogItem(
            id=str(row["id"]),
            item_number=int(row["item_number"]),
            official_title=str(row["official_title"] or ""),
            local_title=row["local_title"],
            archived_at=row["archived_at"],
        )

    @staticmethod
    def _fiche(row: sqlite3.Row) -> CatalogFiche:
        return CatalogFiche(
            id=str(row["id"]),
            item_id=str(row["item_id"]),
            external_notion_id=row["external_notion_id"],
            imported_title=str(row["imported_title"] or ""),
            archived_at=row["archived_at"],
        )
