# Alignement de la grille Collèges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fixer la largeur de la colonne Action pour aligner l'en-tête et les lignes de la grille des items Collèges.

**Architecture:** Le contrat `DataGrid` et le template CSS de `.cg-item-head` / `.cg-item` partageront la même grille à huit colonnes, avec une colonne Action fixe de `88px`. Les cellules directes auront `min-width:0` pour préserver l'ellipsis sans recalcul de largeur.

**Tech Stack:** Python, NiceGUI, CSS Grid, pytest, Chromium via Playwright.

## Global Constraints

- Ne pas modifier les métriques lecture, maîtrise, statut, retard, prochaine ou QCM.
- Ne pas ajouter au commit les fichiers utilisateur déjà modifiés ou non suivis.
- Commit et push sur `main`, puis tenter la commande de mise à jour homeserver habituelle.

---

### Task 1: Verrouiller le contrat d'alignement

**Files:**
- Modify: `tests/test_colleges_cockpit_ui.py`

- [x] **Step 1: Ajouter le test rouge**

Ajouter une assertion qui exige `GridColumn("action", "", "88px")` et `grid-template-columns:... 88px;` dans le CSS source.

- [x] **Step 2: Exécuter le test et constater l'échec**

Run: `pytest tests/test_colleges_cockpit_ui.py::test_college_item_grid_uses_fixed_action_track -q`

Expected: FAIL car le code utilise encore `auto`.

### Task 2: Corriger la grille

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py`

- [x] **Step 1: Remplacer `auto` par `88px`**

Utiliser `88px` pour la huitième track CSS et la colonne `action` du `DataGrid`. Ajouter `.cg-item-head > *, .cg-item > * { min-width:0; box-sizing:border-box; }`.

- [x] **Step 2: Exécuter le test vert et les tests ciblés**

Run: `pytest tests/test_colleges_cockpit_ui.py tests/test_colleges_cockpit_items.py tests/test_college_validation.py tests/test_college_validation_ui.py -q`

Expected: PASS.

- [ ] **Step 3: Committer la correction**

```bash
git add frontend/pages/colleges_cockpit.py tests/test_colleges_cockpit_ui.py docs/superpowers/specs/2026-08-09-colleges-grid-alignment-design.md docs/superpowers/plans/2026-08-09-colleges-grid-alignment-implementation.md
git commit -m "fix: align college item grid columns"
git push origin main
```

### Task 3: Vérifier la livraison

- [ ] **Step 1: Exécuter la suite complète**

Run: `pytest -q`

- [ ] **Step 2: Vérifier Chromium**

Sur `/colleges`, ouvrir un collège comportant au moins une ligne d'item et confirmer visuellement que les axes de `Lecture`, `Maîtrise`, `Statut`, `Retard`, `Prochaine`, `QCM` et `Action` sont identiques entre l'en-tête et les lignes.

- [ ] **Step 3: Mettre à jour le rapport de déploiement**

Ajouter le résultat de la suite, de Chromium et de la tentative homeserver dans `DEPLOYMENT_SESSION_2026-08-09.md`, puis committer et pousser ce rapport séparément.
