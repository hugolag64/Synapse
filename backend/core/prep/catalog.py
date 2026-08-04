"""Configurable preparation-provider shortcuts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.core.reviews import local_store


@dataclass(frozen=True)
class PrepShortcut:
    provider: str
    category: str
    title: str
    description: str
    url: str
    icon: str
    enabled: bool = True


_PROVIDERS = (
    {"name": "EDNpro", "root_url": "https://ednpro.app", "enabled": True},
    {"name": "Hypocampus", "root_url": "https://hypocampus.fr", "enabled": True},
    {"name": "EDNi", "root_url": "", "enabled": False},
)
_DEFAULTS = (
    PrepShortcut("EDNpro", "entrainement", "Tous les items", "Entraînement EDN", "https://ednpro.app/training-v2", "quiz"),
    PrepShortcut("EDNpro", "annales", "Annales", "Sujets EDN et corrections", "https://ednpro.app/annales", "school"),
    PrepShortcut("EDNpro", "iconographie", "Iconographie", "Radio, dermato et imagerie", "https://ednpro.app/iconographie", "image"),
    PrepShortcut("EDNpro", "videos", "Vidéos ECG", "Vidéos ECG commentées", "https://ednpro.app/videos", "favorite"),
    PrepShortcut("EDNpro", "videos", "Physiologie", "Cours de physiologie", "https://ednpro.app/videos", "monitor_heart"),
    PrepShortcut("EDNpro", "videos", "Anatomie et sémiologie", "Bases de sémiologie", "https://ednpro.app/videos", "accessibility"),
    PrepShortcut("EDNpro", "lca", "LCA", "Lecture critique d’article", "https://ednpro.app/lca", "menu_book"),
    PrepShortcut("Hypocampus", "accueil", "Hypocampus", "Plateforme de préparation", "https://hypocampus.fr", "school"),
)


def _ensure_table() -> None:
    with local_store._conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS prep_shortcuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL,
                icon TEXT NOT NULL DEFAULT 'open_in_new',
                enabled INTEGER NOT NULL DEFAULT 1,
                last_used TEXT,
                UNIQUE(provider, category, title)
            )"""
        )
        for shortcut in _DEFAULTS:
            con.execute(
                """INSERT OR IGNORE INTO prep_shortcuts
                   (provider, category, title, description, url, icon, enabled)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    shortcut.provider, shortcut.category, shortcut.title, shortcut.description,
                    shortcut.url, shortcut.icon, int(shortcut.enabled),
                ),
            )


def list_prep_providers() -> list[dict]:
    return [dict(provider) for provider in _PROVIDERS]


def list_prep_shortcuts(provider: str | None = None) -> list[dict]:
    _ensure_table()
    with local_store._conn() as con:
        if provider:
            rows = con.execute(
                "SELECT * FROM prep_shortcuts WHERE provider=? AND enabled=1 ORDER BY category, id",
                (provider,),
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM prep_shortcuts WHERE enabled=1 ORDER BY provider, category, id").fetchall()
    return [dict(row) for row in rows]


def record_prep_access(shortcut_id: int) -> None:
    _ensure_table()
    with local_store._conn() as con:
        con.execute(
            "UPDATE prep_shortcuts SET last_used=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), int(shortcut_id)),
        )
