# Import du planning des conférences DFASM — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** importer le calendrier XLS annuel des conférences DFASM dans Synapse : chaque
conférence du mardi devient un événement Google Calendar, avec un créneau associé "Dossier
UNESS" (17h30–19h), et un rattachement au référentiel collège UNESS validé automatiquement ou
manuellement.

**Architecture:** un nouveau module `backend/core/conferences/` (parsing XLS, matching collège,
orchestration) au-dessus d'une nouvelle table SQLite `conferences` et d'une petite extension du
service Google Calendar existant. Un panneau `settings_cockpit.py` déclenche l'import et expose
la file de validation manuelle.

**Tech Stack:** Python 3.11, stdlib `zipfile`/`xml.etree.ElementTree` (pas de dépendance XLS
ajoutée), SQLite, NiceGUI, Google Calendar API (intégration déjà en place).

## Global Constraints

- Seules les conférences du **mardi** sont importées (utilisateur DFASM1) — le jeudi est ignoré.
- Aucune lecture de la couleur des cellules XLS ; seul le texte compte pour la v1.
- Un ré-import ne doit jamais écraser silencieusement un lien déjà validé (collège,
  `google_event_id`) tant que le thème brut de la date n'a pas changé.
- Un ré-import ne doit jamais créer de doublon d'événement Google Calendar pour une conférence
  déjà synchronisée.
- Le créneau "Dossier UNESS" est toujours 17h30–19h (90 min), le jour même de la conférence.
- Toute nouvelle fonction publique ajoutée à un fichier existant (`items_mapping.py`,
  `calendar_service.py`) doit avoir sa propre couverture de test, sans modifier le comportement
  des fonctions déjà présentes.

**Spec de référence :** [`docs/superpowers/specs/2026-08-20-import-planning-conferences-design.md`](../specs/2026-08-20-import-planning-conferences-design.md)

---

### Task 1: Accesseurs publics collège dans `items_mapping.py`

**Files:**
- Modify: `backend/core/qcm/items_mapping.py`
- Test: `tests/test_items_mapping_college_helpers.py`

**Interfaces:**
- Produces: `all_college_names() -> list[str]` (noms Notion complets dédupliqués, avec emoji).
  `abbreviation_to_college(abbr: str) -> str | None` (résolution insensible à la casse via la
  table `_ABBR_TO_NOTION` déjà existante).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_items_mapping_college_helpers.py
from backend.core.qcm.items_mapping import abbreviation_to_college, all_college_names


def test_abbreviation_to_college_is_case_insensitive():
    assert abbreviation_to_college("mi") == "Médecine Interne 🏥"
    assert abbreviation_to_college("MI") == "Médecine Interne 🏥"


def test_abbreviation_to_college_returns_none_for_unknown_abbreviation():
    assert abbreviation_to_college("ZZZ") is None


def test_all_college_names_is_deduplicated_and_contains_known_colleges():
    names = all_college_names()
    assert names.count("Médecine légale - Santé publique ⚖️") == 1
    assert "Cardiovasculaire ❤️" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_items_mapping_college_helpers.py -v`
Expected: FAIL with "cannot import name 'abbreviation_to_college'"

- [ ] **Step 3: Implement the two functions**

In `backend/core/qcm/items_mapping.py`, immediately after the existing `college_full` function:

```python
def all_college_names() -> list[str]:
    """Liste dédupliquée des noms Notion complets connus (avec emoji)."""
    return sorted(set(_ABBR_TO_NOTION.values()))


@lru_cache(maxsize=1)
def _abbr_lookup_ci() -> dict[str, str]:
    return {k.lower(): v for k, v in _ABBR_TO_NOTION.items()}


def abbreviation_to_college(abbr: str) -> str | None:
    """Résout une abréviation (insensible à la casse) vers le nom Notion complet, ou None."""
    return _abbr_lookup_ci().get(str(abbr or "").strip().lower())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_items_mapping_college_helpers.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/core/qcm/items_mapping.py tests/test_items_mapping_college_helpers.py
git commit -m "feat: expose college name lookup helpers from items_mapping"
```

---

### Task 2: Table SQLite `conferences` et CRUD dans `local_store.py`

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_conferences_store.py`

