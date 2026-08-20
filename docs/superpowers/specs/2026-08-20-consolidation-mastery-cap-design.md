# Plafond de maîtrise sur l'intervalle de consolidation

## Contexte / problème

La boucle de consolidation (`backend/core/reviews/consolidation.py`, cf. `2026-07-17-consolidation-planning-design.md`) fait progresser son intervalle SM-2 uniquement via `mark_consolidation_done()` (`backend/core/reviews/local_store.py:1792`), qui appelle `compute_next_interval(confidence, easiness_factor, repetition)`. Le score de maîtrise (résultat QCM, couverture OIC, Rang A — `mastery.py`) n'intervient qu'à deux endroits, tous deux ponctuels :

1. Au bootstrap initial de la chaîne (`INITIAL_INTERVAL_BY_LEVEL`), une seule fois par item.
2. Dans le score de priorité qui trie la sélection du jour (`mastery_bonus`), sans effet sur l'intervalle lui-même.

Une fois la chaîne lancée, seule l'autoévaluation déclarative (confiance 1-5) pilote la fréquence. Un item objectivement faible (QCM ratés, OIC non couverts) peut donc s'étirer sur un intervalle long si l'utilisateur déclare une confiance haute — la maîtrise réelle ne vient jamais recadrer l'estimation subjective.

Le cycle J classique (`mark_done`) a déjà un mécanisme voisin (`critical_trap`/`recurrent_trap`, dérivé de `weak_points`), mais il n'est pas branché sur la boucle de consolidation et répond à un signal différent (pièges récurrents ponctuels, pas le score de maîtrise agrégé). Hors périmètre ici — voir section dédiée.

## Décision

`mark_consolidation_done()` calcule l'intervalle SM-2 comme aujourd'hui, puis lui applique un plafond dérivé du niveau de maîtrise déjà connu au moment de la validation :

```
intervalle_final = min(intervalle_sm2, plafond[mastery_level])
```

Le plafond ne joue que dans un sens : il raccourcit un intervalle jugé trop optimiste au vu de la maîtrise réelle, il n'en allonge jamais un court (un item en confiance basse reste sur son intervalle court même si son niveau de maîtrise est bon).

### Table des plafonds

Mêmes six niveaux que `MASTERY_WEIGHT` / `INITIAL_INTERVAL_BY_LEVEL` (cohérence avec l'existant, pas de nouvelle échelle) :

| Niveau | Plafond |
|---|---|
| critique | 10j |
| fragile | 14j |
| en construction | 21j |
| à consolider | 30j |
| à entraîner | 45j |
| maîtrisé | pas de plafond |

### Portée

Uniquement `review_type="consolidation"`. Le cycle J3-J30 classique (`mark_done`) n'est pas modifié — pas de demande en ce sens, et son mécanisme de traps répond déjà à un besoin voisin mais distinct.

### Source du niveau de maîtrise

`mastery_level` est un nouveau paramètre optionnel de `mark_consolidation_done()`, fourni par l'appelant (`complete_consolidation_task()` dans `consolidation.py`) depuis `task.mastery_level` — déjà calculé quand la liste du jour a été construite (`_due_consolidation_task_for_course` / `get_or_bootstrap_task`). **Pas de recalcul** de `get_course_mastery()` après l'évaluation qu'on vient d'enregistrer : le QCM ou l'évaluation qui vient d'être saisie compte pour la *prochaine* échéance, pas celle-ci — cohérent avec ce que l'utilisateur voyait affiché sur la carte au moment de valider.

## Implémentation

`backend/core/reviews/local_store.py` :

```python
CONSOLIDATION_INTERVAL_CAP_BY_LEVEL: dict[str, int] = {
    "critique":          10,
    "fragile":           14,
    "en construction":   21,
    "à consolider":      30,
    "à entraîner":       45,
    # "maîtrisé" absent volontairement : pas de plafond.
}


def mark_consolidation_done(
    course_id: str,
    context: str,
    theoretical_due_date: datetime.date,
    course_title: str = "",
    item_number: str = "",
    confidence: int = 3,
    difficulty: str | None = None,
    notes: str | None = None,
    mastery_level: str | None = None,
) -> int:
    ...
    next_interval, new_ef = compute_next_interval(...)  # inchangé
    cap = CONSOLIDATION_INTERVAL_CAP_BY_LEVEL.get(mastery_level or "")
    if cap is not None:
        next_interval = min(next_interval, cap)
    ...
```

`backend/core/reviews/consolidation.py`, `complete_consolidation_task()` — un seul argument ajouté à l'appel existant :

```python
local_store.mark_consolidation_done(
    course_id=task.course_id,
    context=task.context,
    theoretical_due_date=task.theoretical_due_date,
    course_title=task.course_title,
    item_number=task.item_number or "",
    confidence=confidence or 3,
    difficulty=difficulty,
    mastery_level=task.mastery_level,
)
```

## Cas limites

- `mastery_level` absent de la table (`None`, ou valeur inconnue type future extension de l'échelle) : `cap` vaut `None`, aucun plafond appliqué — comportement identique à avant ce changement, pas de régression silencieuse.
- `mastery_level="maîtrisé"` : absent de la table par construction → jamais plafonné, l'intervalle peut continuer de croître normalement avec l'ease factor.
- Le plafond ne redescend jamais un `next_interval_days` déjà court (`min()` — un item en échec, `next_interval` déjà à 3j via `compute_next_interval`, n'est jamais concerné par un plafond ≥ 10j).

## Hors périmètre

- Cycle J classique (`mark_done`) : pas de plafond de maîtrise ajouté ici. Ses `critical_trap`/`recurrent_trap` existants répondent à un besoin voisin (pièges QCM récurrents), pas traité dans ce changement.
- Pas de recalcul de la maîtrise après l'évaluation en cours de saisie (cf. décision ci-dessus).
- Pas de plafond plancher (un item bien maîtrisé n'est pas *forcé* à un intervalle minimum).

## Tests

Dans `tests/test_consolidation.py` :

1. `test_mark_consolidation_done_plafonne_un_intervalle_critique` — confiance haute + plusieurs répétitions (intervalle SM-2 naturellement long) + `mastery_level="critique"` → intervalle retenu = 10j, pas la valeur SM-2 brute.
2. `test_mark_consolidation_done_ne_plafonne_pas_maitrise` — même scénario avec `mastery_level="maîtrisé"` → intervalle SM-2 brut conservé.
3. `test_mark_consolidation_done_sans_mastery_level_inchange` — `mastery_level=None` (défaut) → comportement identique à avant ce changement (non-régression).
4. `test_mark_consolidation_done_plafond_n_allonge_jamais` — confiance basse (intervalle SM-2 court, ex. 3j) + `mastery_level="à entraîner"` (plafond 45j) → intervalle retenu reste 3j, le plafond ne remonte pas un intervalle court.
5. `test_complete_consolidation_task_transmet_mastery_level` — vérifie que `complete_consolidation_task()` passe bien `task.mastery_level` à `mark_consolidation_done()`.
