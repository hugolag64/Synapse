# Finir 7.4, barème EDN unifié et fuseau métier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Calculer la maîtrise par item réellement interrogé, utiliser un unique barème EDN dans le lecteur, afficher le détail propositionnel dans React/NiceGUI et rendre le fuseau métier configurable.

**Architecture:** Le serveur reste la source de vérité : le score fermé applique toujours la grille EDN, SQLite conserve le score et les lignes propositionnelles, puis la maîtrise agrège les dernières tentatives par lien question-item. Le lecteur React et la correction NiceGUI consomment le même contrat enrichi. Un résolveur central de fuseau, initialisé par la préférence DataStore avec fallback environnement, remplace les constantes historiques.

**Tech Stack:** Python 3, SQLite, FastAPI/Pydantic, NiceGUI, React/TypeScript/Vitest, pytest, zoneinfo.

## Global Constraints

- Toutes les questions fermées exposent score_mode = "edn" et utilisent la grille 1 / 0,5 / 0,2 / 0.
- Les rangs A/B sont des métadonnées affichables, pas un second mode de score.
- Une preuve de maîtrise QCM/DP utilise uniquement ai_practice_question_items.
- ai_practice_session_items ne doit pas être propagée automatiquement aux questions.
- Une QROC non scorée empêche la preuve EDN complète.
- Les valeurs de fuseau acceptées sont exactement Europe/Paris et Indian/Reunion.
- Le défaut applicatif est Europe/Paris.
- Les tests doivent être écrits et observés en échec avant le code de production correspondant.
- Ne pas reclassifier l’arriéré historique UNESS dans ce chantier.
- Ne pas modifier les appels à date.today() hors des dates métier ciblées par l’audit.

---

## Task 1: Unifier le score fermé sur le barème EDN

**Files:**
- Modify: backend/core/practice/scoring.py, fonction score_closed_attempt
- Test: tests/test_practice_scoring.py

**Interfaces:**
- Consumes: score_closed_attempt(response, choices, answer).
- Produces: ScoredAttempt.score_mode == "edn" pour toute question fermée scorée, avec les mêmes lignes propositionnelles.

- [ ] **Step 1: Write the failing test**

Remplacer l’attente training du test sans rangs par :

~~~python
def test_question_without_rank_still_uses_edn_mode():
    result = score_closed_attempt(
        "A",
        [
            {"id": "A", "reponse_uness": True},
            {"id": "B", "reponse_uness": False},
        ],
    )
    assert result.score_percent == 100.0
    assert result.score_mode == "edn"
    assert result.score_reason == ""
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: pytest tests/test_practice_scoring.py::test_question_without_rank_still_uses_edn_mode -q

Expected: FAIL because the current scorer returns training when ranks are absent.

- [ ] **Step 3: Write minimal implementation**

Dans score_closed_attempt, conserver la normalisation des rangs pour l’affichage, supprimer la branche ranks_known et retourner mode edn avec une raison vide. Ne pas modifier compute_question_score_edn ni les catégories de discordance.

- [ ] **Step 4: Run test to verify it passes**

Run: pytest tests/test_practice_scoring.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add tests/test_practice_scoring.py backend/core/practice/scoring.py
git commit -m "feat: use EDN scoring for every closed practice question"
~~~

---

## Task 2: Faire de question-item la seule source de preuve de maîtrise

**Files:**
- Create: backend/core/practice/item_evidence.py
- Modify: backend/core/practice/mastery.py
- Modify: backend/core/reviews/local_store.py, près des helpers ai_practice
- Create: tests/test_practice_mastery.py
- Modify: tests/test_practice_question_items.py

**Interfaces:**
- Consumes: les questions d’une session, leurs dernières tentatives scorées et ai_practice_question_items.
- Produces: get_session_item_evidence(session_id) -> dict[str, dict] avec score_percent, total_questions, correct_answers, wrong_answers et question_ids.
- Produces: une EvaluationInput(source="qcm", item_number=item lié) par item lié.

- [ ] **Step 1: Write the failing tests**

Créer une fixture SQLite isolée et tester :

