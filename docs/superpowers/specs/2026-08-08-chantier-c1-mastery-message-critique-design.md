# Chantier C1 — Correction du message trompeur « Socle Rang A critique »

**Date** : 2026-08-08
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Premier sous-chantier de C (fond pédagogique), suite de A/B1-B4 (design system Linear, terminé).
Découverte pendant l'audit du chantier A (7 août 2026) : `get_course_mastery()`
(`backend/core/reviews/mastery.py:279`) affiche la raison « Socle Rang A critique (<40%) » même
quand le niveau « critique » est déclenché par un score général bas, sans aucune preuve de
couverture OIC de Rang A pour l'item. Le message induit l'étudiant en erreur en pointant vers un
problème de Rang A spécifique qui n'a pas été mesuré.

Ce message est affiché à l'utilisateur dans trois écrans : `frontend/pages/course_detail.py:265-266`,
`frontend/pages/course_detail_cockpit.py:655-658`, `frontend/pages/stats.py:408-409` — toutes ces
vues consomment `CourseProgressSnapshot.reasons` directement, aucune ne fait de traitement
spécifique du texte, donc corriger la source suffit pour les trois.

## Objectif

Le message « Socle Rang A critique (<40%) » n'apparaît dans `reasons` que quand le niveau critique
est effectivement déclenché par une preuve de Rang A insuffisante (`_has_rang_a_evidence` vrai et
`score_rang_a < 40`) — jamais quand seul le score général (`score < 40`) est en cause.

## Périmètre

### Bug — `backend/core/reviews/mastery.py:275-280`

Code actuel :

```python
    if score < 40 or (
        _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 40
    ):
        level = "critique"
        reasons.append("Socle Rang A critique (<40%)")
```

`reasons.append(...)` est inconditionnel : il s'exécute dès que le bloc `if` est vrai, quelle que
soit la sous-condition (`score < 40` seule, OU `_has_rang_a_evidence and score_rang_a < 40`) qui a
été satisfaite. Le bloc `fragile` juste en dessous (lignes 281-286) a le même type de condition à
deux branches mais gère déjà correctement le message :

```python
    elif score < 60 or (
        _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 75
    ):
        level = "fragile"
        if _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 75:
            reasons.append("Sécurité Rang A non atteinte (<75%)")
```

### Correction

Reprendre exactement le motif déjà utilisé par le bloc `fragile` pour le bloc `critique` :

```python
    if score < 40 or (
        _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 40
    ):
        level = "critique"
        if _has_rang_a_evidence and score_rang_a is not None and score_rang_a < 40:
            reasons.append("Socle Rang A critique (<40%)")
```

**Décision utilisateur.** Quand le niveau critique est déclenché par `score < 40` seul (sans preuve
Rang A), aucun message de remplacement générique n'est ajouté — les raisons spécifiques qui ont fait
baisser `score` (« QCM raté », « confiance basse », « QCM récent faible (…) », etc., lignes 170-235)
sont déjà accumulées dans `reasons` plus tôt dans la fonction et restent visibles à l'utilisateur.
Ajouter un résumé générique serait redondant avec elles dans le cas courant.

**Condition de déclenchement du niveau inchangée.** Le `if` qui décide `level = "critique"` n'est
pas touché — seul l'ajout du message devient conditionnel à l'intérieur du bloc.

## Hors périmètre

- Aucun changement aux seuils (40 / 60 / 75 / 80), au calcul de `score` ou de `score_rang_a`, ni au
  bloc `fragile` (déjà correct, sert de modèle).
- Aucun changement aux trois écrans qui affichent `reasons` — ils consomment la liste telle quelle,
  rien à adapter côté frontend.
- Pas de message de remplacement générique (voir décision ci-dessus).

## Tests

Dans `tests/test_knowledge_mastery.py` :
- Nouveau test : un cours au niveau critique déclenché par `score < 40` seul (pas d'item déclaré,
  pas de couverture OIC de Rang A pour l'item — `_has_rang_a_evidence` reste faux) ne contient
  **pas** `"Socle Rang A critique (<40%)"` dans `snap.reasons`.
- Nouveau test miroir (non-régression) : quand `_has_rang_a_evidence` est vrai et
  `score_rang_a < 40`, `"Socle Rang A critique (<40%)"` reste présent dans `snap.reasons`.
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la
  dernière — aucun test existant n'affirme la présence de cette chaîne (vérifié par grep sur tout le
  dépôt), donc aucune régression de test attendue au-delà des deux nouveaux tests.
