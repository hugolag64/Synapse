# Cours FAC — Préparations automatiques dans la boucle

> Design validé en conversation le 19 août 2026.

## Objectif

Afficher le calendrier de la FAC dans Synapse et transformer les cours imminents en tâches de préparation dans la boucle quotidienne.

Le calendrier FAC est identifié par :

`kvj2875m68cng7oeiq6mbfh8k20ha1ru@import.calendar.google.com`

Pour un événement prévu dans deux jours, Synapse crée les tâches manquantes à J-2. Si Synapse n’a pas traité l’événement à J-2, le traitement est rattrapé automatiquement à J-1.

La source de vérité est SQLite. Notion peut recevoir une copie lisible, mais aucune décision métier ne dépend de la lecture ou de la validation dans Notion.

## Décisions métier

### Événements pris en compte

Seuls les événements dont le titre contient explicitement `Item` ou `Items` suivi d’un ou plusieurs numéros sont pris en compte.

Exemples reconnus :

- `UE2.S7 Médecine Légale - Item 13` → item `13` ;
- `UE2.S7 Médecine Légale - Item 57` → item `57` ;
- `UE7.S7 Orthopédie - items 363, 362, 334, 365` → items `363`, `362`, `334`, `365`.

Les événements sans item explicite, comme `UE14 LCA - Introduction` ou `Choix des lieux de stage`, sont ignorés par le générateur de préparations. Les numéros présents dans `UE7.S7`, les horaires ou les salles ne sont jamais interprétés comme des items.

Les items sont dédoublonnés dans un même événement. Le flux cible exclusivement les fiches collège ; les fiches UE sont hors périmètre.

### Actions de préparation

Pour chaque item identifié, Synapse évalue l’état local du cours et crée uniquement les tâches manquantes :

1. lier le PDF si aucun PDF collège n’est lié ;
2. créer ou lier la fiche Obsidian si la référence Obsidian est vide ;
3. faire le résumé si le résumé collège n’est pas marqué comme fait ;
4. faire une première lecture si aucune date de première lecture collège n’existe.

Ces actions restent des tâches à faire. Synapse ne réalise pas automatiquement le résumé, la lecture, la création de fiche ou la liaison du PDF.

Les boutons d’action ouvrent les écrans ou raccourcis existants, mais ne valident jamais automatiquement la tâche. La validation est un clic manuel séparé.

### Première lecture et cycle de révision

La validation de la tâche `Première lecture` utilise comme date d’ancrage la date du cours, même si la tâche est validée à J-2 ou J-1.

Le cycle collège est :

| Jalon | Date calculée |
|---|---|
| Première lecture | date du cours |
| J1 | date du cours + 1 jour |
| J3 | date du cours + 3 jours |
| J7 | date du cours + 7 jours |
| J14 | date du cours + 14 jours |
| J30 | date du cours + 30 jours |

Le moteur de révision SQLite doit donc intégrer `J1`, qui n’est pas encore présent dans le code actuel, tout en conservant J3, J7, J14 et J30. Les dates suivantes alimentent la boucle de révision normale.

## Architecture

### Source de vérité locale

Le workflow de préparation lit et écrit l’état du cours depuis les dépôts SQLite locaux : PDF collège, référence Obsidian, statut du résumé et date de première lecture collège.

La logique ne doit pas appeler Notion pour décider qu’une action est manquante ou terminée. Les écritures Notion éventuelles sont des projections secondaires et peuvent échouer sans bloquer SQLite.

Les données de planification de la première lecture et des jalons J1/J3/J7/J14/J30 sont persistées dans un état local SQLite, séparé de Notion. Cet état est indexé par `(course_id, context)` et contient au minimum `first_read_date`, `j1_date`, `j3_date`, `j7_date`, `j14_date`, `j30_date` et `updated_at`. Le contexte utilisé par ce flux est toujours `college`.

La validation de la première lecture crée ou met à jour cette ligne avec les six dates calculées. Le moteur de révision lit ces dates locales en priorité ; les anciennes dates provenant de Notion ne servent qu’à la compatibilité des données historiques et ne peuvent pas écraser une valeur locale.