~~~python
def test_mastery_aggregates_latest_attempts_per_linked_item(practice_db):
    # Q1 -> 115 à 100 %, Q2 -> 221 à 0 %.
    evidence = item_evidence.get_session_item_evidence(session_id)
    assert evidence["115"]["score_percent"] == 100.0
    assert evidence["115"]["total_questions"] == 1
    assert evidence["221"]["score_percent"] == 0.0
    assert evidence["221"]["total_questions"] == 1

def test_session_item_list_alone_does_not_create_question_evidence(practice_db):
    # ai_practice_session_items contient 115 et 221, sans lien question-item.
    assert item_evidence.get_session_item_evidence(session_id) == {}
~~~

Tester aussi que record_ai_practice_mastery appelle record_evaluation une fois par item, puis ne rappelle rien au second appel.

- [ ] **Step 2: Run tests to verify they fail**

Run: pytest tests/test_practice_mastery.py tests/test_practice_question_items.py -q

Expected: FAIL because la maîtrise actuelle envoie un seul item session-level.

- [ ] **Step 3: Write minimal implementation**

Ajouter un helper qui sélectionne la dernière tentative non vide et scorée de chaque question, joint uniquement les lignes ai_practice_question_items, puis agrège les scores par item. Une question liée à deux items contribue aux deux ; aucun fallback vers ai_practice_session_items.

Modifier record_ai_practice_mastery : conserver le chemin OIC, agréger QCM/DP/KFP par item, appeler record_evaluation une fois par item avec le nombre réel de questions, ne marquer mastery_recorded_at qu’après succès de toutes les évaluations et ne rien enregistrer si aucun lien explicite n’existe.

- [ ] **Step 4: Run tests to verify they pass**

Run: pytest tests/test_practice_mastery.py tests/test_practice_question_items.py tests/test_evaluation_service.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add tests/test_practice_mastery.py tests/test_practice_question_items.py backend/core/practice/item_evidence.py backend/core/practice/mastery.py
git commit -m "feat: record practice mastery per linked question item"
~~~

---

## Task 3: Exposer le texte des propositions dans le contrat backend

**Files:**
- Modify: backend/core/reviews/local_store.py, get_ai_practice_attempt_propositions
- Modify: backend/api/qcm.py, complete_session
- Modify: frontend/components/qcm_replay.py, build_correction_rows
- Modify: tests/test_qcm_api_completion.py
- Modify: tests/test_qcm_replay.py

**Interfaces:**
- Consumes: les lignes persistées et les choix immuables de la question.
- Produces: proposition_id, text, selected, expected, rank, points et discordance.
- Produces: score_mode edn pour les sessions fermées.

- [ ] **Step 1: Write the failing tests**

Étendre le test API de session fermée :

~~~python
payload = response.json()
assert payload["session"]["score_mode"] == "edn"
assert payload["rows"][0]["propositions"][0]["text"] == "A"
assert payload["rows"][0]["propositions"][0]["selected"] == 1
assert payload["rows"][0]["propositions"][0]["expected"] == 1
~~~

Ajouter le même contrat au test NiceGUI de build_correction_rows.

- [ ] **Step 2: Run tests to verify they fail**

Run: pytest tests/test_qcm_api_completion.py tests/test_qcm_replay.py -q

Expected: FAIL because les lignes ne contiennent pas le texte et le test attend encore training.

- [ ] **Step 3: Write minimal implementation**

Lors de la lecture des propositions, décoder choices_json de la question immuable et associer A/B/etc. au texte correspondant, en supportant aussi les choix dictionnaires. Faire remonter les lignes dans build_correction_rows et conserver le même contrat dans la réponse API.

- [ ] **Step 4: Run tests to verify they pass**

Run: pytest tests/test_qcm_api_completion.py tests/test_qcm_replay.py tests/test_practice_scoring.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add tests/test_qcm_api_completion.py tests/test_qcm_replay.py backend/core/reviews/local_store.py backend/api/qcm.py frontend/components/qcm_replay.py
git commit -m "feat: expose EDN proposition details in correction data"
~~~

