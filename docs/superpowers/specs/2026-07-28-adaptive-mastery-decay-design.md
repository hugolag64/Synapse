# Maîtrise adaptative et décroissance temporelle

## Objectif

La note de maîtrise et sa courbe de prédiction doivent représenter la
connaissance actuelle d’un item, et non seulement son état historique. Une
absence prolongée de preuves doit faire baisser progressivement la note, mais
la vitesse de baisse doit dépendre de la solidité acquise par les révisions.

## Décision

Le calcul repose sur une note de base issue des preuves, puis sur une
stabilité adaptative :

```text
note actuelle = plancher + (note de base - plancher) × 2^(-âge / stabilité)
```

La stabilité est exprimée en jours et est calculée à partir des preuves
récentes. Elle augmente après des preuves réussies et diminue après une preuve
faible. Il n’y a donc pas de demi-vie fixe de 30 jours pour tous les items.

Le plancher est fixé à 25 pour éviter qu’un item disparaisse totalement de la
maîtrise. La note reste bornée entre 0 et 100.

## Effet des sources

- Une lecture seule apporte une preuve faible et une stabilité courte.
- Une autoévaluation de confiance apporte une preuve moyenne ; une confiance
  basse réduit la stabilité et une confiance haute l’augmente.
- Une évaluation QCM, DP ou KFP apporte une preuve forte. La réussite augmente
  davantage la stabilité ; l’échec la réduit fortement.
- Une tentative OIC réussie ou échouée suit la même logique d’évaluation
  objective.
- Anki contribue avec les résultats `again`, `hard`, `good` et `easy`, ainsi
  qu’avec la date de la révision. Le nombre de cartes faites seul ne constitue
  pas une preuve de maîtrise.
- Une révision manuelle utilise la date de séance saisie, y compris lorsqu’il
  s’agit d’une date historique.

Les preuves sont pondérées par source et par résultat. Les lectures ne doivent
pas pouvoir compenser à elles seules une absence d’évaluation objective.

## Cohérence note / graphique

Le moteur de maîtrise expose une projection commune, réutilisée par :

1. la note affichée dans le cockpit ;
2. le niveau de maîtrise ;
3. le graphique de prédiction.

Le graphique affiche la projection « sans nouvelle preuve » à partir de la
note et de la stabilité actuelles. Une nouvelle preuve recalculée avec sa date
met à jour la note et la courbe.

## Dates et cas historiques

Une preuve datée dans le passé influence l’historique à cette date, mais la
maîtrise affichée aujourd’hui est calculée avec l’âge écoulé depuis cette
preuve. Une nouvelle preuve datée aujourd’hui réinitialise l’âge à zéro et
actualise la stabilité.

## Compatibilité

Le calendrier interne Anki reste la source de vérité pour la planification des
cartes. Synapse ne reproduit pas le scheduler Anki ; il consomme ses résultats
comme preuves de maîtrise. Les données existantes sans date exploitable
utilisent une date de compatibilité déterministe, sans modifier les anciennes
sessions.

## Tests d’acceptation

- À preuves identiques, un item plus ancien a une note inférieure à un item
  récent.
- Une série de bonnes évaluations ralentit la baisse par rapport à une seule
  lecture.
- Une mauvaise évaluation accélère la baisse.
- Une révision manuelle historique apparaît dans l’historique et influence la
  note selon sa date.
- Une révision actuelle remonte la note et actualise la stabilité.
- Le score projeté par le graphique est calculé par le même moteur que la note.
- Le score ne descend jamais sous le plancher.
