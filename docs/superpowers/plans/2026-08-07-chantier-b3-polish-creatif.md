# Chantier B3 — Polish créatif : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Animer l'ouverture des collèges (fondu + glissement) et rendre la page Prépa plus vivante (section « Récemment consulté » réelle, relief au survol, apparition échelonnée) — sans toucher à la logique métier ni introduire de couleur décorative.

**Architecture:** Le point Collèges est un ajout CSS pur (une classe d'animation, appliquée au conteneur déjà existant). Le point Prépa ajoute une fonction backend pure et testable (`list_recent_prep_shortcuts`) et une fonction de présentation pure (`relative_time_label`), toutes deux couvertes par des tests directs, avant d'être branchées dans le rendu de la page.

**Tech Stack:** Python 3.12, NiceGUI (Quasar/Vue), SQLite via `backend/core/reviews/local_store.py`, pytest.

## Global Constraints

- Réponses et messages d'interface en français.
- Aucune couleur de wayfinding par plateforme (direction B, écartée par l'utilisateur) — aucune
  nouvelle couleur non-sémantique nulle part dans ce chantier.
- Aucun changement à `_toggle_expand`, `_compute`, `_render` (colleges_cockpit.py) ni à
  `list_prep_providers`, `list_prep_shortcuts`, `build_prepa_view` (prep/catalog.py, prepa.py) —
  uniquement des ajouts.
- La fermeture d'un collège reste instantanée (contrainte architecturale assumée, pas un bug à
  corriger dans ce chantier).
- La section « Récemment consulté » ne doit jamais s'afficher vide — masquée entièrement si
  `list_recent_prep_shortcuts()` retourne une liste vide.
- Commit après chaque tâche, message en anglais préfixé `feat:`/`fix:` (convention du dépôt).
- Les tests tournent avec `./.venv/Scripts/python.exe -m pytest` depuis la racine du dépôt.

## File Structure

| Fichier | Changement | Tâche |
|---|---|---|
| `frontend/pages/colleges_cockpit.py` | `@keyframes cgItemsEnter` + classe `cg-items-enter` sur le conteneur `.cg-items` | 1 |
| `backend/core/prep/catalog.py` | + `list_recent_prep_shortcuts(limit=5)` | 2 |
| `frontend/pages/prepa.py` | + `relative_time_label()`, section « Récemment consulté », relief au survol, apparition échelonnée | 3 |
| `tests/test_colleges_cockpit_ui.py` | + test de présence de l'animation | 1 |
| `tests/test_prep_catalog.py` | + tests de `list_recent_prep_shortcuts` | 2 |
| `tests/test_prepa_page.py` | + tests de `relative_time_label` et de la condition d'affichage | 3 |

---

### Task 1: Animation d'ouverture des collèges

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py:105` (CSS), `:439` (classe du conteneur)
- Test: `tests/test_colleges_cockpit_ui.py` (étendre)

**Interfaces:**
- Consumes: rien.
- Produces: rien (changement CSS pur).

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/test_colleges_cockpit_ui.py` :

```python
def test_college_items_container_plays_an_entrance_animation_on_open():
    """La fermeture d'un collège est instantanée par construction (le nœud est
    détruit, pas transitionné) ; seule l'ouverture peut être animée puisque le
    conteneur est toujours neuf à ce moment-là."""
    from pathlib import Path

    source = Path("frontend/pages/colleges_cockpit.py").read_text(encoding="utf-8")

    assert "@keyframes cgItemsEnter" in source
    assert ".cg-items-enter { animation: cgItemsEnter var(--duration-base) var(--ease-standard) both; }" in source
    assert 'ui.element("div").classes("cg-items cg-items-enter")' in source
```

Si `tests/test_colleges_cockpit_ui.py` n'existe pas déjà, le créer avec ce seul test (aucun autre
test de ce fichier n'est modifié dans cette tâche).

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_colleges_cockpit_ui.py::test_college_items_container_plays_an_entrance_animation_on_open -v`
Expected: FAIL — ni le `@keyframes` ni la classe ne sont encore présents.

- [ ] **Step 3: Ajouter le keyframes**

Dans `frontend/pages/colleges_cockpit.py`, juste après la ligne 105
(`.cg-items { padding:8px 12px 12px 34px; background:var(--surface); border-bottom:1px solid var(--border); overflow-x:auto; }`),
ajouter :

```css
@keyframes cgItemsEnter {
  0% { opacity: 0; transform: translateY(-8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.cg-items-enter { animation: cgItemsEnter var(--duration-base) var(--ease-standard) both; }
```

- [ ] **Step 4: Appliquer la classe au conteneur**

Ligne 439, remplacer :
```python
            with ui.element("div").classes("cg-items"):
```
par :
```python
            with ui.element("div").classes("cg-items cg-items-enter"):
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_colleges_cockpit_ui.py -v`
Expected: 1 passed (ou plus, si le fichier existait déjà avec d'autres tests — tous doivent passer)

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/colleges_cockpit.py tests/test_colleges_cockpit_ui.py
git commit -m "feat: animate college item list entrance with a fade and slide"
```

---

### Task 2: `list_recent_prep_shortcuts` — backend

**Files:**
- Modify: `backend/core/prep/catalog.py` (ajout en fin de fichier, après `record_prep_access`)
- Test: `tests/test_prep_catalog.py` (étendre)

**Interfaces:**
- Consumes: rien de nouveau — réutilise `_ensure_table()` et `local_store._conn()`, déjà présents
  dans ce fichier.
- Produces: `list_recent_prep_shortcuts(limit: int = 5) -> list[dict]` — une entrée par ligne de
  `prep_shortcuts` ayant `last_used` renseigné, triée du plus récent au plus ancien, clés
  identiques à `list_prep_shortcuts()` (`id`, `provider`, `category`, `title`, `description`,
  `url`, `icon`, `enabled`, `last_used`).

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/test_prep_catalog.py` :

```python
def test_list_recent_prep_shortcuts_returns_empty_when_nothing_used(prep_db):
    from backend.core.prep.catalog import list_recent_prep_shortcuts

    assert list_recent_prep_shortcuts() == []


def test_list_recent_prep_shortcuts_only_returns_shortcuts_with_last_used(prep_db):
    from backend.core.prep.catalog import list_prep_shortcuts, record_prep_access, list_recent_prep_shortcuts

    rows = list_prep_shortcuts("EDNpro")
    target = next(r for r in rows if r["title"] == "Masterclass")
    record_prep_access(target["id"])

    recent = list_recent_prep_shortcuts()

    assert len(recent) == 1
    assert recent[0]["title"] == "Masterclass"
    assert recent[0]["last_used"] is not None


def test_list_recent_prep_shortcuts_orders_most_recent_first(prep_db):
    from backend.core.prep.catalog import list_prep_shortcuts, record_prep_access, list_recent_prep_shortcuts

    rows = list_prep_shortcuts("EDNpro")
    first, second = rows[0], rows[1]
    record_prep_access(first["id"])
    record_prep_access(second["id"])

    recent = list_recent_prep_shortcuts()

    assert recent[0]["id"] == second["id"]
    assert recent[1]["id"] == first["id"]


def test_list_recent_prep_shortcuts_respects_limit(prep_db):
    from backend.core.prep.catalog import list_prep_shortcuts, record_prep_access, list_recent_prep_shortcuts

    rows = list_prep_shortcuts("EDNpro")
    for row in rows[:3]:
        record_prep_access(row["id"])

    recent = list_recent_prep_shortcuts(limit=2)

    assert len(recent) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prep_catalog.py -v`
Expected: les 4 nouveaux tests FAIL — `ImportError: cannot import name 'list_recent_prep_shortcuts'`

- [ ] **Step 3: Écrire l'implémentation**

Dans `backend/core/prep/catalog.py`, à la fin du fichier, après `record_prep_access` :

```python
def list_recent_prep_shortcuts(limit: int = 5) -> list[dict]:
    _ensure_table()
    with local_store._conn() as con:
        rows = con.execute(
            "SELECT * FROM prep_shortcuts WHERE enabled=1 AND last_used IS NOT NULL "
            "ORDER BY last_used DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prep_catalog.py -v`
Expected: tous les tests passent (les 2 déjà existants + les 4 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add backend/core/prep/catalog.py tests/test_prep_catalog.py
git commit -m "feat: add list_recent_prep_shortcuts to power a recently-used section"
```

---

### Task 3: Page Prépa — récents, relief au survol, apparition échelonnée

**Files:**
- Modify: `frontend/pages/prepa.py` (imports, `_CSS`, `prepa_page`)
- Test: `tests/test_prepa_page.py` (étendre)

**Interfaces:**
- Consumes: `list_recent_prep_shortcuts(limit=5) -> list[dict]` (Task 2), `record_prep_access(shortcut_id) -> None` (déjà existant).
- Produces: `relative_time_label(last_used: datetime.datetime, now: datetime.datetime) -> str` —
  fonction pure, testable indépendamment du rendu.

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/test_prepa_page.py` :

```python
def test_relative_time_label_buckets_by_recency():
    import datetime

    from frontend.pages.prepa import relative_time_label

    now = datetime.datetime(2026, 8, 7, 14, 0, 0, tzinfo=datetime.timezone.utc)

    assert relative_time_label(now - datetime.timedelta(seconds=30), now) == "à l'instant"
    assert relative_time_label(now - datetime.timedelta(minutes=5), now) == "il y a 5min"
    assert relative_time_label(now - datetime.timedelta(hours=2), now) == "il y a 2h"
    assert relative_time_label(now - datetime.timedelta(days=1), now) == "hier"
    assert relative_time_label(now - datetime.timedelta(days=3), now) == "il y a 3j"


def test_prepa_css_adds_hover_lift_and_staggered_entrance():
    from pathlib import Path

    source = Path("frontend/pages/prepa.py").read_text(encoding="utf-8")

    assert "transform:translateY(-2px)" in source
    assert "box-shadow:var(--shadow-popover)" in source
    assert "@keyframes prepProviderEnter" in source
    assert ".prep-provider:nth-of-type(2) { animation-delay: 60ms; }" in source


def test_prepa_page_hides_recent_section_when_nothing_was_used(monkeypatch):
    """La section « Récemment consulté » ne doit jamais apparaître vide."""
    from pathlib import Path
    import frontend.pages.prepa as prepa_module

    monkeypatch.setattr(prepa_module, "list_recent_prep_shortcuts", lambda limit=5: [])

    source = Path("frontend/pages/prepa.py").read_text(encoding="utf-8")
    assert "if recent:" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prepa_page.py -v`
Expected: les 3 nouveaux tests FAIL — `ImportError: cannot import name 'relative_time_label'`, puis
les assertions de source échouent.

- [ ] **Step 3: Ajouter les imports et la fonction pure**

Dans `frontend/pages/prepa.py`, remplacer la ligne d'import :
```python
from backend.core.prep.catalog import list_prep_providers, list_prep_shortcuts, record_prep_access
```
par :
```python
from datetime import datetime, timezone

from backend.core.prep.catalog import (
    list_prep_providers, list_prep_shortcuts, list_recent_prep_shortcuts, record_prep_access,
)
```

Puis, juste après le bloc `_CSS = """ ... """` (avant `_CATEGORY_ORDER`), ajouter :

```python
def relative_time_label(last_used: datetime, now: datetime) -> str:
    """Libellé relatif compact pour un horodatage passé (« à l'instant », « il y a 5min »…)."""
    delta_seconds = (now - last_used).total_seconds()
    if delta_seconds < 60:
        return "à l'instant"
    minutes = int(delta_seconds // 60)
    if minutes < 60:
        return f"il y a {minutes}min"
    hours = int(delta_seconds // 3600)
    if hours < 24:
        return f"il y a {hours}h"
    days = int(delta_seconds // 86400)
    if days == 1:
        return "hier"
    return f"il y a {days}j"
```

- [ ] **Step 4: Ajouter les règles CSS de relief et d'apparition échelonnée**

Remplacer dans `_CSS` :
```css
.prep-shortcut { border:1px solid var(--border); border-radius:8px; padding:13px 14px; background:var(--bg-alt); transition:border-color .12s, background .12s; }
.prep-shortcut:hover { border-color:var(--accent); background:var(--surface); }
```
par :
```css
.prep-shortcut { border:1px solid var(--border); border-radius:8px; padding:13px 14px; background:var(--bg-alt); transition:border-color .12s, background .12s, transform .12s, box-shadow .12s; }
.prep-shortcut:hover { border-color:var(--accent); background:var(--surface); transform:translateY(-2px); box-shadow:var(--shadow-popover); }
```

Et remplacer :
```css
.prep-provider { border:1px solid var(--border); border-radius:8px; padding:14px 16px; background:var(--bg-alt); }
```
par :
```css
.prep-provider { border:1px solid var(--border); border-radius:8px; padding:14px 16px; background:var(--bg-alt); }
@keyframes prepProviderEnter {
  0% { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.prep-provider { animation: prepProviderEnter var(--duration-base) var(--ease-standard) both; }
.prep-provider:nth-of-type(1) { animation-delay: 0ms; }
.prep-provider:nth-of-type(2) { animation-delay: 60ms; }
.prep-provider:nth-of-type(3) { animation-delay: 120ms; }
```

Et ajouter, à la suite des règles `.prep-category` existantes :
```css
.prep-recent { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
.prep-recent-item { flex:1; min-width:160px; padding:10px 12px; border:1px solid var(--border); border-radius:8px; background:var(--bg-alt); transition:border-color .12s, background .12s, transform .12s, box-shadow .12s; }
.prep-recent-item:hover { border-color:var(--accent); background:var(--surface); transform:translateY(-2px); box-shadow:var(--shadow-popover); }
.prep-recent-title { font-size:13px; font-weight:600; color:var(--text); }
.prep-recent-time { font-size:11px; color:var(--text-muted); margin-top:2px; }
```

- [ ] **Step 5: Brancher la section « Récemment consulté »**

Dans `prepa_page()`, remplacer :
```python
    shortcuts = list_prep_shortcuts()
    providers = list_prep_providers()
    view = build_prepa_view(shortcuts, providers)
```
par :
```python
    shortcuts = list_prep_shortcuts()
    providers = list_prep_providers()
    view = build_prepa_view(shortcuts, providers)
    recent = list_recent_prep_shortcuts()
```

Puis, juste après le bloc topbar (après la fermeture du `with ui.row().classes("w-full items-start justify-between gap-4 pb-5 border-b"):` et avant `with ui.column().classes("w-full gap-4 pt-6"):`), insérer :

```python
            if recent:
                with ui.column().classes("w-full gap-2 pt-5"):
                    ui.label("Récemment consulté").classes("prep-section-title")
                    with ui.element("div").classes("prep-recent"):
                        for item in recent:
                            last_used = datetime.fromisoformat(item["last_used"])
                            with ui.link(target=item["url"], new_tab=True).classes(
                                "prep-recent-item no-underline"
                            ) as link:
                                ui.label(item["title"]).classes("prep-recent-title")
                                ui.label(
                                    relative_time_label(last_used, datetime.now(timezone.utc))
                                ).classes("prep-recent-time")
                            link.on(
                                "click",
                                lambda _event=None, sid=item.get("id"): record_prep_access(sid),
                            )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prepa_page.py -v`
Expected: tous les tests passent (le test déjà existant + les 3 nouveaux)

- [ ] **Step 7: Vérifier l'absence de régression**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prep_catalog.py tests/test_prepa_page.py tests/test_colleges_cockpit_ui.py tests/test_colleges_cockpit_items.py tests/test_colleges_mastery_colors.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/prepa.py tests/test_prepa_page.py
git commit -m "feat: add recently-used shortcuts, hover lift, and staggered entrance to Prepa"
```

---

## Vérification finale

- [ ] **Suite complète**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: aucune nouvelle défaillance par rapport à la ligne de base établie avant la Task 1 (1137
tests passés en sortie du chantier B2). Relever la ligne de base avec la même commande avant de
commencer, comparer après la Task 3.

- [ ] **Vérification manuelle dans l'application**

Lancer l'application et confirmer visuellement :

1. Ouvrir un collège fait apparaître ses cours en fondu + léger glissement vers le bas ; le
   refermer est instantané (comportement assumé, pas un bug).
2. Après avoir cliqué au moins un raccourci Prépa, une section « Récemment consulté » apparaît en
   haut de la page avec un horodatage relatif correct.
3. Sur une base neuve (aucun raccourci jamais cliqué), la section « Récemment consulté »
   n'apparaît pas du tout.
4. Survoler une tuile de plateforme (section principale ou récents) la soulève légèrement avec une
   ombre douce.
5. Au chargement de la page, les sections de plateforme apparaissent l'une après l'autre avec un
   léger décalage, pas toutes d'un coup.
