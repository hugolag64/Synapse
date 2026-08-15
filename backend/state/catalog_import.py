"""Explicit, reversible import of the local catalog snapshot."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.state.catalog_migrations import run_catalog_migrations
from backend.state.catalog_repository import CatalogRepository


@dataclass(frozen=True)
class ImportPreview:
    id: str
    item_count: int
    fiche_count: int
    archived_course_count: int
    ambiguous_matches: int


@dataclass(frozen=True)
class ImportRun:
    id: str
    backup_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_item(value: object) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


class CatalogImportService:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path is not None else None
        run_catalog_migrations(self.db_path)
        self.repository = CatalogRepository(self.db_path)
        self._previews: dict[str, dict] = {}

    def preview(self, source_path: Path) -> ImportPreview:
        payload = json.loads(Path(source_path).read_text(encoding="utf-8"))
        referential = json.loads(
            Path("data/nexternat_items.json").read_text(encoding="utf-8")
        )
        item_courses = [
            course
            for course in payload.get("cours", [])
            if course.get("college") and _normalize_item(course.get("item_number")) is not None
        ]
        archived_courses = [course for course in payload.get("cours", []) if course not in item_courses]
        preview = ImportPreview(
            id=str(uuid.uuid4()),
            item_count=len(referential.get("items", {})),
            fiche_count=len(item_courses),
            archived_course_count=len(archived_courses),
            ambiguous_matches=0,
        )
        self._previews[preview.id] = {
            "payload": payload,
            "referential": referential,
            "preview": preview,
            "source": str(source_path),
        }
        return preview

    def apply(self, source_path: Path, preview_id: str) -> ImportRun:
        entry = self._previews.get(preview_id)
        if entry is None or Path(entry["source"]) != Path(source_path):
            raise ValueError("Import preview missing or does not match source")
        backup = self._backup()
        run_id = str(uuid.uuid4())
        try:
            self._apply_payload(entry["payload"], entry["referential"])
            self.repository.create_import_run(
                run_id=run_id,
                source=str(source_path),
                mode="apply",
                status="completed",
                backup_path=str(backup),
                summary={
                    "items": entry["preview"].item_count,
                    "fiches": entry["preview"].fiche_count,
                    "archived_courses": entry["preview"].archived_course_count,
                },
            )
            return ImportRun(run_id, backup)
        except Exception:
            self._restore(backup)
            raise

    def rollback(self, import_run_id: str) -> None:
        path = self.db_path
        if path is None:
            from backend.state.catalog_migrations import DEFAULT_DB_PATH

            path = DEFAULT_DB_PATH
        with sqlite3.connect(path) as connection:
            row = connection.execute(
                "SELECT backup_path FROM catalog_import_runs WHERE id = ?", (import_run_id,)
            ).fetchone()
        if not row or not row[0]:
            raise ValueError(f"Unknown import run: {import_run_id}")
        self._restore(Path(row[0]))

    def _apply_payload(self, payload: dict, referential: dict) -> None:
        consolidation = json.loads(
            Path("data/college_consolidation.json").read_text(encoding="utf-8")
        )
        college_mapping = consolidation.get("mapping", {})
        notion_colleges = set(consolidation.get("notion_colleges", []))
        courses = payload.get("cours", [])
        for course in courses:
            for college in course.get("college") or []:
                notion_colleges.add(str(college))
        for index, college in enumerate(sorted(notion_colleges)):
            self.repository.upsert_college(
                college_id=f"college:{index}:{college}",
                name=college,
                source="import",
            )

        for raw_number, item in referential.get("items", {}).items():
            item_number = int(raw_number)
            item_id = f"item:{item_number}"
            self.repository.upsert_item(
                item_id=item_id,
                item_number=item_number,
                title=str(item.get("title") or ""),
                provenance="official_referential",
            )
            for official in item.get("ecriture") or []:
                acronym = str(official.get("acronym") or "")
                college_name = college_mapping.get(acronym)
                if college_name:
                    self.repository.add_official_college(
                        item_id=item_id,
                        college_name=college_name,
                        source_acronym=acronym,
                    )

        for course in courses:
            item_number = _normalize_item(course.get("item_number"))
            colleges = [str(college) for college in course.get("college") or [] if str(college).strip()]
            if item_number is None or not colleges:
                self.repository.insert_archived_course(
                    course_id=str(course.get("id") or uuid.uuid4()),
                    title=str(course.get("title") or ""),
                    payload=course,
                    reason="sans item et/ou collège actif",
                )
                continue
            fiche_id = str(course.get("id") or uuid.uuid4())
            item_id = f"item:{item_number}"
            self.repository.upsert_fiche(
                fiche_id=fiche_id,
                item_id=item_id,
                external_notion_id=fiche_id,
                title=str(course.get("title") or ""),
                payload=course,
            )
            for college in colleges:
                self.repository.link_fiche_college(
                    fiche_id=fiche_id,
                    college_name=college,
                    source="import",
                )
            pdf = str(course.get("url_pdf") or "").strip()
            if pdf:
                self.repository.upsert_resource(
                    resource_id=f"resource:{fiche_id}:pdf",
                    fiche_id=fiche_id,
                    resource_type="pdf",
                    title=str(course.get("title") or "PDF"),
                    url=pdf,
                    college_names=colleges,
                )

    def _backup(self) -> Path:
        path = self.db_path
        if path is None:
            from backend.state.catalog_migrations import DEFAULT_DB_PATH

            path = DEFAULT_DB_PATH
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        destination = backup_dir / f"catalog-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
        if path.exists():
            shutil.copy2(path, destination)
        else:
            sqlite3.connect(destination).close()
        return destination

    def _restore(self, backup: Path) -> None:
        path = self.db_path
        if path is None:
            from backend.state.catalog_migrations import DEFAULT_DB_PATH

            path = DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, path)
        run_catalog_migrations(path)
