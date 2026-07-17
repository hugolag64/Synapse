# Flux de consolidation long terme (SM-2 étendu) pour le planning

Date : 2026-07-17
Périmètre : moteur de planification (`backend/core/planning`, `backend/core/reviews`, `backend/core/knowledge`) + page Planning (`frontend/pages/planning.py`). Le sélecteur de charge de travail (Basse/Normal/Hot) évoqué initialement est **hors périmètre** — sous-projet séparé, voir section "Hors périmètre".

## Problème

Deux besoins distincts, qui convergent vers la même solution.

**1. Bug** : les items à niveau déclaré (flou/correct/solide, via `ItemState` dans `backend/core/knowledge`) ne génèrent aucune tâche de révision. Cause : `ReviewService.generate_reviews()` (`backend/core/reviews/service.py:120-125`) fait `if not date_ref: continue` — un cours sans `date_1ère_lecture` est écarté avant même l'appel à `get_course_mastery()`. Or `mastery.py` a une logique dédiée (lignes 108-119) pour les items déclarés sans preuve réelle, mais elle n'est jamais atteinte depuis `generate_reviews()`. Ces items ont en réalité déjà été lus (avant l'existence de l'app) — l'absence de `date_1ère_lecture` est un trou de données, pas une absence de lecture.

**2. Besoin produit** : l'EDN est un marathon. Un item qui termine son cycle J3→J7→J14→J30 dans l'app ne génère plus aucune tâche ensuite — il disparaît du radar. Il faut un mécanisme de consolidation qui continue indéfiniment, pour les deux populations (items déclarés pré-app **et** items qui ont fini leur cycle J30), sans que la charge quotidienne explose à mesure que de nouveaux collèges se valident chaque semestre.

## Solution

### Extension du moteur SM-2 existant plutôt qu'un nouveau système

Synapse a déjà un moteur SM-2 fonctionnel (`backend/core/reviews/sm2.py` : `compute_next_interval`, `easiness_factor`, `repetition_count`, `next_interval_days`, déjà stockés dans `review_history`), utilisé aujourd'hui uniquement pour ajuster les échéances **à l'intérieur** de la chaîne fixe J3→J7→J14→J30 (`_PREV_REVIEW_TYPE` dans `local_store.py`). Il s'arrête à J30. On le prolonge avec un nouveau `review_type = "consolidation"`, **chaîné à lui-même indéfiniment** :

```python
# backend/core/reviews/local_store.py
_PREV_REVIEW_TYPE: dict[str, str] = {
    "J7": "J3", "J14": "J7", "J30": "J14",
    "consolidation": "consolidation",   # nouveau : self-chaining
}
```

`get_sm2_effective_date(course_id, context, "consolidation")` cherchera alors la dernière ligne `review_history` `status='done'` avec `review_type="consolidation"` pour ce cours, et calculera `completed_at + next_interval_days` — exactement le même mécanisme que J7 dépend de J3, mais sans jamais s'arrêter.

**Pourquoi c'est la bonne réponse à l'accumulation** : ce n'est plus "tout le pool doit repasser tous les X jours" (charge qui grossit linéairement avec le nombre de collèges validés). Chaque item a son propre rythme, qui s'étire automatiquement dès qu'il est bien maîtrisé (ease factor croissant, comme Anki). Un nouveau collège ajoute une chaîne qui démarre à un intervalle court puis s'étire — la charge quotidienne reste bornée même après plusieurs semestres d'accumulation.

### Amorçage (bootstrap) de la chaîne

Une chaîne "consolidation" a besoin d'un premier maillon avant que `get_sm2_effective_date` puisse calculer quoi que ce soit. Nouvelle fonction dans `local_store.py` :

```python
def bootstrap_consolidation(
    course_id: str, context: str, course_title: str, item_number: str,
    initial_interval_days: int, at_date: datetime.date,
) -> None:
    """Insère la ligne d'amorçage 'consolidation' si elle n'existe pas déjà
    (idempotent — vérifie l'absence d'une ligne review_type='consolidation')."""
```

Elle insère une ligne synthétique `status='done'`, `completed_at=at_date`, `next_interval_days=initial_interval_days`, `easiness_factor=SM2_INIT_EF`, `repetition_count=0`. Deux déclencheurs :

1. **Item déclaré pré-app** (pas de `date_1ère_lecture`) : amorcé dès que `ItemState` existe pour ce cours, avec `at_date = declared_at`.
2. **Item qui termine son cycle J30** : amorcé quand les 4 lignes `review_history` (J3/J7/J14/J30, `context` donné) sont toutes `status='done'`, avec `at_date = date de complétion du J30`.

