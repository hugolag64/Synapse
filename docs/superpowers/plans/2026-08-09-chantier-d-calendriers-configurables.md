# Chantier D — Calendriers Google configurables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre d'ajouter/retirer des IDs de calendrier Google depuis Paramètres (sans redémarrage) et afficher la source de chaque événement dans la grille Planning.

**Architecture:** Une préférence `data_store.preferences["planning_calendar_sources"]` (liste de `{"id", "label"}`) gérée par trois fonctions pures dans un nouveau module `backend/core/planning/calendar_sources.py`. `GoogleCalendarService.get_events_for_day` fusionne ces IDs avec ceux déjà lus depuis `.env`, dédupliqués, et étiquette chaque événement récupéré. Un nouveau composant `frontend/components/calendar_sources_panel.py` (pattern identique à `dp_coverage_panel.py`) expose la gestion dans `settings_cockpit.py`. `planning_cockpit.py` affiche le label en préfixe du titre de l'événement dans la grille.

**Tech Stack:** Python 3, NiceGUI, pytest, Google Calendar API (`googleapiclient`), SQLite-backed preferences via `data_store`.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-08-09-chantier-d-calendriers-configurables-design.md`
- TDD strict : test en échec avant toute implémentation, à chaque tâche.
- Aucune vérification d'existence de l'ID de calendrier côté API Google à l'ajout (hors périmètre spec).
- Le correctif +4h « Agenda FAC » (`calendar_service.py:168-186`) reste inchangé, indexé par ID littéral.
- Pas de migration automatique des IDs `.env` vers la préférence — les deux sources coexistent.
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la dernière. Baseline mesurée le 2026-08-09 : **1172 passed**.
- Ce plan est exécuté en session, jamais commité (reste `??` dans `git status`, comme la spec).

---

## Task 0: Baseline

- [ ] **Step 1: Confirmer l'état de départ**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `1172 passed` (aucune régression préexistante avant de commencer).

---

## Task 1: Fonctions pures de gestion des sources de calendrier

**Files:**
- Create: `backend/core/planning/calendar_sources.py`
- Test: `tests/test_planning_calendar_sources.py`

**Interfaces:**
- Consumes: rien (fonctions pures, aucune dépendance à `data_store` ni `ui`).
- Produces:
  - `list_calendar_sources(preferences: dict) -> list[dict]` — chaque dict `{"id": str, "label": str}`.
  - `add_calendar_source(sources: list[dict], calendar_id: str, label: str) -> list[dict]` — lève `ValueError` si `calendar_id.strip()` est vide.
  - `remove_calendar_source(sources: list[dict], calendar_id: str) -> list[dict]`

Ces trois fonctions sont utilisées telles quelles par Task 2 (backend) et Task 3 (panneau Paramètres).

- [ ] **Step 1: Write the failing tests**

Créer `tests/test_planning_calendar_sources.py` :

```python
import pytest

from backend.core.planning.calendar_sources import (
    add_calendar_source,
    list_calendar_sources,
    remove_calendar_source,
)


def test_list_calendar_sources_returns_empty_list_by_default():
    assert list_calendar_sources({}) == []


def test_list_calendar_sources_ignores_malformed_preference():
    assert list_calendar_sources({"planning_calendar_sources": "not-a-list"}) == []
    assert list_calendar_sources({"planning_calendar_sources": [{"label": "Fac"}]}) == []
    assert list_calendar_sources({"planning_calendar_sources": ["not-a-dict"]}) == []


def test_list_calendar_sources_normalizes_entries():
    prefs = {"planning_calendar_sources": [{"id": " abc@x.com ", "label": " Fac "}]}
    assert list_calendar_sources(prefs) == [{"id": "abc@x.com", "label": "Fac"}]


def test_list_calendar_sources_defaults_missing_label_to_empty_string():
    prefs = {"planning_calendar_sources": [{"id": "abc@x.com"}]}
    assert list_calendar_sources(prefs) == [{"id": "abc@x.com", "label": ""}]


def test_add_calendar_source_appends_new_entry():
    result = add_calendar_source([], "abc@x.com", "Fac")
    assert result == [{"id": "abc@x.com", "label": "Fac"}]


