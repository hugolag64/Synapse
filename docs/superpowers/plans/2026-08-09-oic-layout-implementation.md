# Uniformisation OIC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabiliser les trois colonnes des lignes OIC sur desktop et mobile.

**Architecture:** Le composant partagé `frontend/components/oic_panel.py` définit une grille code / contenu / actions. Le contenu reste flexible, les deux autres zones sont fixes et bornées.

**Tech Stack:** Python, NiceGUI, CSS Grid, pytest.

## Global Constraints

- Ne pas modifier les données ni les actions OIC.
- Conserver les titres longs tronqués et la responsive mobile.
- Ne pas ajouter les fichiers utilisateur existants au commit.

---

### Task 1: Contrat et correction

**Files:**
- Modify: `tests/test_course_detail_oic_tab.py`
- Modify: `frontend/components/oic_panel.py`

- [x] **Step 1: Test rouge** — remplacer l'attente de la track `auto` par `110px minmax(0,1fr) 132px` et exécuter le test ciblé.
- [x] **Step 2: Correction minimale** — fixer les tracks desktop/mobile et ajouter `min-width:0` / `box-sizing:border-box`.
- [x] **Step 3: Vérification** — tests ciblés `9 passed`, suite complète `1312 passed, 2 warnings`.
- [x] **Step 4: Commit et push** — `a425e5f` (`fix: stabilize OIC panel row layout`).

### Task 2: Livraison

- [ ] **Step 1: QA navigateur après déploiement** — ouvrir un item avec OIC de niveaux différents et vérifier l'alignement code, titre, niveau et actions.
- [ ] **Step 2: Déploiement homeserver** — exécuter la commande habituelle après rétablissement de l'authentification SSH.