**Interfaces:**
- Produces:
  - `upsert_conference(*, date: datetime.date, theme_raw: str, speaker_initials: str = "", speaker_name: str = "", match_status: str, college_name: str | None, source_file: str) -> tuple[str, dict]` — outcome is `"created"`, `"updated"` or `"unchanged"`.
  - `get_conference(conference_id: int) -> dict | None`
  - `list_conferences(*, match_status: str = "") -> list[dict]`
  - `set_conference_match(conference_id: int, *, match_status: str, college_name: str | None) -> dict`
  - `set_conference_google_event_ids(conference_id: int, *, google_event_id: str | None = None, uness_slot_google_event_id: str | None = None) -> dict`
  - Row dict keys: `id, date, theme_raw, college_id, match_status, speaker_initials, speaker_name, uness_session_id, google_event_id, uness_slot_google_event_id, source_file, created_at, updated_at`.
  - Valid `match_status` values: `"matched"`, `"needs_validation"`, `"skipped"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conferences_store.py
import datetime

import pytest


@pytest.fixture
def isolated_local_store(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "conferences.db")
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


def test_upsert_conference_creates_then_reports_unchanged(isolated_local_store):
    store = isolated_local_store
    outcome, row = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    assert outcome == "created"
    assert row["match_status"] == "matched"

    outcome2, row2 = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    assert outcome2 == "unchanged"
    assert row2["id"] == row["id"]


def test_upsert_conference_preserves_validated_college_when_theme_unchanged(isolated_local_store):
    store = isolated_local_store
    _, row = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="needs_validation",
        college_name=None, source_file="cal.xlsx",
    )
    store.set_conference_match(
        row["id"], match_status="matched", college_name="Hépato-Gastro-entérologie 🧻"
    )

    outcome, row2 = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="needs_validation",
        college_name=None, source_file="cal-v2.xlsx",
    )
    assert outcome == "unchanged"
    assert row2["match_status"] == "matched"
    assert row2["college_id"] == "Hépato-Gastro-entérologie 🧻"


def test_upsert_conference_resets_validation_when_theme_changes(isolated_local_store):
    store = isolated_local_store
    store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )

    outcome, row2 = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="Cardio", match_status="needs_validation",
        college_name=None, source_file="cal-v2.xlsx",
    )
    assert outcome == "updated"
    assert row2["theme_raw"] == "Cardio"
    assert row2["match_status"] == "needs_validation"
    assert row2["college_id"] is None


def test_set_conference_google_event_ids_updates_only_given_fields(isolated_local_store):
    store = isolated_local_store
    _, row = store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    updated = store.set_conference_google_event_ids(row["id"], google_event_id="evt-1")
    assert updated["google_event_id"] == "evt-1"
    assert updated["uness_slot_google_event_id"] is None

    updated2 = store.set_conference_google_event_ids(row["id"], uness_slot_google_event_id="evt-2")
    assert updated2["google_event_id"] == "evt-1"
    assert updated2["uness_slot_google_event_id"] == "evt-2"


def test_list_conferences_filters_by_match_status(isolated_local_store):
    store = isolated_local_store
    store.upsert_conference(
        date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="matched",
        college_name="Hépato-Gastro-entérologie 🧻", source_file="cal.xlsx",
    )
    store.upsert_conference(
        date=datetime.date(2026, 9, 8), theme_raw="Toussaint", match_status="needs_validation",
        college_name=None, source_file="cal.xlsx",
    )
    pending = store.list_conferences(match_status="needs_validation")
    assert [row["theme_raw"] for row in pending] == ["Toussaint"]


def test_upsert_conference_rejects_invalid_match_status(isolated_local_store):
    store = isolated_local_store
    with pytest.raises(ValueError):
        store.upsert_conference(
            date=datetime.date(2026, 9, 1), theme_raw="HGE", match_status="bogus",
            college_name=None, source_file="cal.xlsx",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conferences_store.py -v`
Expected: FAIL with "AttributeError: module ... has no attribute 'upsert_conference'"

- [ ] **Step 3: Add the migration function**

In `backend/core/reviews/local_store.py`, add near the other `_migrate_*` functions (e.g. right
after `_migrate_flash_zero_ai_questions`):

```python
_CONFERENCE_MATCH_STATUSES = {"matched", "needs_validation", "skipped"}


def _migrate_conferences_table() -> None:
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS conferences (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                date                        TEXT NOT NULL UNIQUE,
                theme_raw                   TEXT NOT NULL,
                college_id                  TEXT,
                match_status                TEXT NOT NULL DEFAULT 'needs_validation',
                speaker_initials            TEXT NOT NULL DEFAULT '',
                speaker_name                TEXT NOT NULL DEFAULT '',
                uness_session_id            INTEGER,
                google_event_id             TEXT,
                uness_slot_google_event_id  TEXT,
                source_file                 TEXT NOT NULL DEFAULT '',
                created_at                  TEXT NOT NULL,
                updated_at                  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conferences_match_status
                ON conferences(match_status);
            """
        )
```

Register the call in `init_db()`, right after `_migrate_flash_zero_ai_questions()`:

```python
    _migrate_flash_zero_ai_questions()
    _migrate_conferences_table()
```

- [ ] **Step 4: Add the CRUD functions**

Add near the end of the file (after `delete_manual_planning_entry`, for example):

```python
def upsert_conference(
    *,
    date: datetime.date,
    theme_raw: str,
    speaker_initials: str = "",
    speaker_name: str = "",
    match_status: str,
    college_name: str | None,
    source_file: str,
) -> tuple[str, dict]:
    """Insert or update a conference keyed by date.

    Returns (outcome, row) where outcome is "created", "updated" or "unchanged".
    A row whose theme_raw is unchanged is left untouched on college_id/match_status
    so a validated link (or a manually skipped entry) survives a re-import; only
    speaker metadata is refreshed in that case. A changed theme_raw resets the
    match to the freshly computed status/college so a stale link is never kept.
    """
    if match_status not in _CONFERENCE_MATCH_STATUSES:
        raise ValueError(f"Statut de correspondance invalide: {match_status}")
    date_iso = date.isoformat() if isinstance(date, datetime.date) else str(date)
    now = _now()
    with _conn() as con:
        existing = con.execute(
            "SELECT * FROM conferences WHERE date = ?", (date_iso,)
        ).fetchone()
        if existing is None:
            con.execute(
                """INSERT INTO conferences
                   (date, theme_raw, college_id, match_status, speaker_initials,
                    speaker_name, source_file, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date_iso, theme_raw, college_name, match_status, speaker_initials,
                 speaker_name, source_file, now, now),
            )
            row = con.execute("SELECT * FROM conferences WHERE date = ?", (date_iso,)).fetchone()
            return "created", dict(row)

        existing = dict(existing)
        if existing["theme_raw"] == theme_raw:
            if existing["speaker_initials"] == speaker_initials and existing["speaker_name"] == speaker_name:
                return "unchanged", existing
            con.execute(
                """UPDATE conferences SET speaker_initials = ?, speaker_name = ?,
                   source_file = ?, updated_at = ? WHERE id = ?""",
                (speaker_initials, speaker_name, source_file, now, existing["id"]),
            )
        else:
            con.execute(
                """UPDATE conferences SET theme_raw = ?, college_id = ?, match_status = ?,
                   speaker_initials = ?, speaker_name = ?, source_file = ?, updated_at = ?
                   WHERE id = ?""",
                (theme_raw, college_name, match_status, speaker_initials, speaker_name,
                 source_file, now, existing["id"]),
            )
        row = con.execute("SELECT * FROM conferences WHERE id = ?", (existing["id"],)).fetchone()
        return "updated", dict(row)


def get_conference(conference_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM conferences WHERE id = ?", (int(conference_id),)
        ).fetchone()
    return dict(row) if row else None


def list_conferences(*, match_status: str = "") -> list[dict]:
    query = "SELECT * FROM conferences"
    params: list = []
    if match_status:
        if match_status not in _CONFERENCE_MATCH_STATUSES:
            raise ValueError(f"Statut de correspondance invalide: {match_status}")
        query += " WHERE match_status = ?"
        params.append(match_status)
    query += " ORDER BY date"
    with _conn() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def set_conference_match(conference_id: int, *, match_status: str, college_name: str | None) -> dict:
    if match_status not in _CONFERENCE_MATCH_STATUSES:
        raise ValueError(f"Statut de correspondance invalide: {match_status}")
    now = _now()
    with _conn() as con:
        con.execute(
            "UPDATE conferences SET match_status = ?, college_id = ?, updated_at = ? WHERE id = ?",
            (match_status, college_name, now, int(conference_id)),
        )
        row = con.execute(
            "SELECT * FROM conferences WHERE id = ?", (int(conference_id),)
        ).fetchone()
    if row is None:
        raise ValueError(f"Conférence introuvable: {conference_id}")
    return dict(row)


def set_conference_google_event_ids(
    conference_id: int,
    *,
    google_event_id: str | None = None,
    uness_slot_google_event_id: str | None = None,
) -> dict:
    updates: list[str] = []
    params: list = []
    if google_event_id is not None:
        updates.append("google_event_id = ?")
        params.append(google_event_id)
    if uness_slot_google_event_id is not None:
        updates.append("uness_slot_google_event_id = ?")
        params.append(uness_slot_google_event_id)
    if not updates:
        row = get_conference(conference_id)
        if row is None:
            raise ValueError(f"Conférence introuvable: {conference_id}")
        return row
    updates.append("updated_at = ?")
    params.append(_now())
    params.append(int(conference_id))
    with _conn() as con:
        con.execute(f"UPDATE conferences SET {', '.join(updates)} WHERE id = ?", params)
        row = con.execute(
            "SELECT * FROM conferences WHERE id = ?", (int(conference_id),)
        ).fetchone()
    if row is None:
        raise ValueError(f"Conférence introuvable: {conference_id}")
    return dict(row)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_conferences_store.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_conferences_store.py
git commit -m "feat: add conferences table and CRUD to local_store"
```