def test_add_calendar_source_strips_id_and_label():
    result = add_calendar_source([], "  abc@x.com  ", "  Fac  ")
    assert result == [{"id": "abc@x.com", "label": "Fac"}]


def test_add_calendar_source_rejects_blank_id():
    with pytest.raises(ValueError):
        add_calendar_source([], "   ", "Fac")


def test_add_calendar_source_replaces_existing_entry_without_duplicating():
    existing = [{"id": "abc@x.com", "label": "Fac"}]
    result = add_calendar_source(existing, "abc@x.com", "Faculté de médecine")
    assert result == [{"id": "abc@x.com", "label": "Faculté de médecine"}]


def test_add_calendar_source_accepts_empty_label():
    result = add_calendar_source([], "abc@x.com", "")
    assert result == [{"id": "abc@x.com", "label": ""}]


def test_remove_calendar_source_drops_matching_id():
    existing = [{"id": "abc@x.com", "label": "Fac"}, {"id": "def@x.com", "label": ""}]
    result = remove_calendar_source(existing, "abc@x.com")
    assert result == [{"id": "def@x.com", "label": ""}]


def test_remove_calendar_source_is_noop_for_unknown_id():
    existing = [{"id": "abc@x.com", "label": "Fac"}]
    assert remove_calendar_source(existing, "unknown@x.com") == existing
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_planning_calendar_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.planning.calendar_sources'`

- [ ] **Step 3: Write the implementation**

Créer `backend/core/planning/calendar_sources.py` :

```python
"""Gestion des IDs de calendrier Google supplémentaires (préférence planning)."""

from __future__ import annotations


def list_calendar_sources(preferences: dict) -> list[dict]:
    """Lit planning_calendar_sources depuis les préférences, normalisé.

    Retourne une liste vide si la clé est absente ou mal formée (jamais
    d'exception — même défense que les autres lectures de préférences
    planning, ex. _target_for dans planning_cockpit.py).
    """
    raw = preferences.get("planning_calendar_sources") if isinstance(preferences, dict) else None
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        calendar_id = str(entry.get("id", "")).strip()
        if not calendar_id:
            continue
        label = str(entry.get("label", "")).strip()
        result.append({"id": calendar_id, "label": label})
    return result


def add_calendar_source(sources: list[dict], calendar_id: str, label: str) -> list[dict]:
    """Retourne une nouvelle liste avec l'entrée ajoutée (ou son label remplacé si l'ID existe déjà)."""
    calendar_id = (calendar_id or "").strip()
    if not calendar_id:
        raise ValueError("L'identifiant de calendrier ne peut pas être vide.")
    label = (label or "").strip()
    updated = [s for s in sources if s.get("id") != calendar_id]
    updated.append({"id": calendar_id, "label": label})
    return updated


def remove_calendar_source(sources: list[dict], calendar_id: str) -> list[dict]:
    """Retourne une nouvelle liste sans l'entrée dont l'ID correspond."""
    return [s for s in sources if s.get("id") != calendar_id]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_planning_calendar_sources.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/core/planning/calendar_sources.py tests/test_planning_calendar_sources.py
git commit -m "feat: add pure functions for configurable calendar sources"
```

---

## Task 2: Fusion des IDs de préférence + étiquetage des événements

**Files:**
- Modify: `backend/core/google/calendar_service.py:121-200` (méthode `get_events_for_day`)
- Test: `tests/test_planning_calendar_actions.py`

