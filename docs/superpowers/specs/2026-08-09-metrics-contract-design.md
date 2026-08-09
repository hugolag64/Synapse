# Contrat Avancement / Maîtrise / Rétention

Date : 2026-08-09  
Statut : design validé, implémentation à venir

## Objectif

Supprimer l’ambiguïté du terme `Progression` dans l’interface Synapse. Les vues doivent distinguer explicitement :

- **Avancement** : part des cours lus parmi les cours attendus.
- **Maîtrise** : score de compétence calculé à partir des preuves disponibles.
- **Rétention** : score estimé aujourd’hui à partir de la mémoire et de la stabilité.

Cette tranche clarifie les contrats et les branchements UI. Elle ne modifie aucune formule de maîtrise, de rétention ou de prédiction.

## Décisions de contrat

### Avancement

L’avancement est une métrique cardinale :

```text
done = nombre de cours considérés comme lus
total = nombre de cours attendus
percent = round(done / total * 100) si total > 0, sinon None
```

Le statut `college validé` conserve la règle métier déjà validée : l’ensemble des cours du collège est considéré comme lu. Cette règle doit être appliquée avant le calcul de `done`.

Valeur UI : `Avancement`, avec `done/total` et le pourcentage lorsqu’il est calculable. Si `total` est inconnu ou nul, afficher `—` et non `0 %`.

### Maîtrise

La maîtrise provient de `mastery_score` et `mastery_level` :

- `mastery_score` est un score de `0` à `100` ;
- `mastery_level` est le libellé qualitatif existant ;
- `None` signifie qu’aucune preuve suffisante n’est disponible.

La maîtrise ne doit jamais être déduite de l’avancement ou de la lecture seule. Une lecture peut alimenter la rétention, mais ne constitue pas à elle seule une preuve de compétence.

Valeur UI sans preuve : `Maîtrise —` ou `Maîtrise non évaluée`, selon le composant existant. Le même vocabulaire doit être conservé dans toutes les vues.

### Rétention

La rétention provient de `retention_score`, complétée par les métadonnées de stabilité et de dernière preuve lorsque disponibles.

- elle représente une projection à la date courante ;
- elle n’est pas un taux de lecture ;
- elle ne remplace pas la maîtrise ;
- `None` signifie qu’aucune projection fiable n’est disponible.

Valeur UI : `Rétention`, avec le score et, lorsque le composant le permet, une explication courte de la stabilité ou de la dernière preuve.

## Adaptateur commun

Un adaptateur UI commun normalisera les données sans modifier les sources métier. Il exposera trois structures indépendantes :

```python
{
    "advancement": {"done": int, "total": int, "percent": int | None},
    "mastery": {"score": int | None, "level": str | None},
    "retention": {
        "score": int | None,
        "stability_days": float | None,
        "last_evidence": date | None,
    },
}
```

Les vues ne liront pas directement des champs alternatifs pour reconstruire un score. Si une valeur est absente, l’adaptateur la conserve absente et le composant applique son état vide explicite.

## Surfaces concernées

- **Collèges** : colonne et sous-titre `Avancement`, score de `Maîtrise`, KPI séparé de `Rétention`.
- **Items** : supprimer le sens implicite de `Progression` ; conserver la maîtrise dans sa colonne dédiée et afficher l’avancement uniquement lorsqu’un total lisible existe.
- **Semestres** : remplacer le libellé générique par `Avancement par UE / semestre`.
- **Statistiques** : séparer les cartes et légendes d’avancement, maîtrise et rétention.
- **Vue Item** : réutiliser le même vocabulaire et les mêmes états vides pour l’en-tête et le panneau de pilotage.

Les éléments de progression propres à une interaction (barre de question, chronomètre, import) ne sont pas concernés lorsqu’ils ne représentent pas une métrique d’apprentissage.

## États et textes UI

| État | Avancement | Maîtrise | Rétention |
|---|---|---|---|
| Donnée disponible | `12/20 · 60 %` | `72 % · solide` | `64 %` |
| Partiellement connu | valeur calculable + indication de contexte | score si disponible | score si disponible |
| Donnée absente | `—` | `— · non évaluée` | `— · pas encore de projection` |

Les valeurs absentes ne doivent pas être colorées comme des échecs. Elles utilisent l’état neutre existant.

## Tests et QA

### Tests automatisés

- tester le calcul `done/total` et le cas `total = 0` ;
- tester la règle du collège validé ;
- vérifier que `mastery_score` et `retention_score` restent indépendants ;
- tester les états `None` sans affichage de `0 %` ;
- vérifier les libellés des quatre surfaces principales.

### QA Chromium

Vérifier sur le homeserver :

1. `/colleges` : avancement, maîtrise et rétention distincts ;
2. `/items` : colonne de maîtrise non confondue avec l’avancement ;
3. `/stats` : cartes et légendes séparées ;
4. `/cours/<id>` : en-tête et pilotage global cohérents.

La QA doit relever les textes visibles, les valeurs affichées, les états vides et les logs navigateur `error`/`warning`.

## Hors périmètre

- recalibrage de l’algorithme de maîtrise ;
- changement de la courbe de rétention ;
- migration de colonnes SQLite ;
- ajout de nouvelles preuves d’apprentissage ;
- refonte générale de la grille UI ;
- suppression des noms historiques dans les fonctions backend lorsque cela risquerait une rupture.

## Critères d’acceptation

- aucun titre ou colonne ambigu `Progression` sur les surfaces concernées ;
- les trois métriques utilisent des sources et des états vides distincts ;
- aucune valeur inconnue n’est rendue comme `0 %` ;
- la suite de tests reste au vert ;
- le journal de déploiement est mis à jour à chaque étape ;
- le changement est committé et poussé sur `main` avant le déploiement homeserver.