---

### Task 3: Support des événements journée entière dans `calendar_service.py`

**Files:**
- Modify: `backend/core/google/calendar_service.py:75-123` (`create_event`)
- Test: `tests/test_calendar_service_events.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GoogleCalendarService.create_event(..., all_day: bool = False)` — when `all_day=True`,
  builds the Google event with `{"date": "YYYY-MM-DD"}` start/end (end = start + 1 day) instead
  of `dateTime`/`timeZone`, and ignores `duration_minutes`. Existing timed-event behavior is
  unchanged when `all_day` is omitted or `False`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_calendar_service_events.py
import asyncio

import pytest


class _FakeEvents:
    def __init__(self):
        self.inserted_bodies = []

    def insert(self, calendarId, body):
        self.inserted_bodies.append(body)
        return self

    def execute(self):
        return {"id": "evt-1"}


class _FakeGoogleService:
    def __init__(self):
        self._events = _FakeEvents()

    def events(self):
        return self._events


@pytest.fixture
def fake_calendar_service():
    from backend.core.google.calendar_service import GoogleCalendarService

    service = GoogleCalendarService()
    service.service = _FakeGoogleService()
    return service


def test_create_event_all_day_uses_date_not_datetime(fake_calendar_service):
    result = asyncio.run(
        fake_calendar_service.create_event(
            summary="Conférence — HGE",
            start_time_iso="2026-09-01T00:00:00",
            all_day=True,
        )
    )
    body = fake_calendar_service.service._events.inserted_bodies[0]
    assert body["start"] == {"date": "2026-09-01"}
    assert body["end"] == {"date": "2026-09-02"}
    assert "dateTime" not in body["start"]
    assert result == {"id": "evt-1"}


def test_create_event_timed_slot_still_uses_datetime(fake_calendar_service):
    asyncio.run(
        fake_calendar_service.create_event(
            summary="Dossier UNESS — HGE",
            start_time_iso="2026-09-01T17:30:00",
            duration_minutes=90,
        )
    )
    body = fake_calendar_service.service._events.inserted_bodies[0]
    assert body["start"]["dateTime"].startswith("2026-09-01T17:30:00")
    assert body["end"]["dateTime"].startswith("2026-09-01T19:00:00")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_calendar_service_events.py -v`
Expected: FAIL with "TypeError: create_event() got an unexpected keyword argument 'all_day'"

- [ ] **Step 3: Add `all_day` support**

In `backend/core/google/calendar_service.py`, replace the `create_event` signature and body
construction (lines 75-105):

```python
    async def create_event(self, summary, start_time_iso, duration_minutes=60, description="", color_id=None, reminders=None, all_day=False):
        """Creates an event in the primary calendar. Thread-safe."""
        if not self.service:
            try:
                await asyncio.to_thread(self.authenticate)
            except Exception as error:
                logger.error(f"Authentication failed before event creation: {error}")
                raise GoogleCalendarAuthError(
                    f"Authentification Google Calendar échouée : {error}"
                ) from error

        # Handle start time
        if isinstance(start_time_iso, str):
            start = datetime.datetime.fromisoformat(start_time_iso)
        else:
            start = start_time_iso

        if all_day:
            start_date = start.date() if isinstance(start, datetime.datetime) else start
            end_date = start_date + datetime.timedelta(days=1)
            event = {
                "summary": summary,
                "description": description,
                "start": {"date": start_date.isoformat()},
                "end": {"date": end_date.isoformat()},
            }
        else:
            end = start + datetime.timedelta(minutes=duration_minutes)
            event = {
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": get_app_timezone().key,
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": get_app_timezone().key,
                },
            }

        if color_id:
            event["colorId"] = color_id

        if reminders:
            event["reminders"] = reminders
