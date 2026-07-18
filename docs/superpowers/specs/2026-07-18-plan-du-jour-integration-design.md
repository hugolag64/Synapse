# Intégration "Plan du jour" — To Do & Dashboard

## Problème

Le Planning (Journée / Semaine / Consolidation), le Dashboard et la page To Do
recalculent chacun leur propre liste de tâches, sans jamais se recouper :

- Journée/Semaine : `review_service.generate_reviews()` + lacunes → `PlannedSlot`
  (`backend/core/planning/service.py:plan_day/plan_week`), affiché uniquement
  dans l'onglet Planning, jamais persisté (`backend/core/planning/models.py:8`).
- Consolidation : `consolidation.get_due_consolidation_tasks()` + `select_daily()`
  → `ReviewTask(review_type="consolidation")`, affiché uniquement dans son
  propre onglet Planning (`backend/core/reviews/consolidation.py`).
- Dashboard "RETARD/AUJOURD'HUI" (`frontend/pages/dashboard/_reviews.py:852`) :
  `review_service.generate_reviews()` (même moteur que Journée), avec un vrai
  bouton "Valider" déjà câblé sur `open_session_feedback_dialog` — mais ne
  connaît pas les tâches de Consolidation.
- Dashboard "Agenda du jour" (`frontend/pages/dashboard/_agenda.py:98`) :
  événements Google Calendar uniquement.
- To Do (`frontend/pages/todo.py`) : routine locale (SQLite `routine_items`) +
  tâches Notion du jour — aucune notion de révision/consolidation/lacune.

Résultat : valider un item de Consolidation dans Planning n'a aucun effet
visible ailleurs, et l'utilisateur doit visiter 3 pages différentes pour voir
"tout ce qu'il a à faire aujourd'hui".

## Solution

Pas de nouvelle table ni de mécanisme de "commit" sur clic. Toutes les listes
concernées sont déjà recalculées à la volée (c'est le pattern existant partout
dans l'app — Dashboard, Journée, Consolidation n'ont jamais utilisé de
sélection persistée). On étend ce même pattern à deux nouveaux points de
lecture, qui partagent les mêmes fonctions source déjà existantes :

| Source                              | Fonction                                             | Type produit |
|--------------------------------------|-------------------------------------------------------|--------------|
| Révisions urgentes/du jour           | `review_service.generate_reviews()` + `get_urgent_tasks`/`get_today_tasks` | `ReviewTask` |
| Lacunes actives                      | `local_store.get_all_weak_points_table(status_filter="active")` | ligne SQLite `weak_points` |
| Consolidation du jour                | `planning_service.plan_consolidation()`               | `ReviewTask(review_type="consolidation")` |

### 1. Dashboard — extension de RETARD/AUJOURD'HUI

Dans `rebuild_all()` (`frontend/pages/dashboard/_reviews.py:852`), fusionner
les tâches de consolidation du jour dans `all_tasks` **avant** le filtre
collège et avant le calcul de `urgent`/`today_tasks` (donc juste après la
ligne `all_tasks = externat_service.apply_stage_boost(all_tasks)`, avant
`render_college_chips(state, all_tasks)`) :

```python
from backend.core.planning.service import planning_service
consolidation_selected, _ = planning_service.plan_consolidation()
all_tasks = all_tasks + consolidation_selected
```

`get_urgent_tasks`/`get_today_tasks` (`backend/core/reviews/service.py:285,303`)
sont déjà génériques (`t.due_date < today` / `t.due_date == today`, aucune
dépendance à `review_type`) : les tâches de consolidation, qui ont un
`due_date` correctement calculé par `consolidation.py`, se répartissent donc
naturellement entre RETARD et AUJOURD'HUI sans logique supplémentaire, et
passent par le même filtre collège que les révisions classiques (voir
Erreurs / cas limites). Pas de nouvelle colonne, pas de section séparée. Les
cartes rendues par
`render_review_row` fonctionnent déjà pour n'importe quel `ReviewTask` ; le
seul changement nécessaire est dans `validate_fn`/`on_postpone`/`on_ignore`
(passés en paramètre à `rebuild_all`, définis par l'appelant du module
dashboard) : ces callbacks doivent brancher sur `task.review_type`:

