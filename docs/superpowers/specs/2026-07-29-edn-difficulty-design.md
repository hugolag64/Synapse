# Réglage de difficulté EDN pour les sessions IA

## Objectif

Permettre de générer des sessions OIC, QCM, DP et KFP adaptées à une préparation réelle aux EDN. Le niveau doit être visible et modifiable dans le dialogue de génération, sans rendre les réglages plus complexes à utiliser.

## Choix fonctionnels

Le dialogue propose quatre niveaux :

- `Standard` : rappel et application directe du cours ;
- `EDN` : niveau par défaut, avec raisonnement clinique et distracteurs plausibles ;
- `Difficile` : informations parasites, pièges fréquents et décisions moins évidentes ;
- `Concours` : cas intégratifs, hiérarchisation, incertitude et distracteurs très proches.

Le niveau est conservé avec la session afin que l’historique indique dans quel contexte la session a été produite et que le rejeu conserve exactement les mêmes questions.

## Génération et routage

Le niveau est ajouté à `PracticeSessionSpec` et injecté explicitement dans le prompt. Le prompt impose notamment :

- une répartition exacte ouvert/fermé ;
- des distracteurs médicalement plausibles ;
- des données utiles et inutiles dans les cas cliniques ;
- un raisonnement clinique proportionné au type OIC/QCM/DP/KFP ;
- une correction pédagogique expliquant chaque piège.

Les niveaux `Standard` et `EDN` utilisent le modèle économique déjà prévu pour la tâche. Les niveaux `Difficile` et `Concours` utilisent Gemini 2.5 Flash pour privilégier la fiabilité et la qualité du raisonnement.

## Interface

Le réglage est un contrôle visuel compact placé dans le dialogue existant, sous le type de session. Le choix `EDN` est présélectionné. Les curseurs de nombre total et de questions ouvertes restent inchangés, avec 0 question ouverte par défaut.

## Historique et compatibilité

Les sessions existantes restent lisibles ; leur niveau est affiché comme `Standard` lorsqu’il n’est pas encore stocké. Les sessions rejouées conservent leur niveau et leur contenu initial.

## Validation

- tests unitaires du modèle et du prompt ;
- tests du routage Standard/EDN vers Flash-Lite et Difficile/Concours vers Flash ;
- test UI du niveau EDN par défaut ;
- test Playwright du changement de niveau et de l’ouverture directe de la session générée ;
- suite complète de tests existante.