```

The rest of the method (the `try`/`except HttpError`/`except Exception` block that inserts the
event) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_calendar_service_events.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/core/google/calendar_service.py tests/test_calendar_service_events.py
git commit -m "feat: support all-day events in GoogleCalendarService.create_event"
```

---

### Task 4: Parseur de la grille calendrier XLS

**Files:**
- Create: `backend/core/conferences/__init__.py`
- Create: `backend/core/conferences/xlsx_parser.py`
- Create: `tests/conferences_xlsx_fixtures.py` (helper, not collected as tests — builds a minimal `.xlsx`)
- Test: `tests/test_conferences_xlsx_parser.py`

**Interfaces:**
- Produces: `ParsedConference` dataclass `(date: datetime.date, weekday_abbr: str, theme_raw: str, speaker_initials: str, speaker_name: str)`.
  `parse_calendar_xlsx(path: Path) -> list[ParsedConference]` — returns every non-empty
  conference cell, any weekday (filtering to Tuesday happens in Task 6's `service.py`, not here).
  Raises `ValueError` if no month-header row or no year row is found.

- [ ] **Step 1: Create the package and the test fixture helper**

```python
# backend/core/conferences/__init__.py
```

```python
# tests/conferences_xlsx_fixtures.py
"""Builds a minimal .xlsx (inline strings, no sharedStrings.xml) for parser tests."""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _col_letter(idx: int) -> str:
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell_xml(ref: str, text: str) -> str:
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _row_xml(row_num: int, cells: dict[int, str]) -> str:
    cell_xml = "".join(
        _cell_xml(f"{_col_letter(col)}{row_num}", text)
        for col, text in sorted(cells.items())
        if text is not None
    )
    return f'<row r="{row_num}">{cell_xml}</row>'


def write_minimal_xlsx(path: Path, rows: dict[int, dict[int, str]]) -> None:
    rows_xml = "".join(_row_xml(r, cells) for r, cells in sorted(rows.items()))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{rows_xml}</sheetData></worksheet>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_conferences_xlsx_parser.py
import datetime

import pytest

from tests.conferences_xlsx_fixtures import write_minimal_xlsx
from backend.core.conferences.xlsx_parser import parse_calendar_xlsx


def test_parses_tuesday_and_thursday_conferences_with_correct_dates(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Sa"},
        5: {1: "4", 2: "Ma", 3: "HGE"},
        6: {1: "6", 2: "Je", 3: "Onco"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert [(c.date, c.weekday_abbr, c.theme_raw) for c in conferences] == [
        (datetime.date(2026, 8, 4), "Ma", "HGE"),
        (datetime.date(2026, 8, 6), "Je", "Onco"),
    ]


def test_resolves_speaker_initials_via_legend(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Ma", 3: "Onco JFD"},
        10: {1: "JFD", 2: "Jean-François Delattre"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert conferences[0].theme_raw == "Onco"
    assert conferences[0].speaker_initials == "JFD"
    assert conferences[0].speaker_name == "Jean-François Delattre"


def test_keeps_theme_whole_when_legend_absent(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Ma", 3: "Onco JFD"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert conferences[0].theme_raw == "Onco JFD"
    assert conferences[0].speaker_initials == ""


def test_stops_a_month_block_at_the_first_non_incrementing_day(tmp_path):
    rows = {
        2: {1: "2026"},
        3: {1: "Août"},
        4: {1: "1", 2: "Ma", 3: "HGE"},
        5: {1: "2", 2: "Me", 3: ""},
        6: {1: "1", 2: "Ma", 3: "Rentrée bis"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert [c.theme_raw for c in conferences] == ["HGE"]


def test_resolves_year_after_the_year_boundary_column(tmp_path):
    rows = {
        2: {1: "2026", 5: "2027"},
        3: {1: "Décembre", 5: "Janvier"},
        4: {1: "1", 2: "Ma", 3: "MI", 5: "1", 6: "Ve"},
        5: {1: "8", 2: "Ma", 3: "EDN", 5: "8", 6: "Ve"},
    }
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    conferences = parse_calendar_xlsx(path)

    assert conferences[0].date == datetime.date(2026, 12, 1)
    assert conferences[1].date == datetime.date(2026, 12, 8)


def test_raises_when_no_month_header_found(tmp_path):
    rows = {2: {1: "2026"}}
    path = tmp_path / "calendrier.xlsx"
    write_minimal_xlsx(path, rows)

    with pytest.raises(ValueError):
        parse_calendar_xlsx(path)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_conferences_xlsx_parser.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.core.conferences.xlsx_parser'"

- [ ] **Step 4: Implement the parser**

```python
# backend/core/conferences/xlsx_parser.py
"""Lit un fichier XLS "grille calendrier" (mois en colonnes, jours en lignes) tel
que fourni par la faculté pour le planning des conférences DFASM. Seul le texte
des cellules est exploité — la couleur de remplissage n'est pas lue (v1)."""
from __future__ import annotations

import datetime
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

_MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12,
}

_YEAR_RE = re.compile(r"^\d{4}$")
_INITIALS_RE = re.compile(r"^[A-ZÉÈÀ]{2,5}\.?\*?$")


@dataclass(frozen=True)
class ParsedConference:
    date: datetime.date
    weekday_abbr: str
    theme_raw: str
    speaker_initials: str
    speaker_name: str