Intervalle initial selon le niveau de maîtrise au moment de l'amorçage (échelle unifiée `mastery.level`, qui couvre aussi bien les niveaux déclarés — via `level_from_seed` — que les niveaux calculés) :

| Niveau | Intervalle initial |
|---|---|
| critique | 14j |
| fragile | 18j |
| en construction | 18j |
| à consolider | 24j |
| à entraîner | 24j |
| maîtrisé | 30j |

Au-delà de ce premier maillon, chaque validation avec une confiance (1-5) recalcule le prochain intervalle via `compute_next_interval` — même mécanisme que J3→J7→J14→J30, aucune nouvelle formule.

### Pool de consolidation (unifié, global)

Un seul pool, pas un pool par collège. Nouvelle fonction, ex. `backend/core/reviews/service.py::get_consolidation_pool(context="college")` :

Un cours y entre si `mastery.score is not None` (démarré, lu ou déclaré) **et** :
- soit il n'a jamais eu de `date_1ère_lecture` (`context`-dépendant),
- soit ses 4 tâches J3/J7/J14/J30 sont toutes `status='done'`.

(Un cours en cours de cycle J-normal, `date_ref` présent mais toutes les tâches pas encore faites, reste exclu — pas de double-tracking.)

Pour chaque cours éligible : appeler `bootstrap_consolidation` si nécessaire, lire l'échéance via `get_sm2_effective_date`, et ne garder que les tâches **dues aujourd'hui ou en retard** (`due_date <= today`) — exactement comme `generate_reviews()` filtre déjà les tâches classiques.

### Priorité et diversité à la sélection du jour

Le nombre d'items dus un jour donné peut occasionnellement dépasser ce qu'on veut proposer (plusieurs chaînes arrivées à échéance le même jour par coïncidence). Score de tri, calculé seulement parmi les items **déjà dus** (pas de "cycle cible" global à gérer) :

```
score = jours_de_retard × poids_semestre × poids_niveau
```

- `poids_semestre` : croissant plus le semestre de l'item (`c.semestre`, propriété Notion déjà en place et renseignée pour les 9 collèges validés + Hépato-Gastro) est ancien par rapport à une nouvelle préférence `semestre_actuel` (dans `data_store.preferences`, incrémentée manuellement par l'utilisateur à chaque rentrée — actuellement "Semestre 7"). Formule : `poids_semestre = 1 + max(0, semestre_actuel_num - item_semestre_num) * 0.15` (ex. item S3 vs semestre actuel S7 → `1 + 4*0.15 = 1.6`). Un item du semestre en cours ou futur (gap ≤ 0) reste à `1.0` — pas de pénalité, juste pas de bonus.
- `poids_niveau` : réutilise le mapping `mastery_bonus` déjà existant dans `_calculate_priority` (`reviews/service.py:443-450`), pas de nouvelle échelle.

**Diversité** : sélection gloutonne des N scores les plus hauts avec un plafond par collège (ex. max 2/collège/jour, valeur en dur pour la v1) — le surplus va dans `DailyPlan.skipped` (champ déjà présent dans `backend/core/planning/models.py:58`, actuellement toujours vide) et repasse naturellement le(s) jour(s) suivant(s) puisque sa date d'échéance SM-2 ne change pas tant qu'il n'est pas validé.

### UI — nouvel onglet "À consolider"

Sur la page Planning (`frontend/pages/planning.py`), à côté des boutons Journée/Semaine : un troisième mode "Consolidation". Nouveau `slot_type: "consolidation"` dans `SLOT_META` (`backend/core/planning/models.py`), couleur/icône dédiées (proposition : `cyan` / `history_edu`, à distinguer visuellement des review classiques).

Chaque carte propose trois actions :

1. **Valider** : ouvre le même dialogue de validation que les révisions classiques (confiance 1-5, difficulté) → `mark_done()` avec `review_type="consolidation"`, qui recalcule `next_interval_days` via SM-2. L'autoéval demandée module donc directement la fréquence future, sans mécanisme séparé.
2. **Passer** ("pas aujourd'hui") : réutilise `postpone()` (`local_store.py:405`), déjà générique par `course_id`/`context`/`review_type`. Un report de quelques jours, sans impact sur l'ease factor (contrairement à "Valider" avec confiance basse). Bouton global **"Tout reporter"** au niveau de l'onglet, qui appelle `postpone()` sur toutes les cartes affichées ce jour-là — pour les jours vacances / sans motivation.
3. **Ajouter un cours travaillé** (action au niveau de l'onglet, pas d'une carte) : champ de recherche réutilisant `_search_courses()` (`frontend/components/command_palette.py:40`) pour choisir n'importe quel cours du collège en dehors de la liste proposée. Amorce sa chaîne "consolidation" si elle n'existe pas encore, puis ouvre le même dialogue de validation — le cours avance dans sa chaîne SM-2 même s'il n'était pas dû aujourd'hui.

