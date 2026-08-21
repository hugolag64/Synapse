# Chantier A — Correctifs & navigation : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger sept défauts fonctionnels confirmés de l'interface Synapse (report de révision, tri des items, Flash-Zero, récents figés, palette de recherche dupliquée, navigation) sans toucher au design system ni à la logique pédagogique.

**Architecture:** Chaque tâche extrait la logique corrigée dans une **fonction pure au niveau module**, testée en isolation, puis branche cette fonction dans la closure de page qui la consomme. Les pages NiceGUI construisent leur UI dans des closures imbriquées non testables ; c'est le seul moyen d'obtenir une couverture réelle. Quand un comportement est purement CSS, le test assert sur la source du fichier — convention déjà établie dans `tests/test_cockpit_shell.py`.

**Tech Stack:** Python 3.12, NiceGUI (Quasar/Vue), SQLite via `backend/core/reviews/local_store.py`, pytest.

## Global Constraints

- Réponses et messages d'interface **en français**.
- Aucune modification du design system (tokens, cards grises, largeurs de page hors `.it-wrap`) : réservé au chantier B.
- Aucune modification de la logique pédagogique (calcul de maîtrise, banque Flash-Zero, Sprint EDN) : réservé au chantier C.
- Le style des fichiers suit l'existant : docstrings de module en français, commentaires expliquant le *pourquoi*, sections `# ── Titre ───`.
- Nouvelles tables SQLite : toujours `CREATE TABLE IF NOT EXISTS` dans `init_db()`, jamais de migration destructive.
- Commit après chaque tâche, message en anglais préfixé `fix:` / `feat:` / `refactor:` (convention du dépôt).
- Les tests tournent avec `python -m pytest` depuis la racine du dépôt.

## File Structure

| Fichier | Responsabilité | Tâche |
|---|---|---|
| `backend/core/reviews/service.py` | + `next_postpone_date()` — calcul pur de la date de report | 1 |
| `frontend/pages/todo_cockpit.py` | consomme `next_postpone_date` | 1 |
| `frontend/pages/dashboard/_cockpit_today.py` | consomme `next_postpone_date` | 1 |
| `frontend/pages/items.py` | + `visible_item_rows()` (filtre **et** tri), `.it-wrap` élargi | 2 |
| `frontend/components/flash_zero_cockpit.py` | croix dans le flux, correction en deux blocs | 3 |
| `frontend/components/flash_zero_dialog.py` | **supprimé** (Streamlit mort) | 3 |
| `backend/core/reviews/local_store.py` | + table `recent_courses`, `record_course_visit()`, `get_recent_course_ids()` | 4 |
| `frontend/pages/course_detail_cockpit.py` | enregistre la visite ; lien collège corrigé | 4, 6 |
| `frontend/cockpit_shell.py` | + `_recent_nav_entries()`, badge raccourci, retrait Semestres, câblage clavier | 4, 5, 6 |
| `frontend/components/command_palette.py` | palette unique : shell tokenisé + commandes texte + `search_items` | 5 |
| `frontend/components/item_search_palette.py` | **supprimé** (fusionné) | 5 |
| `frontend/keybindings.py` | raccourci global unique `Ctrl+Alt+P` | 5 |
| `frontend/pages/planning_cockpit.py` | import `search_items` déplacé ; blocs de jour cliquables | 5, 6 |

---

### Task 1: Report de révision relatif à aujourd'hui

Une tâche en retard de cinq jours reportée « d'un jour » atterrit aujourd'hui à J−4 : elle reste en retard. La date de report doit partir d'aujourd'hui quand la tâche est déjà dépassée.

**Files:**
- Modify: `backend/core/reviews/service.py` (ajout en fin de module, avant le singleton)
- Modify: `frontend/pages/todo_cockpit.py:167-176`
- Modify: `frontend/pages/dashboard/_cockpit_today.py:352-361`
- Test: `tests/test_review_postpone_date.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: `backend.core.reviews.service.next_postpone_date(due_date: datetime.date, today: datetime.date, days: int = 1) -> datetime.date`

- [ ] **Step 1: Write the failing test**

Créer `tests/test_review_postpone_date.py` :

```python
"""Report d'une révision : la nouvelle date part toujours d'aujourd'hui
quand la tâche est déjà en retard."""
import datetime

from backend.core.reviews.service import next_postpone_date


TODAY = datetime.date(2026, 8, 7)


def test_overdue_task_is_postponed_relative_to_today():
    five_days_late = TODAY - datetime.timedelta(days=5)

    assert next_postpone_date(five_days_late, TODAY) == TODAY + datetime.timedelta(days=1)


def test_task_due_today_is_postponed_to_tomorrow():
    assert next_postpone_date(TODAY, TODAY) == TODAY + datetime.timedelta(days=1)


def test_future_task_is_postponed_relative_to_its_own_due_date():
    in_three_days = TODAY + datetime.timedelta(days=3)

    assert next_postpone_date(in_three_days, TODAY) == in_three_days + datetime.timedelta(days=1)


