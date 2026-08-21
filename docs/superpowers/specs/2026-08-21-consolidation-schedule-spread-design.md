# Étalement persisté du backlog de consolidation + capacité par jour cliquable

**Date** : 2026-08-21
**Statut** : validé, prêt pour plan d'implémentation

## 1. Contexte

Retour d'usage sur la page Planning (`/planning`, `frontend/pages/planning_cockpit.py`) : la
répartition des items « à consolider » sur la grille semaine est extrêmement inégale — le jour
« aujourd'hui » affiche l'intégralité du backlog en retard plafonné à 6-8 items visibles avec un
badge `+N en attente` (N atteignant 107 sur la base réelle), tandis que les autres jours de la
semaine n'affichent presque rien.

Cause racine, dans `_load_and_render()` :

```python
consolidation_for_day = [
    task for task in consolidation_tasks
    if (d == today and task.due_date <= today) or task.due_date == d
]
```

Le jour « aujourd'hui » récupère tout le backlog en retard (`due_date <= today`). Les jours futurs
n'affichent que les tâches dont la date d'échéance SM-2 tombe *pile* ce jour-là — rare puisque la
quasi-totalité du backlog est déjà en retard. Le surplus du jour « aujourd'hui » (`skipped`,
badge `+N en attente`) n'est jamais reporté sur les jours suivants de la grille.

Le mécanisme de « bruit » déjà présent dans le code (`docs/ROADMAP_PLANNING_CHARGE_TRAVAIL.md` §1,
`deploy/reprise_historique_consolidation.py::anchor_jitter_days`) ne concerne que l'amorçage
ponctuel des chaînes SM-2 lors de la reprise historique — pas cette grille.

Second besoin exprimé dans la même session : pouvoir cliquer directement sur l'heure affichée en
pied de chaque colonne pour ajuster (ajouter/enlever du temps) la capacité de ce jour précis, et
voir l'algorithme reprogrammer immédiatement le nombre d'items affichés.

**Travail en cours non committé à respecter** : `backend/core/reviews/consolidation.py` contient
déjà (non committé) `postpone_days_for_task`/`is_algorithmic_postpone` et, dans
`backend/core/planning/service.py::plan_consolidation`, un mécanisme qui réduit le plafond du jour
du nombre de reports/ignorés déjà faits aujourd'hui (`count_consolidation_dismissed_today`), pour
qu'un report ne soit pas aussitôt comblé par un autre item du backlog (`tests/test_consolidation_daily_cap_shrinks.py`).
Ce chantier doit s'intégrer par-dessus, pas le contourner.

## 2. Objectif

1. Étaler le backlog de consolidation sur les jours à venir de façon stable et prévisible, au lieu
   de tout empiler sur « aujourd'hui ».
2. Permettre d'ajuster finement la capacité d'un jour donné en cliquant sur l'heure affichée, avec
   répercussion en cascade sur les jours suivants.

## 3. Modèle de données

Nouvelle table dans `backend/core/reviews/local_store.py`, migration `_migrate_consolidation_schedule()`
suivant le style des migrations existantes (`_migrate_course_prep_tables`, table `consolidation_gates`) :

```sql
CREATE TABLE IF NOT EXISTS consolidation_schedule (
    course_id      TEXT NOT NULL,
    context        TEXT NOT NULL,
    scheduled_date TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (course_id, context)
);
CREATE INDEX IF NOT EXISTS idx_consolidation_schedule_date
    ON consolidation_schedule(context, scheduled_date);
```

Accesseurs (`local_store.py`) :

- `get_consolidation_schedule_map(context: str) -> dict[str, datetime.date]`
- `set_consolidation_schedule_batch(context: str, mapping: dict[str, datetime.date]) -> None` (upsert)
- `delete_consolidation_schedule(course_ids: list[str], context: str) -> None`
- `clear_consolidation_schedule_from(context: str, from_date: datetime.date) -> None` (delete où
  `scheduled_date >= from_date`, utilisé par la cascade de capacité)

## 4. Algorithme d'allocation

Nouvelle fonction dans `backend/core/reviews/consolidation.py` :

```python
def ensure_schedule(context: str = "college", today: datetime.date | None = None) -> dict[str, datetime.date]
```

Étapes :

1. `tasks = get_due_consolidation_tasks(context, today, horizon_days=SCHEDULE_HORIZON_DAYS)`
   avec `SCHEDULE_HORIZON_DAYS = 60` — assez pour capter les items qui vont bientôt entrer dans le
   backlog sans essayer de planifier des mois à l'avance (au-delà, l'item n'est de toute façon pas
   encore éligible).
