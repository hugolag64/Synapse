# Mode Focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Brancher le mode Focus cockpit plein écran sur le flux de révision existant, sans modifier le rendu classic.

**Architecture:** Le composant `frontend/components/focus_mode_cockpit.py` encapsule le rendu cockpit, le minuteur et la navigation entre tâches. `frontend/pages/dashboard/_reviews.py::open_focus_mode` reste le point d’entrée partagé et délègue uniquement lorsque `ui_mode == "cockpit"`; le chemin classic reste inchangé.

**Tech Stack:** Python 3.11, NiceGUI 3.8, pytest, ruff.

## Global Constraints

- Ne pas toucher au backend.
- Brancher sur le flag `ui_mode` sans toucher au chemin classic.
- Utiliser les tokens CSS existants et `ui.add_head_html` uniquement au build synchrone.
- Réutiliser les dialogs existants pour la lacune et le feedback de session.
- Conserver les callbacks `state._on_done`, `state._on_postpone`, `state._on_ignore` et `state.rebuild_all`.

### Task 1: Intégrer le composant cockpit

**Files:**
- Modify: `frontend/pages/dashboard/_reviews.py` dans `open_focus_mode`
- Use: `frontend/components/focus_mode_cockpit.py`

**Interfaces:**
- Consumes: `DashboardState`, `data_store.preferences['ui_mode']`, `open_focus_mode_cockpit(state)`.
- Produces: délégation cockpit transparente pour les pages Aujourd’hui, Révisions et Détail item.

- [ ] Ajouter l’early return cockpit au début de `open_focus_mode`, après le garde `focus_tasks` ou avant la construction du dialog.
- [ ] Vérifier que le chemin classic conserve son rendu et ses callbacks inchangés.
- [ ] Vérifier que l’import du composant reste local pour éviter un couplage import-time inutile.

### Task 2: Vérifier le composant et les intégrations

**Files:**
- Test: `tests/test_focus_mode_cockpit.py` si un test isolé est nécessaire
- Verify: `frontend/components/focus_mode_cockpit.py`, `frontend/pages/dashboard/_reviews.py`

**Interfaces:**
- Consumes: branchement de Task 1 et contrat `DashboardState` existant.
- Produces: vérification syntaxique, lint ciblé, tests unitaires et absence de modification backend/classic.

- [ ] Compiler les deux modules avec `py_compile`.
- [ ] Lancer les tests ciblés puis la suite pytest disponible.
- [ ] Lancer ruff sur les fichiers modifiés.
- [ ] Contrôler le diff final et l’état Git avant de conclure.

