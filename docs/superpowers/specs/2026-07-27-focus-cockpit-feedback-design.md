# Synapse — reconnexion du retour de session Focus cockpit

Date : 27 juillet 2026  
Statut : conception validée par Hugo

## Objectif

Faire persister, depuis le mode Focus cockpit, l'intégralité du retour de
session déjà saisi dans le wizard partagé : activités, durée, confiance,
difficulté, résultat QCM, catégorie d'erreur et détail de l'erreur.

Une erreur isolée reste un signal enregistré. Elle ne crée pas directement une
lacune : le pipeline existant doit appliquer son seuil de répétition et ne
proposer une lacune qu'à ce moment-là.

## Périmètre

- Réutiliser le wizard `open_session_feedback_dialog` existant.
- Ajouter un adaptateur commun qui reçoit un résultat de session complet et le
  transmet au workflow métier de validation déjà utilisé par les autres vues.
- Reconnecter le callback Focus cockpit à cet adaptateur.
- Ajouter des tests de caractérisation de la persistance et de la proposition
  différée de lacune.

## Hors périmètre

- Nouvelle interface ou nouveau formulaire.
- Modification du calcul de maîtrise.
- Nouveau seuil de répétition ou nouvelle politique de lacunes.
- Refonte globale en événement métier `learning_event`.

## Conception

Le wizard reste la source de collecte des données. À sa validation, il passe
un résultat normalisé au callback Focus, sans supprimer les paramètres
existants pendant cette reconnexion. L'adaptateur fait suivre tous les champs
au service de complétion de révision ; il ne contient ni logique UI ni règle
de maîtrise.

Le service existant reste responsable des écritures SQLite de session et du
pipeline QCM/lacunes. Ainsi, Focus produit les mêmes données que les autres
points d'entrée et ne peut pas créer une lacune après une seule erreur.

## Flux

1. L'utilisateur termine une session dans Focus cockpit.
2. Le wizard partagé recueille le retour détaillé.
3. Le callback Focus passe le résultat complet à l'adaptateur commun.
4. L'adaptateur appelle la complétion métier existante.
5. La session est persistée ; le pipeline existant enregistre le signal QCM
   et ne propose une lacune qu'au seuil de répétition configuré.
6. Focus reconstruit sa vue après succès ; en cas d'échec métier, il ne montre
   pas la session comme validée.

## Critères d'acceptation

- Une validation Focus persiste `qcm_result`, `weak_category` et
  `weak_detail` dans la session.
- Une unique erreur n'ajoute pas de lacune.
- La répétition selon le seuil existant déclenche au plus une proposition de
  lacune pour le même signal.
- Les tests ciblés sont verts, sans régression de la suite concernée.

