# Charge de consolidation allégée le week-end

## Contexte / problème

La sélection quotidienne de consolidation (`backend/core/reviews/consolidation.py::select_daily`) plafonne aujourd'hui à `MAX_ITEMS_PER_DAY=6` / `MAX_PER_COLLEGE_PER_DAY=2`, tous les jours de la semaine identiquement. L'utilisateur veut une charge de travail conséquente en semaine mais plus légère le week-end — en gardant le cycle J (J1/J3/J7/J14/J30, lectures/révisions programmées) inchangé : seule la boucle de consolidation (long terme, auto-chaînée) doit se réduire le samedi et le dimanche.

## Décision

Nouveau réglage on/off dans Paramètres, désactivé par défaut (aucun changement de comportement tant qu'il n'est pas activé — même convention que `daily_budget_min` et le mode vacances de Planning).

### Plafonds

| | Semaine | Week-end (si activé) |
|---|---|---|
| Items consolidation max/jour | 6 | 2 |
| Max par collège | 2 | 1 |

Le samedi et le dimanche sont fixes (pas de jours configurables — cas d'usage standard, pas de besoin exprimé pour un rythme de garde irrégulier ici).

### Portée

Uniquement `PlanningService.plan_consolidation()`, seul appelant réel de `select_daily()` — utilisé par le cockpit "Aujourd'hui" du dashboard (`frontend/pages/dashboard/_cockpit_today.py:257`). Le cycle J (`ReviewService.generate_reviews`) n'est pas touché. La page Planning n'utilise pas `select_daily` (elle appelle `get_due_consolidation_tasks()` brut) — non concernée par ce changement, cf. section Hors périmètre.

## Implémentation

`backend/core/reviews/consolidation.py` — nouvelle fonction pure, à côté de `select_daily` :

```python
WEEKEND_MAX_ITEMS_PER_DAY = 2
WEEKEND_MAX_PER_COLLEGE_PER_DAY = 1


def daily_caps(
    today: Optional[datetime.date] = None,
    weekend_light: bool = False,
) -> tuple[int, int]:
    """(max_items, max_per_college) du jour, réduits le week-end si activé."""
    today = today or datetime.date.today()
    if weekend_light and today.weekday() >= 5:  # samedi=5, dimanche=6
        return WEEKEND_MAX_ITEMS_PER_DAY, WEEKEND_MAX_PER_COLLEGE_PER_DAY
    return MAX_ITEMS_PER_DAY, MAX_PER_COLLEGE_PER_DAY
```

`backend/core/planning/service.py::plan_consolidation` — les paramètres explicites restent prioritaires (rétrocompatible avec les appels existants, y compris les tests) ; sans eux, dérivés de `daily_caps()` + préférence :

```python
def plan_consolidation(
    self,
    max_items: int | None = None,
    max_per_college: int | None = None,
):
    from backend.core.reviews import consolidation
    from backend.state.store import data_store

    if max_items is None or max_per_college is None:
        weekend_light = bool(data_store.preferences.get("weekend_light_consolidation", False))
        default_items, default_per_college = consolidation.daily_caps(weekend_light=weekend_light)
        max_items = max_items if max_items is not None else default_items
        max_per_college = max_per_college if max_per_college is not None else default_per_college

    tasks = consolidation.get_due_consolidation_tasks()
    return consolidation.select_daily(tasks, max_items=max_items, max_per_college=max_per_college)
```

`frontend/pages/settings_cockpit.py` — nouveau toggle dans le domaine "PLANIFICATION EDN" (même pattern que le switch "Mode sombre" de la section APPARENCE : `se-switch` custom, appliqué immédiatement, pas de bouton "Enregistrer" séparé) :

```python
with ui.element("div").classes("se-appearance-row"):
    with ui.column().classes("gap-0"):
        ui.label("Charge allégée le week-end").classes("se-appearance-label")
        ui.label(
            "Samedi et dimanche : moins d'items à consolider. "
            "Les lectures J1→J30 restent inchangées."
        ).classes("se-appearance-sub")

    is_light = bool(data_store.preferences.get("weekend_light_consolidation", False))
    we_switch = ui.element("div").classes("se-switch on" if is_light else "se-switch")
    with we_switch:
        ui.element("div").classes("se-switch-knob")

    def _toggle_weekend_light(sw=we_switch):
        new_val = not bool(data_store.preferences.get("weekend_light_consolidation", False))
        data_store.set_preference("weekend_light_consolidation", new_val)
        sw.classes(add="on") if new_val else sw.classes(remove="on")
        ui.notify("Charge week-end allégée" if new_val else "Charge week-end normale", type="positive")

    we_switch.on("click", _toggle_weekend_light)
```

## Cas limites

- Préférence absente/`False` (défaut) : `daily_caps()` retourne toujours `(MAX_ITEMS_PER_DAY, MAX_PER_COLLEGE_PER_DAY)`, quel que soit le jour — comportement identique à avant ce changement.
- `plan_consolidation()` appelé avec des valeurs explicites (comme le font les tests existants) : la préférence n'est jamais consultée, ces appels restent inchangés.
- Le surplus non retenu le week-end n'est pas perdu : `select_daily` le retourne déjà dans `skipped`, qui repasse naturellement les jours suivants (mécanisme existant, pas de nouvelle logique de report).

## Hors périmètre

- Page Planning (vue semaine) : n'utilise pas `select_daily`, donc pas concernée par ce plafond. Le user a confirmé vouloir traiter l'unification Dashboard/Planning (deux mécanismes de troncature différents aujourd'hui) comme un chantier séparé, plus large — cf. `docs/ROADMAP_PLANNING_CHARGE_TRAVAIL.md`.
- Jours de week-end configurables (au-delà de samedi/dimanche fixes).
- Toute modification du cycle J (J1-J30).

## Tests

Dans `tests/test_consolidation.py` :

1. `test_daily_caps_weekday_ignore_le_mode_leger` — un jour de semaine avec `weekend_light=True` retourne quand même les plafonds normaux (6, 2).
2. `test_daily_caps_weekend_normal_si_mode_desactive` — samedi/dimanche avec `weekend_light=False` (défaut) retourne (6, 2), pas de changement.
3. `test_daily_caps_weekend_leger_si_active` — samedi ET dimanche avec `weekend_light=True` retournent (2, 1).

Dans `tests/test_consolidation.py` (section `PlanningService.plan_consolidation`) :

4. `test_plan_consolidation_utilise_le_plafond_leger_le_we_si_active` — préférence activée, `data_store.cours` avec plus de 2 items dus d'un même collège un samedi mocké → `selected` respecte (2, 1), le reste dans `skipped`.
5. `test_plan_consolidation_defaut_inchange_si_preference_absente` — non-régression : sans la préférence, comportement actuel préservé (utilise déjà `test_plan_consolidation_retourne_selection_et_surplus`, à vérifier qu'il passe toujours tel quel).