2. `existing = get_consolidation_schedule_map(context)`.
3. Une entrée existante reste **valide** (donc inchangée — c'est ce qui garantit la stabilité d'un
   rendu à l'autre) si et seulement si :
   - son `course_id` est toujours présent dans `tasks` (sinon : traité, ignoré, ou sorti d'horizon) ;
   - `scheduled_date >= today` (sinon : le jour est passé sans que l'item soit traité) ;
   - `scheduled_date >= task.due_date` (sinon : un report manuel a repoussé l'échéance réelle
     au-delà de l'ancienne date programmée — évite qu'un item reporté continue d'apparaître avant
     sa nouvelle échéance, cf. le correctif déjà en place pour `dismissed_today`).
4. Les tâches non couvertes par une entrée valide (`needs_assignment`) sont triées par
   `_priority_score` décroissant, avec `course_id` en tie-break explicite pour un ordre 100%
   déterministe.
5. Marche en avant à partir de `today`, jour par jour, sans limite haute autre qu'un garde-fou de
   sécurité (`MAX_SCHEDULE_LOOKAHEAD_DAYS = 200`, pour ne jamais boucler indéfiniment) :
   - si `target_for_day(day, preferences) == 0` (jour de vacances en coupure complète, ou capacité
     du jour ramenée à 0 min via le réglage ponctuel du §7) : plafond du jour forcé à 0, l'allocateur
     saute ce jour sans y placer d'item — évite qu'un item se retrouve assigné à un jour masqué à
     l'affichage et disparaisse de la vue jusqu'à ce que le jour soit passé ;
   - sinon, plafond du jour = `daily_caps(day, weekend_light)` (`max_items`, `max_per_college`),
     **réduit comme aujourd'hui par `count_consolidation_dismissed_today` si `day == today`** —
     seule dérogation, ce plafond réduit ne s'applique qu'au jour courant, jamais aux jours futurs ;
   - les entrées déjà valides sur ce jour (étape 3) comptent dans l'occupation du plafond ;
   - on comble les places restantes avec la file `needs_assignment`, dans l'ordre de priorité, en
     respectant le plafond par collège ;
   - ce qui ne rentre pas passe au jour suivant.
6. Persiste (`set_consolidation_schedule_batch`) : les entrées valides inchangées + les nouvelles
   assignations. Supprime les entrées devenues invalides (étape 3) qui n'ont pas été réassignées
   au même jour.
7. Retourne la carte fusionnée `{course_id: date}`.

**Limite assumée** : un item reporté manuellement à une date proche pourrait en théorie être
replacé un peu avant sa nouvelle échéance si sa priorité recalculée reste élevée — cas marginal,
pas de garde-fou dédié au-delà de la règle de l'étape 3.

## 5. Intégration Dashboard + Planning

- `PlanningService.plan_consolidation()` (utilisé par le Dashboard « Aujourd'hui ») appelle
  `consolidation.ensure_schedule(context, today)` puis filtre les tâches dont
  `schedule_map[course_id] == today` — le filtrage/plafonnement est déjà fait par l'allocateur,
  plus besoin de rappeler `select_daily` séparément. `selected`/`skipped` restent retournés pour
  compatibilité (skipped = tâches du backlog dont le jour assigné est postérieur à aujourd'hui).
- `planning_cockpit.py::_load_and_render()` appelle `ensure_schedule` une fois par rendu, puis pour
  chaque jour affiché : `consolidation_for_day = [t for t in tasks if schedule_map.get(t.course_id) == d]`.
  Remplace le filtre actuel à la ligne 810-813. `plan_day()` n'a plus besoin de replafonner ces
  tâches (déjà capées par l'allocateur) — la voie Consolidation de `plan_day` garde uniquement le
  découpage par budget minutes restant (le plafond items/collège devient un no-op sur une liste
  déjà pré-filtrée par jour, donc sans risque de régression si on le laisse tel quel).
- Les deux vues lisent donc la même table → même jour affiché pour un item donné sur Dashboard et
  Planning.

## 6. Cascade de capacité (clic sur l'heure)

Point d'entrée unique, appelé par tout code qui modifie `planning_targets` pour un jour (le
dialogue existant `_open_day_capacity_dialog` et le nouveau raccourci du §7) :

```python
def reschedule_from(context: str, day: datetime.date) -> None:
    local_store.clear_consolidation_schedule_from(context, day)
    ensure_schedule(context, today=datetime.date.today())
```

Efface toutes les assignations à partir de `day` (incluses) puis relance l'allocateur : les items
qui ne rentrent plus dans `day` avec la nouvelle capacité glissent naturellement vers les jours
suivants (et en cascade si ceux-ci débordent à leur tour). Les jours avant `day` ne sont pas
touchés.

Le même point d'entrée est appelé si la préférence `weekend_light_consolidation` change (effet sur
tous les jours futurs → `reschedule_from(context, today)`).

## 7. UI — capacité par jour cliquable

- Le pied de chaque colonne (`ref["foot"]`, actuellement `ui.label(_load_label(...))` non cliquable)
  devient cliquable et ouvre directement `_open_day_capacity_dialog(day)` — raccourci du menu actuel
  (qui reste accessible via l'en-tête pour les autres actions : planifier un item, créer un
  événement).
- `_open_day_capacity_dialog` gagne deux boutons `-30min` / `+30min` à côté des 4 paliers existants
  (3h/6h/9h/12h), agissant sur une valeur en minutes affichée en direct (ex. `2h50`).
- Le plancher `MIN_CAPACITY_HOURS` (3h, `backend/core/planning/policy.py`) ne s'applique plus au
  réglage **par jour** (`planning_targets`) — seulement à la capacité globale par défaut (dialogue
  « Ma charge »). Un jour peut descendre à 0 min via ce réglage ponctuel (équivalent à un jour de
  repos sans passer par le mode vacances). Le plafond haut `MAX_CAPACITY_HOURS` (12h) reste appliqué
  aux deux.
- À l'enregistrement (`_save`), après avoir écrit `planning_targets`, appelle
  `consolidation.reschedule_from("college", day)` avant de relancer `_load_and_render()`.
- Idem pour `_reset` (retour à la capacité par défaut = un changement de capacité comme un autre,
  déclenche la même cascade).

## 8. Cas limites

- **Semaine sans backlog** (rare, base propre) : `needs_assignment` vide, `ensure_schedule` ne
  touche à rien, coût quasi nul.
- **Jour de vacances ou capacité mise à 0** : couvert par le check `target_for_day == 0` de l'étape 5
  — l'allocateur ne place jamais rien sur un jour masqué à l'affichage, les items sautent
  directement au prochain jour utile. Le comportement d'affichage existant
  (`_load_and_render` vide `consolidation_for_day` sur ces jours) devient une garantie redondante
  mais sans effet, plus une source d'items fantômes.
- **Item validé pendant qu'il était programmé dans le futur** (ex. l'utilisateur va sur la fiche
  cours et valide directement) : `complete_consolidation_task` fait disparaître le cours de
  `get_due_consolidation_tasks` au prochain `ensure_schedule` → entrée invalidée (étape 3), pas de
  suppression explicite nécessaire côté `local_store` (la réconciliation passive suffit).
- **Item ignoré/reporté un jour déjà entièrement assigné dans le futur** : n'affecte que le jour
  du jour (`count_consolidation_dismissed_today` ne compte que « aujourd'hui »), aucun impact sur
  les jours futurs déjà programmés.
- **Boucle de sécurité `MAX_SCHEDULE_LOOKAHEAD_DAYS`** : si jamais atteinte (backlog gigantesque ou
  plafonds nuls sur une trop longue période), les tâches restantes ne sont simplement pas
  assignées (elles réapparaîtront au prochain appel une fois de la place libérée) — pas d'erreur.

## 9. Tests

- `tests/test_consolidation_schedule.py` (nouveau) : détermine et fige le comportement de
  `ensure_schedule` — stabilité entre deux appels sans changement, étalement correct d'un gros
  backlog sur plusieurs jours en respectant `daily_caps`, invalidation d'une entrée dont le jour
  est passé, invalidation après report manuel (date réelle dépasse la date programmée),
  interaction avec `count_consolidation_dismissed_today` (pas de comblement le jour même),
  comportement sur jour de vacances (plafond 0).
- `tests/test_planning_cockpit_day_capacity.py` ou extension d'un test existant : la cascade
  `reschedule_from` déplace bien le surplus vers les jours suivants après réduction de capacité.
- Mise à jour de `tests/test_consolidation_daily_cap_shrinks.py` si `plan_consolidation` change de
  signature interne (le test actuel mocke `get_due_consolidation_tasks`/`daily_caps` directement —
  à vérifier si le mock doit désormais cibler `ensure_schedule`/`get_due_consolidation_tasks` avec
  la même intention).

## 10. Hors périmètre

- Pas de changement au calcul de `mastery`/SM-2/`postpone_days_for_task` (déjà en place, non
  committé, conservé tel quel).
- Pas d'étalement pour le cycle de lecture J1-J30 (dates fixes, hors sujet).
- Pas de drag & drop manuel d'un item vers un autre jour (non demandé).
- Le budget minutes de `plan_day` (voie Lecture) n'est pas remanié — seule la voie Consolidation
  change de source.
