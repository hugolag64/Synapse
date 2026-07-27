# Recherche Items Ctrl+P et double-clic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une palette de recherche dédiée à la vue Items et rendre fiable l’ouverture par double-clic depuis la file Aujourd’hui.

**Architecture:** La palette Item sera un composant NiceGUI séparé, déclenché par le bouton de la vue `/items` et par Ctrl+P uniquement sur cette route. Elle réutilisera l’index de recherche existant avec un filtrage déterministe numéro/titre/collège et ouvrira directement `/cours/{id}`. Le composant de ligne différera le clic simple afin de laisser le double-clic annuler la sélection et naviguer.

**Tech Stack:** Python, NiceGUI, pytest, index `backend.core.search.service.search_index`.

## Global Constraints

- Ne pas modifier la palette globale Ctrl+K ni ses commandes.
- La recherche porte sur le numéro d’item, le titre et les collèges associés.
- Préserver les fichiers locaux non liés déjà modifiés.

---

### Task 1: Palette de recherche dédiée aux items

**Files:**
- Create: `frontend/components/item_search_palette.py`
- Modify: `frontend/pages/items.py`
- Modify: `frontend/keybindings.py`
- Test: `tests/test_item_search_palette.py`

**Interfaces:**
- Produces `open_item_search_palette() -> None`.
- Produces `search_items(query: str, courses: list) -> list` for deterministic unit tests.
- Ctrl+P calls the palette only when the current route is `/items`.

- [ ] **Step 1: Write failing tests** for exact number/title/college matching, empty query suggestions, and Ctrl+P registration.
- [ ] **Step 2: Run the focused tests** and verify they fail because the component and binding do not exist.
- [ ] **Step 3: Implement the component** with animated dialog CSS, autofocus input, result rows, Escape/Enter hints, and direct navigation.
- [ ] **Step 4: Replace the Items button callback** and visible shortcut label with the dedicated palette.
- [ ] **Step 5: Add route-aware Ctrl+P handling** while leaving Ctrl+K and `/` unchanged.
- [ ] **Step 6: Run focused tests** and verify they pass.

### Task 2: Double-clic fiable dans la file Aujourd’hui

**Files:**
- Modify: `frontend/components/study_task_row.py`
- Test: `tests/test_study_task_row_navigation.py`

**Interfaces:**
- `study_task_row` keeps `on_select` and `on_double_click` callbacks.
- A single click invokes `on_select` after a short debounce; a double-click cancels that pending callback and invokes `on_double_click` immediately.

- [ ] **Step 1: Add a failing regression test** asserting the row implementation has a cancellable single-click delay and double-click cancellation path.
- [ ] **Step 2: Run the focused test** and verify it fails against the current immediate click handler.
- [ ] **Step 3: Implement the debounce** with a per-row NiceGUI timer and cancellation on double-click.
- [ ] **Step 4: Run the focused test and dashboard tests** to verify both behaviors.

### Task 3: Vérification intégrée

**Files:**
- No source changes expected.

- [ ] **Step 1: Run the complete test suite.**
- [ ] **Step 2: Confirm no unrelated dirty files were staged or changed.**
- [ ] **Step 3: Report the exact test result and usage behavior.**
