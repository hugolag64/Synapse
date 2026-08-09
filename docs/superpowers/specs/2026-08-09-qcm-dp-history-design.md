# Historique rejouable QCM / DP — Design

Date : 2026-08-09

## Objectif

Rendre l’historique rejouable lisible quand il contient plusieurs types de
sessions IA. Les sessions QCM et DP ne doivent plus être présentées comme une
liste homogène, car leurs usages et leurs actions principales diffèrent.

## Décision

La colonne « Historique rejouable » conserve sa recherche et son filtre d’état,
mais affiche deux sections fixes :

- **Historique QCM** : sessions QCM avec les actions existantes de sélection,
  reprise/correction, rejeu et suppression.
- **Historique DP** : sessions DP avec les mêmes actions génériques, plus une
  action explicite **Tuteur DP**.

L’action Tuteur DP réutilise le dialogue existant. Elle reconstruit son contexte
à partir des cinq premiers énoncés de la session DP et conserve l’ITEM, le cours
et l’identifiant de session comme contexte d’ouverture. Les erreurs et lacunes
ne sont pas inventées dans cette vue globale : elles restent vides si elles ne
sont pas disponibles dans le contexte de l’ITEM.

## Contrats conservés

- La recherche et le filtre de statut s’appliquent aux deux sections.
- La sélection, la correction, le rejeu et la suppression utilisent les mêmes
  callbacks qu’avant.
- Une session sans `practice_kind` reste classée QCM par compatibilité avec les
  anciennes données.
- La séparation est uniquement une présentation : aucune migration SQLite et
  aucun changement de score ou de maîtrise n’est introduit.

## Vérification attendue

Vérifier une liste vide, une liste uniquement QCM, une liste uniquement DP et
une liste mixte. En production, vérifier que les deux titres sont visibles et
que le bouton Tuteur DP ouvre bien le dialogue existant.
