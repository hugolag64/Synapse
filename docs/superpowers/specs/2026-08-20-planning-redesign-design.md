# Refonte Planning — visibilité fiable + pilotage de la charge

## Contexte

Suite à `docs/ROADMAP_PLANNING_CHARGE_TRAVAIL.md` §3 : la page Planning (vue semaine) est
censée montrer les items à venir (lecture JX + consolidation) et permettre de piloter la
charge de travail, mais l'utilisateur la juge peu fiable en navigant vers les semaines
futures, et lente à charger. L'investigation a confirmé et affiné trois causes réelles,
au-delà du simple manque de plafond partagé décrit dans le roadmap :

1. **Plafond dur de 5 tâches** (`max_today` dans `PlanningService.plan_day`) appliqué à une
   liste fusionnée lecture+consolidation, *avant* le budget en minutes. Un item de
   consolidation fraîchement amorcé (`days_overdue=0`) perd systématiquement face aux
   lectures JX dans le score de priorité (`consolidation._priority_score`), et disparaît
   sans indication.
2. **Aucune anticipation des cours fac** dans Planning : le module `backend/core/prep/`
   (déjà en prod, tourne quotidiennement via `daily_routine.py::_sync_fac_preparations`)
   détecte les cours à J+1/J+2 dans le calendrier fac importé et génère des tâches de
   préparation (`pdf`, `obsidian`, `resume`, `first_read`) — mais elles ne s'affichent
   qu'au Dashboard "Aujourd'hui" (`course_prep_task_row.py`), jamais dans la grille
   Planning. C'est la cause principale du ressenti "je ne vois pas ce qui arrive".
3. **7 appels séquentiels à l'API Google Calendar** par chargement de semaine (un par
   jour, boucle `await` non parallélisée dans `planning_cockpit.py::_load_and_render`) —
   cause probable de la lenteur perçue.

