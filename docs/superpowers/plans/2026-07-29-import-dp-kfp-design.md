# Import DP/KFP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Importer des banques DP/KFP préparées dans ChatGPT, les rattacher aux ITEMS et les conserver dans Synapse sans appel API.

**Architecture:** Un parseur accepte un JSON versionné et valide chaque dossier, ses questions et ses références ITEM. Le stockage SQLite conserve les cas importés, leur statut de validation et leur provenance. L’interface propose l’import depuis la vue QCM et le cockpit ITEM, avec signalement des références ITEM absentes ou ambiguës.

**Tech Stack:** Python stdlib, SQLite existant, NiceGUI, pytest.

## Global Constraints

- Aucun appel Gemini pendant l’import.
- Les associations ITEM incertaines ne sont jamais appliquées silencieusement.
- Les DP/KFP importés restent rejouables et historisés.
- Le format initial supporté est JSON UTF-8, avec export Markdown possible dans une étape ultérieure.

### Task 1: Contrat et parseur JSON

**Files:**
- Create: `backend/core/practice/importer.py`
- Test: `tests/test_practice_importer.py`

Le parseur expose `parse_practice_bank(payload) -> ImportBatch`, accepte `{"version": 1, "source": "...", "cases": [...]}`, valide `kind` (`dp` ou `kfp`), `item_numbers`, `title`, `stem`, `questions`, `answer` et `explanation`, et renvoie un statut `ready` ou `needs_review`.

### Task 2: Persistance SQLite

**Files:**
- Modify: `backend/core/reviews/local_store.py`
- Test: `tests/test_practice_importer.py`

Ajouter `imported_practice_cases` et `imported_practice_questions`, avec `import_practice_batch`, `get_imported_practice_cases` et `get_import_review_queue`. Dédupliquer par empreinte du cas et conserver source, date, ITEMs, statut et correction.

### Task 3: Interface d’import

**Files:**
- Modify: `frontend/components/ai_practice_panel.py`
- Modify: `frontend/pages/qcm_cockpit.py`
- Test: `tests/test_practice_importer_ui.py`

Ajouter un bouton `Importer DP/KFP`, un upload JSON, un aperçu du nombre de cas/ITEMs, puis une confirmation. Le cockpit ITEM affiche les cas importés associés et les cas nécessitant une vérification.

### Task 4: Documentation et vérification

**Files:**
- Modify: `docs/AI_MODEL_ROUTING.md`
- Create: `docs/IMPORT_DP_KFP.md`

Documenter le format JSON, l’absence de coût API, les règles de validation et les exemples d’usage. Exécuter les tests ciblés puis la suite complète.
