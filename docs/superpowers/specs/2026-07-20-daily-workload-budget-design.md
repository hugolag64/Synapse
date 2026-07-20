# Plafond de charge quotidienne (daily workload budget)

## Contexte / problème

Le flux de consolidation long-terme (`plan_consolidation`, cf. `2026-07-17-consolidation-planning-design.md`) fonctionne correctement mais ses items sont fusionnés dans `all_tasks` avec les révisions J3/J7/J14/J30/bonus avant le split retard/aujourd'hui (`frontend/pages/dashboard/_reviews.py::rebuild_all`, lignes ~858-951). L'affichage tronque à 5 (retard) / 8 (aujourd'hui) lignes visibles, avec un bouton "Voir X de plus" — mais ce bouton révèle **tout** le reste sans aucune limite (`_add_voir_plus_rows`). Résultat : l'utilisateur perçoit une liste quasi infinie dès qu'il clique dessus, sans moyen de dire "je ne veux pas plus de X par jour".

Un réglage `daily_goal` existe déjà (`data_store.preferences`, utilisé dans `_banner.py` et `dashboard_legacy.py`) mais c'est un **objectif minimum** ("3/5 fait aujourd'hui"), pas un plafond.

## Décisions (validées avec l'utilisateur)

- Unité du plafond : **minutes estimées**, pas nombre d'items (réutilise `get_next_action(t).duration_min`, déjà utilisé par `compute_daily_load`).
- Périmètre : **tout confondu** — retard + aujourd'hui + consolidation partagent un seul budget minutes/jour (pas d'exemption pour le retard).
- Valeur par défaut : **désactivée (0 = illimité)**. Le comportement actuel ne change pas tant que l'utilisateur n'a pas réglé la valeur dans Paramètres.
- Un badge "charge lourde" est ajouté à la bannière active (elle n'en a pas aujourd'hui — le seuil fixe 120 min n'existe que dans la page legacy), et son seuil s'aligne sur le plafond perso quand il est réglé (cf. section 3, corrigée après exploration du code).

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

Correction post-exploration : `urgent_tasks` et `today_tasks` arrivent déjà triés par `priority_score` décroissant (`ReviewService.generate_reviews` trie à la ligne 212/263 avant le split retard/aujourd'hui). `apply_daily_budget` ne re-trie donc pas — il consomme les deux listes dans l'ordre reçu (`urgent_tasks` d'abord, puis `today_tasks`), cumule `get_next_action(t).duration_min`, et coupe dès que l'ajout du prochain item dépasserait `budget_min`. Aucun état à persister — les items non retenus gardent leur `due_date` d'origine et redeviennent (ou restent) prioritaires le jour suivant.

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

Correction post-exploration : le badge "charge lourde" fixe à 120 min existe seulement dans `dashboard_legacy.py` (page legacy, hors périmètre). La bannière active (`frontend/pages/dashboard/_banner.py`, utilisée par `frontend/pages/dashboard/__init__.py`) n'affiche actuellement **aucun** indicateur de charge lourde — seulement la pill "Objectif quotidien" (minimum) et la barre de progression. Il faut donc en ajouter un, pas en modifier un existant.

- `compute_daily_load` (`recommendation_service.py`) gagne un paramètre optionnel `heavy_threshold_min: int = 120`, utilisé à la place du `120` en dur pour calculer `is_heavy`.
- Dans `rebuild_all()`, l'appel devient :
  ```python
  _budget = data_store.preferences.get("daily_budget_min", 0)
  load = compute_daily_load(
      urgent, today_tasks,
      heavy_threshold_min=_budget if _budget > 0 else 120,
  )
  ```
  (appelé sur les listes **avant** `apply_daily_budget`, cf. section 2).
- Dans `_banner.py` :
  - `render_banner` : ajouter une pill "heavy" à côté de la pill "goal" existante (même structure `ui.element` + `ui.icon` + `ui.label`, masquée par défaut via `state.banner_refs["heavy_el"]`/`state.banner_refs["heavy"]`), icône `"warning"`, couleur ambre.
  - `update_banner` : nouveau paramètre `overflow_count: int = 0`. Affiche la pill "heavy" quand `load["is_heavy"]` est vrai, texte `"Charge lourde"`. Si `overflow_count > 0`, texte `f"{overflow_count} reportée(s) — plafond atteint"` à la place (priorité à l'info la plus actionnable).

## Hors périmètre

- Pas de configuration par type de révision (pas de plafond distinct pour consolidation vs J3/J7/J14/J30).
- Pas de persistance d'état "skipped" — le report au lendemain est purement dérivé des due_date existantes, comme le fait déjà `consolidation.select_daily`.
- Pas de changement au comportement quand `daily_budget_min == 0` (défaut).

## Tests

- `apply_daily_budget` : liste vide, budget=0 (no-op), budget qui coupe au milieu de `urgent`, budget qui coupe au milieu de `today_tasks`, budget suffisant pour tout.
- Vérifier que `compute_daily_load` reste basé sur les listes pré-trim (non-régression).
- Test dashboard : `rebuild_all` avec `daily_budget_min` réglé bas → nombre d'items rendus dans `urgent_col`/`today_col` respecte le budget.