Un quatrième point découvert en cours de route : `daily_budget_min` (préférence jamais
exposée dans aucune UI) n'est pas totalement inerte — elle alimente avec deux défauts
différents (0 et 60) deux mécanismes réels : le tronquage de la liste Dashboard (no-op
avec le défaut 0) et la projection Sprint EDN (`project_to_exam`, figée à un facteur de
capacité de 1.0 avec le défaut 60, jamais les vraies heures de l'utilisateur).

## Décisions

### 1. Sélection par jour — waterfall temporel (au lieu d'un plafond d'items)

**Modèle** : pour chaque jour, `T` = capacité du jour (réglage global ou override du
jour, cf. §3). La voie **Lecture** (urgent + du jour + lacunes + prépa fac, cf. §2)
consomme `T` en premier ; les tâches en retard (`is_urgent`) ne sont jamais coupées,
comme aujourd'hui. Ce qu'il reste de `T` après la voie Lecture est alloué à la voie
**Consolidation**, sélectionnée par urgence avec le plafond diversité-par-collège
existant (`consolidation.select_daily` + `daily_caps`). Si Lecture dépasse déjà `T` à
elle seule, Consolidation tombe à 0 ce jour-là — pas d'erreur, juste un remainder négatif
clampé à 0.

**Ce qui disparaît** : le plafond dur `max_today=5`. Il n'existait que pour éviter une
liste trop longue visuellement ; le budget en minutes fait déjà ce travail, sans le biais
de priorité qui écrasait la consolidation.

**Ce qui remplace la disparition silencieuse** : tout item écarté (par le budget minutes
ou le plafond diversité-collège) est comptabilisé et exposé comme `+N en attente` dans le
pied de la case-jour, au lieu de disparaître sans trace.

#### Implémentation

`backend/core/planning/service.py::PlanningService.plan_day` — signature actuelle :

```python
def plan_day(
    self, urgent_tasks, today_tasks, active_lacunes,
    calendar_events=None, max_urgent=8, max_today=5, max_lacunes=3,
    target_minutes=None, target_items=None,
) -> DailyPlan:
```

Nouvelle signature (retire `max_today` et `target_items`, qui n'ont plus de sens dans un
modèle waterfall ; personne d'autre que `planning_cockpit.py` n'appelle `plan_day` avec
ces paramètres, `plan_week` non plus — cf. Hors périmètre) :

```python
def plan_day(
    self, urgent_tasks, today_tasks, active_lacunes,
    calendar_events=None, max_urgent=8, max_lacunes=3,
    target_minutes=None,
    prep_slots=None,            # NEW — blocs de prépa fac agrégés du jour (cf. §2)
    consolidation_tasks=None,   # NEW — pool séparé, plus fusionné par l'appelant
    consolidation_today=None,   # NEW — date du jour planifié, pour daily_caps() par-jour
) -> DailyPlan:
```

Logique interne (remplace le bloc "Totaux" actuel) :

```python
lecture_slots = [...]  # urgent + today + lacunes + (prep_slots or []), comme aujourd'hui
lecture_min = sum(s.duration_min for s in lecture_slots)
# les slots urgent restent toujours gardés (bypass du plafond), mais leur durée compte
# bien dans le total consommé — comportement identique au trim existant.

remaining = None if target_minutes is None else max(0, target_minutes - lecture_min)

cons_selected, cons_skipped = [], list(consolidation_tasks or [])
if consolidation_tasks:
    from backend.core.reviews import consolidation
    weekend_light = bool(data_store.preferences.get("weekend_light_consolidation", False))
    max_items, max_per_college = consolidation.daily_caps(
        today=consolidation_today, weekend_light=weekend_light,
    )
    diversity_selected, diversity_skipped = consolidation.select_daily(
        consolidation_tasks, max_items=max_items, max_per_college=max_per_college,
    )
    if remaining is None:
        cons_selected, cons_skipped = diversity_selected, diversity_skipped
    else:
        kept, overflow, used = [], [], 0
        for t in diversity_selected:  # déjà trié par priorité dans select_daily
            dur = self._slot_from_task(t, "consolidation").duration_min
            (kept if used + dur <= remaining else overflow).append(t)
            if used + dur <= remaining:
                used += dur
        cons_selected, cons_skipped = kept, overflow + diversity_skipped

skipped = [...]  # slots lecture écartés par target_minutes (comportement conservé) + cons_skipped
```

`daily_caps(today=consolidation_today, ...)` doit recevoir la **date du jour planifié**
(pas forcément `date.today()`) pour que la charge allégée week-end s'applique au bon jour
quand on navigue vers une semaine future — c'est le point exact du roadmap §4 "étendre
week-end à Planning".

`frontend/pages/planning_cockpit.py::_load_and_render` — ne fusionne plus
`due = due + consolidation_for_day` ; passe les deux pools séparément :

```python
plan = planning_service.plan_day(
    urgent, due, lacunes_day,
    target_minutes=target_minutes,
    consolidation_tasks=consolidation_for_day,
    consolidation_today=d,
)
```

#### Cas limites

- `target_minutes is None` (aucun appelant actuel dans ce cas, mais signature publique) :
  Consolidation garde uniquement les plafonds diversité (comportement proche de
  l'actuel `get_due_consolidation_tasks` brut), pas de coupure minutes.
- Jour sans aucune tâche de consolidation due : `consolidation_tasks=[]`, la boucle ne
  s'exécute pas, `cons_selected=[]` — aucun changement visible.
- `lecture_min` dépasse déjà `target_minutes` : `remaining=0`, Consolidation entièrement
  dans `skipped`. Le badge `+N en attente` inclut ces items.

### 2. Prépa fac dans Planning — un bloc agrégé par cours

**Décision** : les tâches de préparation (`pdf`/`obsidian`/`resume`/`first_read`, dues à
J+1/J+2 avant un cours fac) rejoignent la voie Lecture de la case-jour correspondant à
`lecture_date`, **agrégées en un seul bloc par cours** — pas 4 lignes séparées. Titre
`ITEM {n} – Préparer`, sous-titre listant les sous-tâches manquantes ("PDF · Fiche
Obsidian · 1ère lecture"), durée = somme des durées des sous-tâches restantes.

Les événements de calendrier eux-mêmes (la conférence/le cours affiché en pointillé,
`pl-block-event`) restent purement informatifs et ne consomment jamais de `T` — déjà le
cas aujourd'hui (`_calendar_busy_min` sert uniquement à `free_min`, jamais au trim), pas
de changement nécessaire sur ce point.

#### Implémentation

`backend/core/planning/service.py` — nouvelles clés de durée :

```python
_DUR_KEYS = {
    ...  # inchangé
    "prep_pdf":    ("dur_prep_pdf",    5),   # NEW
    "prep_resume": ("dur_prep_resume", 20),  # NEW
    # "obsidian" et "lecture" existants réutilisés pour les sous-tâches obsidian/first_read
}

_PREP_DURATION_KEY = {"pdf": "prep_pdf", "obsidian": "obsidian", "resume": "prep_resume", "first_read": "lecture"}
_PREP_LABEL = {"pdf": "PDF", "obsidian": "Fiche Obsidian", "resume": "Résumé", "first_read": "1ère lecture"}

def _slot_from_prep_tasks(self, course_tasks: list, durations: dict) -> PlannedSlot:
    """Un bloc agrégé par cours, à partir des PrepTask 'todo' du jour pour ce course_id."""
    first = course_tasks[0]
    total = sum(self._dur(_PREP_DURATION_KEY[t.task_type], durations) for t in course_tasks)
    labels = " · ".join(_PREP_LABEL[t.task_type] for t in course_tasks)
    return PlannedSlot(
        slot_type="prep", label=f"ITEM {first.item_number} – Préparer", subtitle=labels,
        duration_min=total, color="amber", icon="assignment",
        course_id=first.course_id, item_number=first.item_number, source_ref="prep",
    )
```

`SLOT_META` (`backend/core/planning/models.py`) : ajouter `"prep": {"color": "amber",
"icon": "assignment"}`.

`planning_cockpit.py::_load_and_render` — par jour de la semaine, avant l'appel à
`plan_day` :

```python
from backend.core.prep.store import list_prep_tasks
from itertools import groupby

prep_tasks_by_course = groupby(
    sorted(list_prep_tasks(day=d, statuses=("todo",)), key=lambda t: t.course_id),
    key=lambda t: t.course_id,
)
prep_slots = [planning_service._slot_from_prep_tasks(list(g), durations) for _, g in prep_tasks_by_course]
```

Ces `prep_slots` sont passés à `plan_day(..., prep_slots=prep_slots)`, qui les ajoute à
`lecture_slots` (cf. §1). Appels locaux SQLite (`list_prep_tasks`), pas de coût réseau :
pas besoin d'une variante "range" comme pour Calendar (cf. §4).

**Clic sur le bloc** : ouvre un dialogue léger listant les `PrepTask` individuelles du
cours pour ce jour, réutilisant `course_prep_task_row` (ou une variante alignée sur les
tokens Linear — le composant actuel utilise des classes Tailwind `amber-*` brutes, hors
système de tokens ; à migrer à cette occasion) avec ses actions `on_open`/`on_validate`
existantes. Valider une sous-tâche individuelle continue de fonctionner comme aujourd'hui
(`validate_prep_task`) ; la case Planning se recalcule au prochain rendu.

#### Cas limites

- Un cours a plusieurs `item_number` extraits du même événement calendrier (titre
  mentionnant plusieurs items) : chaque item a son propre `course_id` résolu séparément
  par `default_course_resolver`, donc son propre bloc agrégé — pas de fusion inter-cours.
- Toutes les sous-tâches d'un cours sont déjà `done` : `list_prep_tasks(statuses=("todo",))`
  ne les retourne plus, le bloc disparaît naturellement.

### 3. Réglages de charge — un seul concept, deux niveaux

**Décision** :
- **Capacité globale** : reste `planning_capacity_minutes` (3-12h, `policy.py`), réglable
  depuis le dialogue "Ma charge" existant sur Planning **et** un nouveau contrôle dans
  Paramètres → PLANIFICATION EDN (même préférence, deux points d'entrée).
- **Override par jour** : nouveau, branché sur `planning_targets[jour_iso] = {"mode":
  "minutes", "value": X}` — mécanique déjà lue par `policy.capacity_from_preferences` et
  `_cockpit_today.py`, jamais écrite jusqu'ici. Un clic sur l'en-tête d'une case-jour
  propose d'ajuster (ou de réinitialiser) la capacité de ce jour précis.
- **`daily_budget_min`** : supprimé comme source de vérité. Ses deux usages réels sont
  traités séparément (décision explicite de l'utilisateur pour chacun) :
  - Projection Sprint EDN (`_cockpit_today.py:299`, `project_to_exam`) : branchée sur
    `capacity_from_preferences(data_store.preferences)` (la vraie capacité, 6h par
    défaut au lieu de 60 min figés). Changement de comportement assumé et voulu — la
    projection devient nettement plus optimiste, et plus juste.
  - Tronquage de la liste Dashboard (`_cockpit_today.py:268-270`,
    `apply_daily_budget`) : **laissé désactivé** pour l'instant (remplacer le fallback
    `daily_budget_min` par `0` explicite, pas par la vraie capacité) — l'activer
    silencieusement reproduirait le même bug de disparition sans indication que ce
    chantier corrige par ailleurs sur Planning. Un futur chantier pourra l'activer une
    fois doté du même traitement `+N en attente`.
- **Toggle "charge allégée week-end"** : s'applique désormais aussi à Planning via
  `daily_caps(today=<jour affiché>, ...)` (cf. §1) — jusqu'ici limité au Dashboard.

#### Implémentation

`frontend/pages/settings_cockpit.py`, section PLANIFICATION EDN — nouveau bloc
`se-appearance-row`, sur le modèle du toggle "Charge allégée le week-end" déjà présent :

```python
with ui.element("div").classes("se-appearance-row"):
    with ui.column().classes("gap-0"):
        ui.label("Capacité quotidienne").classes("se-appearance-label")
        ui.label("Ta charge de référence, utilisée par Planning et la projection Sprint EDN.").classes("se-appearance-sub")
    capacity_toggle = ui.toggle({3: "3 h", 6: "6 h", 9: "9 h", 12: "12 h"},
                                 value=capacity_from_preferences(data_store.preferences) // 60
                                 ).props("dense unelevated no-caps")
    capacity_toggle.on_value_change(
        lambda e: data_store.set_preference("planning_capacity_minutes", capacity_hours_to_minutes(e.value))
    )
```

`planning_cockpit.py` — override par jour, nouvelle option dans `_open_day_actions` (qui
propose déjà "Planifier un item" / "Créer un événement") :

```python
ui.button("Ajuster la capacité de ce jour", icon="tune",
          on_click=lambda: (_close_and_open(dialog, _open_day_capacity_dialog, day))
          ).props("outline no-caps unelevated").classes("w-full justify-start")

def _open_day_capacity_dialog(day: datetime.date) -> None:
    targets = dict(data_store.preferences.get("planning_targets", {}))
    current = targets.get(day.isoformat(), {})
    current_hours = (current.get("value", capacity_from_preferences(data_store.preferences)) // 60
                      if current.get("mode") == "minutes" else capacity_from_preferences(data_store.preferences) // 60)
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-sm p-4"):
        ui.label(f"Capacité du {_month_day(day)}").classes("text-base font-semibold")
        hours = ui.toggle({3: "3 h", 6: "6 h", 9: "9 h", 12: "12 h"}, value=current_hours).props("dense unelevated no-caps")
        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            def _reset():
                targets.pop(day.isoformat(), None)
                data_store.set_preference("planning_targets", targets)
                dialog.close(); asyncio.create_task(_load_and_render())
            ui.button("Réinitialiser", on_click=_reset).props("flat no-caps color=slate")
            def _save():
                targets[day.isoformat()] = {"mode": "minutes", "value": capacity_hours_to_minutes(hours.value)}
                data_store.set_preference("planning_targets", targets)
                dialog.close(); asyncio.create_task(_load_and_render())
            ui.button("Enregistrer", on_click=_save).props("unelevated color=indigo no-caps")
    dialog.open()
```

Un jour avec override actif affiche un petit indicateur dans `.pl-day-head` (ex: point
`--accent` à côté de la date) pour que ce ne soit pas un état invisible.

`_cockpit_today.py:268` et `:299` — remplacer les deux lectures de `daily_budget_min` :

```python
# ligne 268 (tronquage, reste désactivé)
budget = target.get("value", 0) if target.get("mode") == "minutes" else 0

# ligne 299 (projection Sprint EDN, activé)
daily_capacity_minutes=capacity_from_preferences(data_store.preferences),
```

#### Cas limites

- Aucun override pour un jour donné : `planning_targets.get(jour, {})` retourne `{}`,
  `capacity_from_preferences` retombe sur la capacité globale — comportement identique à
  avant l'ajout de cette fonctionnalité.
- Capacité globale changée après qu'un override par jour existe déjà : l'override reste
  figé à sa valeur explicite tant qu'il n'est pas réinitialisé — comportement voulu (un
  override est une exception assumée, pas un pourcentage du défaut).

### 4. UI de la case-jour

Deux groupes labellisés dans `.pl-day-body`, avant/après selon l'ordre lecture→
consolidation, avec un petit en-tête de groupe (10px, uppercase, `--text-dim` — même
traitement que `.pl-day-dow` existant) : `LECTURE` puis `CONSOLIDATION` (seulement si le
groupe a au moins un slot, pas d'en-tête vide). Le bloc `.pl-block-consolidation`
existant (bordure gauche cyan) est conservé comme accent supplémentaire à l'intérieur de
son groupe, en plus du label — la bordure seule ne suffisait pas à être repérable, le
groupe résout ça sans la retirer.

Badge `+N en attente` : nouvelle classe `.pl-day-overflow`, rendu dans `.pl-day-foot` à
côté de la charge totale, seulement si `plan.skipped` (lecture + consolidation) est
non-vide.

Le dialogue "Ma charge" (`_open_capacity_dialog`) n'a pas besoin de changement structurel
majeur — juste un renommage du label pour clarifier "Capacité par défaut" (vs. l'override
du jour, qui vit dans son propre petit dialogue au §3).

### 5. Performance — un seul appel Calendar par semaine

**Décision** : ajouter `CalendarService.get_events_for_range(start, end) ->
dict[date, list[dict]]`, qui reprend la boucle par-calendrier existante de
`get_events_for_day` mais avec `timeMin`/`timeMax` couvrant toute la semaine, puis range
les événements par date de début côté client. `planning_cockpit.py::_load_and_render`
remplace sa boucle de 7 appels séquentiels par un seul appel à cette méthode.

La contrainte de séquentialité documentée dans `calendar_service.py` ("Fetch
sequentially to avoid thread-safety issues with Google API client") concerne les
calendriers *entre eux* au sein d'un même appel (`calendar_ids` loop), pas les jours —
elle est donc préservée telle quelle à l'intérieur de `get_events_for_range`, qui ne fait
qu'éliminer la boucle jour-par-jour côté appelant.

#### Implémentation

```python
async def get_events_for_range(self, start: datetime.date, end: datetime.date) -> dict[datetime.date, list[dict]]:
    """Comme get_events_for_day, mais sur une plage — un seul passage par calendrier."""
    # même résolution de calendar_ids, même boucle fetch_calendar séquentielle,
    # timeMin/timeMax couvrant [start 00:00, end 23:59]
    events_by_day: dict[datetime.date, list[dict]] = {d: [] for d in _daterange(start, end)}
    for ev in all_events:
        day = event_start_date(ev, app_timezone)  # helper déjà utilisé dans backend/core/prep/calendar_parser.py
        if day in events_by_day:
            events_by_day[day].append(ev)
    return events_by_day
```

```python
# planning_cockpit.py::_load_and_render
events_by_day = await calendar_service.get_events_for_range(week[0], week[-1])
for idx, (d, plan) in enumerate(zip(week, plans)):
    _draw_day(idx, d, plan, events_by_day.get(d, []))
```

#### Cas limites

- Échec réseau : `get_events_for_range` doit préserver le même comportement de
  dégradation que `get_events_for_day` (retourne un dict vide plutôt que de lever, la
  page reste utilisable sans Calendar) — même `try/except` que l'appelant actuel autour
  de `get_events_for_day`.
- `get_events_for_day` (appelé ailleurs — Dashboard "Aujourd'hui" notamment) n'est pas
  touché, reste tel quel pour l'usage jour unique.

## Hors périmètre

- **Dashboard "Aujourd'hui"** : garde sa propre logique d'affichage (deux voies déjà
  correctes via `plan_consolidation` séparé de `generate_reviews`). Seules ses deux
  lectures de `daily_budget_min` changent (§3) ; son tronquage réel reste désactivé.
- **`plan_week()`** : déjà non-utilisé par `planning_cockpit.py` (bug d'ancrage documenté
  dans le code, la page recalcule ses propres `plan_day` par date réelle) — pas touché.
- **Mode vacances** (`planning_vacation`) : fonctionnel, pas retouché.
- **Vue "3 jours" / "1 jour"** (`state["days"]`) : le waterfall et les deux voies
  s'appliquent identiquement quel que soit le nombre de jours affichés, aucun changement
  spécifique nécessaire.
- **Migration du composant `course_prep_task_row.py` vers les tokens Linear** : mentionnée
  au §2 comme opportunité, pas un prérequis bloquant — peut rester en l'état si le plan
  d'implémentation la juge hors budget.

## Tests

`tests/test_planning_service.py` (ou fichier équivalent existant) :
1. Waterfall — Lecture qui consomme tout `T` laisse Consolidation vide, `skipped` contient
   les tâches de consolidation écartées.
2. Waterfall — Lecture légère laisse un `remaining` positif, Consolidation sélectionne
   dans la limite de ce reste, en respectant toujours `max_per_college`.
3. Tâches urgentes jamais coupées même si elles dépassent `T` à elles seules.
4. `daily_caps` appelé avec la date du jour planifié (pas `date.today()`) applique la
   charge allégée week-end au bon jour lors de la navigation vers une semaine future.
5. Bloc de prépa agrégé : plusieurs `PrepTask` `todo` du même `course_id`/jour produisent
   un seul `PlannedSlot`, durée = somme des sous-tâches ; aucune tâche `todo` → aucun bloc.

`tests/test_planning_policy.py` :
6. Override par jour (`planning_targets`) prioritaire sur la capacité globale ; absence
   d'override retombe sur `planning_capacity_minutes`.

`tests/test_calendar_service.py` (ou équivalent) :
7. `get_events_for_range` répartit correctement des événements de jours différents dans
   le bon compartiment du dict retourné ; gère une plage sans événements.

Non-régression :
8. Vérifier que la projection Sprint EDN (`project_to_exam`) change bien de valeur avec
   `capacity_from_preferences` (test existant à mettre à jour s'il fige l'ancien défaut
   60 min).
9. Vérifier que le tronquage Dashboard (`apply_daily_budget` appelé depuis
   `_cockpit_today.py`) reste un no-op (budget=0) après le remplacement de
   `daily_budget_min`.
