"""Safe local registry for external preparation resources."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.core.ednpro.collector import normalize_stable_resource_url
from backend.core.reviews import local_store


def _ensure_table() -> None:
    with local_store._conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS prep_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                item_number TEXT NOT NULL DEFAULT '',
                match_method TEXT NOT NULL DEFAULT 'manual',
                confidence REAL NOT NULL DEFAULT 1.0,
                source_url TEXT NOT NULL DEFAULT '',
                last_verified TEXT NOT NULL,
                UNIQUE(provider, url, item_number)
            )"""
        )


def upsert_prep_resource(
    *,
    provider: str,
    resource_type: str,
    title: str,
    url: str,
    item_number: str = "",
    match_method: str = "manual",
    confidence: float = 1.0,
    source_url: str = "",
) -> int:
    _ensure_table()
    stable_url = normalize_stable_resource_url(url)
    now = datetime.now(timezone.utc).isoformat()
    with local_store._conn() as con:
        con.execute(
            """INSERT INTO prep_resources
               (provider, resource_type, title, url, item_number, match_method,
                confidence, source_url, last_verified)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(provider, url, item_number) DO UPDATE SET
                title=excluded.title, resource_type=excluded.resource_type,
                match_method=excluded.match_method, confidence=excluded.confidence,
                source_url=excluded.source_url, last_verified=excluded.last_verified""",
            (
                provider, resource_type, title, stable_url, str(item_number or "").strip(),
                match_method, float(confidence), source_url, now,
            ),
        )
        row = con.execute(
            "SELECT id FROM prep_resources WHERE provider=? AND url=? AND item_number=?",
            (provider, stable_url, str(item_number or "").strip()),
        ).fetchone()
    return int(row["id"])


def list_prep_resources_for_item(item_number: str) -> list[dict]:
    _ensure_table()
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT * FROM prep_resources
               WHERE item_number = ? AND confidence >= 0.8
               ORDER BY confidence DESC, last_verified DESC, title COLLATE NOCASE""",
            (str(item_number or "").strip(),),
        ).fetchall()
    return [dict(row) for row in rows]
