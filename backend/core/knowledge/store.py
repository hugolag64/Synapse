"""
knowledge.store — Synapse
-------------------------
Persistance SQLite de l'état des connaissances :
  - college_status : statut académique d'un collège (déclaré)
  - item_state     : niveau déclaré d'un item (solide / correct / flou)

Réutilise la connexion de local_store : une seule base, une seule connexion,
et la fixture de test isolated_db isole les deux modules d'un coup.

Aucune écriture Notion : ce sont des données de pilotage personnel.
"""
from __future__ import annotations

import datetime
from loguru import logger

from backend.core.reviews.local_store import _conn, _now
from backend.core.knowledge.models import (
    ItemState, COLLEGE_STATUSES, DECLARED_LEVELS,
)


# ── Initialisation ────────────────────────────────────────────────────────────

def init_knowledge_tables() -> None:
    """Crée les tables du domaine « connaissances » si elles n'existent pas."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS college_status (
                college      TEXT PRIMARY KEY,
                status       TEXT NOT NULL DEFAULT 'non_etudie',
                validated_at TEXT,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS item_state (
                course_id      TEXT NOT NULL,
                context        TEXT NOT NULL DEFAULT 'college',
                declared_level TEXT NOT NULL,
                declared_at    TEXT NOT NULL,
                source         TEXT NOT NULL DEFAULT 'reprise',
                updated_at     TEXT NOT NULL,
                PRIMARY KEY (course_id, context)
            );

            CREATE INDEX IF NOT EXISTS idx_item_state_ctx ON item_state(context);
        """)
    logger.debug("knowledge : tables college_status et item_state initialisées.")


# ── college_status ────────────────────────────────────────────────────────────

def set_college_status(college: str, status: str) -> None:
    """Déclare le statut académique d'un collège. Statuts : non_etudie | en_cours | valide."""
    if status not in COLLEGE_STATUSES:
        raise ValueError(f"Statut de collège inconnu : {status!r}")

    validated_at = datetime.date.today().isoformat() if status == "valide" else None

    with _conn() as con:
        con.execute(
            """INSERT INTO college_status (college, status, validated_at, updated_at)
                    VALUES (?, ?, ?, ?)
               ON CONFLICT(college) DO UPDATE SET
                    status       = excluded.status,
                    validated_at = excluded.validated_at,
                    updated_at   = excluded.updated_at""",
            (college, status, validated_at, _now()),
        )


def get_college_status(college: str) -> str:
    """Statut d'un collège. Un collège absent de la table est réputé non_etudie."""
    with _conn() as con:
        row = con.execute(
            "SELECT status FROM college_status WHERE college = ?", (college,)
        ).fetchone()
    return row["status"] if row else "non_etudie"


def get_all_college_statuses() -> dict[str, str]:
    """{college: status} pour tous les collèges déclarés."""
    with _conn() as con:
        rows = con.execute("SELECT college, status FROM college_status").fetchall()
    return {r["college"]: r["status"] for r in rows}


# ── item_state ────────────────────────────────────────────────────────────────

def set_item_state(
    course_id: str,
    level: str,
    context: str = "college",
    source: str = "reprise",
) -> None:
    """Déclare (ou redéclare) le niveau ressenti d'un item."""
    if level not in DECLARED_LEVELS:
        raise ValueError(f"Niveau déclaré inconnu : {level!r}")

    today = datetime.date.today().isoformat()

    with _conn() as con:
        con.execute(
            """INSERT INTO item_state
                    (course_id, context, declared_level, declared_at, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(course_id, context) DO UPDATE SET
                    declared_level = excluded.declared_level,
                    declared_at    = excluded.declared_at,
                    source         = excluded.source,
                    updated_at     = excluded.updated_at""",
            (course_id, context, level, today, source, _now()),
        )


def _row_to_item_state(row) -> ItemState:
    return ItemState(
        course_id=row["course_id"],
        context=row["context"],
        declared_level=row["declared_level"],
        declared_at=datetime.date.fromisoformat(row["declared_at"]),
        source=row["source"],
        updated_at=row["updated_at"],
    )


def get_item_state(course_id: str, context: str = "college") -> ItemState | None:
    """État déclaré d'un item, ou None s'il est encore « à situer »."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM item_state WHERE course_id = ? AND context = ?",
            (course_id, context),
        ).fetchone()
    return _row_to_item_state(row) if row else None


def get_all_item_states(context: str = "college") -> dict[str, ItemState]:
    """{course_id: ItemState} — chargement par lot, pour éviter N requêtes."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM item_state WHERE context = ?", (context,)
        ).fetchall()
    return {r["course_id"]: _row_to_item_state(r) for r in rows}


# ── Auto-init à l'import ──────────────────────────────────────────────────────
# Garantit que les tables existent dès que knowledge.store est importé.
try:
    init_knowledge_tables()
except Exception as _e:
    logger.error(f"Impossible d'initialiser les tables knowledge: {_e}")
