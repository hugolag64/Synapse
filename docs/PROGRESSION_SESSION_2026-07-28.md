# Synapse — feuille de route actualisée

Date : 28 juillet 2026

## Clôture de session — cockpit, maîtrise, Anki et planning

### Terminé

- Intégration Anki native sur le paquet `Fiches EDN Notion` : lecture du deck,
  mapping item, preuves idempotentes, scheduler natif et boutons Again/Hard/
  Good/Easy.
- Algorithme de maîtrise adaptatif : preuves datées, auto-évaluation,
  QCM/DP/KFP/OIC, Anki et décroissance temporelle adaptative.
- Système d’ancrage des lacunes récurrentes avec priorité, échéance et revue.
- Cockpit Points faibles : sidebar interne, vues Lacunes/Ancrages/À revoir/
  Résolues, grille responsive et priorisation.
- Refonte de la vue Collèges : panneau de pilotage global, progression,
  fragilités, retards, PDF manquants et collèges prioritaires.
- Refonte Planning : vues 1/3/7 jours, colonnes centrées, cartes compactes,
  pilotage de période et file « À placer ».
- Objectifs de charge par date : durée ou nombre d’items. Les urgences restent
  prioritaires ; le surplus est conservé comme créneaux à placer. L’objectif du
  jour est repris dans le cockpit Aujourd’hui.
- Correctifs UI/UX : splitter dashboard, wizard QCM, backdrop dismiss,
  cockpit OIC et affichage de la session Anki.

### Vérification de clôture

- `pytest -q` → **557 passed, 2 warnings**.
- Compilation Python des modules modifiés → succès.
- Les deux warnings sont externes ou préexistants : versions `requests` et
  boucle asyncio dépréciée dans un test historique.

### Suite de la feuille de route

- Tester manuellement les vues Planning 1/3/7 jours et la saisie d’objectifs
  avec les données réelles.
- Affiner la répartition automatique selon les préférences lecture/QCM/Anki et
  la capacité Calendar.
- Continuer les caractérisations de robustesse avant toute nouvelle évolution
  de l’algorithme de maîtrise.

## Terminé

- Correction du splitter dashboard : la sidebar se redimensionne sans élargir
  artificiellement la zone principale.
- Refonte du wizard QCM : style Linear/Synapse, recherche enrichie de cours,
  fermeture par clic sur le backdrop.
- Reconnexion des écritures d’évaluation à `record_evaluation()` :
  - QCM cockpit et QCM classique ;
  - import QCM IA ;
  - auto-évaluation Focus/dashboard ;
  - consolidation et saisies rapides ;
  - évaluation OIC.
- Refonte UI-UX de l’onglet OIC de la fiche item : synthèse compacte, listes
  Rang A/B denses, actions explicites, responsive et tokens Synapse.
- Les données de feedback sont conservées : activités, durée, confiance,
  difficulté, résultat QCM, erreur, score brut et commentaires.
- Vérification historique de l’étape : **495 tests passés**.

## Vérifications déjà couvertes

- Les workflows de validation de séance, consolidation et évaluation sont
  couverts par les tests ciblés et passent.
- Les erreurs répétées et les propositions de lacunes sont couvertes et
  passent.
- L’évaluation OIC et le chargement lazy de l’onglet sont couverts et passent.
- La note Obsidian canonique d’un item partagé par plusieurs collèges, dont le
  cas de l’item 75, est caractérisée et passe.

## Prochain chantier immédiat

Les premiers tests de robustesse sont maintenant en place :

- écritures SQLite concurrentes sérialisées par verrou réentrant ;
- panne Notion convertie en échec explicite avec rollback de la mise à jour
  optimiste ;
- migrations SQLite existantes conservées.

Il reste à caractériser l’idempotence des tâches asynchrones et les pannes
partielles Obsidian/SQLite. Ces tests doivent précéder toute évolution de
l’algorithme de maîtrise.

## Chantiers suivants

- Examiner la concurrence SQLite et l’idempotence des tâches asynchrones.
- Mettre à jour la décision produit sur la maîtrise : score unique ou
  dimensions séparées.

## Règle de travail

Ne pas modifier `mastery.py` ni ajouter de nouvel algorithme avant d’avoir
terminé les tests de caractérisation et validé les comportements de panne.

## Vérification finale — maîtrise adaptative datée (28 juillet 2026)

- Les preuves datées pilotent désormais le score courant : une lecture seule
  reste une preuve faible, une révision manuelle/confidence vaut davantage, et
  les évaluations QCM/DP/KFP/OIC pèsent le plus sur la stabilité.
- Les révisions manuelles utilisent leur `session_date` réelle : à base égale,
  une révision du `2026-07-28` maintient une maîtrise plus haute qu’une preuve
  équivalente datée du `2026-04-29`.
- Les issues Anki sont intégrées comme preuves de rétention (`again`, `hard`,
  `good`, `easy`) et peuvent faire monter ou baisser le score, sans jamais
  remplacer à elles seules la préparation EDN ni valider un QCM.
- La courbe de projection et le score affiché partagent maintenant la même
  projection adaptative, avec un plancher commun fixé à `25`, au lieu de faire
  décroître le graphe avec une formule séparée.
- Vérifications exactes du 28 juillet 2026 :
  - `pytest -q` → `557 passed, 2 warnings` en clôture de session
  - `git diff --check` → échec sur deux espaces finaux préexistants dans
    `frontend/pages/qcm.py:78` et `frontend/pages/qcm.py:79`
  - `python -m compileall backend frontend tests -q` → succès
- Warnings conservés et signalés tels quels :
  - `RequestsDependencyWarning` dans `requests`
  - `DeprecationWarning: There is no current event loop` dans
    `tests/test_delete_course_action.py`