### Tâches de préparation

Une table SQLite dédiée `course_prep_tasks` porte les tâches opérationnelles de ce flux. Elle est distincte de `review_history`, qui reste réservé à l’historique et au suivi des révisions espacées.

Chaque ligne contient au minimum :

- `id` ;
- `course_id` ;
- `item_number` ;
- `lecture_date` ;
- `calendar_event_id` ;
- `calendar_title` ;
- `task_type` : `pdf`, `obsidian`, `resume` ou `first_read` ;
- `status` : `todo`, `done` ou `cancelled` ;
- `created_at` ;
- `updated_at` ;
- `completed_at`.

Une contrainte unique sur `(course_id, lecture_date, task_type)` garantit l’idempotence entre le traitement J-2, le rattrapage J-1 et les exécutions répétées. `calendar_event_id` et `calendar_title` servent à conserver la provenance et à suivre les modifications du calendrier. Lorsqu’un événement est déplacé, la ligne existante `todo` est mise à jour vers la nouvelle `lecture_date` ; elle n’est pas supprimée puis recréée.

### Détection et génération

À chaque exécution de la routine quotidienne ou du mécanisme de synchronisation équivalent, Synapse :

1. récupère les événements FAC à J+2 et J+1 ;
2. parse les titres ;
3. résout les numéros dans le catalogue local SQLite ;
4. ignore les items introuvables sans créer de fausse tâche ;
5. compare l’état local du cours aux quatre actions ;
6. insère les tâches manquantes de façon idempotente ;
7. expose les tâches `todo` du jour dans la boucle.

Le passage à J-1 constitue le rattrapage automatique. Plusieurs événements portant le même item le même jour ne créent qu’une seule série de tâches.

## Interface utilisateur

Les tâches apparaissent dans un bloc `Préparations FAC` de la boucle du jour.

Chaque ligne affiche :

- l’item et le titre du cours ;
- l’action à effectuer ;
- l’état de la tâche ;
- un bouton `Ouvrir` ou `Raccourci` ;
- un bouton `Valider`.

Les raccourcis réutilisent les actions existantes de Synapse : liaison du PDF, création/lien de la fiche Obsidian, accès au résumé et ouverture de la fiche pour la première lecture.

La validation écrit immédiatement dans SQLite. Une projection Notion peut être générée, mais aucune synchronisation retour n’est requise.

## Gestion des changements et erreurs

- Une indisponibilité Google Calendar ne supprime et ne modifie aucune tâche locale existante.
- Un item absent de SQLite produit un avertissement visible et journalisé.
- Une donnée déjà présente dans SQLite empêche la création de la tâche correspondante.
- Une tâche déjà validée ne réapparaît pas.
- Si un événement est déplacé, les tâches `todo` associées suivent la nouvelle date.
- Si un événement est annulé, les tâches `todo` associées passent à `cancelled` sans suppression de l’historique.
- Une erreur de projection Notion ne bloque pas la génération ni la validation SQLite.

## Tests attendus

Les tests doivent couvrir :

- parsing de `Item` et `Items` ;
- absence de faux positifs sur les numéros d’UE, horaires et salles ;
- extraction de plusieurs items et dédoublonnage ;
- résolution d’un item dans SQLite et comportement pour un item absent ;
- création conditionnelle des quatre types de préparation ;
- idempotence entre J-2, J-1 et exécutions répétées ;
- validation manuelle et transitions de statut ;
- calcul des dates Première lecture, J1, J3, J7, J14 et J30 ;
- déplacement et annulation d’un événement ;
- indisponibilité de Google Calendar ou de Notion ;
- affichage des préparations dans la boucle ;
- non-régression du moteur de révision existant.

## Hors périmètre

- traiter les événements FAC sans numéro d’item ;
- préparer automatiquement les fiches UE ;
- générer automatiquement le contenu du résumé ;
- valider automatiquement une tâche après ouverture d’un raccourci ;
- utiliser Notion comme source de vérité ;
- créer une synchronisation retour Notion → SQLite.