**Interfaces:**
- Consumes: `list_calendar_sources(preferences: dict) -> list[dict]` (Task 1), `data_store.preferences` (`backend/state/store.py`), `settings.get_calendar_ids() -> list[str]` (déjà existant).
- Produces: `get_events_for_day` retourne des événements dont chaque dict porte désormais une clé `_synapse_source_label: str` (vide si la source n'est pas étiquetée). Consommé par Task 4.

Avant de modifier, relire l'état exact du fichier (les lignes ci-dessous sont vérifiées au 2026-08-09) :

```
142	        # Calendriers à interroger : primary + IDs configurés dans les paramètres
143	        from backend.config.settings import settings as _cfg
144	        configured_ids = _cfg.get_calendar_ids()
145	        seen_ids: set[str] = set()
146	        calendar_ids: list[str] = []
147	        for cid in ["primary"] + configured_ids:
148	            if cid not in seen_ids:
149	                seen_ids.add(cid)
150	                calendar_ids.append(cid)
151	        
152	        all_events = []
153	        
154	        async def fetch_calendar(cal_id):
155	            try:
156	                events_result = await asyncio.to_thread(
157	                    lambda: self.service.events().list(
158	                        calendarId=cal_id, 
159	                        timeMin=time_min, 
160	                        timeMax=time_max,
161	                        singleEvents=True,
162	                        orderBy='startTime'
163	                    ).execute()
164	                )
165	                items = events_result.get('items', [])
166	                
167	                # FIX: Apply +4h offset for "Agenda FAC" (User reported 4h early events)
168	                # ID: dm1rlvvim8vemcspm4momjq8f7qfqc3g@import.calendar.google.com
169	                if cal_id == 'dm1rlvvim8vemcspm4momjq8f7qfqc3g@import.calendar.google.com':
```

- [ ] **Step 1: Write the failing tests**

Ajouter `from unittest.mock import patch` aux imports en tête de `tests/test_planning_calendar_actions.py`
(le reste — `asyncio`, `datetime`, `GoogleCalendarService`, `app_settings` — est déjà importé). Puis
ajouter à la fin du fichier :

```python
class _FakeEventsMultiCalendar:
    def __init__(self, items_by_cal: dict):
        self.items_by_cal = items_by_cal
        self.calls: list[str] = []
        self._current = None

    def list(self, **kwargs):
        self._current = kwargs["calendarId"]
        self.calls.append(self._current)
        return self

    def execute(self):
        return {"items": self.items_by_cal.get(self._current, [])}


class _FakeServiceMultiCalendar:
    def __init__(self, events_api):
        self.events_api = events_api

    def events(self):
        return self.events_api


def _event(summary: str) -> dict:
    return {
        "summary": summary,
        "start": {"dateTime": "2026-08-10T09:00:00+02:00"},
        "end": {"dateTime": "2026-08-10T10:00:00+02:00"},
    }


@patch("backend.state.store.data_store")
def test_get_events_for_day_queries_preference_calendar_ids(mock_data_store):
    mock_data_store.preferences = {
        "planning_calendar_sources": [{"id": "fac@x.com", "label": "Fac"}]
    }
    events_api = _FakeEventsMultiCalendar({"fac@x.com": [_event("Sémio")], "primary": []})
    service = GoogleCalendarService()
    service.service = _FakeServiceMultiCalendar(events_api)

    events = asyncio.run(service.get_events_for_day(datetime.date(2026, 8, 10)))

    assert "fac@x.com" in events_api.calls
    assert events[0]["_synapse_source_label"] == "Fac"


@patch("backend.state.store.data_store")
def test_get_events_for_day_deduplicates_id_present_in_env_and_preferences(mock_data_store, monkeypatch):
    mock_data_store.preferences = {
        "planning_calendar_sources": [{"id": "fac@x.com", "label": "Fac"}]
    }
    monkeypatch.setattr(app_settings.settings, "google_calendar_ids", "fac@x.com")
    events_api = _FakeEventsMultiCalendar({"fac@x.com": [], "primary": []})
    service = GoogleCalendarService()
    service.service = _FakeServiceMultiCalendar(events_api)

    asyncio.run(service.get_events_for_day(datetime.date(2026, 8, 10)))

    assert events_api.calls.count("fac@x.com") == 1
    monkeypatch.setattr(app_settings.settings, "google_calendar_ids", "")


@patch("backend.state.store.data_store")
def test_get_events_for_day_leaves_unlabeled_events_with_empty_source_label(mock_data_store):
    mock_data_store.preferences = {}
    events_api = _FakeEventsMultiCalendar({"primary": [_event("Perso")]})
    service = GoogleCalendarService()
    service.service = _FakeServiceMultiCalendar(events_api)

    events = asyncio.run(service.get_events_for_day(datetime.date(2026, 8, 10)))

    assert events[0]["_synapse_source_label"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_planning_calendar_actions.py -v -k get_events_for_day_queries_preference or get_events_for_day_deduplicates or get_events_for_day_leaves_unlabeled`
Expected: FAIL — `KeyError: '_synapse_source_label'` (la clé n'existe pas encore) pour les trois nouveaux tests.

- [ ] **Step 3: Write the implementation**

Dans `backend/core/google/calendar_service.py`, remplacer les lignes 142-150 par :

```python
        # Calendriers à interroger : primary + IDs configurés (.env) + IDs configurés (Paramètres)
        from backend.config.settings import settings as _cfg
        from backend.state.store import data_store as _store
        from backend.core.planning.calendar_sources import list_calendar_sources as _list_calendar_sources

        configured_ids = _cfg.get_calendar_ids()
        preference_sources = _list_calendar_sources(_store.preferences)
        source_labels: dict[str, str] = {s["id"]: s["label"] for s in preference_sources if s["label"]}

        seen_ids: set[str] = set()
        calendar_ids: list[str] = []
        for cid in ["primary"] + configured_ids + [s["id"] for s in preference_sources]:
            if cid not in seen_ids:
                seen_ids.add(cid)
                calendar_ids.append(cid)
```

Puis, juste après `items = events_result.get('items', [])` (ligne 165 dans l'état relu), ajouter l'étiquetage avant le bloc de correctif « Agenda FAC » existant :

```python
                items = events_result.get('items', [])

                label = source_labels.get(cal_id, "")
                for event in items:
                    event["_synapse_source_label"] = label

                # FIX: Apply +4h offset for "Agenda FAC" (User reported 4h early events)
```

(Le reste du bloc « Agenda FAC », le `except`, et le tri final par `startTime` ne changent pas.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_planning_calendar_actions.py -v`
Expected: 9 passed (6 tests existants — dont 2 issus du même test paramétré — + 3 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add backend/core/google/calendar_service.py tests/test_planning_calendar_actions.py
git commit -m "feat: merge preference-based calendar IDs and label fetched events"
```

---

## Task 3: Panneau Paramètres pour gérer les calendriers

**Files:**
- Create: `frontend/components/calendar_sources_panel.py`
- Modify: `frontend/pages/settings_cockpit.py:45-46` (imports) et `:134-136` (insertion de la section)
- Test: `tests/test_calendar_sources_panel.py`

**Interfaces:**
- Consumes: `list_calendar_sources`, `add_calendar_source`, `remove_calendar_source` (Task 1), `data_store` (`backend/state/store.py`).
- Produces: `render(container: ui.element) -> None` (même signature que `dp_coverage_panel.render`, `frontend/components/dp_coverage_panel.py:93`), appelé depuis `settings_cockpit.py`.

Avant de modifier, relire l'état exact de `frontend/pages/settings_cockpit.py` (vérifié au 2026-08-09) :

```
41	from backend.state.store import data_store
42	from backend.config.settings import settings
43	from backend.core.uness import import_service
44	from backend.core.lisa import item_service
45	from frontend.components.uness_diagnostic_panel import render as render_uness_diagnostics
46	from frontend.components.dp_coverage_panel import render as render_dp_coverage
```

```
123	        ui.label("CONNEXIONS").classes("se-label")
124	        with ui.element("div").classes("se-list"):
125	            for name, ok, status_label in _connection_rows():
...
133	                    ui.label(name).classes("se-name")
134	                    ui.label(status_label).classes("se-status")
135	
136	        ui.label("APPARENCE").classes("se-label")
```

- [ ] **Step 1: Write the failing test**

Créer `tests/test_calendar_sources_panel.py` :

```python
import frontend.components.calendar_sources_panel as panel


def test_display_rows_uses_label_when_present():
    rows = panel._display_rows([{"id": "abc@x.com", "label": "Fac"}])
    assert rows == [{"id": "abc@x.com", "display_label": "Fac"}]


def test_display_rows_falls_back_to_id_when_label_is_empty():
    rows = panel._display_rows([{"id": "abc@x.com", "label": ""}])
    assert rows == [{"id": "abc@x.com", "display_label": "abc@x.com"}]


def test_display_rows_preserves_order():
    sources = [{"id": "a@x.com", "label": "A"}, {"id": "b@x.com", "label": "B"}]
    rows = panel._display_rows(sources)
    assert [row["id"] for row in rows] == ["a@x.com", "b@x.com"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_calendar_sources_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'frontend.components.calendar_sources_panel'`

- [ ] **Step 3: Write the implementation**

Créer `frontend/components/calendar_sources_panel.py` :

```python
"""Panneau de gestion des calendriers Google supplémentaires (Planning)."""

from __future__ import annotations

from nicegui import ui

from backend.core.planning.calendar_sources import (
    add_calendar_source,
    list_calendar_sources,
    remove_calendar_source,
)
from backend.state.store import data_store

_CSS = """
.cs-row { display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px solid var(--border); }
.cs-row:last-child { border-bottom:none; }
.cs-label { font-size:12.5px; color:var(--text); flex:0 0 auto; }
.cs-id { font-family:var(--font-mono); font-size:11px; color:var(--text-muted); flex:1 1 auto;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.cs-empty { padding:10px 0; color:var(--text-dim); font-size:12px; font-style:italic; }
"""


def _display_rows(sources: list[dict]) -> list[dict]:
    """Lignes prêtes à l'affichage : label, ou l'ID si le label est vide."""
    return [{"id": s["id"], "display_label": s["label"] or s["id"]} for s in sources]


def render(container: ui.element) -> None:
    with container:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        ui.label("CALENDRIERS").classes("se-label")
        ui.label(
            "Calendriers Google supplémentaires affichés dans la grille Planning, "
            "en plus du calendrier principal."
        ).classes("se-appearance-sub")

        rows_container = ui.column().classes("w-full gap-0 mt-2")

        def _sources() -> list[dict]:
            return list_calendar_sources(data_store.preferences)

        def _redraw() -> None:
            rows_container.clear()
            sources = _sources()
            with rows_container:
                if not sources:
                    ui.label("Aucun calendrier supplémentaire configuré.").classes("cs-empty")
                for row in _display_rows(sources):
                    with ui.element("div").classes("cs-row"):
                        ui.label(row["display_label"]).classes("cs-label")
                        ui.label(row["id"]).classes("cs-id")
                        ui.button(
                            icon="close",
                            on_click=lambda cid=row["id"]: _remove(cid),
                        ).props("flat round dense size=sm color=grey")

        def _remove(calendar_id: str) -> None:
            updated = remove_calendar_source(_sources(), calendar_id)
            data_store.set_preference("planning_calendar_sources", updated)
            _redraw()
            ui.notify("Calendrier retiré", type="positive")

        with ui.row().classes("w-full gap-2 mt-3 items-end"):
            id_input = ui.input(label="ID du calendrier").props("outlined dense").classes("flex-1")
            label_input = ui.input(label="Label (optionnel)").props("outlined dense").classes("flex-1")

            def _add() -> None:
                try:
                    updated = add_calendar_source(_sources(), id_input.value or "", label_input.value or "")
                except ValueError as exc:
                    ui.notify(str(exc), type="negative")
                    return
                data_store.set_preference("planning_calendar_sources", updated)
                id_input.value = ""
                label_input.value = ""
                _redraw()
                ui.notify("Calendrier ajouté", type="positive")

            ui.button("Ajouter", on_click=_add).props("unelevated color=indigo no-caps dense")

        _redraw()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_calendar_sources_panel.py -v`
Expected: 3 passed

- [ ] **Step 5: Wire the panel into Settings — write the failing wiring test**

Ajouter à `tests/test_calendar_sources_panel.py` :

```python
from pathlib import Path


def test_settings_cockpit_renders_the_calendar_sources_panel():
    source = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")

    assert "render_calendar_sources" in source
    assert "calendar_sources_panel import render as render_calendar_sources" in source
```

- [ ] **Step 6: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_calendar_sources_panel.py -v -k settings_cockpit_renders`
Expected: FAIL — `assert "render_calendar_sources" in source` is False

- [ ] **Step 7: Wire the panel**

Dans `frontend/pages/settings_cockpit.py`, ajouter l'import après la ligne 46 :

```python
from frontend.components.calendar_sources_panel import render as render_calendar_sources
```

Puis insérer l'appel entre les lignes 134 et 136 (juste après la boucle CONNEXIONS, avant la section APPARENCE) :

```python
                    ui.label(status_label).classes("se-status")

        render_calendar_sources(ui.column().classes("w-full"))

        ui.label("APPARENCE").classes("se-label")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_calendar_sources_panel.py -v`
Expected: 4 passed

- [ ] **Step 9: Commit**

```bash
git add frontend/components/calendar_sources_panel.py frontend/pages/settings_cockpit.py tests/test_calendar_sources_panel.py
git commit -m "feat: add Settings panel to manage additional Google calendars"
```

---

## Task 4: Étiquette de source dans la grille Planning

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:67-79` (ajout de la fonction), `:458-465` (utilisation dans `_draw_day`)
- Test: `tests/test_planning_navigation.py`

**Interfaces:**
- Consumes: événements portant `_synapse_source_label: str` (Task 2).
- Produces: `event_display_title(ev: dict) -> str`, exportée depuis `frontend/pages/planning_cockpit.py` au même niveau que `block_target`.

Avant de modifier, relire l'état exact de `frontend/pages/planning_cockpit.py` (vérifié au 2026-08-09) :

```
67	def block_target(slot_type: str, course_id: str | None) -> str | None:
...
79	    return f"/cours/{course_id}"
80	
81	_CSS = """
```

```
458	            for ev in events:
459	                summary = ev.get("summary") or "Événement"
460	                dur = _event_duration_min(ev)
461	                with ui.element("div").classes("pl-block pl-block-event").tooltip(summary):
462	                    ui.label(summary).classes("pl-block-title")
463	                    if dur:
464	                        h, m = divmod(dur, 60)
465	                        ui.label(f"{h}h{m:02d}" if h else f"{dur} min").classes("pl-block-sub")
```

- [ ] **Step 1: Write the failing tests**

Ajouter à `tests/test_planning_navigation.py` :

```python
from frontend.pages.planning_cockpit import event_display_title


def test_event_display_title_prefixes_labeled_source():
    ev = {"summary": "Cours de sémiologie", "_synapse_source_label": "Fac"}
    assert event_display_title(ev) == "Fac · Cours de sémiologie"


def test_event_display_title_returns_summary_when_unlabeled():
    ev = {"summary": "Rendez-vous perso", "_synapse_source_label": ""}
    assert event_display_title(ev) == "Rendez-vous perso"


def test_event_display_title_defaults_missing_summary():
    ev = {"_synapse_source_label": ""}
    assert event_display_title(ev) == "Événement"


def test_day_events_use_the_display_title_helper():
    source = Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")

    assert "event_display_title(ev)" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_planning_navigation.py -v -k event_display_title or day_events_use_the_display_title`
Expected: FAIL — `ImportError: cannot import name 'event_display_title'`

- [ ] **Step 3: Write the implementation**

Dans `frontend/pages/planning_cockpit.py`, ajouter après `block_target` (après la ligne 79, avant `_CSS = """`) :

```python

def event_display_title(ev: dict) -> str:
    """Titre affiché pour un événement Calendar, préfixé par sa source si étiquetée."""
    summary = ev.get("summary") or "Événement"
    label = (ev.get("_synapse_source_label") or "").strip()
    return f"{label} · {summary}" if label else summary

```

Puis remplacer les lignes 458-465 (boucle `for ev in events`) par :

```python
            for ev in events:
                title = event_display_title(ev)
                dur = _event_duration_min(ev)
                with ui.element("div").classes("pl-block pl-block-event").tooltip(title):
                    ui.label(title).classes("pl-block-title")
                    if dur:
                        h, m = divmod(dur, 60)
                        ui.label(f"{h}h{m:02d}" if h else f"{dur} min").classes("pl-block-sub")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_planning_navigation.py -v`
Expected: 8 passed (4 tests existants + 4 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/planning_cockpit.py tests/test_planning_navigation.py
git commit -m "feat: show calendar source label on planning grid events"
```

---

## Task 5: Vérification finale

- [ ] **Step 1: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `1194 passed` (1172 baseline + 11 nouveaux Task 1 + 3 nouveaux Task 2 + 4 nouveaux Task 3 + 4 nouveaux Task 4, aucune régression). Si le total diffère, identifier si c'est un test préexistant qui encodait un ancien comportement volontairement changé (cf. convention des chantiers précédents) avant de le corriger.

- [ ] **Step 2: Mettre à jour le suivi**

Mettre à jour `docs/UI_REFONTE_ETAT_DES_LIEUX.md` section 6 (chantier D) avec les hash de commit des 4 tâches et le nouveau total de tests, en suivant le format déjà utilisé pour les chantiers A/B/C.
