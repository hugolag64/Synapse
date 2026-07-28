# Specification — Révision Anki dans Synapse

## Décision validée

Le paquet Anki existant `Fiches EDN Notion` reste la source des cartes. Synapse ne crée pas de nouvelles cartes.

La première phase permet de réviser ces cartes dans Synapse, tout en faisant calculer les intervalles et le planning par le moteur natif d'Anki. Les résultats sont ensuite enregistrés dans l'historique et l'algorithme de maîtrise Synapse.

Une seconde phase pourra ajouter une extension AnkiConnect pour répercuter les réponses faites dans Synapse dans le planning Anki.

## Objectifs de la première phase

- Détecter AnkiConnect localement.
- Limiter l'intégration au paquet `Fiches EDN Notion`.
- Identifier les cartes par leur `cardId` et leur identifiant de note.
- Rattacher les cartes aux items depuis les noms de sous-paquets.
- Gérer les sous-paquets contenant plusieurs numéros d'items.
- Afficher les cartes dues ou sélectionnées dans un mode de révision Synapse.
- Envoyer la réponse donnée dans Synapse au moteur natif Anki : `again`, `hard`, `good`, `easy`.
- Récupérer après chaque réponse l'intervalle, la maturité et l'état de la carte recalculés par Anki.
- Faire contribuer ces réponses à la maîtrise des connaissances, sans les confondre avec une évaluation QCM EDN.
- Importer les historiques Anki existants quand ils deviennent disponibles.

## Ce qui ne compte pas

- Le simple fait qu'une carte existe dans le paquet.
- Le nombre total de cartes créées.
- Le statut « paquet complet ».
- La présence d'AnkiConnect quand aucune carte n'a été révisée.
- Une indisponibilité temporaire d'AnkiConnect, qui ne doit pas créer de pénalité.

## Mapping

Le mapping initial repose sur la hiérarchie des decks :

```text
Fiches EDN Notion::Spécialité::221. Athérome
```

Les decks avec plusieurs numéros sont rattachés à chacun des items correspondants, sans multiplier l'évidence : une même réponse Anki ne doit être comptée qu'une fois dans l'historique source.

Les tags ne sont pas requis pour la première phase. Le champ `ID (hidden)` est conservé comme identifiant de note utile pour la stabilité du mapping.

## Historique et algorithme

Chaque révision est une preuve indépendante, avec :

- source : `anki` ou `synapse_anki` ;
- card ID et note ID si disponibles ;
- item(s) associé(s) ;
- réponse choisie ;
- date ;
- intervalle et maturité Anki lorsqu'ils sont disponibles.

Les réponses issues d'Anki ou de Synapse alimentent principalement la maîtrise des connaissances. Elles ne remplacent pas les évaluations QCM, DP et KFP dans le score de préparation EDN.

L'algorithme doit éviter le double comptage lorsqu'un même historique Anki est importé plusieurs fois.

## Hors périmètre première phase

- Création de cartes ou de paquets dans Synapse.
- Modification automatique du contenu des cartes Anki.
- Synchronisation de contenu bidirectionnelle.

## Composant d'intégration requis

Une extension AnkiConnect dédiée exposera une action contrôlée permettant à Synapse de transmettre une réponse pour un `cardId`. Cette extension appellera le même scheduler que l'interface Anki, puis renverra le nouvel état de la carte. La phase devra être précédée par des tests sur les doublons, les cartes suspendues, les cartes en apprentissage et les décalages horaires.

## Critères d'acceptation

- Synapse indique clairement si Anki est connecté, indisponible ou si les données sont anciennes.
- La fermeture d'Anki ne bloque pas l'application.
- Une carte révisée dans Synapse apparaît dans l'historique Synapse et modifie le score de maîtrise attendu.
- Une carte déjà importée ne génère pas une seconde preuve à chaque synchronisation.
- Une carte d'un deck multi-items ne gonfle pas artificiellement le score global.
- Les QCM/DP/KFP restent la source principale du score de préparation EDN.