def parse_calendar_xlsx(path: Path) -> list[ParsedConference]:
    rows = _read_sheet_rows(path)
    legend = _read_legend(rows)

    month_row_num, month_cols = _find_month_header(rows)
    if month_row_num is None:
        raise ValueError("Aucune ligne d'en-tête de mois trouvée dans le classeur.")
    year_row = rows.get(month_row_num - 1, {})
    years_by_col = {
        col: int(str(value).strip())
        for col, value in year_row.items()
        if value and _YEAR_RE.match(str(value).strip())
    }
    if not years_by_col:
        raise ValueError(
            "Impossible de déterminer l'année du calendrier (ligne des années absente)."
        )

    conferences: list[ParsedConference] = []
    for month_col, month_number in month_cols.items():
        year = _year_for_column(month_col, years_by_col)
        previous_day = 0
        row_num = month_row_num + 1
        while True:
            row = rows.get(row_num)
            if row is None:
                break
            day_text = str(row.get(month_col) or "").strip()
            if not day_text.isdigit():
                break
            day = int(day_text)
            if day < previous_day:
                break
            previous_day = day
            weekday_abbr = str(row.get(month_col + 1) or "").strip()
            theme_cell = str(row.get(month_col + 2) or "").strip()
            if theme_cell:
                try:
                    conf_date = datetime.date(year, month_number, day)
                except ValueError:
                    row_num += 1
                    continue
                theme, initials, speaker_name = _split_speaker(theme_cell, legend)
                conferences.append(
                    ParsedConference(
                        date=conf_date,
                        weekday_abbr=weekday_abbr,
                        theme_raw=theme,
                        speaker_initials=initials,
                        speaker_name=speaker_name,
                    )
                )
            row_num += 1
    return conferences


def _split_speaker(theme_cell: str, legend: dict[str, str]) -> tuple[str, str, str]:
    parts = theme_cell.rsplit(" ", 1)
    if len(parts) == 2:
        theme, last = parts
        key = last.strip("*").upper()
        if key in legend:
            return theme.strip(), last.strip(), legend[key]
    return theme_cell, "", ""


def _col_to_index(ref: str) -> int:
    letters = "".join(c for c in ref if c.isalpha())
    idx = 0
    for c in letters:
        idx = idx * 26 + (ord(c.upper()) - ord("A") + 1)
    return idx


def _cell_text(cell: ET.Element, shared: list[str]) -> str | None:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        is_el = cell.find("m:is", _NS)
        if is_el is None:
            return None
        texts = is_el.findall(".//m:t", _NS)
        return "".join(t.text or "" for t in texts)
    value_el = cell.find("m:v", _NS)
    if value_el is None:
        return None
    value = value_el.text
    if cell_type == "s" and value is not None:
        return shared[int(value)]
    return value


def _read_sheet_rows(path: Path) -> dict[int, dict[int, str]]:
    with zipfile.ZipFile(path) as archive:
        sheet_xml = archive.read("xl/worksheets/sheet1.xml")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            sst_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in sst_root.findall("m:si", _NS):
                texts = si.findall(".//m:t", _NS)
                shared.append("".join(t.text or "" for t in texts))

    root = ET.fromstring(sheet_xml)
    rows: dict[int, dict[int, str]] = {}
    for row_el in root.findall(".//m:row", _NS):
        row_num = int(row_el.get("r"))
        cells: dict[int, str] = {}
        for cell in row_el.findall("m:c", _NS):
            ref = cell.get("r")
            if not ref:
                continue
            text = _cell_text(cell, shared)
            if text is not None:
                cells[_col_to_index(ref)] = text
        if cells:
            rows[row_num] = cells
    return rows


def _find_month_header(rows: dict[int, dict[int, str]]) -> tuple[int | None, dict[int, int]]:
    for row_num in sorted(rows):
        found: dict[int, int] = {}
        for col, value in rows[row_num].items():
            month_number = _MONTHS_FR.get(str(value).strip().lower())
            if month_number:
                found[col] = month_number
        if len(found) >= 2:
            return row_num, found
    return None, {}


def _year_for_column(col: int, years_by_col: dict[int, int]) -> int:
    candidates = [c for c in years_by_col if c <= col]
    reference_col = max(candidates) if candidates else min(years_by_col)
    return years_by_col[reference_col]


def _read_legend(rows: dict[int, dict[int, str]]) -> dict[str, str]:
    """Best-effort initials -> full name lookup, built from adjacent
    (initials cell, name cell) pairs found anywhere in the sheet. The real
    source file's legend layout is irregular (some entries share a single
    cell), so this intentionally only captures the clean two-cell case
    rather than over-fitting to one file's exact quirks."""
    legend: dict[str, str] = {}
    for cols in rows.values():
        for col, value in cols.items():
            text = str(value).strip()
            if not _INITIALS_RE.match(text):
                continue
            name = str(cols.get(col + 1) or "").strip()
            if name and " " in name:
                legend[text.strip("*").upper()] = name.strip("*").strip()
    return legend
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_conferences_xlsx_parser.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/core/conferences/__init__.py backend/core/conferences/xlsx_parser.py \
        tests/conferences_xlsx_fixtures.py tests/test_conferences_xlsx_parser.py
git commit -m "feat: parse the DFASM conference calendar grid from xlsx"
```

---

### Task 5: Rapprochement thème → collège UNESS

**Files:**
- Create: `backend/core/conferences/matcher.py`
- Test: `tests/test_conferences_matcher.py`

**Interfaces:**
- Consumes: `all_college_names()`, `abbreviation_to_college()` from Task 1
  (`backend.core.qcm.items_mapping`).
- Produces: `MatchResult` dataclass `(status: str, college_name: str | None)` where `status` is
  `"matched"` or `"needs_validation"`. `match_college(theme_raw: str) -> MatchResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conferences_matcher.py
from backend.core.conferences.matcher import match_college


def test_matches_via_known_abbreviation_table():
    result = match_college("MI")
    assert result.status == "matched"
    assert result.college_name == "Médecine Interne 🏥"


def test_matches_abbreviation_even_with_trailing_speaker_word():
    result = match_college("Psy CA")
    assert result.status == "matched"
    assert result.college_name == "Psychiatrie 🧩"


def test_matches_via_prefix_against_full_college_name():
    result = match_college("Cardio")
    assert result.status == "matched"
    assert result.college_name == "Cardiovasculaire ❤️"


def test_unrecognized_theme_needs_validation():
    result = match_college("Toussaint")
    assert result.status == "needs_validation"
    assert result.college_name is None


