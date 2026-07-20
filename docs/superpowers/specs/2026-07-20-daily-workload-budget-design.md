# Plafond de charge quotidienne (daily workload budget)

## Contexte / problème

Le flux de consolidation long-terme (`plan_consolidation`, cf. `2026-07-17-consolidation-planning-design.md`) fonctionne correctement mais ses items sont fusionnés dans `all_tasks` avec les révisions J3/J7/J14/J30/bonus avant le split retard/aujourd'hui (`frontend/pages/dashboard/_reviews.py::rebuild_all`, lignes ~858-951). L'affichage tronque à 5 (retard) / 8 (aujourd'hui) lignes visibles, avec un bouton "Voir X de plus" — mais ce bouton révèle **tout** le reste sans aucune limite (`_add_voir_plus_rows`). Résultat : l'utilisateur perçoit une liste quasi infinie dès qu'il clique dessus, sans moyen de dire "je ne veux pas plus de X par jour".

Un réglage `daily_goal` existe déjà (`data_store.preferences`, utilisé dans `_banner.py` et `dashboard_legacy.py`) mais c'est un **objectif minimum** ("3/5 fait aujourd'hui"), pas un plafond.

## Décisions (validées avec l'utilisateur)

- Unité du plafond : **minutes estimées**, pas nombre d'items (réutilise `get_next_action(t).duration_min`, déjà utilisé par `compute_daily_load`).
- Périmètre : **tout confondu** — retard + aujourd'hui + consolidation partagent un seul budget minutes/jour (pas d'exemption pour le retard).
- Valeur par défaut : **désactivée (0 = illimité)**. Le comportement actuel ne change pas tant que l'utilisateur n'a pas réglé la valeur dans Paramètres.
- Le badge "charge lourde" de la bannière (actuellement seuil fixe 120 min) s'aligne sur le plafond perso quand il est réglé.

## 1. Réglage — préférence `daily_budget_min`

Fichier : `frontend/pages/settings.py`, section "Objectif quotidien" (~ligne 242).

Ajouter un champ `ui.number` juste sous l'objectif quotidien :
- Label : "Charge max quotidienne (min)"
- `value=data_store.preferences.get('daily_budget_min', 0)`, `min=0, max=300, step=15`
- Aide : "0 = illimité"
- `on_change` : `data_store.set_preference('daily_budget_min', int(e.value))` + `ui.notify`

## 2. Application du plafond — trim unifié

Nouvelle fonction dans `backend/core/reviews/recommendation_service.py`, à côté de `compute_daily_load` :

```python
def apply_daily_budget(
    urgent_tasks: list["ReviewTask"],
    today_tasks:  list["ReviewTask"],
    budget_min: int,
) -> tuple[list["ReviewTask"], list["ReviewTask"], int]:
    """
    Si budget_min > 0, tronque urgent_tasks + today_tasks (dans cet ordre de
    priorité) pour que le total estimé ne dépasse pas budget_min minutes.
    Ne modifie aucune due_date : les items coupés repasseront naturellement
    le(s) jour(s) suivant(s) (même logique que consolidation.select_daily).

    Retourne (kept_urgent, kept_today, overflow_count).
    """
```

Ordre de priorité pour le cumul : `urgent_tasks` trié par `days_overdue` décroissant (déjà l'ordre utilisé à l'affichage), puis `today_tasks` trié par `priority_score` décroissant. On cumule `get_next_action(t).duration_min` et on coupe dès que l'ajout du prochain item dépasserait `budget_min`. Aucun état à persister — les items non retenus gardent leur `due_date` d'origine et redeviennent (ou restent) prioritaires le jour suivant.

Si `budget_min == 0` : retourne les listes inchangées et `overflow_count=0`.

### Point d'intégration

Dans `rebuild_all()` (`frontend/pages/dashboard/_reviews.py`, après la ligne 878 `state.focus_tasks = urgent + today_tasks`) :

```python
_budget = data_store.preferences.get("daily_budget_min", 0)
urgent, today_tasks, _overflow_count = recommendation_service.apply_daily_budget(
    urgent, today_tasks, _budget
)
```

Important : `compute_daily_load` (ligne ~889, pour la bannière) doit être appelé sur les listes **avant** ce trim, pour refléter la charge réelle totale et non ce qui est effectivement affiché. Le trim s'applique donc APRÈS le calcul de `load`, juste avant les sections de rendu (RETARD / AUJOURD'HUI).

Les troncatures d'affichage existantes ([:5] retard, [:8] aujourd'hui + "voir plus") restent inchangées : elles opèrent désormais sur des listes déjà bornées par le budget, donc "voir plus" ne peut plus révéler qu'un nombre borné d'items.

## 3. Bannière + transparence

Fichier : `frontend/pages/dashboard/_banner.py`.

- Seuil `is_heavy` : actuellement fixe à 120 min dans `compute_daily_load`. Remplacer par une comparaison au niveau de la bannière : `threshold = daily_budget_min if daily_budget_min > 0 else 120`, `is_heavy = load["total_min"] > threshold`.
- Si `overflow_count > 0` (retourné par `apply_daily_budget`) : afficher un texte discret sous le header "Aujourd'hui", ex. `"{overflow_count} tâche(s) reportée(s) — plafond atteint"`.

## Hors périmètre

- Pas de configuration par type de révision (pas de plafond distinct pour consolidation vs J3/J7/J14/J30).
- Pas de persistance d'état "skipped" — le report au lendemain est purement dérivé des due_date existantes, comme le fait déjà `consolidation.select_daily`.
- Pas de changement au comportement quand `daily_budget_min == 0` (défaut).

## Tests

- `apply_daily_budget` : liste vide, budget=0 (no-op), budget qui coupe au milieu de `urgent`, budget qui coupe au milieu de `today_tasks`, budget suffisant pour tout.
- Vérifier que `compute_daily_load` reste basé sur les listes pré-trim (non-régression).
- Test dashboard : `rebuild_all` avec `daily_budget_min` réglé bas → nombre d'items rendus dans `urgent_col`/`today_col` respecte le budget.
