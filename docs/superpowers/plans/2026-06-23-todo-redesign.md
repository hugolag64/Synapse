# To Do — Refonte Complète : Plan d'Implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refaire la page `/todo` de Synapse en une timeline verticale (Routine / Ajouté / Note) avec navigation fluide par dates, routine locale SQLite instantanée, et skeleton UI pour les données Notion/GCal.

**Architecture:** La Routine (5 checkboxes fixes) est stockée en SQLite local (zéro latence). Les données Notion + GCal sont chargées en parallèle avec `asyncio.gather` derrière un skeleton UI animé. Les mises à jour de checkboxes sont optimistes (UI immédiate, sync réseau en arrière-plan). La page est une colonne scrollable sans tabs.

**Tech Stack:** NiceGUI, SQLite (`backend/core/reviews/local_store.py` — DB existante `data/synapse_local.db`), Notion API, Google Calendar API, `asyncio`, Tailwind CSS via classes NiceGUI, `clinical-black.css` existant.

## Global Constraints

- Cohérence visuelle avec `clinical-black.css` et polices Inter/Plus Jakarta Sans existantes
- Dark mode : toutes les classes couleur ont leur variante `dark:`
- Optimistic updates sur tous les toggles (pas d'attente réseau avant mise à jour UI)
- `props('dense')` sur tous les inputs et checkboxes
- Transitions CSS : `transition-all duration-200` pour les checkboxes, `duration-300` pour les cartes
- Pas de nouveau fichier SQLite — tout passe par `local_store._conn()` et `init_db()` existants
- Fonctions UI privées préfixées `_render_` ou `_load_`

---

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `backend/core/reviews/local_store.py` | **Modifier** : ajouter tables `routine_items` + `routine_checks` dans `init_db()`, migration `_migrate_routine_tables()`, et 3 fonctions CRUD publiques |
| `frontend/theme.py` | **Modifier** : ajouter `('To Do', '/todo')` dans `_NAV_ITEMS` + `'Suivi Quotidien': 'To Do'` dans `_TITLE_TO_NAV` |
| `frontend/pages/todo.py` | **Réécriture complète** : `todo_page()` + helpers `_render_*` + `_load_*` + `_build_course_list()` |
| `tests/test_local_store.py` | **Modifier** : ajouter `TestRoutineChecks` |
| `tests/test_todo_logic.py` | **Créer** : tests de `_build_course_list()` (pure function) |

---

## Task 1 — SQLite : Tables Routine + CRUD

**Files:**
- Modify: `backend/core/reviews/local_store.py` (sections `init_db()` et fin de fichier)
- Test: `tests/test_local_store.py`

**Interfaces:**
- Produces:
  - `get_routine_items() -> list[str]` — noms des items actifs triés par position
  - `get_routine_checks(date_str: str) -> dict[str, bool]` — état coché par item pour une date
  - `set_routine_check(date_str: str, item_name: str, checked: bool) -> None` — upsert

---

- [ ] **Step 1 : Écrire les tests**

Dans `tests/test_local_store.py`, ajouter à la fin du fichier :

```python
# ── Tests Routine ─────────────────────────────────────────────────────────────

class TestRoutineChecks:
    def test_get_routine_items_defaults(self):
        items = ls.get_routine_items()
        assert items == ['Révision', 'QCM', 'Sport', 'Musique', 'Anki']

    def test_get_routine_checks_empty(self):
        checks = ls.get_routine_checks('2026-06-23')
        assert checks == {}

    def test_set_and_get_check_true(self):
        ls.set_routine_check('2026-06-23', 'Sport', True)
        assert ls.get_routine_checks('2026-06-23')['Sport'] is True

    def test_set_check_idempotent_update(self):
        ls.set_routine_check('2026-06-23', 'Anki', True)
        ls.set_routine_check('2026-06-23', 'Anki', False)
        assert ls.get_routine_checks('2026-06-23')['Anki'] is False

    def test_checks_isolated_by_date(self):
        ls.set_routine_check('2026-06-23', 'Sport', True)
        assert 'Sport' not in ls.get_routine_checks('2026-06-24')

    def test_get_routine_items_excludes_inactive(self):
        with ls._conn() as con:
            con.execute("UPDATE routine_items SET active = 0 WHERE name = 'Anki'")
        items = ls.get_routine_items()
        assert 'Anki' not in items
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
pytest tests/test_local_store.py::TestRoutineChecks -v
```

Expected : `AttributeError: module 'backend.core.reviews.local_store' has no attribute 'get_routine_items'`

- [ ] **Step 3 : Ajouter les tables dans `init_db()`**

Dans `local_store.py`, dans le `executescript` de `init_db()`, ajouter avant la fermeture `""")` :

```python
        -- ── Routine quotidienne locale ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS routine_items (
            name     TEXT    PRIMARY KEY,
            position INTEGER NOT NULL DEFAULT 0,
            active   INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS routine_checks (
            date      TEXT    NOT NULL,
            item_name TEXT    NOT NULL,
            checked   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, item_name)
        );
```

- [ ] **Step 4 : Ajouter la migration et l'appel dans `init_db()`**

Après la ligne `_migrate_pending_gap_proposals()` dans `init_db()`, ajouter :

```python
    _migrate_routine_tables()
```

Puis définir la fonction de migration (à la fin du fichier, avant les autres `_migrate_*` ou en queue) :

```python
def _migrate_routine_tables() -> None:
    """Insère les items de routine par défaut si la table est vide."""
    with _conn() as con:
        count = con.execute("SELECT COUNT(*) FROM routine_items").fetchone()[0]
        if count == 0:
            con.executemany(
                "INSERT OR IGNORE INTO routine_items (name, position) VALUES (?, ?)",
                [('Révision', 0), ('QCM', 1), ('Sport', 2), ('Musique', 3), ('Anki', 4)],
            )
```

- [ ] **Step 5 : Ajouter les 3 fonctions CRUD publiques**

À la fin de `local_store.py` (section API publique) :

```python
# ── API publique — Routine quotidienne ───────────────────────────────────────

def get_routine_items() -> list[str]:
    """Retourne les noms des items de routine actifs, triés par position."""
    rows = _conn().execute(
        "SELECT name FROM routine_items WHERE active = 1 ORDER BY position"
    ).fetchall()
    return [r["name"] for r in rows]


def get_routine_checks(date_str: str) -> dict[str, bool]:
    """Retourne {item_name: checked} pour une date ('YYYY-MM-DD')."""
    rows = _conn().execute(
        "SELECT item_name, checked FROM routine_checks WHERE date = ?",
        (date_str,),
    ).fetchall()
    return {r["item_name"]: bool(r["checked"]) for r in rows}


def set_routine_check(date_str: str, item_name: str, checked: bool) -> None:
    """Upsert l'état coché d'un item de routine pour une date donnée."""
    with _conn() as con:
        con.execute(
            "INSERT INTO routine_checks (date, item_name, checked) VALUES (?, ?, ?) "
            "ON CONFLICT(date, item_name) DO UPDATE SET checked = excluded.checked",
            (date_str, item_name, 1 if checked else 0),
        )
```

- [ ] **Step 6 : Vérifier que les tests passent**

```
pytest tests/test_local_store.py::TestRoutineChecks -v
```

Expected : 6 × PASSED

- [ ] **Step 7 : Commit**

```bash
git add backend/core/reviews/local_store.py tests/test_local_store.py
git commit -m "feat: add routine_items/routine_checks SQLite tables with CRUD"
```

---

## Task 2 — Nav + Shell de la page + Header sticky

**Files:**
- Modify: `frontend/theme.py` (lignes `_NAV_ITEMS` et `_TITLE_TO_NAV`)
- Modify: `frontend/pages/todo.py` (remplacement complet du contenu)

**Interfaces:**
- Consumes: `local_store.get_routine_items()`, `local_store.get_routine_checks()`, `local_store.set_routine_check()`
- Produces: `todo_page()` — fonction async de page NiceGUI ; `_render_content(container, date_obj, progress_state, refresh_progress)` — fonction async interne

---

- [ ] **Step 1 : Mettre à jour la navigation dans `theme.py`**

Dans `_NAV_ITEMS`, ajouter `('To Do', '/todo')` entre `'Planning'` et `'Externat'` :

```python
_NAV_ITEMS = [
    ('Dashboard',   '/'),
    ('Collèges',    '/colleges'),
    ('QCM',         '/qcm'),
    ('Lacunes',     '/lacunes'),
    ('Progression', '/stats'),
    ('Planning',    '/planning'),
    ('To Do',       '/todo'),       # ← ajouté
    ('Externat',    '/externat'),
]
```

Dans `_TITLE_TO_NAV`, ajouter :

```python
    'Suivi Quotidien': 'To Do',
```

- [ ] **Step 2 : Réécrire `todo.py` — imports + `todo_page()` + header sticky**

Remplacer l'intégralité du fichier `frontend/pages/todo.py` par :

```python
from nicegui import ui
from backend.core.notion.service import notion_service
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import local_store
from backend.state.store import data_store
from frontend.theme import frame
import asyncio
import datetime

_MONTHS = ['jan.','fév.','mars','avr.','mai','juin','juil.','août','sep.','oct.','nov.','déc.']
_DAYS   = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']


def _fmt_date(d: datetime.date) -> str:
    return f"{_DAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]} {d.year}"


async def todo_page():
    with frame("Suivi Quotidien"):
        state          = {'date': datetime.date.today()}
        # Chaque entrée = [total, done] — isolé par bloc pour éviter le double-comptage
        # lors des re-renders partiels (ex: ajout d'une tâche libre)
        progress_state = {'routine': [0, 0], 'ajout': [0, 0]}

        # ── Header sticky ──────────────────────────────────────────────────────
        with ui.element('div').style(
            'position: sticky; top: 0; z-index: 10;'
        ).classes(
            'bg-white/90 dark:bg-slate-900/90 backdrop-blur-md '
            'border-b border-slate-200 dark:border-slate-700 '
            'px-4 pt-3 pb-2 w-full'
        ):
            with ui.row().classes('w-full items-center gap-1'):
                btn_prev = ui.button(icon='chevron_left').props('flat round dense')

                with ui.row().classes('items-center gap-1 flex-1 justify-center'):
                    btn_hier = ui.button('Hier').props('flat dense size=sm rounded')
                    btn_auj  = ui.button("Auj.").props('flat dense size=sm rounded')
                    btn_dem  = ui.button('Demain').props('flat dense size=sm rounded')

                date_btn = ui.button('').props('flat dense').classes(
                    'font-semibold text-slate-700 dark:text-slate-100 min-w-[190px] text-sm')

                btn_next = ui.button(icon='chevron_right').props('flat round dense')

            progress_bar   = ui.linear_progress(value=0, show_value=False).classes(
                'h-1.5 rounded-full mt-2 mb-0')
            progress_label = ui.label('0 / 0 · 0%').classes(
                'text-xs text-slate-400 text-right mt-0.5')

        # ── Zone de contenu ────────────────────────────────────────────────────
        content = ui.column().classes('w-full px-4 py-5 gap-6')

        # ── Helpers ────────────────────────────────────────────────────────────
        def _refresh_progress():
            t = sum(b[0] for b in progress_state.values())
            d = sum(b[1] for b in progress_state.values())
            p = d / t if t > 0 else 0
            progress_bar.set_value(p)
            progress_label.set_text(f"{d} / {t} · {int(p * 100)}%")

        def _update_header():
            today = datetime.date.today()
            d     = state['date']
            date_btn.set_text(_fmt_date(d))
            for btn, delta in [(btn_hier, -1), (btn_auj, 0), (btn_dem, 1)]:
                if d == today + datetime.timedelta(days=delta):
                    btn.props(remove='flat').props('unelevated color=primary size=sm rounded')
                else:
                    btn.props(remove='unelevated color=primary').props('flat size=sm rounded')

        async def _render_day(date_obj: datetime.date):
            state['date'] = date_obj
            for k in progress_state:
                progress_state[k] = [0, 0]
            _update_header()
            _refresh_progress()
            await _render_content(content, date_obj, progress_state, _refresh_progress)

        # ── Bindings ───────────────────────────────────────────────────────────
        btn_prev.on('click', lambda: asyncio.create_task(
            _render_day(state['date'] - datetime.timedelta(days=1))))
        btn_next.on('click', lambda: asyncio.create_task(
            _render_day(state['date'] + datetime.timedelta(days=1))))
        btn_hier.on('click', lambda: asyncio.create_task(
            _render_day(datetime.date.today() - datetime.timedelta(days=1))))
        btn_auj.on('click',  lambda: asyncio.create_task(
            _render_day(datetime.date.today())))
        btn_dem.on('click',  lambda: asyncio.create_task(
            _render_day(datetime.date.today() + datetime.timedelta(days=1))))

        def _open_date_picker():
            with ui.dialog() as dlg, ui.card().classes('items-center gap-3 p-4'):
                dp = ui.date(value=state['date'].isoformat()).props('no-unset')
                async def _confirm():
                    if dp.value:
                        dlg.close()
                        await _render_day(datetime.date.fromisoformat(dp.value))
                ui.button('OK', on_click=_confirm).props('unelevated color=primary rounded')
            dlg.open()

        date_btn.on('click', _open_date_picker)

        _update_header()
        ui.timer(0.1, lambda: asyncio.create_task(
            _render_day(datetime.date.today())), once=True)
```

- [ ] **Step 3 : Vérifier manuellement**

Lancer l'app (`python main.py`), naviguer vers `/todo`. Vérifier :
- "To Do" apparaît dans la barre de navigation
- La page s'affiche (vide — le contenu sera ajouté aux tâches suivantes)
- Le header sticky reste visible en scrollant
- Les boutons Hier / Auj. / Demain et les flèches ◀ ▶ sont présents
- Le clic sur la date ouvre un date picker

- [ ] **Step 4 : Commit**

```bash
git add frontend/theme.py frontend/pages/todo.py
git commit -m "feat: todo page shell — sticky header, date navigation, nav link"
```

---

## Task 3 — Bloc Routine + `_render_content`

**Files:**
- Modify: `frontend/pages/todo.py`

**Interfaces:**
- Consumes: `local_store.get_routine_items()`, `local_store.get_routine_checks(date_str)`, `local_store.set_routine_check(date_str, item_name, checked)`
- Produces:
  - `_render_content(container, date_obj, progress_state, refresh_progress)` — async, orchestre les 3 blocs
  - `_render_routine_block(container, date_str, progress_state, refresh_progress)` — synchrone, SQLite only

---

- [ ] **Step 1 : Ajouter `_render_content` et `_render_routine_block` dans `todo.py`**

Ajouter ces deux fonctions **après** `todo_page()` dans le fichier :

```python
async def _render_content(
    container: ui.column,
    date_obj: datetime.date,
    progress_state: dict,
    refresh_progress,
) -> None:
    container.clear()
    if container.is_deleted:
        return
    date_str = date_obj.isoformat()
    is_past  = date_obj < datetime.date.today()

    with container:
        # Routine : SQLite, instantané
        routine_col = ui.column().classes('w-full')
        _render_routine_block(routine_col, date_str, progress_state, refresh_progress)

        # Ajouté + Note : chargés en réseau (tâches 4 et 5)
        ajout_col = ui.column().classes('w-full')
        note_col  = ui.column().classes('w-full')

        asyncio.create_task(
            _load_and_render_network_blocs(
                ajout_col, note_col, date_obj, is_past,
                progress_state, refresh_progress,
            )
        )


def _render_routine_block(
    container: ui.column,
    date_str: str,
    progress_state: dict,
    refresh_progress,
) -> None:
    items  = local_store.get_routine_items()
    checks = local_store.get_routine_checks(date_str)

    progress_state['routine'] = [
        len(items),
        sum(1 for name in items if checks.get(name, False)),
    ]

    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-sky-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('ROUTINE').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')
                with ui.element('div').classes(
                        'grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1'):
                    for name in items:
                        checked = checks.get(name, False)

                        def _on_toggle(e, item_name=name):
                            progress_state['routine'][1] += 1 if e.value else -1
                            refresh_progress()
                            local_store.set_routine_check(date_str, item_name, e.value)

                        ui.checkbox(name, value=checked, on_change=_on_toggle).props('dense').classes(
                            'text-slate-700 dark:text-slate-200 transition-opacity duration-200')

    refresh_progress()
```

- [ ] **Step 2 : Ajouter un stub pour `_load_and_render_network_blocs`** (pour que le code tourne avant la tâche 4)

```python
async def _load_and_render_network_blocs(
    ajout_col, note_col, date_obj, is_past, progress_state, refresh_progress
) -> None:
    # Stub — implémenté en Task 4
    with ajout_col:
        ui.label('Chargement…').classes('text-sm text-slate-400 italic')
    with note_col:
        ui.label('').classes('')
```

- [ ] **Step 3 : Vérifier manuellement**

Naviguer vers `/todo`. Vérifier :
- Le bloc ROUTINE s'affiche immédiatement (pas de spinner)
- Les 5 checkboxes sont présentes (Révision, QCM, Sport, Musique, Anki)
- Cocher/décocher met à jour la barre de progression en temps réel
- Naviguer vers une autre date puis revenir : l'état est persisté

- [ ] **Step 4 : Commit**

```bash
git add frontend/pages/todo.py
git commit -m "feat: todo bloc Routine — SQLite local, optimistic toggle, progress bar"
```

---

## Task 4 — Chargement réseau + Bloc Ajouté

**Files:**
- Modify: `frontend/pages/todo.py`
- Create: `tests/test_todo_logic.py`

**Interfaces:**
- Consumes: `notion_service.get_daily_task_by_date()`, `notion_service.get_daily_reviewed_courses()`, `notion_service.get_daily_manual_revision_courses()`, `calendar_service.get_events_for_day()`, `notion_service.add_dynamic_task()`, `notion_service.toggle_dynamic_task()`, `notion_service.add_course_to_daily_manual()`, `notion_service.create_daily_task()`, `notion_service.increment_lecture_college()`, `notion_service.mark_manual_revision_done()`, `notion_service.add_course_to_daily_reviewed()`
- Produces:
  - `_build_course_list(events, manual_titles, all_courses) -> list[dict]` — pure function
  - `_render_skeleton_bloc(container, marker_css, title)` — synchrone
  - `_load_and_render_network_blocs(...)` — async, remplace le stub
  - `_render_ajout_block(...)` — async
  - `_render_course_item(...)` — synchrone
  - `_open_add_course_dialog(date_obj, task)` — synchrone

---

- [ ] **Step 1 : Écrire les tests pour `_build_course_list`**

Créer `tests/test_todo_logic.py` :

```python
"""Tests unitaires — logique pure de la page To Do."""
import pytest
from unittest.mock import MagicMock


class _MockCourse:
    def __init__(self, id, title, college=True, item_number=None, nb_lectures=0):
        self.id          = id
        self.title       = title
        self.college     = college
        self.item_number = item_number
        self.nb_lectures = nb_lectures


@pytest.fixture
def courses():
    return [
        _MockCourse('c1', 'Insuffisance cardiaque', item_number='232'),
        _MockCourse('c2', 'Diabète', item_number='245'),
        _MockCourse('c3', 'Non collège', college=False),
    ]


# Import after fixture to avoid NiceGUI import errors at module level
from frontend.pages.todo import _build_course_list


class TestBuildCourseList:
    def test_empty_inputs(self, courses):
        assert _build_course_list([], [], courses) == []

    def test_gcal_event_matched(self, courses):
        events = [{'summary': 'Collège — Insuffisance cardiaque'}]
        result = _build_course_list(events, [], courses)
        assert len(result) == 1
        assert result[0]['type'] == 'gcal'
        assert result[0]['course'].id == 'c1'

    def test_gcal_revision_manuelle_matched(self, courses):
        events = [{'summary': 'Révision Manuelle Diabète'}]
        result = _build_course_list(events, [], courses)
        assert len(result) == 1
        assert result[0]['course'].id == 'c2'

    def test_manual_notion_matched(self, courses):
        result = _build_course_list([], ['Diabète'], courses)
        assert len(result) == 1
        assert result[0]['type'] == 'notion_manual'
        assert result[0]['course'].id == 'c2'

    def test_no_duplicate_gcal_and_manual(self, courses):
        events = [{'summary': 'Collège — Insuffisance cardiaque'}]
        result = _build_course_list(events, ['Insuffisance cardiaque'], courses)
        assert len(result) == 1  # Pas de doublon

    def test_unmatched_event_ignored(self, courses):
        events = [{'summary': 'Cours magistral de cardiologie'}]
        result = _build_course_list(events, [], courses)
        assert result == []

    def test_multiple_sources(self, courses):
        events = [{'summary': 'Collège — Insuffisance cardiaque'}]
        result = _build_course_list(events, ['Diabète'], courses)
        assert len(result) == 2
        assert result[0]['type'] == 'gcal'
        assert result[1]['type'] == 'notion_manual'
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
pytest tests/test_todo_logic.py -v
```

Expected : `ImportError` ou `AttributeError` — `_build_course_list` n'existe pas encore.

- [ ] **Step 3 : Remplacer le stub `_load_and_render_network_blocs` et ajouter toutes les fonctions**

Remplacer dans `todo.py` le stub `_load_and_render_network_blocs` et ajouter toutes les fonctions suivantes :

```python
def _build_course_list(events, manual_titles, all_courses) -> list[dict]:
    """Pure function — fusionne événements GCal et révisions Notion en une liste unifiée."""
    result = []
    for evt in (events or []):
        summary = evt.get('summary', '')
        if 'Collège' in summary or 'Révision Manuelle' in summary:
            for c in all_courses:
                if c.title in summary:
                    result.append({'course': c, 'type': 'gcal', 'summary': summary})
                    break
    for title in (manual_titles or []):
        c = next((x for x in all_courses if x.title == title), None)
        if c and not any(r['course'].id == c.id for r in result):
            result.append({'course': c, 'type': 'notion_manual', 'summary': title})
    return result


def _render_skeleton_bloc(container: ui.column, marker_css: str, title: str) -> None:
    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes(
                f'w-1 rounded-full {marker_css} self-stretch min-h-[2rem] opacity-30')
            with ui.column().classes('flex-1 gap-2'):
                ui.label(title).classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')
                for w in ['w-3/4', 'w-1/2', 'w-2/3']:
                    ui.element('div').classes(
                        f'h-5 rounded-md animate-pulse bg-slate-200 dark:bg-slate-700 {w}')


async def _load_and_render_network_blocs(
    ajout_col: ui.column,
    note_col: ui.column,
    date_obj: datetime.date,
    is_past: bool,
    progress_state: dict,
    refresh_progress,
) -> None:
    _render_skeleton_bloc(ajout_col, 'bg-violet-500', 'AJOUTÉ')
    _render_skeleton_bloc(note_col,  'bg-amber-500',  'NOTE DU JOUR')

    task, events = await asyncio.gather(
        notion_service.get_daily_task_by_date(date_obj),
        calendar_service.get_events_for_day(date_obj),
    )

    reviewed_titles: list[str] = []
    manual_titles:   list[str] = []
    if task:
        reviewed_titles, manual_titles = await asyncio.gather(
            notion_service.get_daily_reviewed_courses(task.id),
            notion_service.get_daily_manual_revision_courses(task.id),
        )

    if ajout_col.is_deleted or note_col.is_deleted:
        return

    course_items = _build_course_list(events, manual_titles, data_store.cours)

    await _render_ajout_block(
        ajout_col, date_obj, task, course_items,
        reviewed_titles, progress_state, refresh_progress,
    )
    _render_note_block(note_col, task, is_past)
    refresh_progress()


async def _render_ajout_block(
    container: ui.column,
    date_obj: datetime.date,
    task,
    course_items: list[dict],
    reviewed_titles: list[str],
    progress_state: dict,
    refresh_progress,
) -> None:
    dynamic_tasks = task.dynamic_checkboxes if task else {}
    ajout_total = len(course_items) + len(dynamic_tasks)
    ajout_done  = (sum(1 for r in course_items if r['course'].title in reviewed_titles)
                   + sum(1 for d in dynamic_tasks.values() if d['checked']))
    # Écrase (ne cumule pas) pour éviter le double-comptage lors des re-renders
    progress_state['ajout'] = [ajout_total, ajout_done]

    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-violet-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('AJOUTÉ').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')

                # ── Cours ─────────────────────────────────────────────────────
                for item in course_items:
                    _render_course_item(
                        item['course'], item['course'].title in reviewed_titles,
                        item['type'], task, progress_state, refresh_progress,
                    )

                # ── Tâches dynamiques ─────────────────────────────────────────
                for b_id, data in dynamic_tasks.items():
                    async def _toggle_dyn(e, bid=b_id):
                        progress_state['ajout'][1] += 1 if e.value else -1
                        refresh_progress()
                        await notion_service.toggle_dynamic_task(bid, e.value)

                    ui.checkbox(data['text'], value=data['checked'],
                                on_change=_toggle_dyn).props('dense').classes(
                        'text-slate-700 dark:text-slate-200')

                if not course_items and not dynamic_tasks:
                    ui.label('Rien de planifié pour ce jour.').classes(
                        'text-sm text-slate-400 italic')

                # ── Contrôles d'ajout ─────────────────────────────────────────
                with ui.row().classes(
                        'items-center gap-2 mt-2 pt-2 '
                        'border-t border-slate-100 dark:border-slate-800'):
                    ui.button('+ Cours',
                              on_click=lambda: _open_add_course_dialog(date_obj, task)).props(
                        'flat dense').classes(
                        'text-violet-600 dark:text-violet-400 text-sm font-medium')

                    new_task_input = ui.input(placeholder='+ Tâche libre…').props(
                        'borderless dense').classes('flex-1 text-sm text-slate-600 dark:text-slate-300')

                    async def _add_task_free():
                        val = new_task_input.value.strip()
                        if not val or not task:
                            return
                        new_task_input.value = ''
                        if await notion_service.add_dynamic_task(task.id, val):
                            ui.notify('Tâche ajoutée', type='positive')
                            updated = await notion_service.get_daily_task_by_date(date_obj)
                            if updated and not container.is_deleted:
                                await _render_ajout_block(
                                    container, date_obj, updated, course_items,
                                    reviewed_titles, progress_state, refresh_progress,
                                )

                    new_task_input.on('keydown.enter',
                                      lambda: asyncio.create_task(_add_task_free()))
                    ui.button(icon='send',
                              on_click=lambda: asyncio.create_task(_add_task_free())).props(
                        'flat round dense').classes('text-violet-500')


def _render_course_item(
    c,
    is_reviewed: bool,
    source_type: str,
    task,
    progress_state: dict,
    refresh_progress,
) -> None:
    bg = ('bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
          if is_reviewed else
          'bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700')

    with ui.row().classes(
            f'w-full items-center justify-between p-2.5 rounded-xl {bg} '
            f'transition-all duration-300'):
        with ui.column().classes('gap-0.5 flex-1 min-w-0'):
            title_cls = ('text-sm font-medium text-slate-400 line-through'
                         if is_reviewed else
                         'text-sm font-medium text-slate-700 dark:text-slate-200 truncate')
            ui.label(c.title).classes(title_cls)
            badge_color = 'text-blue-400' if source_type == 'gcal' else 'text-violet-400'
            badge_text  = 'GCal' if source_type == 'gcal' else 'Manuel'
            ui.label(badge_text).classes(f'text-xs {badge_color}')

        if is_reviewed:
            ui.icon('check_circle', color='green', size='sm')
        else:
            async def _validate(course=c, s=source_type):
                ui.notify(f'Validation de {course.title}…', type='ongoing')
                await notion_service.increment_lecture_college(course.id, course.nb_lectures)
                if task:
                    if s == 'notion_manual':
                        await notion_service.mark_manual_revision_done(task.id, course.title)
                    else:
                        await notion_service.add_course_to_daily_reviewed(task.id, course.title)
                course.nb_lectures += 1
                progress_state['ajout'][1] += 1
                refresh_progress()
                ui.notify('Validé !', type='positive')

            ui.button(icon='check', on_click=_validate).props('flat round dense').classes(
                'text-green-500').tooltip('Marquer comme révisé')


def _open_add_course_dialog(date_obj: datetime.date, task) -> None:
    college_courses = sorted(
        [c for c in data_store.cours if c.college],
        key=lambda c: (float(c.item_number.replace(',', '.'))
                       if c.item_number else 999999),
    )
    options = {
        c.id: (f"ITEM {c.item_number} — " if c.item_number else '') + c.title
        for c in college_courses
    }
    sel = {'id': None}

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-4 gap-3'):
        ui.label('Programmer une révision').classes(
            'text-base font-bold text-slate-700 dark:text-slate-200')
        ui.label(f"Date : {date_obj.strftime('%d/%m/%Y')}").classes('text-sm text-slate-400')
        ui.select(options=options, label='Cours (ITEM XXX)',
                  with_input=True).bind_value(sel, 'id').props(
            'outlined use-input clearable').classes('w-full')

        async def _confirm():
            if not sel['id']:
                ui.notify('Sélectionnez un cours', type='warning')
                return
            dlg.close()
            c = next((x for x in college_courses if x.id == sel['id']), None)
            if not c:
                return
            target = task or await notion_service.get_daily_task_by_date(date_obj)
            if not target:
                created = await notion_service.create_daily_task(
                    date_obj, f"Suivi - {date_obj.strftime('%d/%m/%Y')}")
                if created:
                    target = await notion_service.get_daily_task_by_date(date_obj)
            if target:
                ok = await notion_service.add_course_to_daily_manual(target.id, c.title)
                ui.notify('Programmé !' if ok else 'Erreur Notion',
                          type='positive' if ok else 'negative')
            else:
                ui.notify('Impossible de créer la fiche', type='negative')

        with ui.row().classes('w-full justify-end gap-2 mt-2'):
            ui.button('Annuler', on_click=dlg.close).props('flat')
            ui.button('Programmer', on_click=_confirm).props('unelevated color=primary rounded')

    dlg.open()
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_todo_logic.py -v
```

Expected : 7 × PASSED

- [ ] **Step 5 : Vérifier manuellement**

Naviguer vers `/todo`. Vérifier :
- Skeleton violet animé apparaît pendant le chargement Notion/GCal
- Les cours du jour s'affichent (si des events GCal ou révisions manuelles existent)
- Cocher un cours l'anime et met à jour la barre de progression
- `+ Cours` ouvre la dialog avec le sélecteur pré-daté
- `+ Tâche libre` : taper un texte + Entrée → tâche ajoutée + rechargement
- Naviguer vers Demain → skeleton → contenu de demain

- [ ] **Step 6 : Commit**

```bash
git add frontend/pages/todo.py tests/test_todo_logic.py
git commit -m "feat: todo bloc Ajouté — skeleton UI, cours GCal/Notion, tâches libres, dialog cours"
```

---

## Task 5 — Bloc Note + vérification finale

**Files:**
- Modify: `frontend/pages/todo.py`

**Interfaces:**
- Consumes: `notion_service.add_daily_comment(task_id, text)`, `task` (objet Notion daily)
- Produces: `_render_note_block(container, task, is_past)` — synchrone

---

- [ ] **Step 1 : Ajouter `_render_note_block` dans `todo.py`**

```python
def _render_note_block(container: ui.column, task, is_past: bool) -> None:
    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-amber-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('NOTE DU JOUR').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')

                if is_past:
                    ui.label('Journée passée — notes visibles dans Notion.').classes(
                        'text-sm italic text-slate-400')
                    return

                note_ta = ui.textarea(
                    placeholder='Comment s\'est passée la journée ?'
                ).props('outlined rows=2 autogrow').classes('w-full text-sm')

                save_row = ui.row().classes('w-full justify-end hidden')
                with save_row:
                    save_btn = ui.button('Enregistrer').props(
                        'unelevated dense rounded').classes(
                        'bg-amber-500 text-white text-sm')

                def _on_input(e):
                    if e.value.strip():
                        save_row.classes(remove='hidden')
                    else:
                        save_row.classes(add='hidden')

                note_ta.on('update:model-value', _on_input)

                async def _save():
                    val = note_ta.value.strip()
                    if not val:
                        return
                    if not task:
                        ui.notify('Pas de fiche pour ce jour', type='warning')
                        return
                    note_ta.value = ''
                    save_row.classes(add='hidden')
                    if await notion_service.add_daily_comment(task.id, val):
                        ui.notify('Note enregistrée', type='positive')
                    else:
                        ui.notify('Erreur Notion', type='negative')

                save_btn.on('click', lambda: asyncio.create_task(_save()))
```

- [ ] **Step 2 : Vérifier manuellement — scénarios complets**

Test 1 — Aujourd'hui :
- Bloc Note présent avec textarea vide
- Taper du texte → bouton "Enregistrer" apparaît
- Clic → note envoyée, textarea vidée, notify positive

Test 2 — Hier (jour passé) :
- Bloc Note affiche "Journée passée — notes visibles dans Notion."
- Pas de textarea

Test 3 — Barre de progression :
- Décocher/cocher des items Routine → barre se met à jour
- Valider un cours → barre se met à jour
- Le compteur `X / Y · Z%` est juste

Test 4 — Navigation :
- ◀ ▶ naviguent jour par jour
- Clic sur la date → date picker → navigation directe
- L'état Routine est persisté entre les pages (SQLite)

Test 5 — Ajouter un cours pour Demain :
- Naviguer sur Demain
- `+ Cours` → sélectionner → Programmer
- Retour sur Aujourd'hui puis Demain → cours visible dans Ajouté

- [ ] **Step 3 : Vérifier que tous les tests passent**

```
pytest tests/test_local_store.py::TestRoutineChecks tests/test_todo_logic.py -v
```

Expected : 13 × PASSED

- [ ] **Step 4 : Commit final**

```bash
git add frontend/pages/todo.py
git commit -m "feat: todo bloc Note, dark mode, transitions — refonte To Do complète"
```
