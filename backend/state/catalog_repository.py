"""Persistence boundary for the local item/college catalog."""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4
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

    def get_item(self, item_id: str) -> CatalogItem | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT id, item_number, official_title, local_title, archived_at
                   FROM catalog_items WHERE id = ?""",
                (item_id,),
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

    def list_all_fiches(self, include_archived: bool = False) -> list[CatalogFiche]:
        where = "" if include_archived else " WHERE archived_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, item_id, external_notion_id, imported_title, archived_at
                FROM catalog_fiches
                """ + where + " ORDER BY created_at, id"
            ).fetchall()
        return [self._fiche(row) for row in rows]

    def get_fiche_payload(self, fiche_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM catalog_fiches WHERE id = ?", (fiche_id,)
            ).fetchone()
        return json.loads(row[0]) if row and row[0] else {}

    def get_fiche_colleges(self, fiche_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.name
                FROM catalog_colleges c
                JOIN catalog_fiche_colleges link ON link.college_id = c.id
                WHERE link.fiche_id = ?
                ORDER BY c.sort_order, c.name
                """,
                (fiche_id,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def get_primary_resource(self, item_id: str, college_name: str | None = None) -> dict | None:
        """Select college-specific, then shared, then deterministic fallback resource."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.id, r.fiche_id, r.resource_type, r.title, r.url,
                       r.status, r.is_primary,
                       GROUP_CONCAT(c.name) AS colleges
                FROM catalog_resources r
                JOIN catalog_fiches f ON f.id = r.fiche_id
                LEFT JOIN catalog_resource_colleges rc ON rc.resource_id = r.id
                LEFT JOIN catalog_colleges c ON c.id = rc.college_id
                WHERE f.item_id = ? AND f.archived_at IS NULL AND r.status = 'active'
                GROUP BY r.id
                ORDER BY r.is_primary DESC, r.created_at, r.id
                """,
                (item_id,),
            ).fetchall()
        if not rows:
            return None
        normalized = str(college_name or "").strip()
        specific = [row for row in rows if normalized and normalized in (row["colleges"] or "").split(",")]
        shared = [row for row in rows if not (row["colleges"] or "").strip()]
        chosen = (specific or shared or list(rows))[0]
        return dict(chosen)

    def list_colleges(self, active_only: bool = True) -> list[str]:
        where = " WHERE active = 1" if active_only else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM catalog_colleges" + where + " ORDER BY sort_order, name"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def is_populated(self) -> bool:
        return self.count_items() > 0

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

    def list_item_ids_for_college(self, college_name: str) -> list[str]:
        """Return unique active item ids related to a college."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT item_id FROM catalog_official_item_colleges oi
                JOIN catalog_colleges c ON c.id = oi.college_id
                JOIN catalog_items i ON i.id = oi.item_id
                WHERE c.name = ? AND i.archived_at IS NULL
                UNION
                SELECT DISTINCT f.item_id FROM catalog_fiche_colleges fc
                JOIN catalog_colleges c ON c.id = fc.college_id
                JOIN catalog_fiches f ON f.id = fc.fiche_id
                JOIN catalog_items i ON i.id = f.item_id
                WHERE c.name = ? AND f.archived_at IS NULL AND i.archived_at IS NULL
                ORDER BY item_id
                """,
                (college_name, college_name),
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

    def save_override(self, item_id: str, college_id: str, action: str, justification: str) -> None:
        """Persist and apply a local item-college mapping override."""
        if action not in {"add", "remove"}:
            raise ValueError("action inconnue")
        if not str(justification or "").strip():
            raise ValueError("justification obligatoire")
        with self._connect() as connection:
            item = connection.execute("SELECT id FROM catalog_items WHERE id = ?", (item_id,)).fetchone()
            college = connection.execute("SELECT id FROM catalog_colleges WHERE id = ?", (college_id,)).fetchone()
            if not item or not college:
                raise ValueError("item ou collège introuvable")
            before = connection.execute(
                "SELECT 1 FROM catalog_official_item_colleges WHERE item_id = ? AND college_id = ?",
                (item_id, college_id),
            ).fetchone()
            connection.execute(
                """INSERT INTO catalog_local_overrides
                   (id, item_id, college_id, action, justification, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), item_id, college_id, action, justification.strip(), _now()),
            )
            if action == "add":
                connection.execute(
                    """INSERT OR IGNORE INTO catalog_official_item_colleges
                       (item_id, college_id, source_acronym) VALUES (?, ?, 'local_override')""",
                    (item_id, college_id),
                )
            else:
                connection.execute(
                    "DELETE FROM catalog_official_item_colleges WHERE item_id = ? AND college_id = ?",
                    (item_id, college_id),
                )
            self._audit(
                connection, "item_college", f"{item_id}:{college_id}", "override",
                {"linked": bool(before)}, {"linked": action == "add"}, justification,
            )

    def archive_item(self, item_id: str, justification: str) -> None:
        self._set_item_archived(item_id, justification, archived=True)

    def restore_item(self, item_id: str, justification: str) -> None:
        self._set_item_archived(item_id, justification, archived=False)

    def _set_item_archived(self, item_id: str, justification: str, *, archived: bool) -> None:
        if not str(justification or "").strip():
            raise ValueError("justification obligatoire")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT archived_at FROM catalog_items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                raise ValueError("item introuvable")
            before = {"archived_at": row[0]}
            value = _now() if archived else None
            connection.execute(
                "UPDATE catalog_items SET archived_at = ?, updated_at = ? WHERE id = ?",
                (value, _now(), item_id),
            )
            self._audit(
                connection, "item", item_id, "archive" if archived else "restore",
                before, {"archived_at": value}, justification,
            )

    def merge_items(self, master_id: str, duplicate_id: str, justification: str) -> None:
        if not str(justification or "").strip():
            raise ValueError("justification obligatoire")
        if master_id == duplicate_id:
            raise ValueError("fusion impossible avec le même item")
        with self._connect() as connection:
            master = connection.execute("SELECT id FROM catalog_items WHERE id = ?", (master_id,)).fetchone()
            duplicate = connection.execute("SELECT id, archived_at FROM catalog_items WHERE id = ?", (duplicate_id,)).fetchone()
            if not master or not duplicate:
                raise ValueError("item introuvable")
            fiche_count = connection.execute(
                "SELECT COUNT(*) FROM catalog_fiches WHERE item_id = ?", (duplicate_id,)
            ).fetchone()[0]
            connection.execute("UPDATE catalog_fiches SET item_id = ? WHERE item_id = ?", (master_id, duplicate_id))
            connection.execute(
                "UPDATE catalog_items SET archived_at = ?, updated_at = ? WHERE id = ?",
                (_now(), _now(), duplicate_id),
            )
            self._audit(
                connection, "item", duplicate_id, "merge",
                {"master_id": None, "fiche_count": fiche_count},
                {"master_id": master_id, "fiche_count": fiche_count}, justification,
            )

    def list_audit_log(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM catalog_audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _audit(connection, entity_type, entity_id, operation, before, after, justification):
        connection.execute(
            """INSERT INTO catalog_audit_log
               (id, entity_type, entity_id, operation, before_json, after_json,
                justification, provenance, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'local_admin', ?)""",
            (
                str(uuid4()), entity_type, entity_id, operation,
                json.dumps(before, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
                justification,
                _now(),
            ),
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