## Erreurs / cas limites

- **Item déclaré puis suivi normalement plus tard** (l'utilisateur renseigne `date_1ère_lecture` après coup pour un item déjà en chaîne "consolidation") : le cours redevient exclu du pool tant que son nouveau cycle J3-J30 n'est pas entièrement fait. Une fois refait, il redevient éligible et reprend simplement depuis la dernière ligne "consolidation" déjà en base (le prochain intervalle SM-2 continue sa progression, pas de reset) — comportement accepté, cas rare.
- **`bootstrap_consolidation` appelé plusieurs fois** : idempotent, vérifie l'absence d'une ligne `review_type='consolidation'` avant d'insérer.
- **Collège sans `semestre` renseigné** (nouveau collège validé avant que l'utilisateur n'ait mis à jour Notion) : `poids_semestre` retombe sur une valeur neutre (1.0) plutôt que de planter ou de sur-pondérer — l'item reste éligible et trié par défaut sur date d'échéance + niveau seul.
- **`semestre_actuel` non renseigné** : valeur par défaut raisonnable (ex. le semestre max observé parmi `data_store.cours`), pas d'exception.
- **Pool vide** (aucun item dû aujourd'hui) : onglet affiche un état vide, cohérent avec le pattern déjà utilisé pour "Rien à planifier" dans `_render_day_plan`.

## Tests

Dans `tests/test_review_service.py` ou un nouveau `tests/test_consolidation.py` :

1. `test_bootstrap_consolidation_idempotent` — deux appels successifs ne créent qu'une ligne.
2. `test_bootstrap_triggered_on_j30_completion` — les 4 tâches J3/J7/J14/J30 marquées `done` déclenchent l'amorçage ; 3 sur 4 ne le déclenchent pas.
3. `test_bootstrap_triggered_on_declared_item` — un `ItemState` sans `date_1ère_lecture` déclenche l'amorçage avec l'intervalle initial correspondant au niveau déclaré.
4. `test_consolidation_pool_excludes_mid_cycle` — un cours avec `date_1ère_lecture` et une tâche J14 encore `todo` n'apparaît pas dans le pool.
5. `test_consolidation_interval_grows_with_confidence` — valider deux fois de suite avec confiance haute allonge `next_interval_days` (test direct de `compute_next_interval`, déjà couvert indirectement mais à vérifier pour le cas self-chaining).
6. `test_daily_selection_respects_college_cap` — 5 items dus le même jour dont 4 du même collège → au plus 2 retenus pour ce collège, les autres dans `skipped`.

## Vérification manuelle

1. Lancer l'app, ouvrir l'onglet "À consolider" sur un compte avec au moins un des 9 collèges validés (ex. Pneumologie) → l'item doit apparaître (vérifie le fix du bug initial).
2. Valider un item avec confiance haute (4-5) → rouvrir l'onglet plus tard (ou vérifier en base `next_interval_days`) → l'intervalle doit être plus long qu'à l'amorçage.
3. Valider un autre item avec confiance basse (1-2) → l'intervalle doit être court (retour rapide, comportement SM-2 standard déjà vérifié pour J3-J30).
4. Cliquer "Passer" sur une carte → elle disparaît du jour, revient à la date reportée.
5. Cliquer "Tout reporter" avec plusieurs cartes affichées → toutes reportées d'un coup.
6. Ajouter un cours via la recherche, le valider → vérifier qu'une ligne `consolidation` apparaît en base pour ce cours même s'il n'était pas dans la liste du jour.
7. Faire terminer artificiellement un cycle J3-J30 complet sur un cours de test → vérifier qu'il apparaît ensuite dans l'onglet Consolidation sans action manuelle.

## Hors périmètre

- **Sélecteur de charge de travail (Basse/Normal/Hot)** : amélioration future, viendrait se brancher comme un multiplicateur ponctuel sur le nombre d'items retenus à la sélection du jour — pas de dépendance structurelle avec ce design, peut être fait indépendamment.
- **Historique de révisions consolidation dans l'UI** (visualiser combien de fois un item a été consolidé) : pas demandé, `repetition_count` est déjà stocké si besoin plus tard.