def test_short_unmatched_theme_needs_validation():
    result = match_college("OK")
    assert result.status == "needs_validation"


def test_ambiguous_prefix_across_multiple_colleges_needs_validation():
    result = match_college("Médecine")
    assert result.status == "needs_validation"
    assert result.college_name is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conferences_matcher.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.core.conferences.matcher'"

- [ ] **Step 3: Implement the matcher**

```python
# backend/core/conferences/matcher.py
"""Rapproche un thème abrégé de conférence (ex: "HGE", "Cardio", "MI") du
référentiel collège UNESS déjà connu de Synapse (items_mapping._ABBR_TO_NOTION
et les 39 noms Notion complets qui en dérivent).

Deux passes, dans cet ordre :
  1. Table d'abréviations exactes (insensible à la casse) — couvre les sigles
     qui ne sont pas de simples préfixes du nom complet (ex: "MI", "GO").
  2. Préfixe des mots "forts" (>= 4 caractères) du thème contre les mots du
     nom de collège complet — couvre les troncatures lisibles ("Cardio" ->
     "Cardiovasculaire"). Les mots courts sont ignorés : trop peu
     discriminants pour un rapprochement fiable.
Un thème sans mot fort qui n'a pas matché en passe 1, ou qui matche
plusieurs collèges en passe 2, part en validation humaine plutôt que
de risquer un mauvais rapprochement.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.core.qcm.items_mapping import abbreviation_to_college, all_college_names

_STOPWORDS = {"de", "du", "des", "la", "le", "les", "et", "en", "d", "l"}


@dataclass(frozen=True)
class MatchResult:
    status: str
    college_name: str | None


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


def _words(text: str) -> list[str]:
    return [w for w in _normalize(text).split() if w not in _STOPWORDS and len(w) >= 2]


def match_college(theme_raw: str) -> MatchResult:
    for word in theme_raw.split():
        college = abbreviation_to_college(word)
        if college:
            return MatchResult(status="matched", college_name=college)

    strong_words = [w for w in _words(theme_raw) if len(w) >= 4]
    if not strong_words:
        return MatchResult(status="needs_validation", college_name=None)

    candidates: set[str] = set()
    for college_name in all_college_names():
        college_words = _words(college_name)
        if all(any(cw.startswith(sw) for cw in college_words) for sw in strong_words):
            candidates.add(college_name)

    if len(candidates) == 1:
        return MatchResult(status="matched", college_name=next(iter(candidates)))
    return MatchResult(status="needs_validation", college_name=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_conferences_matcher.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/core/conferences/matcher.py tests/test_conferences_matcher.py
git commit -m "feat: match conference themes to the UNESS college referential"
```

---

### Task 6: Orchestration import + validation (`service.py`)

**Files:**
- Create: `backend/core/conferences/service.py`
- Test: `tests/test_conferences_service.py`

**Interfaces:**
- Consumes:
  - `parse_calendar_xlsx(path) -> list[ParsedConference]` (Task 4), field `.weekday_abbr` used to
    keep only `"Ma"` (Tuesday) rows.
  - `match_college(theme_raw) -> MatchResult` (Task 5).
  - `local_store.upsert_conference(...)`, `local_store.set_conference_match(...)`,
    `local_store.set_conference_google_event_ids(...)`, `local_store.list_conferences(...)`,
    `local_store.get_conference(...)` (Task 2).
  - `calendar_service.create_event(..., all_day=...)` (Task 3) — imported as the module-level
    singleton `backend.core.google.calendar_service.calendar_service`.
- Produces:
  - `ImportSummary` dataclass `(imported: int, updated: int, unchanged: int, needs_validation: int)`.
  - `async def import_conferences_from_xlsx(path: Path) -> ImportSummary`.
  - `async def validate_conference(conference_id: int, *, college_name: str | None, skip: bool = False) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conferences_service.py
import asyncio
import datetime

import pytest

from tests.conferences_xlsx_fixtures import write_minimal_xlsx


@pytest.fixture
def isolated_local_store(tmp_path, monkeypatch):
    from backend.core.reviews import local_store

    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None
    monkeypatch.setattr(local_store, "DB_PATH", tmp_path / "conferences.db")
    local_store.init_db()
    yield local_store
    if local_store._DB is not None:
        local_store._DB.close()
    local_store._DB = None


@pytest.fixture
def fake_calendar(monkeypatch):
    from backend.core.conferences import service

    created = []

    async def _fake_create_event(*, summary, start_time_iso, duration_minutes=60,
                                  description="", color_id=None, reminders=None, all_day=False):
        event = {"id": f"evt-{len(created) + 1}", "summary": summary, "all_day": all_day}
        created.append(event)
        return event

    monkeypatch.setattr(service.calendar_service, "create_event", _fake_create_event)
    return created


def test_import_creates_conference_and_two_calendar_events(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "4", 2: "Ma", 3: "HGE"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.imported == 1
    assert summary.needs_validation == 0
    assert len(fake_calendar) == 2
    conferences = isolated_local_store.list_conferences()
    assert conferences[0]["google_event_id"] == "evt-1"
    assert conferences[0]["uness_slot_google_event_id"] == "evt-2"


def test_import_skips_thursday_only_conferences(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "6", 2: "Je", 3: "Onco"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.imported == 0
    assert isolated_local_store.list_conferences() == []


def test_import_flags_unmatched_theme_without_calendar_sync(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "1", 2: "Ma", 3: "Toussaint"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.needs_validation == 1
    assert fake_calendar == []


def test_validate_conference_assigns_college_and_syncs_calendar(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "1", 2: "Ma", 3: "Toussaint"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)
    asyncio.run(service.import_conferences_from_xlsx(path))
    pending = isolated_local_store.list_conferences(match_status="needs_validation")[0]

    updated = asyncio.run(
        service.validate_conference(
            pending["id"], college_name="Médecine légale - Santé publique ⚖️"
        )
    )

    assert updated["match_status"] == "matched"
    assert len(fake_calendar) == 2


def test_validate_conference_skip_does_not_sync_calendar(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "1", 2: "Ma", 3: "Toussaint"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)
    asyncio.run(service.import_conferences_from_xlsx(path))
    pending = isolated_local_store.list_conferences(match_status="needs_validation")[0]

    updated = asyncio.run(service.validate_conference(pending["id"], college_name=None, skip=True))

    assert updated["match_status"] == "skipped"
    assert fake_calendar == []


def test_reimport_does_not_duplicate_calendar_events(tmp_path, isolated_local_store, fake_calendar):
    from backend.core.conferences import service

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "4", 2: "Ma", 3: "HGE"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    asyncio.run(service.import_conferences_from_xlsx(path))
    asyncio.run(service.import_conferences_from_xlsx(path))

    assert len(fake_calendar) == 2


def test_failed_calendar_sync_does_not_crash_and_stays_retryable(tmp_path, isolated_local_store, monkeypatch):
    from backend.core.conferences import service

    async def _failing_create_event(**kwargs):
        return None  # mirrors GoogleCalendarService.create_event on HttpError

    monkeypatch.setattr(service.calendar_service, "create_event", _failing_create_event)

    rows = {2: {1: "2026"}, 3: {1: "Août"}, 4: {1: "4", 2: "Ma", 3: "HGE"}}
    path = tmp_path / "cal.xlsx"
    write_minimal_xlsx(path, rows)

    summary = asyncio.run(service.import_conferences_from_xlsx(path))

    assert summary.imported == 1
    row = isolated_local_store.list_conferences()[0]
    assert row["google_event_id"] is None
    assert row["uness_slot_google_event_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conferences_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.core.conferences.service'"

- [ ] **Step 3: Implement the service**

```python
# backend/core/conferences/service.py
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from backend.core.conferences.matcher import match_college
from backend.core.conferences.xlsx_parser import parse_calendar_xlsx
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import local_store

