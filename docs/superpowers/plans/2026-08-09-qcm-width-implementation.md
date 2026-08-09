# Largeur QCM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aligner les lignes QCM sur toute la largeur de l'en-tête.

**Architecture:** Le contrat CSS partagé `.qc-head, .qc-row` conserve ses tracks existantes et ajoute une largeur explicite à 100 %. Les cellules restent tronquées dans leur track.

**Tech Stack:** Python, NiceGUI, CSS Grid, pytest, Chromium via Playwright.

## Global Constraints

- Ne pas modifier les scores, sessions, filtres ou actions QCM.
- Ne pas ajouter les fichiers utilisateur existants au commit.
- Vérifier la largeur réelle dans Chromium après déploiement.

---

### Task 1: Correction de largeur

**Files:**
- Modify: `frontend/pages/qcm_cockpit.py`
- Modify: `tests/test_qcm_cockpit_ui.py`

- [x] **Step 1: Test rouge** — vérifier `width:100%`, `box-sizing:border-box` et `min-width:0` dans le contrat QCM ; l'ancien CSS échoue.
- [x] **Step 2: Correction** — ajouter les règles partagées sans toucher aux tracks métier.
- [x] **Step 3: Vérification locale** — tests ciblés `28 passed`, suite complète `1313 passed, 2 warnings`.
- [x] **Step 4: Commit et push** — `94b5170` (`fix: stretch QCM course rows to full width`).

### Task 2: QA et livraison

- [ ] **Step 1: Déployer** — exécuter la commande SSH habituelle sur le homeserver.
- [ ] **Step 2: Mesurer Chromium** — vérifier que la largeur de `.qc-head` et `.qc-row` est identique.