- `review_type == "consolidation"` → `mark_consolidation_done(...)` +
  `add_study_session(...)` (reprendre exactement la logique de
  `_do_mark_consolidation` dans `frontend/pages/planning.py:519-529`) pour
  Valider, `postpone(review_type="consolidation", ...)` pour Passer/Ignorer.
- sinon → comportement actuel inchangé (`mark_done`, etc.)

Pas de nouvelle sous-liste sous "Agenda du jour" (`_agenda.py` reste
calendrier-uniquement, inchangé).

### 2. To Do — nouvelle section "Plan du jour"

Nouvelle section dans `frontend/pages/todo.py`, positionnée avant les
sections "Routine"/"Ajouté" existantes, construite à partir des trois
sources ci-dessus (mêmes fonctions, aucune duplication de logique) :

1. Révisions : `review_service.generate_reviews()` filtré par
   `get_urgent_tasks`/`get_today_tasks` (mêmes fonctions que le Dashboard).
2. Lacunes actives : `local_store.get_all_weak_points_table(status_filter="active")`.
3. Consolidation : `planning_service.plan_consolidation()` (le tuple
   `(selected, skipped)` — n'afficher que `selected`).

Chaque ligne : icône + label + sous-titre (niveau/retard/collège pour les
révisions et la consolidation, catégorie/sévérité pour une lacune) + un
bouton qui ouvre `open_session_feedback_dialog`. Style de carte : réutiliser
le pattern de `_consolidation_card` (`frontend/pages/planning.py:127`, déjà
approuvé en revue) plutôt que d'en inventer un nouveau — même
`border-l-4`/`rounded-xl`/icône+colonne+actions, avec une couleur de bordure
différente par source (bleu révision, cyan consolidation, orange lacune,
cohérent avec `SLOT_META`/`type_color` existants).

### 3. Adaptateur lacune → `ReviewTask`

`open_session_feedback_dialog` attend un `ReviewTask` (accède à
`task.review_type`, `task.course_id`, `task.college`, `task.context`,
`task.label` en interne — `frontend/pages/dashboard/_dialogs.py:205-227`).
Une ligne `weak_points` (schéma : `id, course_id, course_title, item_number,
category, detail, severity, status, created_at` —
`backend/core/reviews/local_store.py:144-156`) n'a pas cette forme. Ajouter
une fonction `weak_point_to_task(row) -> ReviewTask` dans un nouveau module
`backend/core/reviews/lacune_adapter.py` (pas dans `consolidation.py`, qui
reste dédié à l'éligibilité de consolidation par contrainte du plan
précédent) qui :

- résout le cours via `data_store.cours` par `course_id` pour peupler
  `college` (même pattern que `consolidation.get_or_bootstrap_task`,
  `backend/core/reviews/consolidation.py:201-204`) ; si le cours est
  introuvable, `college=[]` ; `item_number`/`course_title` viennent de la
  ligne `weak_points` en repli ; `context="college"` toujours (les lacunes
  ne distinguent pas collège/UE, même contrainte que Consolidation) ;
- `id = f"lacune_{row.id}"`, `theoretical_due_date = due_date = date.today()`
  (une lacune n'a pas d'échéance théorique — cosmétique, jamais lu pour ce
  chemin de validation) ;
- `review_type = "lacune"` (**nouvelle valeur** à ajouter au `Literal`
  `ReviewType` dans `backend/core/reviews/models.py:15`, à la suite de
  `"consolidation"` — même pattern que l'extension faite pour Consolidation) ;
- `label` = `row.detail` (le texte de la lacune) tronqué si besoin par le
  composant d'affichage, pas par l'adaptateur.

`open_session_feedback_dialog` doit gérer `review_type == "lacune"` dans son
bloc de presets (`_dialogs.py:210-215`, aux côtés de `"bonus"`/`"qcm_error"`) :
activités par défaut `["correction"]`, durée `15`, confiance `3`, difficulté
`"moyen"`, `qcm_result=None` — une lacune se traite typiquement par une
relecture ciblée de l'erreur notée, pas une révision complète.

Le `validate_fn` pour une carte lacune appelle `local_store.resolve_weak_point(weak_point_id)`
(existant, `backend/core/reviews/local_store.py:1093`) au lieu de
`mark_done`/`mark_consolidation_done`, puis `add_study_session(...)` comme les
autres chemins (cohérence du suivi de séances).

## Erreurs / cas limites

- Cours introuvable pour une lacune (`course_id` orphelin) : l'adaptateur ne
  doit pas lever d'exception — `college=[]` par défaut (voir ci-dessus), la
  carte reste affichable et validable (seul `is_to_situate` retournera `False`
  sans crasher).
- Une lacune déjà résolue entre le rendu de la liste et le clic (race
  improbable, un seul utilisateur) : `resolve_weak_point` est idempotent
  (`UPDATE ... WHERE id=?`, pas d'erreur si déjà `résolue`) — pas de garde
  supplémentaire nécessaire.
- Filtre collège du Dashboard (`state.college_filter`, `_reviews.py:871-874`) :
  les tâches de consolidation ajoutées doivent passer par le même filtre
  (les insérer dans `all_tasks` avant le filtre, pas après dans `urgent`/
  `today_tasks`, pour rester cohérent avec le filtre collège existant).

## Tests

- Nouveau test unitaire pour `weak_point_to_task` : ligne `weak_points`
  valide → `ReviewTask` correctement peuplé (cas cours trouvé, cas cours
  introuvable).
- Test que `rebuild_all` inclut bien les tâches de consolidation dans
  `urgent`/`today_tasks` selon `days_overdue`, et respecte le filtre collège.
- Test que le nouveau bloc "Plan du jour" de To Do agrège bien les 3 sources
  (mock `review_service`/`local_store`/`planning_service`, vérifier le
  nombre et le type d'items rendus) — suivre le pattern `isolated_db` déjà
  utilisé dans `tests/test_consolidation.py`.
- Pas de test automatisé pour le rendu NiceGUI lui-même (aucun précédent
  dans le projet, comme noté dans la spec Consolidation) — vérification
  manuelle en fin d'implémentation.

## Vérification manuelle

1. Ouvrir Dashboard : un item Consolidation (avec un niveau déclaré,
   collège validé) doit apparaître dans RETARD ou AUJOURD'HUI avec un
   bouton Valider fonctionnel (assistant → écriture SQLite confirmée).
2. Ouvrir To Do : la section "Plan du jour" affiche les mêmes révisions/
   lacunes/consolidation qu'on voit sur Dashboard et Planning>Consolidation,
   sans duplication de logique.
3. Valider une lacune depuis To Do : l'assistant s'ouvre, la validation
   marque la lacune "résolue" (vérifiable via
   `select status from weak_points where id=...`).
4. Filtrer par collège sur le Dashboard : les items de consolidation
   apparaissent/disparaissent avec le filtre comme les révisions classiques.

## Hors périmètre

- Pas de nouvelle table de "sélection validée du jour" — décision actée en
  brainstorming après découverte que Dashboard fonctionne déjà en lecture
  live (voir section Solution).
- L'onglet Journée/Semaine du Planning garde ses cases à cocher pour l'export
  Google Calendar ; pas de bouton Valider ajouté à `_slot_card` — ce sont des
  consommateurs supplémentaires des mêmes données, pas un remplacement de
  l'existant.
- Pas de nouvelle sous-liste sous "Agenda du jour" (calendrier uniquement,
  inchangé) — la Consolidation rejoint RETARD/AUJOURD'HUI à la place.
- Pas de changement au mécanisme de résolution de lacune déjà existant dans
  `frontend/components/weak_point_card.py` (boutons Revu/Résolu/À revoir) —
  le nouveau chemin via l'assistant est additif, pas un remplacement.
