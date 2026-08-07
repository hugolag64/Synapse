# Fréquences EDNpro et priorité de gain — spécification

## Objectif

Enrichir Synapse avec les statistiques de fréquence EDNpro par item afin de
proposer un entraînement directement depuis la fiche item et de calculer une
priorité de gain personnalisée.

EDNpro reste une source tierce fiable mais non officielle. Les statistiques
collectées sont donc affichées avec leur provenance et leur date de collecte.

## Périmètre

La synchronisation porte sur la page EDNpro `/training-v2` et les données
structurées qu'elle charge. Pour chaque item, Synapse conserve :

- la catégorie EDNpro : `indispensable`, `important`, `basique` ou
  `jamais_tombe` ;
- le nombre de sessions d'annales dans lesquelles l'item apparaît ;
- le nombre total de questions rattachées à l'item ;
- les années de passage ;
- la date de dernière collecte ;
- l'URL source et, si nécessaire, un artefact JSON brut pour audit et reprise.

La fréquence EDNpro ne remplace pas la maîtrise Synapse. Elle constitue un
signal externe séparé.

## Synchronisation

La synchronisation est considérée comme due après 180 jours. Au démarrage de
Synapse, le service vérifie la date de dernière collecte et déclenche une
collecte non bloquante lorsqu'elle est due. Un bouton **Synchroniser maintenant**
permet de forcer une mise à jour.

Le collecteur utilise Playwright avec un profil persistant déjà prévu pour
EDNpro. Il ouvre `/training-v2`, écoute les réponses JSON authentifiées et
normalise les lignes par item. Il ne dépend pas du texte ou de la disposition
des cartes pour calculer les statistiques. Si la session Google n'est plus
valide, la synchronisation est interrompue proprement et l'interface indique
qu'une reconnexion est nécessaire ; les anciennes statistiques restent
disponibles.

Les données normalisées sont stockées dans SQLite. Une collecte réussie
remplace atomiquement le snapshot précédent et conserve `collected_at`, afin
que l'interface sache quelle version elle affiche.

## Modèle de données

Une table dédiée, indépendante des annales importées, sera ajoutée :

```text
ednpro_item_frequency
  item_number       TEXT PRIMARY KEY
  priority          TEXT NOT NULL
  session_count     INTEGER NOT NULL
  question_count    INTEGER NOT NULL
  years_json        TEXT NOT NULL
  source_url        TEXT NOT NULL
  collected_at      TEXT NOT NULL
  raw_payload_json  TEXT
```

Le stockage d'une ligne par item permet une lecture rapide dans la fiche item
et évite de recalculer la fréquence depuis tout l'historique des annales à
chaque affichage. Les questions EDNpro importées restent dans les tables de
pratique existantes ; la fréquence est seulement reliée par `item_number`.

## Entraînement depuis la fiche item

Dans l'onglet **Entraînement** d'une fiche item, un encart EDNpro présente :

- la catégorie de fréquence ;
- le nombre de sessions et de questions ;
- les années de passage ;
- la date de mise à jour ;
- un bouton **Travailler les annales**.

Le bouton réutilise le moteur de sessions QCM existant en filtrant les
questions importées dont `item_number` correspond à l'item. Il ne crée pas de
nouveau format de lecteur ni de copie des questions. Si aucune question EDNpro
n'est encore importée, l'interface affiche la statistique mais désactive le
bouton avec une indication claire.

## Priorité de gain

La catégorie EDNpro et la priorité personnalisée sont deux signaux distincts.
Le score personnalisé est calculé localement à partir de :

```text
fréquence EDNpro × (100 - maîtrise actuelle) × disponibilité des questions
```

La fréquence est pondérée par le nombre de sessions, la maîtrise vient du
moteur Synapse existant et la disponibilité est plafonnée à 1 selon le nombre
de questions réellement importées pour l'item. Le score sert à classer les
items et à afficher un potentiel relatif ; il ne prétend pas prédire un rang
ou une note EDN.

## Erreurs et reprise

- Une collecte sans données exploitables ne remplace pas le dernier snapshot.
- Une session EDNpro expirée ne supprime aucune statistique existante.
- Les doublons d'item sont fusionnés pendant la normalisation.
- Les années sont dédupliquées et triées.
- Les données brutes restent limitées à la collecte nécessaire et ne sont pas
  redistribuées.

## Tests et vérification

Le changement sera développé en TDD avec :

- tests de normalisation des cartes/réponses JSON EDNpro ;
- tests de persistance SQLite et de seuil de 180 jours ;
- tests du score de priorité avec maîtrise faible, forte et absence de
  questions importées ;
- test du filtrage d'entraînement par item ;
- test frontend de l'encart fréquence et de l'état désactivé sans questions.

La vérification finale couvrira la suite Python, les tests frontend,
`compileall`, le build frontend et `git diff --check`.