_DFASM1_WEEKDAY = "Ma"
_UNESS_SLOT_HOUR = 17
_UNESS_SLOT_MINUTE = 30
_UNESS_SLOT_DURATION_MINUTES = 90


@dataclass
class ImportSummary:
    imported: int = 0
    updated: int = 0
    unchanged: int = 0
    needs_validation: int = 0


async def import_conferences_from_xlsx(path: Path) -> ImportSummary:
    parsed = [c for c in parse_calendar_xlsx(path) if c.weekday_abbr == _DFASM1_WEEKDAY]
    summary = ImportSummary()
    for conf in parsed:
        match = match_college(conf.theme_raw)
        outcome, row = local_store.upsert_conference(
            date=conf.date,
            theme_raw=conf.theme_raw,
            speaker_initials=conf.speaker_initials,
            speaker_name=conf.speaker_name,
            match_status=match.status,
            college_name=match.college_name,
            source_file=path.name,
        )
        if outcome == "created":
            summary.imported += 1
        elif outcome == "updated":
            summary.updated += 1
        else:
            summary.unchanged += 1
        if row["match_status"] == "matched":
            await _sync_calendar_events(row)
        elif row["match_status"] == "needs_validation":
            summary.needs_validation += 1
    return summary


async def validate_conference(
    conference_id: int, *, college_name: str | None, skip: bool = False
) -> dict:
    if skip:
        return local_store.set_conference_match(
            conference_id, match_status="skipped", college_name=None
        )
    if not college_name:
        raise ValueError("college_name requis sauf si skip=True")
    row = local_store.set_conference_match(
        conference_id, match_status="matched", college_name=college_name
    )
    await _sync_calendar_events(row)
    return row