---

## Task 4: Afficher le barème EDN et les lignes propositionnelles dans React

**Files:**
- Modify: qcm_app/src/types.ts
- Modify: qcm_app/src/main.tsx
- Modify: qcm_app/src/styles.css
- Modify: qcm_app/src/main.test.tsx

**Interfaces:**
- Consumes: CorrectionPayload.session.score_mode et CorrectionRow.propositions.
- Produces: bandeau EDN et correction propositionnelle dans chaque question de la correction.

- [ ] **Step 1: Write the failing tests**

Ajouter aux fixtures une session edn et deux propositions, puis vérifier que le markup contient Barème EDN propositionnel, le texte des propositions, omission et Rang A. Vérifier aussi l’absence de Validé Rang A.

- [ ] **Step 2: Run tests to verify they fail**

Run: cd qcm_app; npm test -- --run src/main.test.tsx

Expected: FAIL because les types et le rendu omettent les lignes propositionnelles et affichent encore un badge Rang A.

- [ ] **Step 3: Write minimal implementation**

Ajouter les types PropositionCorrection, score_mode et propositions. Dans Correction, afficher le bandeau Barème EDN propositionnel et uniquement le score sur 20, sans badge de validation Rang A. Dans CorrectionCard, afficher une liste/table accessible contenant texte, sélection, vérité attendue, rang, points et discordance. Ajouter les styles responsive.

- [ ] **Step 4: Run tests to verify they pass**

Run: cd qcm_app; npm test -- --run src/main.test.tsx; npm run build

Expected: PASS et build réussi.

- [ ] **Step 5: Commit**

~~~bash
git add qcm_app/src/types.ts qcm_app/src/main.tsx qcm_app/src/styles.css qcm_app/src/main.test.tsx
git commit -m "feat: render EDN score and proposition correction in reader"
~~~

---

## Task 5: Afficher le même détail dans la correction NiceGUI

**Files:**
- Modify: frontend/components/qcm_replay.py, open_qcm_correction
- Modify: tests/test_qcm_replay.py

**Interfaces:**
- Consumes: les lignes propositionnelles de build_correction_rows.
- Produces: correction NiceGUI avec le même libellé EDN et les mêmes champs.

- [ ] **Step 1: Write the failing test**

Avec les helpers UI existants, ouvrir une correction et vérifier les labels Barème EDN propositionnel, Sélectionnée, Attendue et la discordance omission.

- [ ] **Step 2: Run test to verify it fails**

Run: pytest tests/test_qcm_replay.py -q

Expected: FAIL car la correction NiceGUI n’affiche pas encore les lignes propositionnelles.

- [ ] **Step 3: Write minimal implementation**

Dans open_qcm_correction, afficher le libellé EDN au-dessus du résumé. Dans chaque expansion, afficher une ligne par proposition avec texte, état sélection/attendu, rang, points et discordance. Ne pas ajouter de second score ni de badge Rang A.

- [ ] **Step 4: Run test to verify it passes**

Run: pytest tests/test_qcm_replay.py tests/test_qcm_api_completion.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add frontend/components/qcm_replay.py tests/test_qcm_replay.py
git commit -m "feat: show EDN proposition correction in NiceGUI replay"
~~~

---

## Task 6: Ajouter le résolveur de fuseau et la préférence Paramètres

**Files:**
- Modify: backend/config/settings.py
- Modify: backend/state/store.py
- Modify: frontend/pages/settings_cockpit.py
- Modify: tests/test_app_timezone.py
- Modify: tests/test_settings.py

**Interfaces:**
- Consumes: préférence timezone et fallback APP_TIMEZONE.
- Produces: get_app_timezone(), set_app_timezone(name), now_local() et business_today() dynamiques.

- [ ] **Step 1: Write the failing tests**

Tester le changement Europe/Paris → Indian/Reunion, le fallback d’une valeur invalide vers Europe/Paris et la présence de timezone = Europe/Paris dans les préférences par défaut.

- [ ] **Step 2: Run tests to verify they fail**

Run: pytest tests/test_app_timezone.py tests/test_settings.py -q