def test_multi_day_postpone_is_honoured():
    two_days_late = TODAY - datetime.timedelta(days=2)

    assert next_postpone_date(two_days_late, TODAY, days=7) == TODAY + datetime.timedelta(days=7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_postpone_date.py -v`
Expected: FAIL — `ImportError: cannot import name 'next_postpone_date'`

- [ ] **Step 3: Write minimal implementation**

Dans `backend/core/reviews/service.py`, juste avant le bloc `# ── Singleton ──` en fin de fichier :

```python
# ── Report d'une révision ─────────────────────────────────────────────────────

def next_postpone_date(
    due_date: date,
    today: date,
    days: int = 1,
) -> date:
    """
    Date effective après report.

    Le calcul part de `max(due_date, today)` et non de `due_date` seule : sinon
    reporter « d'un jour » une tâche en retard de cinq jours la place quatre
    jours dans le passé, elle reste en retard, et il faut cliquer cinq fois
    pour la sortir de la file.
    """
    return max(due_date, today) + timedelta(days=days)
```

`date` et `timedelta` sont déjà importés en tête de module (`from datetime import date, timedelta`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_postpone_date.py -v`
Expected: 4 passed

- [ ] **Step 5: Brancher la file Révisions**

Dans `frontend/pages/todo_cockpit.py`, remplacer la première ligne de `_on_postpone` (ligne 168) :

```python
        new_date = task.due_date + datetime.timedelta(days=days)
```

par :

```python
        new_date = next_postpone_date(task.due_date, datetime.date.today(), days)
```

et ajouter l'import à la ligne d'import existante du service (ligne 28) :

```python
from backend.core.reviews.service import review_service, next_postpone_date
```

- [ ] **Step 6: Brancher le dashboard Aujourd'hui**

Dans `frontend/pages/dashboard/_cockpit_today.py`, remplacer la première ligne de `_on_postpone` (ligne 353) :

```python
        new_date = task.due_date + datetime.timedelta(days=days)
```

par :

```python
        new_date = next_postpone_date(task.due_date, datetime.date.today(), days)
```

Ajouter l'import en tête de fichier, dans le bloc des imports `backend.core.reviews` :

```python
from backend.core.reviews.service import next_postpone_date
```

Si `_cockpit_today.py` importe déjà quelque chose depuis `backend.core.reviews.service`, fusionner sur la ligne existante plutôt que d'en ajouter une.

- [ ] **Step 7: Vérifier l'absence de régression**

Run: `python -m pytest tests/test_todo_cockpit_ui.py tests/test_todo_logic.py tests/test_review_service.py tests/test_cockpit_today_session_feedback.py -v`
Expected: PASS (aucun de ces tests n'assert sur l'ancien calcul ; s'il en existe un, corriger le test — l'ancien comportement était le bug)

- [ ] **Step 8: Commit**

```bash
git add backend/core/reviews/service.py frontend/pages/todo_cockpit.py frontend/pages/dashboard/_cockpit_today.py tests/test_review_postpone_date.py
git commit -m "fix: postpone reviews relative to today instead of their stale due date"
```

---

### Task 2: Tri et largeur de la vue Items

Les boutons « Trier par : Item / Collège » ne changent que l'état actif du chip : `_draw_list` réaffiche la liste triée une seule fois par `_compute()`. On extrait filtrage **et** tri dans une fonction pure appelée au rendu.

**Files:**
- Modify: `frontend/pages/items.py:41` (CSS), `:212-220` (`_visible` → remplacé), `:333-342` (`_draw_list`)
- Test: `tests/test_items_sorting.py` (étendre)

**Interfaces:**
- Consumes: `_sort_item_rows(rows, mode)` — existe déjà, `frontend/pages/items.py:102`.
- Produces: `frontend.pages.items.visible_item_rows(rows: list[dict], filt: dict) -> list[dict]`
  - `rows` : dicts produits par `_compute()`, clés utilisées ici — `course` (objet cours, attributs `college`, `item_number`, `title`), `mastery_level` (str), `overdue` (bool).
  - `filt` : dict d'état de page, clés — `mode` (`"all"` | `"college"` | `"fragile"` | `"overdue"`), `college` (nom ou `"Tous"`), `sort` (`"item"` | `"college"`).

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/test_items_sorting.py` :

```python
from frontend.pages.items import visible_item_rows


def _full_row(item, title, colleges, level="maîtrisé", overdue=False):
    return {
        "course": SimpleNamespace(item_number=item, title=title, college=colleges),
        "mastery_level": level,
        "overdue": overdue,
    }


def _filt(**overrides):
    base = {"mode": "all", "college": "Tous", "sort": "item"}
    base.update(overrides)
    return base


def test_visible_rows_apply_the_current_sort_mode():
    rows = [
        _full_row("2", "Deux", ["Pneumologie"]),
        _full_row("1", "Un", ["Cardiologie"]),
    ]

    by_item = visible_item_rows(rows, _filt(sort="item"))
    by_college = visible_item_rows(rows, _filt(sort="college"))

    assert [r["course"].title for r in by_item] == ["Un", "Deux"]
    assert [r["course"].title for r in by_college] == ["Un", "Deux"]


def test_switching_sort_mode_changes_the_rendered_order():
    rows = [
        _full_row("1", "Un", ["Pneumologie"]),
        _full_row("2", "Deux", ["Cardiologie"]),
    ]

    by_item = visible_item_rows(rows, _filt(sort="item"))
    by_college = visible_item_rows(rows, _filt(sort="college"))

    assert [r["course"].title for r in by_item] == ["Un", "Deux"]
    assert [r["course"].title for r in by_college] == ["Deux", "Un"]


def test_visible_rows_filter_on_selected_college():
    rows = [
        _full_row("1", "Un", ["Cardiologie"]),
        _full_row("2", "Deux", ["Pneumologie"]),
    ]

    visible = visible_item_rows(rows, _filt(college="Cardiologie", mode="college"))

    assert [r["course"].title for r in visible] == ["Un"]


def test_visible_rows_filter_on_fragile_and_overdue_modes():
    rows = [
        _full_row("1", "Un", ["A"], level="fragile"),
        _full_row("2", "Deux", ["A"], level="critique"),
        _full_row("3", "Trois", ["A"], level="maîtrisé", overdue=True),
    ]

    fragile = visible_item_rows(rows, _filt(mode="fragile"))
    overdue = visible_item_rows(rows, _filt(mode="overdue"))

    assert [r["course"].title for r in fragile] == ["Un", "Deux"]
    assert [r["course"].title for r in overdue] == ["Trois"]


def test_items_list_is_not_capped_at_a_fixed_width():
    from pathlib import Path

    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert ".it-wrap { max-width:none;" in source
    assert "max-width:1200px" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_items_sorting.py -v`
Expected: FAIL — `ImportError: cannot import name 'visible_item_rows'`

- [ ] **Step 3: Ajouter la fonction pure**

Dans `frontend/pages/items.py`, juste après `_sort_item_rows` (ligne 116) :

```python
def visible_item_rows(rows: list[dict], filt: dict) -> list[dict]:
    """
    Lignes réellement rendues : filtre courant puis tri courant.

    Le tri doit être appliqué au rendu et non à la collecte : `_compute()` n'est
    exécuté qu'une fois par chargement de page, alors que le mode de tri change
    à chaque clic sur un chip.
    """
    college = filt.get("college", "Tous")
    mode = filt.get("mode", "all")

    if college != "Tous":
        selected = [r for r in rows if college in (r["course"].college or [])]
    elif mode == "fragile":
        selected = [r for r in rows if r["mastery_level"] in ("fragile", "critique")]
    elif mode == "overdue":
        selected = [r for r in rows if r["overdue"]]
    else:
        selected = list(rows)

    return _sort_item_rows(selected, filt.get("sort", "item"))
```

- [ ] **Step 4: Brancher le rendu et supprimer `_visible`**

Supprimer la closure `_visible` (lignes 212-220) et remplacer le corps de `_draw_list` (lignes 333-342) par :

```python
    def _draw_list(rows: list[dict]) -> None:
        list_col.clear()
        visible = visible_item_rows(rows, filt)
        with list_col:
            if not visible:
                with ui.element("div").classes("it-empty"):
                    ui.label("Aucun item pour ce filtrage.")
                return
            for r in visible:
                _draw_row(r)
```

- [ ] **Step 5: Élargir la vue**

Dans le bloc `_CSS` de `frontend/pages/items.py`, remplacer la ligne 41 :

```css
.it-wrap { max-width:1200px; width:100%; min-width:0; overflow:hidden; }
```

par :

```css
.it-wrap { max-width:none; width:100%; min-width:0; overflow:hidden; }
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_items_sorting.py -v`
Expected: 8 passed

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/items.py tests/test_items_sorting.py
git commit -m "fix: apply items sort at render time and let the list use full width"
```

---

### Task 3: Flash-Zero — croix visible et correction lisible

La croix est en `position:absolute; right:8px`, exactement sous le bouton « Lancer » qui occupe la droite de la carte : elle apparaît au survol mais reste recouverte. Et le bloc de correction empile « Ta réponse » et « Réponse attendue » sans séparation.

**Files:**
- Modify: `frontend/components/flash_zero_cockpit.py` — `_CSS` (lignes 13, 21-23), bloc correction (lignes 117-125), `render_flash_zero_card` (lignes 147-159)
- Delete: `frontend/components/flash_zero_dialog.py`
- Test: `tests/test_flash_zero_cockpit.py` (modifier une assertion, en ajouter)

**Interfaces:**
- Consumes: rien.
- Produces: rien (changements internes au composant).

- [ ] **Step 1: Write the failing test**

Dans `tests/test_flash_zero_cockpit.py`, **remplacer** `test_flash_zero_card_has_a_hover_dismiss_control` (lignes 23-29) par :

```python
def test_flash_zero_card_has_a_hover_dismiss_control():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert ".flash-zero-card:hover .flash-zero-dismiss" in source
    assert 'aria-label="Ignorer le Flash-Zero du jour"' in source
    assert ".flash-zero-layout" in source


def test_dismiss_control_no_longer_overlaps_the_action_button():
    """La croix était en position:absolute right:8px, c'est-à-dire sous le
    bouton « Lancer ». Elle doit vivre dans le flux, avant ce bouton."""
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert "position:absolute" not in source
    assert "top:8px !important" not in source
    assert "pointer-events:none" in source
    assert source.index("flash-zero-dismiss") < source.index('model["action"]')


def test_correction_separates_given_answer_from_expected_answer():
    source = Path("frontend/components/flash_zero_cockpit.py").read_text(encoding="utf-8")

    assert ".flash-zero-answer-label" in source
    assert ".flash-zero-answer-value" in source
    assert '"Ta réponse"' in source
    assert '"Réponse attendue"' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_flash_zero_cockpit.py -v`
Expected: FAIL sur `test_dismiss_control_no_longer_overlaps_the_action_button` (`position:absolute` toujours présent) et `test_correction_separates_given_answer_from_expected_answer`

- [ ] **Step 3: Corriger le CSS**

Dans `_CSS` de `frontend/components/flash_zero_cockpit.py`, remplacer la ligne 13 :

```css
.flash-zero-card { position:relative; border:1px solid var(--border); border-left:3px solid var(--warning); border-radius:8px; background:var(--bg); box-shadow:var(--shadow-popover); transition:border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard); }
```

par (retrait de `position:relative`, devenu inutile) :

```css
.flash-zero-card { border:1px solid var(--border); border-left:3px solid var(--warning); border-radius:8px; background:var(--bg); box-shadow:var(--shadow-popover); transition:border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard); }
```

Remplacer les lignes 21-23 :

```css
.flash-zero-dismiss { position:absolute !important; top:8px !important; right:8px !important; z-index:2; opacity:0; color:var(--text-muted); transition:opacity var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.flash-zero-card:hover .flash-zero-dismiss, .flash-zero-card:focus-within .flash-zero-dismiss { opacity:1; }
.flash-zero-dismiss:hover { color:var(--danger); }
```

par :

```css
/* Dans le flux, avant le bouton d'action : en absolute right:8px elle se
   retrouvait sous « Lancer » et n'était jamais cliquable. L'espace reste
   réservé même masquée, pour que le survol ne décale pas la carte. */
.flash-zero-dismiss { flex:0 0 auto; opacity:0; pointer-events:none; color:var(--text-muted); transition:opacity var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.flash-zero-card:hover .flash-zero-dismiss, .flash-zero-card:focus-within .flash-zero-dismiss { opacity:1; pointer-events:auto; }
.flash-zero-dismiss:hover { color:var(--danger); }
.flash-zero-answer { display:flex; flex-direction:column; gap:2px; margin-top:10px; }
.flash-zero-answer-label { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--text-dim); font-weight:600; }
.flash-zero-answer-value { font-size:13px; color:var(--text); line-height:1.4; }
```

- [ ] **Step 4: Déplacer la croix dans le flux**

Remplacer `render_flash_zero_card` (lignes 147-159) par :

```python
    with ui.element("div").classes("flash-zero-card w-full p-3 mb-4"):
        with ui.element("div").classes("flash-zero-layout w-full"):
            ui.label("⚡").classes("flash-zero-icon")
            with ui.element("div").classes("flash-zero-copy"):
                ui.label(model["title"]).classes("flash-zero-title")
                ui.label("Erreurs récentes et répétées").classes("flash-zero-meta")
            ui.label(f"{model['duration']} · {model['status']}").classes("flash-zero-status")
            ui.button(icon="close", on_click=on_dismiss).props(
                'flat round dense aria-label="Ignorer le Flash-Zero du jour"'
            ).classes("flash-zero-dismiss")
            ui.button(model["action"], on_click=on_open).props(
                "unelevated color=primary size=sm rounded"
            )
```

- [ ] **Step 5: Séparer les deux réponses dans la correction**

Remplacer les lignes 122-125 (`if selected is not None:` jusqu'au label d'explication) par :

```python
                            if selected is not None:
                                with ui.element("div").classes("flash-zero-answer"):
                                    ui.label("Ta réponse").classes("flash-zero-answer-label")
                                    ui.label(question.choices[selected]).classes("flash-zero-answer-value")
                            with ui.element("div").classes("flash-zero-answer"):
                                ui.label("Réponse attendue").classes("flash-zero-answer-label")
                                ui.label(question.choices[question.correct_idx]).classes("flash-zero-answer-value")
                            ui.label(question.explanation).classes("text-sm text-slate-600 mt-3")
```

Conserver l'indentation exacte du bloc `with ui.element("div").classes(f"flash-zero-correction …")` environnant.

- [ ] **Step 6: Supprimer le composant Streamlit mort**

`frontend/components/flash_zero_dialog.py` importe `streamlit`, framework abandonné au profit de NiceGUI, et n'est référencé par aucun autre fichier.

```bash
git rm frontend/components/flash_zero_dialog.py
```

Puis confirmer l'absence de référence résiduelle :

```bash
grep -rn "flash_zero_dialog\|render_flash_zero_dialog" --include=*.py .
```

Expected: aucune sortie.

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_flash_zero_cockpit.py tests/test_flash_zero_integration.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/components/flash_zero_cockpit.py tests/test_flash_zero_cockpit.py
git commit -m "fix: make Flash-Zero dismiss clickable and separate answer from expected answer"
```

---

### Task 4: Section « Récents » réellement alimentée

`cockpit_shell.py:262-264` affiche deux entrées écrites en dur pointant vers `/`. On les remplace par un historique de consultation réel, et la section disparaît quand il est vide plutôt que d'afficher de fausses données.

**Files:**
- Modify: `backend/core/reviews/local_store.py` — `init_db()` (après le bloc `routine_checks`, ligne 504), accesseurs (après `set_routine_check`, ligne 4963)
- Modify: `frontend/pages/course_detail_cockpit.py:300` (après la garde « Item introuvable »)
- Modify: `frontend/cockpit_shell.py:261-264`
- Test: `tests/test_recent_courses.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces:
  - `backend.core.reviews.local_store.record_course_visit(course_id: str) -> None`
  - `backend.core.reviews.local_store.get_recent_course_ids(limit: int = 5) -> list[str]` — ordre de visite décroissant
  - `frontend.cockpit_shell._recent_nav_entries(limit: int = 5) -> list[tuple[str, str]]` — liste de `(label, route)`

- [ ] **Step 1: Write the failing test**

Créer `tests/test_recent_courses.py` :

```python
"""Historique de consultation des fiches item alimentant la section « Récents »."""
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Chaque test utilise sa propre DB temporaire."""
    import backend.core.reviews.local_store as ls
    monkeypatch.setattr(ls, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(ls, "_DB", None)
    ls.init_db()
    yield
    if ls._DB is not None:
        ls._DB.close()
    monkeypatch.setattr(ls, "_DB", None)


import backend.core.reviews.local_store as ls


def test_visits_are_returned_most_recent_first():
    ls.record_course_visit("a")
    ls.record_course_visit("b")
    ls.record_course_visit("c")

    assert ls.get_recent_course_ids() == ["c", "b", "a"]


def test_revisiting_a_course_moves_it_up_without_duplicating():
    ls.record_course_visit("a")
    ls.record_course_visit("b")
    ls.record_course_visit("a")

    assert ls.get_recent_course_ids() == ["a", "b"]


def test_limit_caps_the_returned_history():
    for course_id in ("a", "b", "c", "d", "e", "f"):
        ls.record_course_visit(course_id)

    assert len(ls.get_recent_course_ids(limit=5)) == 5


def test_empty_history_returns_an_empty_list():
    assert ls.get_recent_course_ids() == []


# ── Rendu sidebar ─────────────────────────────────────────────────────────────

def test_recent_nav_entries_label_and_route_each_course(monkeypatch):
    from frontend import cockpit_shell

    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_recent_course_ids",
        lambda limit=5: ["c1", "c2"],
    )
    monkeypatch.setattr(
        cockpit_shell.data_store, "cours",
        [
            SimpleNamespace(id="c1", title="Athérome", display_item_number="221", item_number="221"),
            SimpleNamespace(id="c2", title="Prescription", display_item_number="", item_number=""),
        ],
        raising=False,
    )

    assert cockpit_shell._recent_nav_entries() == [
        ("Item 221 · Athérome", "/cours/c1"),
        ("Prescription", "/cours/c2"),
    ]


def test_recent_nav_entries_skip_courses_absent_from_the_store(monkeypatch):
    """Un cours supprimé côté Notion reste dans l'historique local : on l'ignore
    plutôt que de rendre un lien mort."""
    from frontend import cockpit_shell

    monkeypatch.setattr(
        "backend.core.reviews.local_store.get_recent_course_ids",
        lambda limit=5: ["gone", "c1"],
    )
    monkeypatch.setattr(
        cockpit_shell.data_store, "cours",
        [SimpleNamespace(id="c1", title="Athérome", display_item_number="221", item_number="221")],
        raising=False,
    )

    assert cockpit_shell._recent_nav_entries() == [("Item 221 · Athérome", "/cours/c1")]


def test_sidebar_hides_the_recents_group_when_history_is_empty():
    from pathlib import Path

    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert "if recents:" in source
    assert 'Item 221 · Athérome' not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recent_courses.py -v`
Expected: FAIL — `AttributeError: module 'backend.core.reviews.local_store' has no attribute 'record_course_visit'`

- [ ] **Step 3: Créer la table**

Dans `backend/core/reviews/local_store.py`, à l'intérieur du `con.executescript("""…""")` de `init_db()`, juste après le bloc `routine_checks` (après la ligne 504) :

```sql
        -- ── Historique de consultation des fiches (section « Récents ») ─────
        CREATE TABLE IF NOT EXISTS recent_courses (
            course_id TEXT PRIMARY KEY,
            opened_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_recent_courses_opened
            ON recent_courses(opened_at DESC);
```

- [ ] **Step 4: Ajouter les accesseurs**

Dans le même fichier, juste après `set_routine_check` (ligne 4963) :

```python
# ── Historique de consultation ────────────────────────────────────────────────

def record_course_visit(course_id: str) -> None:
    """Enregistre l'ouverture d'une fiche cours (upsert : pas de doublon)."""
    if not course_id:
        return
    with _conn() as con:
        con.execute(
            "INSERT INTO recent_courses (course_id, opened_at) VALUES (?, ?) "
            "ON CONFLICT(course_id) DO UPDATE SET opened_at = excluded.opened_at",
            (course_id, now_local().isoformat()),
        )


def get_recent_course_ids(limit: int = 5) -> list[str]:
    """Identifiants des dernières fiches ouvertes, de la plus récente à la plus ancienne."""
    rows = _conn().execute(
        "SELECT course_id FROM recent_courses ORDER BY opened_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["course_id"] for r in rows]
```

`now_local()` est déjà importé dans ce module (utilisé par `backup_database`). Si l'exécution montre le contraire, utiliser `datetime.datetime.now().isoformat()`.

- [ ] **Step 5: Enregistrer la visite depuis la fiche**

Dans `frontend/pages/course_detail_cockpit.py`, juste après le bloc de garde « Item introuvable » qui se termine ligne 300 par `return`, et avant le commentaire `# ── Données …` (ligne 302) :

```python
    # Historique de consultation pour la section « Récents » de la sidebar.
    # Une seule écriture upsert, jamais bloquante : cette page est déjà lente.
    try:
        local_store.record_course_visit(course_id)
    except Exception as exc:
        logger.warning(f"visite non enregistrée pour {course_id}: {exc}")
```

- [ ] **Step 6: Brancher la sidebar**

Dans `frontend/cockpit_shell.py`, ajouter la fonction juste avant `_BOTTOM_NAV` (ligne 200) :

```python
def _recent_nav_entries(limit: int = 5) -> list[tuple[str, str]]:
    """(libellé, route) des dernières fiches ouvertes.

    Un cours encore présent dans l'historique local mais disparu du store
    (supprimé côté Notion) est ignoré : on ne rend pas de lien mort.
    """
    try:
        from backend.core.reviews.local_store import get_recent_course_ids
        course_ids = get_recent_course_ids(limit=limit)
    except Exception:
        return []

    by_id = {c.id: c for c in data_store.cours}
    entries: list[tuple[str, str]] = []
    for course_id in course_ids:
        course = by_id.get(course_id)
        if course is None:
            continue
        number = str(
            getattr(course, "display_item_number", "") or getattr(course, "item_number", "") or ""
        ).strip()
        label = f"Item {number} · {course.title}" if number else course.title
        entries.append((label, f"/cours/{course.id}"))
    return entries
```

Puis remplacer les lignes 261-264 :

```python
        # Récents (placeholder — câblage réel session ultérieure)
        ui.label("Récents").classes("cockpit-group-label")
        _nav_item("○", "Item 221 · Athérome", "/", None, active="")
        _nav_item("○", "Item 330 · Prescription", "/", None, active="")
```

par :

```python
        # Récents — masqués tant qu'aucune fiche n'a été ouverte
        recents = _recent_nav_entries()
        if recents:
            ui.label("Récents").classes("cockpit-group-label")
            for label, route in recents:
                _nav_item("○", label, route, None, active="")
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_recent_courses.py tests/test_cockpit_shell.py tests/test_local_store.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/core/reviews/local_store.py frontend/pages/course_detail_cockpit.py frontend/cockpit_shell.py tests/test_recent_courses.py
git commit -m "feat: replace hardcoded sidebar recents with real course visit history"
```

---

### Task 5: Palette de recherche unique sur Ctrl+Alt+P

Deux palettes coexistent. `command_palette` (recherche + commandes texte) est stylée en Tailwind codé en dur ; `item_search_palette` (recherche seule) est correctement tokenisée. On garde le shell de la seconde et les fonctions de la première.

**Découverte importante :** `register_keybindings()` n'est appelé nulle part dans le dépôt. `Ctrl+K` et la touche `/` n'ont donc **jamais** fonctionné — seuls le clic sur la barre de recherche et `Ctrl+Alt+P` sur la page Items sont actifs. Cette tâche câble pour la première fois un raccourci global.

**Files:**
- Modify: `frontend/components/command_palette.py` (391 lignes) — remplacer le shell du dialog (lignes 65-101), le rendu des résultats (lignes 145-172), ajouter `_fold`, `search_items` et la navigation clavier. **Le bloc de câblage final (lignes 380-390 : `search_input.on(…)`, `_render_body("")`, `dlg.open()`) doit être conservé**, on y ajoute seulement le handler clavier. Les dialogs internes `_open_lacune_dialog_prefilled` et `_render_command_shortcut` gardent leur style Tailwind : leur refonte relève du chantier B.
- Delete: `frontend/components/item_search_palette.py`
- Modify: `frontend/keybindings.py` — un seul raccourci
- Modify: `frontend/cockpit_shell.py:253` (badge) et `cockpit_frame` (câblage clavier)
- Modify: `frontend/pages/items.py:38, 232, 355-356`
- Modify: `frontend/pages/planning_cockpit.py:52` (import de `search_items`)
- Test: `tests/test_item_search_palette.py` → renommer en `tests/test_command_palette.py`

**Interfaces:**
- Consumes: `frontend.cockpit_shell.data_store`.
- Produces:
  - `frontend.components.command_palette.search_items(query: str, courses: list) -> list` — déplacée depuis `item_search_palette`, signature et comportement inchangés
  - `frontend.components.command_palette.open_command_palette() -> None` — signature inchangée
  - `frontend.keybindings.register_keybindings() -> None` — signature inchangée, appelée depuis `cockpit_frame`

- [ ] **Step 1: Write the failing test**

```bash
git mv tests/test_item_search_palette.py tests/test_command_palette.py
```

Puis remplacer intégralement le contenu de `tests/test_command_palette.py` par :

```python
"""Palette de recherche unique — fusion de command_palette et item_search_palette."""
from types import SimpleNamespace
from pathlib import Path

from frontend.components.command_palette import search_items


def _course(item, title, colleges):
    return SimpleNamespace(item_number=item, display_item_number=item, title=title, college=colleges)


def test_search_items_matches_item_number_title_and_college():
    courses = [
        _course("75", "Addiction au tabac", ["Psychiatrie"]),
        _course("169", "Infections à VIH", ["Infectiologie"]),
    ]

    assert [c.item_number for c in search_items("75", courses)] == ["75"]
    assert [c.item_number for c in search_items("tabac", courses)] == ["75"]
    assert [c.item_number for c in search_items("infectio", courses)] == ["169"]


def test_search_items_empty_query_returns_recent_slice():
    courses = [_course(str(i), f"Cours {i}", ["Médecine"]) for i in range(12)]

    assert search_items("", courses) == courses[:8]


def test_the_duplicate_item_palette_is_gone():
    assert not Path("frontend/components/item_search_palette.py").exists()


def test_palette_shell_uses_synapse_design_tokens():
    """Seule la coquille de la palette est retokenisée ici. Les dialogs qu'elle
    ouvre (lacune pré-remplie, raccourcis de commande) gardent leur style
    Tailwind : ils relèvent du chantier B."""
    source = Path("frontend/components/command_palette.py").read_text(encoding="utf-8")

    assert "var(--bg)" in source
    assert "var(--border)" in source
    assert 'ui.card().classes("cmd-palette' in source
    assert "rounded-2xl" not in source  # ancienne carte Tailwind de la palette


def test_palette_keeps_keyboard_navigation_over_results():
    """La palette Items offrait ↑↓/Entrée ; la palette fusionnée ne doit pas
    régresser sur ce point, le pied de dialog l'annonce."""
    source = Path("frontend/components/command_palette.py").read_text(encoding="utf-8")

    assert '"ArrowDown"' in source
    assert '"ArrowUp"' in source
    assert '"Enter"' in source
    assert "cmd-palette-result selected" in source or '" selected"' in source


def test_single_global_shortcut_is_ctrl_alt_p():
    bindings = Path("frontend/keybindings.py").read_text(encoding="utf-8")

    assert "e.modifiers.ctrl" in bindings
    assert "e.modifiers.alt" in bindings
    # Les anciens raccourcis, jamais câblés, ne doivent pas réapparaître.
    assert "register_item_search_keybinding" not in bindings
    assert 'key in ("k", "/")' not in bindings


def test_shell_wires_the_global_keybinding_and_shows_the_right_badge():
    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert "register_keybindings()" in source
    assert "Ctrl Alt P" in source
    assert "⌘K" not in source


def test_items_page_no_longer_registers_its_own_palette():
    source = Path("frontend/pages/items.py").read_text(encoding="utf-8")

    assert "item_search_palette" not in source
    assert "register_item_search_keybinding" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_command_palette.py -v`
Expected: FAIL — `ImportError: cannot import name 'search_items' from 'frontend.components.command_palette'`

- [ ] **Step 3: Porter la recherche tolérante dans la palette unique**

Dans `frontend/components/command_palette.py`, ajouter en tête de fichier après les imports existants :

```python
import unicodedata
```

et, avant `def open_command_palette()` (ligne 29), les deux fonctions déplacées depuis `item_search_palette.py` (contenu identique, lignes 30-60 de l'ancien fichier) :

```python
def _fold(value: object) -> str:
    text = str(value or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def search_items(query: str, courses: list) -> list:
    """Recherche tolérante sur numéro, titre et collèges associés."""
    q = _fold(query).strip()
    if not q:
        return list(courses[:8])

    def score(course) -> tuple[int, str, str]:
        number = _fold(getattr(course, "display_item_number", None) or getattr(course, "item_number", None))
        title = _fold(getattr(course, "title", ""))
        colleges = _fold(" ".join(getattr(course, "college", None) or []))
        if number == q:
            rank = 0
        elif number.startswith(q):
            rank = 1
        elif q in title:
            rank = 2
        elif q in colleges:
            rank = 3
        else:
            return (99, title, number)
        return (rank, title, number)

    return sorted((course for course in courses if score(course)[0] < 99), key=score)[:12]
```

- [ ] **Step 4: Remplacer le shell Tailwind par le shell tokenisé**

Ajouter en tête de `command_palette.py`, après les imports, le bloc CSS repris de `item_search_palette.py` (lignes 11-27 de l'ancien fichier) :

```python
_CSS = """
.cmd-palette { animation: cmd-palette-in 140ms ease-out both; background:var(--bg); color:var(--text);
  border:1px solid var(--border); border-radius:12px; box-shadow:0 18px 50px rgba(31,35,50,.18); }
@keyframes cmd-palette-in { from { opacity:0; transform:translateY(-8px) scale(.98); }
  to { opacity:1; transform:translateY(0) scale(1); } }
.cmd-palette-header { background:var(--bg); border-bottom:1px solid var(--border); }
.cmd-palette-input { color:var(--text); font-size:13px; }
.cmd-palette-input input::placeholder { color:var(--text-dim); }
.cmd-palette-result { transition:background 100ms ease; }
.cmd-palette-result:hover { background:var(--surface); }
.cmd-palette-result.selected { background:var(--surface); }
.cmd-palette-number { color:var(--text-muted); font:11px var(--font-mono); }
.cmd-palette-title { color:var(--text); font-size:13px; font-weight:600; }
.cmd-palette-college { color:var(--text-muted); font-size:11.5px; }
.cmd-palette-hint { color:var(--text-dim); font-size:11px; }
.cmd-palette-kbd { border:1px solid var(--border); border-radius:4px; color:var(--text-muted); font:10.5px var(--font-mono); padding:1px 5px; }
.cmd-palette-section { color:var(--text-dim); font-size:10px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; }
"""
```

Remplacer le bloc de construction du dialog (lignes 65-101, de `with ui.dialog() as dlg:` jusqu'à la fin du footer hint) par :

```python
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    with ui.dialog() as dlg:
        with ui.card().classes("cmd-palette w-[620px] max-w-[94vw] p-0 overflow-hidden").style(
            "max-height:80vh"
        ):
            with ui.element("div").classes("cmd-palette-header flex items-center gap-3 px-4 py-3"):
                ui.icon("search", size="sm").style("color:var(--text-muted)")
                search_input = ui.input(
                    placeholder="Rechercher un item, ou taper : lacune / qcm / séance…"
                ).props("autofocus borderless dense").classes("cmd-palette-input flex-1")
                ui.element("kbd").classes("cmd-palette-kbd").text = "Ctrl+Alt+P"
                ui.button(icon="close", on_click=dlg.close).props("flat round dense color=grey")

            body = ui.column().classes("w-full gap-0").style("max-height:52vh;overflow-y:auto")

            with ui.element("div").classes("px-4 py-2 flex gap-4").style(
                "border-top:1px solid var(--border)"
            ):
                ui.label("↑↓ parcourir").classes("cmd-palette-hint")
                ui.label("Entrée ouvrir").classes("cmd-palette-hint")
                ui.label("Échap fermer").classes("cmd-palette-hint")
```

- [ ] **Step 5: Retokeniser la liste de résultats**

Dans `_render_body`, remplacer la recherche (ligne 118) :

```python
            courses = _search_courses(query)
```

par :

```python
            courses = search_items(query, data_store.cours)
```

et supprimer la closure `_search_courses` (lignes 40-53), devenue inutile.

Remplacer les en-têtes de section (lignes 122-125 et 140-143) — les deux blocs `ui.label("ACTIONS RAPIDES")` / `ui.label("COURS RÉCENTS")` — par la classe tokenisée :

```python
                with ui.element("div").classes("px-4 py-2"):
                    ui.label("ACTIONS RAPIDES").classes("cmd-palette-section")
```

```python
                    with ui.element("div").classes("px-4 py-1"):
                        ui.label("COURS RÉCENTS").classes("cmd-palette-section")
```

Remplacer le rendu d'une ligne de résultat (lignes 160-172) par :

```python
                    row = ui.element("div").classes(
                        "cmd-palette-result w-full px-4 py-3 flex items-center gap-3 cursor-pointer"
                    )
                    row.on("click", _pick)
                    with row:
                        ui.label(
                            f"ITEM {course.display_item_number or course.item_number or '—'}"
                        ).classes("cmd-palette-number w-20 shrink-0")
                        with ui.column().classes("flex-1 gap-0 min-w-0"):
                            ui.label(course.title).classes("cmd-palette-title truncate")
                            colleges = " · ".join(course.college or [])
                            if colleges:
                                ui.label(colleges).classes("cmd-palette-college truncate")
```

Les variables `item_txt` et `college_txt` définies lignes 152-153 deviennent inutilisées : les supprimer.

- [ ] **Step 5b: Restaurer la navigation clavier**

Le pied du dialog annonce « ↑↓ parcourir · Entrée ouvrir ». `item_search_palette` implémentait ces touches, pas `command_palette` : sans ce portage, la fusion serait une régression et le pied mentirait.

Étendre l'état initial (lignes 33-36) :

```python
    state: dict = {
        "selected_course": None,
        "query": "",
        "selected": 0,      # index surligné dans la liste de résultats
        "results": [],      # résultats actuellement rendus
    }
```

Au tout début de `_render_body`, après `body.clear()`, réinitialiser les résultats pour qu'une vue sans liste (actions d'un cours, raccourci de commande) ne laisse pas un état périmé :

```python
    def _render_body(query: str = ""):
        body.clear()
        state["results"] = []
        cmd, rest = _detect_command(query)
```

Dans la boucle de rendu des résultats (celle réécrite au Step 5), mémoriser la liste et surligner la ligne courante :

```python
            else:
                state["results"] = courses
                for index, course in enumerate(courses):

                    def _pick(c=course):
                        state["selected_course"] = c
                        search_input.value = ""
                        _render_body("")

                    classes = "cmd-palette-result w-full px-4 py-3 flex items-center gap-3 cursor-pointer"
                    if index == state["selected"]:
                        classes += " selected"
                    row = ui.element("div").classes(classes)
                    row.on("click", _pick)
                    with row:
                        ui.label(
                            f"ITEM {course.display_item_number or course.item_number or '—'}"
                        ).classes("cmd-palette-number w-20 shrink-0")
                        with ui.column().classes("flex-1 gap-0 min-w-0"):
                            ui.label(course.title).classes("cmd-palette-title truncate")
                            colleges = " · ".join(course.college or [])
                            if colleges:
                                ui.label(colleges).classes("cmd-palette-college truncate")
```

Enfin, dans le bloc de câblage final (lignes 380-390), remettre l'index à zéro à chaque frappe et ajouter le handler clavier :

```python
    # Mise à jour réactive sur frappe
    def _on_search_change(e):
        state["selected_course"] = None
        state["selected"] = 0
        state["query"] = e.value or ""
        _render_body(state["query"])

    def _on_key(e) -> None:
        args = getattr(e, "args", None)
        key = args.get("key", "") if isinstance(args, dict) else ""
        results = state["results"]
        if not results:
            return
        if key == "ArrowDown":
            state["selected"] = min(state["selected"] + 1, len(results) - 1)
            _render_body(state["query"])
        elif key == "ArrowUp":
            state["selected"] = max(0, state["selected"] - 1)
            _render_body(state["query"])
        elif key == "Enter":
            state["selected_course"] = results[state["selected"]]
            search_input.value = ""
            _render_body("")

    search_input.on("update:model-value", _on_search_change)
    search_input.on("keydown", _on_key)

    # Affichage initial
    _render_body("")
    dlg.open()
```

- [ ] **Step 6: Un seul raccourci global**

Remplacer intégralement `frontend/keybindings.py` par :

```python
"""
Keybindings — Synapse
---------------------
Raccourci clavier global, injecté depuis cockpit_shell.cockpit_frame().

  Ctrl+Alt+P   → palette de recherche
  Escape       → ferme les dialogs ouverts (géré côté Quasar)

Historique : trois raccourcis (Ctrl+K, Ctrl+/, et la touche « / » seule) étaient
déclarés ici, mais register_keybindings() n'était appelé nulle part — ils n'ont
jamais fonctionné. La touche « / » seule était de toute façon un piège : elle
ouvrait la palette dès qu'un slash était saisi hors champ de texte.
"""
from __future__ import annotations

from nicegui import ui


def register_keybindings() -> None:
    """À appeler une fois par page, depuis cockpit_frame."""
    from frontend.components.command_palette import open_command_palette

    def _on_key(e) -> None:
        if (e.action.keydown and e.modifiers.ctrl and e.modifiers.alt
                and e.key.name.lower() == "p"):
            open_command_palette()

    ui.keyboard(on_key=_on_key, ignore=["input", "select", "textarea"])
```

- [ ] **Step 7: Câbler le shell**

Dans `frontend/cockpit_shell.py`, remplacer la ligne 253 :

```python
            ui.html("<kbd>⌘K</kbd>")
```

par :

```python
            ui.html("<kbd>Ctrl Alt P</kbd>")
```

Et dans `cockpit_frame`, juste après `active = _TITLE_TO_NAV.get(page_title, page_title)` (ligne 225) :

```python
    from frontend.keybindings import register_keybindings
    register_keybindings()
```

- [ ] **Step 8: Nettoyer la page Items et le Planning**

Dans `frontend/pages/items.py` :
- supprimer la ligne 38 `from frontend.components.item_search_palette import open_item_search_palette`
- ajouter `from frontend.components.command_palette import open_command_palette` à sa place
- ligne 233 : `search.on("click", open_item_search_palette)` → `search.on("click", open_command_palette)`
- ligne 232 : `ui.html("<kbd>Ctrl+Alt+P</kbd>")` reste correct, ne rien changer
- supprimer les deux dernières lignes du fichier (355-356), le raccourci étant désormais global :

```python
    from frontend.keybindings import register_item_search_keybinding
    register_item_search_keybinding(open_item_search_palette)
```

Dans `frontend/pages/planning_cockpit.py`, ligne 52 :

```python
from frontend.components.item_search_palette import search_items
```

devient :

```python
from frontend.components.command_palette import search_items
```

- [ ] **Step 9: Supprimer la palette dupliquée**

```bash
git rm frontend/components/item_search_palette.py
grep -rn "item_search_palette\|register_item_search_keybinding" --include=*.py .
```

Expected: aucune sortie.

- [ ] **Step 10: Run tests**

Run: `python -m pytest tests/test_command_palette.py tests/test_cockpit_shell.py tests/test_items_sorting.py tests/test_frontend_shell_import.py -v`
Expected: PASS

Puis la suite complète, pour attraper tout appelant oublié :

Run: `python -m pytest -q`
Expected: aucune nouvelle défaillance par rapport à la ligne de base (25 échecs préexistants sur des modules dépréciés, cf. audit du 3 août)

- [ ] **Step 11: Commit**

```bash
git add frontend/components/command_palette.py frontend/keybindings.py frontend/cockpit_shell.py frontend/pages/items.py frontend/pages/planning_cockpit.py tests/test_command_palette.py
git commit -m "refactor: merge both search palettes into one bound to Ctrl+Alt+P"
```

---

### Task 6: Navigation — blocs de planning, lien collège, retrait de Semestres

Trois corrections indépendantes de navigation, regroupées parce qu'aucune ne justifie son propre cycle de revue.

**Files:**
- Modify: `frontend/pages/planning_cockpit.py:404-434` (`_draw_day`)
- Modify: `frontend/pages/course_detail_cockpit.py:400`
- Modify: `frontend/cockpit_shell.py:59` (`_NAV_GROUPS`), `:78` (`_TITLE_TO_NAV`)
- Test: `tests/test_planning_navigation.py` (créer), `tests/test_cockpit_shell.py` (étendre)

**Interfaces:**
- Consumes: `PlannedSlot` (`backend/core/planning/models.py`) — attributs utilisés : `course_id: str | None`, `slot_type: str`.
- Produces: `frontend.pages.planning_cockpit.block_target(slot_type: str, course_id: str | None) -> str | None` — route à ouvrir, ou `None` si le bloc n'est pas navigable.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_planning_navigation.py` :

```python
"""Les blocs Synapse de la grille Planning ouvrent leur cible au clic."""
from pathlib import Path

from frontend.pages.planning_cockpit import block_target


def test_review_block_opens_the_course_sheet():
    assert block_target("review", "c1") == "/cours/c1"
    assert block_target("review_urgent", "c1") == "/cours/c1"
    assert block_target("consolidation", "c1") == "/cours/c1"


def test_lacune_blocks_open_the_weak_points_view():
    assert block_target("lacune", "c1") == "/lacunes"
    assert block_target("lacune_crit", "c1") == "/lacunes"


def test_block_without_a_course_is_not_navigable():
    assert block_target("review", None) is None
    assert block_target("review", "") is None


def test_day_cells_wire_the_click_handler():
    source = Path("frontend/pages/planning_cockpit.py").read_text(encoding="utf-8")

    assert "block_target(" in source
    assert "pl-block-clickable" in source
```

Ajouter à la fin de `tests/test_cockpit_shell.py` :

```python
def test_semestres_is_no_longer_in_the_sidebar():
    from frontend.cockpit_shell import _NAV_GROUPS, _TITLE_TO_NAV

    routes = [route for _group, items in _NAV_GROUPS for _glyph, _label, route, _badge in items]
    assert "/semestres" not in routes
    assert "Semestres" not in _TITLE_TO_NAV.values()


def test_semestres_page_module_is_kept():
    assert Path("frontend/pages/semestres_cockpit.py").exists()
    assert Path("frontend/pages/semestres.py").exists()


def test_course_sheet_links_the_college_to_its_filtered_item_list():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")

    assert 'ui.link(college, f"/items?college={college}")' in source
    assert 'ui.link(college, "/colleges")' not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_planning_navigation.py tests/test_cockpit_shell.py -v`
Expected: FAIL — `ImportError: cannot import name 'block_target'`, plus les trois nouveaux tests de `test_cockpit_shell.py`

- [ ] **Step 3: Ajouter la fonction de routage des blocs**

Dans `frontend/pages/planning_cockpit.py`, au niveau module (après les imports, avant la définition de la page) :

```python
# ── Cible de navigation d'un bloc de la grille ────────────────────────────────

_LACUNE_SLOT_TYPES = {"lacune", "lacune_crit"}


def block_target(slot_type: str, course_id: str | None) -> str | None:
    """
    Route à ouvrir quand on clique le corps d'un bloc de la grille.

    Retourne None pour un bloc non navigable (événement Google Calendar, ou
    slot sans cours rattaché) : le bloc reste alors inerte plutôt que d'ouvrir
    une page vide.
    """
    if slot_type in _LACUNE_SLOT_TYPES:
        return "/lacunes"
    if not course_id:
        return None
    return f"/cours/{course_id}"
```

- [ ] **Step 4: Rendre les blocs cliquables**

Dans `_draw_day`, remplacer la boucle sur `plan.slots` (lignes 412-419) par :

```python
            for slot in plan.slots:
                slot_classes = "pl-block pl-block-task"
                if slot.slot_type == "consolidation":
                    slot_classes += " pl-block-consolidation"
                target = block_target(slot.slot_type, getattr(slot, "course_id", None))
                if target:
                    slot_classes += " pl-block-clickable"
                block = ui.element("div").classes(slot_classes).tooltip(slot.label)
                if target:
                    block.on("click", lambda route=target: ui.navigate.to(route))
                with block:
                    ui.label(slot.label).classes("pl-block-title")
                    if slot.subtitle:
                        ui.label(f"{slot.subtitle} · {slot.duration_min} min").classes("pl-block-sub")
```

et la boucle sur `manual_entries` (lignes 420-424) par :

```python
            for entry in manual_entries:
                target = block_target("manual", entry["course_id"])
                classes = "pl-block pl-block-task" + (" pl-block-clickable" if target else "")
                block = ui.element("div").classes(classes)
                if target:
                    block.on("click", lambda route=target: ui.navigate.to(route))
                with block:
                    title = f"{entry['course_title']} · {entry['activity_type']}"
                    ui.label(title).classes("pl-block-title")
                    ui.label(f"Planifié manuellement · {entry['duration_minutes']} min").classes("pl-block-sub")
```

La boucle sur `events` (lignes 425-432) reste inchangée : un événement Google Calendar n'a pas de cible Synapse.

Ajouter dans le bloc `_CSS` de `planning_cockpit.py`, à la suite des règles `.pl-block` existantes :

```css
.pl-block-clickable { cursor:pointer; }
.pl-block-clickable:hover { border-color:var(--border-strong); background:var(--surface); }
```

- [ ] **Step 5: Corriger le lien collège de la fiche item**

Dans `frontend/pages/course_detail_cockpit.py`, remplacer la ligne 400 :

```python
                ui.link(college, "/colleges")
```

par :

```python
                # Vers la liste filtrée sur ce collège, pas l'index générique :
                # c'est ce qui permet de circuler entre les items d'un même collège.
                ui.link(college, f"/items?college={college}")
```

- [ ] **Step 6: Retirer Semestres de la navigation**

Dans `frontend/cockpit_shell.py`, supprimer la ligne 59 de `_NAV_GROUPS` :

```python
        ("◫", "Semestres", "/semestres", None),
```

et l'entrée correspondante de `_TITLE_TO_NAV` (ligne 78) — retirer `"Semestres": "Semestres",` de la ligne :

```python
    "Collèges": "Collèges", "Semestres": "Semestres", "QCM": "QCM",
```

qui devient :

```python
    "Collèges": "Collèges", "QCM": "QCM",
```

Ne toucher ni à `frontend/pages/semestres.py`, ni à `frontend/pages/semestres_cockpit.py`, ni à leur enregistrement de route : `/semestres` doit rester accessible par URL directe.

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_planning_navigation.py tests/test_cockpit_shell.py tests/test_planning_cockpit_schedule.py tests/test_course_detail_responsive.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/planning_cockpit.py frontend/pages/course_detail_cockpit.py frontend/cockpit_shell.py tests/test_planning_navigation.py tests/test_cockpit_shell.py
git commit -m "feat: open planning blocks on click, link college to its item list, drop Semestres from nav"
```

---

## Vérification finale

- [ ] **Suite complète**

Run: `python -m pytest -q`
Expected: aucune nouvelle défaillance par rapport à la ligne de base établie avant la Task 1. Relever cette ligne de base **avant** de commencer, avec la même commande, et comparer.

- [ ] **Vérification manuelle dans l'application**

Lancer l'application et confirmer les sept critères d'acceptation de la spec :

1. `Ctrl+Alt+P` ouvre la palette depuis n'importe quelle page ; `Ctrl+K` et `/` n'ouvrent rien.
2. Ouvrir trois fiches item les fait apparaître dans « Récents », dans l'ordre inverse de consultation.
3. Reporter d'un jour une tâche en retard de cinq jours la place à demain et la sort de la file « en retard ».
4. « Trier par : Collège » regroupe visiblement les lignes ; la liste occupe toute la largeur sur grand écran.
5. La croix du Flash-Zero est cliquable au survol sans chevaucher « Lancer » ; la correction distingue les deux réponses.
6. Cliquer un bloc du Planning ouvre sa cible ; cliquer le nom du collège sur une fiche item affiche la liste filtrée.
7. « Semestres » a disparu de la sidebar, mais `/semestres` répond toujours.
