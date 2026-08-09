# Reprise historique des collèges validés vers la consolidation

## Objectif

Traiter comme déjà parcourus les collèges validés avant Synapse, sans réécrire les dates Notion et sans créer de retard artificiel pendant les vacances. Les cours concernés doivent quitter la boucle de lecture J3/J7/J14/J30 et entrer dans la boucle de consolidation à partir du 20 août 2026.

## État constaté

- Les deux boucles existent déjà : lecture initiale J3/J7/J14/J30, puis consolidation SM-2.
- Les neuf collèges actuellement déclarés `valide` sont Cardiovasculaire, Dermatologie, Endocrinologie, Infectiologie, Neurochirurgie, Neurologie, Nutrition, Néphrologie et Pneumologie.
- Hépato-Gastro-entérologie est présent dans les cours mais absent des statuts de collège.
- Le cache contient 176 cours pour les dix collèges visés.
- 146 cours ont déjà un `item_state` local (`correct` ou `flou`) ; 30 n'en ont pas.
- L'historique SQLite contient déjà des validations J et des consolidations réelles qui ne doivent pas être écrasées.

## Décision métier

Un cours est considéré comme historiquement parcouru lorsqu'il appartient à un collège `valide` et possède un `item_state` local. Cette règle signifie « ne pas refaire la lecture initiale », pas « maîtrisé ».

Les niveaux existants sont conservés. Les cours manquants reçoivent le niveau prudent `correct`, avec la source `reprise_historique`. Aucune donnée Notion n'est modifiée et aucune date de lecture fictive n'est injectée.

## Barrière de démarrage

Une table locale dédiée mémorise `not_before=2026-08-20` pour chaque cours repris, dans le contexte `college`. La génération des tâches de consolidation :

1. masque les tâches avant cette date ;
2. ramène leur échéance effective au 20 août si leur échéance historique est antérieure ;
3. ne transforme donc pas les vacances en jours de retard accumulés.

Cette barrière est locale, réversible et ne modifie pas les lignes d'historique existantes.

## Migration idempotente

Un script de reprise sera exécuté en deux temps :

```text
--dry-run   rapport des collèges, cours ciblés, états manquants et tâches attendues
--apply     sauvegarde SQLite puis application de la reprise
```

L'application :

- ajoute Hépato-Gastro-entérologie au statut `valide` si nécessaire ;
- crée uniquement les `item_state` manquants ;
- conserve les niveaux et preuves existants ;
- installe la barrière du 20 août ;
- ne crée pas de fausses lignes J3/J7/J14/J30 ;
- peut être relancée sans doublons.

## Adaptation du moteur

Le service de révision normale ignorera les cours historiquement parcourus. Le service de consolidation les acceptera même si les champs Notion J3/J7/J14/J30 sont incomplets, puisque ces champs décrivent le passé dans Notion et ne sont plus la source de planification pour cette reprise.

## Vérification

Avant application : le dry-run doit afficher les dix collèges, 176 cours ciblés et 30 états manquants.

Après application :

- aucun cours ciblé ne doit produire de tâche J3/J7/J14/J30 ;
- aucune tâche de consolidation ciblée ne doit apparaître avant le 20 août ;
- les tâches ciblées doivent apparaître comme consolidation à partir du 20 août ;
- les compteurs d'historique existants doivent rester inchangés ;
- une sauvegarde SQLite doit être conservée avant l'application.

## Alternatives écartées

### Réécrire les dates dans Notion

Écartée : cela falsifierait la source utilisateur, recréerait des dates J dépassées et mélangerait historique réel et données de planification.

### Insérer quatre validations synthétiques J par cours

Écartée : cela gonflerait artificiellement l'historique et ne résoudrait pas proprement la mise en pause jusqu'au 20 août.

### Marquer tous les cours `solide`

Écartée : une validation de partiel justifie le passage en consolidation, mais ne prouve pas une maîtrise homogène de chaque item.