Expected: FAIL car le fuseau est actuellement statique et absent des préférences.

- [ ] **Step 3: Write minimal implementation**

Dans settings.py, définir les deux zones autorisées, ajouter get_app_timezone et set_app_timezone, et faire utiliser now_local la zone courante. Le fallback d’environnement reste le point de départ, avec Europe/Paris comme secours.

Dans DataStore, ajouter timezone aux valeurs par défaut, appliquer la préférence après chargement et synchroniser le résolveur dans set_preference. Ajouter dans settings_cockpit un select Fuseau horaire métier avec les deux choix, sauvegardé immédiatement.

- [ ] **Step 4: Run tests to verify they pass**

Run: pytest tests/test_app_timezone.py tests/test_settings.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/config/settings.py backend/state/store.py frontend/pages/settings_cockpit.py tests/test_app_timezone.py tests/test_settings.py
git commit -m "feat: make business timezone user-configurable"
~~~

---

## Task 7: Supprimer les derniers usages codés en dur de La Réunion

**Files:**
- Modify: backend/core/google/calendar_service.py
- Modify: frontend/pages/planning_cockpit.py
- Modify: frontend/components/course_quick_actions.py
- Modify: backend/core/background.py
- Modify: tests/test_planning_calendar_actions.py
- Modify: tests/test_app_timezone.py

**Interfaces:**
- Consumes: get_app_timezone() et business_today().
- Produces: dates et bornes Calendar dans le fuseau sélectionné.

- [ ] **Step 1: Write the failing tests**

Ajouter des tests qui sélectionnent successivement les deux zones et vérifient les bornes Google Calendar, la date d’une action et la création des dates planning. Utiliser les mocks existants sans authentifier Google.

- [ ] **Step 2: Run tests to verify they fail**

Run: pytest tests/test_planning_calendar_actions.py tests/test_app_timezone.py -q

Expected: FAIL car les trois modules utilisent encore ZoneInfo("Indian/Reunion").

- [ ] **Step 3: Write minimal implementation**

Remplacer les constantes _TZ_REUNION et _PLANNING_TZ par get_app_timezone(). Remplacer les dates métier concernées par business_today(). Dans les payloads Google, utiliser la clé du fuseau courant pour start et end. Dans background.py, utiliser now_local plutôt qu’un objet APP_TIMEZONE importé statiquement. Ne pas toucher aux timestamps UTC d’Anki ou des sources externes.

- [ ] **Step 4: Run tests to verify they pass**

Run: pytest tests/test_planning_calendar_actions.py tests/test_app_timezone.py tests/test_consolidation.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/core/google/calendar_service.py frontend/pages/planning_cockpit.py frontend/components/course_quick_actions.py backend/core/background.py tests/test_planning_calendar_actions.py tests/test_app_timezone.py
git commit -m "fix: use configured timezone in planning and calendar"
~~~

---

## Task 8: Vérification complète

**Files:**
- Verify: tests/test_practice_scoring.py, tests/test_practice_mastery.py, tests/test_qcm_api_completion.py, tests/test_qcm_replay.py, tests/test_app_timezone.py, qcm_app/src/main.test.tsx

- [ ] **Step 1: Run focused Python verification**

Run: pytest tests/test_practice_scoring.py tests/test_practice_mastery.py tests/test_practice_question_items.py tests/test_qcm_api_completion.py tests/test_qcm_replay.py tests/test_app_timezone.py tests/test_planning_calendar_actions.py -q

Expected: PASS for les tests ciblés.

- [ ] **Step 2: Run React verification**

Run: cd qcm_app; npm test -- --run; npm run build

Expected: PASS et build réussi.

- [ ] **Step 3: Run the complete Python suite**

Run: pytest -q

Expected: distinguer les éventuels échecs historiques Cockpit/IA/Anki des régressions de ce chantier ; aucune nouvelle régression ne doit être introduite.

- [ ] **Step 4: Inspect the final diff**

Run: git status --short; git diff --check

Expected: seuls les fichiers prévus sont modifiés et aucune erreur de whitespace n’est signalée.
