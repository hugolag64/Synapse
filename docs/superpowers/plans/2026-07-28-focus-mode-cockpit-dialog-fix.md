# Correction du dialogue Mode focus (cockpit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger le dialogue Mode focus cockpit (bloqué en transition, fermeture accidentelle, Échap inopérant) en alignant son prop Quasar sur le classic, et ajouter la couverture de tests qui manquait depuis l'introduction du composant.

**Architecture:** Un seul fichier modifié (`frontend/components/focus_mode_cockpit.py`) : le prop `.props(...)` du dialogue passe de `"full-width full-height"` à `"maximized persistent"` ; `_fmt_timer`/`_elapsed_minutes` passent de closures internes à fonctions de module pures, testables sans instancier NiceGUI.

**Tech Stack:** NiceGUI (Python), Quasar (`q-dialog`), pytest.

## Global Constraints

- `ui.add_head_html` au build synchrone uniquement (déjà respecté par le fichier, non touché).
- Aucun changement de contrat côté appelants (`state.focus_tasks`, `state._on_done/_on_postpone/_on_ignore`, `state.rebuild_all`) ni de rendu visuel.
- Référence de spec : `docs/superpowers/specs/2026-07-28-focus-mode-cockpit-dialog-fix-design.md`.

---

## File Structure

- **Modify** `frontend/components/focus_mode_cockpit.py` — prop du dialogue + extraction de `_fmt_timer`/`_elapsed_minutes` en fonctions de module.
- **Create** `tests/test_focus_mode_cockpit.py` — tests unitaires des deux fonctions + assertion source sur le prop du dialogue.
- **Modify** `design_handoff_synapse_refonte/CLAUDE.md` — cocher l'Étape 16, journal, pointeur de reprise → Étape 17.

---

### Task 1: Tests des fonctions pures et du prop du dialogue

**Files:**
- Create: `tests/test_focus_mode_cockpit.py`

**Interfaces:**
- Consumes : rien (module pas encore modifié).
- Produces : fixe le contrat de `frontend.components.focus_mode_cockpit._fmt_timer(seconds: int) -> str` et `_elapsed_minutes(remaining: int, total: int) -> int | None` que la Task 2 doit satisfaire, plus une assertion source sur `.props("maximized persistent")`.

- [ ] **Step 1: Écrire les tests (échoueront — signatures pas encore module-level, prop pas encore corrigé)**

```python
from frontend.components.focus_mode_cockpit import _fmt_timer, _elapsed_minutes


def test_fmt_timer_pads_minutes_and_seconds():
    assert _fmt_timer(25 * 60) == "25:00"
    assert _fmt_timer(65) == "01:05"
    assert _fmt_timer(5) == "00:05"


def test_fmt_timer_clamps_negative_to_zero():
    assert _fmt_timer(-3) == "00:00"


def test_elapsed_minutes_none_when_timer_never_started():
    assert _elapsed_minutes(remaining=1500, total=1500) is None


def test_elapsed_minutes_rounds_down_and_floors_at_one():
    assert _elapsed_minutes(remaining=1500 - 90, total=1500) == 1
    assert _elapsed_minutes(remaining=1500 - 600, total=1500) == 10


def test_focus_dialog_uses_maximized_persistent_prop():
    source = open("frontend/components/focus_mode_cockpit.py", encoding="utf-8").read()

    assert '.props("maximized persistent")' in source
    assert "full-width full-height" not in source
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `.venv/Scripts/python.exe -m pytest tests/test_focus_mode_cockpit.py -v`
Expected: FAIL — `ImportError: cannot import name '_fmt_timer'` (fonctions encore internes à `open_focus_mode_cockpit`) et l'assertion de prop échoue.

- [ ] **Step 3: Commit**

```bash
git add tests/test_focus_mode_cockpit.py
git commit -m "test: fonctions pures et prop du dialogue Mode focus cockpit"
```

---

### Task 2: Corriger le prop et extraire les fonctions pures

**Files:**
- Modify: `frontend/components/focus_mode_cockpit.py`

**Interfaces:**
- Consumes : rien de nouveau.
- Produces : `_fmt_timer(seconds: int) -> str`, `_elapsed_minutes(remaining: int, total: int) -> int | None` (fonctions de module, validées par la Task 1) ; `open_focus_mode_cockpit(state) -> None` (signature inchangée).

- [ ] **Step 1: Remplacer le prop du dialogue**

Dans `open_focus_mode_cockpit`, remplacer :

```python
    with ui.dialog(value=True).props("full-width full-height") as fdlg:  # noqa: SIM117
```

par :

```python
    with ui.dialog(value=True).props("maximized persistent") as fdlg:  # noqa: SIM117
```

- [ ] **Step 2: Extraire `_fmt_timer` en fonction de module**

Supprimer la closure interne :

```python
    def _fmt_timer(seconds: int) -> str:
        m, s = divmod(max(0, seconds), 60)
        return f"{m:02d}:{s:02d}"
```

Ajouter au niveau module, avant `def open_focus_mode_cockpit(state) -> None:` :

```python
def _fmt_timer(seconds: int) -> str:
    m, s = divmod(max(0, seconds), 60)
    return f"{m:02d}:{s:02d}"