async def _sync_calendar_events(conference_row: dict) -> None:
    conf_date = datetime.date.fromisoformat(conference_row["date"])
    theme = conference_row["theme_raw"]
    college = conference_row["college_id"] or ""
    summary = f"Conférence — {theme}" + (f" ({college})" if college else "")

    if not conference_row["google_event_id"]:
        event = await calendar_service.create_event(
            summary=summary,
            start_time_iso=datetime.datetime.combine(conf_date, datetime.time.min).isoformat(),
            all_day=True,
            description=f"Importé depuis {conference_row['source_file']}",
        )
        if event:
            conference_row = local_store.set_conference_google_event_ids(
                conference_row["id"], google_event_id=event["id"]
            )

    if not conference_row["uness_slot_google_event_id"]:
        slot_start = datetime.datetime.combine(
            conf_date, datetime.time(_UNESS_SLOT_HOUR, _UNESS_SLOT_MINUTE)
        )
        event = await calendar_service.create_event(
            summary=f"Dossier UNESS — {theme}",
            start_time_iso=slot_start.isoformat(),
            duration_minutes=_UNESS_SLOT_DURATION_MINUTES,
            description=f"Créneau dossier UNESS pour la conférence du {conf_date.isoformat()}.",
        )
        if event:
            local_store.set_conference_google_event_ids(
                conference_row["id"], uness_slot_google_event_id=event["id"]
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_conferences_service.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/core/conferences/service.py tests/test_conferences_service.py
git commit -m "feat: orchestrate conference import, matching and calendar sync"
```

---

### Task 7: Panneau `settings_cockpit` — import et validation

**Files:**
- Create: `frontend/components/conferences_admin.py`
- Modify: `frontend/pages/settings_cockpit.py` (add import near line 48, mount panel after the
  `LISA / OIC` domain block, before `render_catalog_admin()` around line 510)
- Test: `tests/test_conferences_admin_ui.py`

**Interfaces:**
- Consumes: `service.import_conferences_from_xlsx`, `service.validate_conference` (Task 6),
  `local_store.list_conferences` (Task 2), `items_mapping.all_college_names` (Task 1).
- Produces: `render_conferences_admin(container=None) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conferences_admin_ui.py
from pathlib import Path


def test_conferences_admin_component_contains_import_and_validation_actions():
    source = Path("frontend/components/conferences_admin.py").read_text(encoding="utf-8")

    assert "PLANNING CONFÉRENCES — IMPORT" in source
    assert "Importer le planning" in source
    assert "Valider" in source
    assert "Non applicable" in source


def test_settings_mounts_conferences_admin_panel():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert "render_conferences_admin" in source
    assert "PLANNING CONFÉRENCES" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conferences_admin_ui.py -v`
Expected: FAIL — `frontend/components/conferences_admin.py` does not exist yet.

- [ ] **Step 3: Implement the component**

```python
# frontend/components/conferences_admin.py
"""Panel d'import et de validation du planning des conférences DFASM."""

from __future__ import annotations

import asyncio
from pathlib import Path

from nicegui import ui

from backend.core.conferences import service
from backend.core.qcm.items_mapping import all_college_names
from backend.core.reviews import local_store


def render_conferences_admin(container=None) -> None:
    parent = container or ui.column().classes("w-full")
    with parent:
        ui.label("PLANNING CONFÉRENCES — IMPORT").classes("se-label")
        ui.label(
            "Importe le calendrier XLS des conférences DFASM (mardi). Chaque conférence "
            "reconnue crée un événement Google Calendar et le créneau dossier UNESS "
            "17h30–19h."
        ).classes("se-appearance-sub")

        path_input = ui.input(
            label="Chemin du fichier XLS",
            placeholder=r"C:\Users\...\Calendrier Confs.xlsx",
        ).props("outlined dense").classes("w-full mt-3")
        status = ui.label("Aucun import lancé.").classes("se-uness-status")
        body = ui.column().classes("w-full gap-3 mt-3")

        def _render_body() -> None:
            body.clear()
            pending = local_store.list_conferences(match_status="needs_validation")
            with body:
                if not pending:
                    ui.label("Aucune conférence à valider.").classes("text-sm text-slate-500")
                for conf in pending:
                    _render_pending(conf)

        def _render_pending(conf: dict) -> None:
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(f"{conf['date']} — {conf['theme_raw']}").classes("text-sm flex-1")
                college_select = ui.select(
                    all_college_names(), label="Collège"
                ).props("outlined dense").classes("w-64")

                async def _validate(conf_id=conf["id"], select=college_select) -> None:
                    if not select.value:
                        ui.notify("Choisis un collège avant de valider.", type="warning")
                        return
                    await service.validate_conference(conf_id, college_name=select.value)
                    ui.notify("Conférence validée.", type="positive")
                    _render_body()

                async def _skip(conf_id=conf["id"]) -> None:
                    await service.validate_conference(conf_id, college_name=None, skip=True)
                    ui.notify("Conférence ignorée.", type="positive")
                    _render_body()

                ui.button("Valider", on_click=_validate).props("unelevated color=teal size=sm")
                ui.button("Non applicable", on_click=_skip).props("flat size=sm")

        async def _run_import() -> None:
            path_text = path_input.value.strip()
            if not path_text:
                ui.notify("Indique le chemin du fichier XLS.", type="warning")
                return
            path = Path(path_text)
            if not path.exists():
                status.set_text(f"Fichier introuvable : {path}")
                status.style("color:var(--danger-text)")
                ui.notify("Fichier introuvable", type="negative")
                return
            try:
                summary = await service.import_conferences_from_xlsx(path)
            except ValueError as exc:
                status.set_text(f"Erreur d'import : {exc}")
                status.style("color:var(--danger-text)")
                ui.notify(str(exc), type="negative")
                return
            status.set_text(
                f"Import terminé : {summary.imported} nouvelle(s), "
                f"{summary.updated} mise(s) à jour, {summary.unchanged} inchangée(s), "
                f"{summary.needs_validation} à valider."
            )
            status.style("color:var(--success-text)")
            ui.notify("Import du planning terminé", type="positive", icon="event")
            _render_body()

        ui.button(
            "Importer le planning",
            icon="upload_file",
            on_click=lambda: asyncio.ensure_future(_run_import()),
        ).props("unelevated color=teal size=sm rounded").classes("mt-2")

        _render_body()
```

- [ ] **Step 4: Wire the panel into `settings_cockpit.py`**

Add the import near the other `frontend.components` imports (around line 48):

```python
from frontend.components.conferences_admin import render_conferences_admin
```

Add a new domain block right after the `LISA / OIC` block's closing (after the
`oic_button.on("click", ...)` line, before `render_catalog_admin()`):

```python
        with _settings_domain("PLANNING CONFÉRENCES", "Import du calendrier DFASM (XLS)", "event"):
            render_conferences_admin(ui.column().classes("w-full p-4"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_conferences_admin_ui.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend/components/conferences_admin.py frontend/pages/settings_cockpit.py \
        tests/test_conferences_admin_ui.py
git commit -m "feat: add conference planning import panel to settings cockpit"
```

---

### Task 8: Vérification bout en bout

**Files:** none (verification only).

- [ ] **Step 1: Run the full conference test suite**

Run: `pytest tests/test_items_mapping_college_helpers.py tests/test_conferences_store.py tests/test_calendar_service_events.py tests/test_conferences_xlsx_parser.py tests/test_conferences_matcher.py tests/test_conferences_service.py tests/test_conferences_admin_ui.py -v`
Expected: all PASS.

- [ ] **Step 2: Run the full project test suite to check for regressions**

Run: `pytest -q`
Expected: no new failures compared to the pre-existing baseline (the repo already has some
known-unrelated failing tests per prior audits — compare failure count/names before and after
this change rather than expecting a fully green baseline).

- [ ] **Step 3: Manual smoke test with the real file**

With the app running, open Settings → PLANNING CONFÉRENCES, paste the path to
`Calendrier Confs 26-27.xlsx`, click "Importer le planning", and confirm:
- the status line reports a plausible split (roughly one Tuesday conference imported per week of
  term, several flagged for validation — French bank holidays like "Toussaint", "Noël" will
  legitimately land in "à valider").
- the validation list lets you assign a collège or mark "Non applicable" for holiday entries.
- re-running the same import reports mostly "inchangée(s)" and does not change the count of
  Google Calendar events already created.
