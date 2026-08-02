"""
externat/store.py — Synapse Phase G
--------------------------------------
CRUD SQLite pour les stages d'externat.
Utilise la même base que local_store (synapse_local.db).

Tables créées :
  stages : un stage par ligne, actif ou historique
"""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path
from typing import Optional

from loguru import logger

from backend.core.externat.models import Stage

# ── DB path (même fichier que local_store) ────────────────────────────────────
_ROOT   = Path(__file__).parent.parent.parent.parent
DB_PATH = _ROOT / "data" / "synapse_local.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Crée la table stages si elle n'existe pas (idempotent)."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS stages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                specialty       TEXT    NOT NULL,
                college_notion  TEXT    DEFAULT '',
                start_date      TEXT    NOT NULL,
                end_date        TEXT    NOT NULL,
                objectives      TEXT    DEFAULT '',
                schedules       TEXT    DEFAULT '',
                gardes          TEXT    DEFAULT '',
                contraintes     TEXT    DEFAULT '',
                is_active       INTEGER DEFAULT 1,
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            )
        """)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_stages_active ON stages(is_active)"
        )
    logger.debug("externat.store : table stages vérifiée.")


# ── Conversions ───────────────────────────────────────────────────────────────

def _row_to_stage(row: sqlite3.Row) -> Stage:
    return Stage(
        id=row["id"],
        specialty=row["specialty"],
        college_notion=row["college_notion"] or "",
        start_date=datetime.date.fromisoformat(row["start_date"]),
        end_date=datetime.date.fromisoformat(row["end_date"]),
        objectives=row["objectives"] or "",
        schedules=row["schedules"] or "",
        gardes=row["gardes"] or "",
        contraintes=row["contraintes"] or "",
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── CRUD ─────────────────────────────────────────────────────────────────────

def add_stage(
    specialty: str,
    college_notion: str,
    start_date: datetime.date,
    end_date: datetime.date,
    objectives: str = "",
    schedules: str = "",
    gardes: str = "",
    contraintes: str = "",
    is_active: bool = True,
) -> int:
    """Insère un stage. Retourne l'id."""
    now = _now()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO stages
                (specialty, college_notion, start_date, end_date,
                 objectives, schedules, gardes, contraintes, is_active,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                specialty, college_notion,
                start_date.isoformat(), end_date.isoformat(),
                objectives, schedules, gardes, contraintes,
                1 if is_active else 0,
                now, now,
            ),
        )
        return cur.lastrowid


def get_all_stages() -> list[Stage]:
    """Retourne tous les stages, du plus récent au plus ancien."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM stages ORDER BY start_date DESC"
        ).fetchall()
    return [_row_to_stage(r) for r in rows]


def get_stage(stage_id: int) -> Optional[Stage]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM stages WHERE id = ?", (stage_id,)
        ).fetchone()
    return _row_to_stage(row) if row else None


def get_active_stage() -> Optional[Stage]:
    """
    Retourne le stage en cours aujourd'hui (is_active=1 ET dates encadrent today).
    Si plusieurs matchent, retourne le plus récent.
    """
    today = datetime.date.today().isoformat()
    with _conn() as con:
        row = con.execute(
            """
            SELECT * FROM stages
            WHERE is_active = 1
              AND start_date <= ?
              AND end_date   >= ?
            ORDER BY start_date DESC
            LIMIT 1
            """,
            (today, today),
        ).fetchone()
    return _row_to_stage(row) if row else None


def update_stage(stage_id: int, **fields) -> None:
    """
    Met à jour les champs fournis en kwargs.
    Champs acceptés : specialty, college_notion, start_date, end_date,
                      objectives, schedules, gardes, contraintes, is_active.
    """
    allowed = {
        "specialty", "college_notion", "start_date", "end_date",
        "objectives", "schedules", "gardes", "contraintes", "is_active",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    # Sérialiser les dates
    for date_field in ("start_date", "end_date"):
        if date_field in updates and isinstance(updates[date_field], datetime.date):
            updates[date_field] = updates[date_field].isoformat()
    if "is_active" in updates:
        updates["is_active"] = 1 if updates["is_active"] else 0

    updates["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [stage_id]

    with _conn() as con:
        con.execute(f"UPDATE stages SET {cols} WHERE id = ?", vals)


def delete_stage(stage_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM stages WHERE id = ?", (stage_id,))