```

Tous les appels existants (`_fmt_timer(timer_state["remaining"])` dans `_render`/`_tick`) restent inchangés — la fonction est toujours accessible par son nom dans la portée du module.

- [ ] **Step 3: Extraire `_elapsed_minutes` en fonction de module**

Supprimer la closure interne :

```python
    def _elapsed_minutes() -> int | None:
        if timer_state["remaining"] == timer_state["total"]:
            return None
        return max(1, (timer_state["total"] - timer_state["remaining"]) // 60)
```

Ajouter au niveau module, à côté de `_fmt_timer` :

```python
def _elapsed_minutes(remaining: int, total: int) -> int | None:
    if remaining == total:
        return None
    return max(1, (total - remaining) // 60)
```

Mettre à jour l'unique appelant dans `_mark_done` :

```python
        open_session_feedback_dialog(
            task, dummy_card, _cockpit_on_done,
            initial_duration_minutes=_elapsed_minutes(timer_state["remaining"], timer_state["total"]),
        )
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `.venv/Scripts/python.exe -m pytest tests/test_focus_mode_cockpit.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/focus_mode_cockpit.py
git commit -m "fix: dialogue Mode focus cockpit maximized+persistent, fonctions testables"
```

---

### Task 3: Vérification navigateur

**Files:** aucun (vérification manuelle).

**Interfaces:** N/A.

- [ ] **Step 1: Démarrer le serveur** (`preview_start` avec la config `.claude/launch.json` existante, `name: "synapse"`)

- [ ] **Step 2: Ouvrir `/todo` (cockpit), cliquer « Démarrer la file »**

Vérifier via `javascript_tool` : `document.activeElement.className` ne doit plus contenir `q-transition--scale-enter-active` après un court délai (transition résolue).

- [ ] **Step 3: Cliquer précisément en dehors du contenu du dialogue (sur le fond)**

Le dialogue doit rester ouvert (comportement `persistent`), contrairement à l'état actuel où un clic mal centré le fermait.

- [ ] **Step 4: Presser Échap (`computer{action:"key", text:"Escape"}`)**

Le dialogue doit se fermer.

- [ ] **Step 5: Rouvrir, démarrer le minuteur, vérifier qu'il décompte**

`document.querySelector('.fm-timer').textContent` doit diminuer après quelques secondes (comme avant le fix — pas de régression sur le comportement qui marchait déjà).

- [ ] **Step 6: Confirmer zéro exception serveur** (`preview_logs`, niveau erreur)

---

### Task 4: Mettre à jour le suivi de la refonte

**Files:**
- Modify: `design_handoff_synapse_refonte/CLAUDE.md`

**Interfaces:** N/A (documentation).

- [ ] **Step 1: Cocher l'étape 16 dans la checklist**

Remplacer :

```markdown
- [ ] **16. Mode focus** (`focus_bar`, `q-dialog` maximized) — tâche + minuteur + ressource + noter une lacune.
```

par :

```markdown
- [x] **16. Mode focus** (`focus_bar`, `q-dialog` maximized) — tâche + minuteur + ressource + noter une lacune. Composant déjà présent (`frontend/components/focus_mode_cockpit.py`), dialogue corrigé et testé le 28/07 (voir Journal).
```

- [ ] **Step 2: Mettre à jour le pointeur de reprise en tête de fichier**

Remplacer :

```markdown
> **Prochaine session = ÉTAPE 16 · Mode focus** (`focus_bar`, `q-dialog` maximized) — tâche + minuteur + ressource + noter une lacune.
```

par :

```markdown
> **Prochaine session = ÉTAPE 17 · Responsive** — 3 col ≥1200px ; panneau → drawer 900–1200px ; sidebar icônes 768–900px ; bottom nav <768px.
```

- [ ] **Step 3: Ajouter l'entrée de journal**

Ajouter à la fin de la section Journal (après l'entrée « 2026-07-28 — Recentrage Lacunes ») :

```markdown
- **2026-07-28 — Étape 16 Mode focus (correction + tests).** Modifié : `frontend/components/focus_mode_cockpit.py`. Nouveau : `tests/test_focus_mode_cockpit.py`. Voir `docs/superpowers/specs/2026-07-28-focus-mode-cockpit-dialog-fix-design.md` et `docs/superpowers/plans/2026-07-28-focus-mode-cockpit-dialog-fix.md`.
  - **Le composant existait déjà** (introduit dans le commit fourre-tout `4486b0a` du 27/07, jamais suivi comme les autres écrans) et rendait fidèlement `15-mode-focus.png`, mais n'avait ni test ni vérification navigateur formelle.
  - **Bug trouvé en vérifiant au navigateur — dialogue bloqué en transition Quasar.** `.props("full-width full-height")` (au lieu de `maximized`, le prop dédié aux dialogues plein écran) laissait le dialogue coincé en `q-transition--scale-enter-active` avec `no-pointer-events` traînant : un clic pourtant bien placé pouvait atterrir sur le fond et fermer toute la session (minuteur perdu), et Échap ne fermait pas le dialogue malgré l'affordance affichée. Fix : `.props("maximized persistent")`, identique au dialogue classic — `persistent` bloque en prime la fermeture accidentelle par clic extérieur.
  - `_fmt_timer`/`_elapsed_minutes` extraites en fonctions de module pures pour être testables isolément (même refactor que `type_tag`/`due_info` dans `study_task_row.py`).
  - Chemin classic (`open_focus_mode` avec `ui_mode='classic'`, `render_review_card`) non touché.
```

- [ ] **Step 4: Commit**

```bash
git add design_handoff_synapse_refonte/CLAUDE.md
git commit -m "docs: étape 16 (Mode focus) cochée, journal, reprise étape 17"
```
