# Badge "En retard" basé sur le vrai statut de révision

Date : 2026-07-02
Périmètre : page Collèges (`frontend/pages/colleges.py`) uniquement. Semestres/UE reste hors périmètre (le badge n'y existe pas aujourd'hui et n'est pas activé par ce fix).

## Problème

Le badge "En retard" affiché sur `CourseCard` (page Collèges) est piloté par `_is_urgent()` dans `colleges.py` :

```python
def _is_urgent(c) -> bool:
    if not c.rappel_done or not c.date_1ere_lecture:
        return False
    return (datetime.date.today() - c.date_1ere_lecture).days > 32
```

Cette logique ne regarde que le temps écoulé depuis la 1ère lecture. Elle ignore complètement si les révisions J3/J7/J14/J30 ont réellement été faites (`review_history`, alimenté par le dashboard). Conséquences :

- Un cours dont toutes les révisions ont été cochées dans le dashboard reste marqué "En retard" indéfiniment après J32.
- Le seul moyen de l'éteindre est de cliquer sur le badge pour "redémarrer le suivi", ce qui réinitialise `date_1ere_lecture` et recalcule J3/J7/J14/J30 — une action destinée à un vrai redémarrage, pas à un simple acquittement.
- À l'inverse, un cours dont une révision est en retard mais qui n'a pas encore dépassé le seuil de 32 jours ne remonte pas comme urgent, alors qu'il l'est réellement.

Le dashboard (`frontend/pages/dashboard/_reviews.py`) résout déjà ce problème correctement via `review_service` : il génère des `ReviewTask` virtuelles par cours/type de révision, croisées avec `review_history` (statuts `done`/`postponed`/`ignored`), et `get_urgent_tasks()` retourne celles dont la date effective est dépassée et non traitées. La page Collèges n'utilise pas ce mécanisme et en réinvente une version dégradée.

## Solution

Réutiliser `review_service` comme source unique de vérité pour "un cours a-t-il une révision en retard non traitée ?", au lieu de dupliquer un calcul de date dans `colleges.py`.

### Nouvelle méthode : `ReviewService.get_urgent_course_ids()`

Ajout dans `backend/core/reviews/service.py` :

```python
def get_urgent_course_ids(
    self,
    context: ReviewContext = "college",
    history: Optional[dict] = None,
) -> set[str]:
    """
    Retourne les course_id ayant au moins une révision J3/J7/J14/J30
    en retard et non traitée (ni done, ni postponed dans le futur, ni ignored).
    """
    history = history if history is not None else get_all_history()
    tasks = self.generate_reviews(context, history=history)
    return {t.course_id for t in self.get_urgent_tasks(tasks)}
```

- Isolé et testable indépendamment de l'UI (même style que les tests existants de `test_review_service.py`, avec `data_store.cours` et `history` mockés).
- Réutilise `generate_reviews` / `get_urgent_tasks`, déjà couverts par les tests existants — pas de nouvelle logique métier, juste une nouvelle façade.
- Prend `history` en paramètre explicite (comme le fait déjà le dashboard) pour ne jamais lire le cache mémoïsé par jour de `generate_reviews` : la page Collèges doit toujours voir l'état frais après une action de révision faite dans le dashboard juste avant.

### Changement dans `colleges.py`

Remplacer la fonction module-level `_is_urgent(c)` par un calcul fait une fois par rendu de page (`_show()`), pas par carte :

```python
from backend.core.reviews.service import review_service

def _show():
    ...
    _urgent_ids = review_service.get_urgent_course_ids("college")

    def _is_urgent(c) -> bool:
        return c.id in _urgent_ids
    ...
```

Les deux points d'appel existants (`courses = [c for c in courses if _is_urgent(c)]` pour le filtre "Sans PDF"/"En retard", et la boucle de rendu des cartes) restent inchangés syntaxiquement — seule l'implémentation de `_is_urgent` change.

### Effet observable

- Le badge s'éteint automatiquement dès que la dernière révision due d'un cours est marquée faite (✓) ou reportée à une date future dans le dashboard — sans action manuelle sur la carte.
- Il se rallume si une échéance future (J7, J14, J30...) devient à son tour dépassée sans traitement.
- Le clic sur le badge (`open_start_tracking_dialog(..., is_restart=True)`) reste inchangé et cohérent : redémarrer le suivi change `date_1ere_lecture`, ce qui fait disparaître les anciennes tâches en retard (nouveaux `task_id` calculés depuis la nouvelle date).

## Erreurs / cas limites

- **Cours sans suivi démarré** (`date_1ere_lecture` absent) : `generate_reviews` ne génère aucune tâche pour lui (`if not date_ref: continue`) → jamais dans `get_urgent_course_ids` → jamais urgent. Comportement identique à avant.
- **Cours non commencé côté mastery** (`mastery.score is None`) : idem, filtré en amont dans `generate_reviews`, ne peut pas apparaître comme urgent.
- **`get_all_history()` échoue / DB verrouillée** : pas de nouveau risque introduit — c'est le même appel que celui déjà fait à chaque rendu du dashboard ; une exception remonterait de la même façon qu'aujourd'hui côté dashboard.
- **Page Collèges chargée sans qu'aucune révision n'ait jamais été générée** (base `review_history` vide) : tous les statuts valent `"todo"`, donc un cours en retard réel apparaît bien comme urgent dès la première visite — pas de dépendance à un historique préexistant.

## Tests

Ajouter dans `tests/test_review_service.py` (même style que `test_generate_reviews_categories`) :

1. `test_get_urgent_course_ids_excludes_completed_reviews` — un cours dont la J30 est en retard mais marquée `status="done"` dans l'historique ne doit PAS apparaître dans `get_urgent_course_ids()`.
2. `test_get_urgent_course_ids_includes_real_overdue` — un cours avec une J3 en retard et `status="todo"` doit apparaître.
3. `test_get_urgent_course_ids_respects_postponed_future` — une révision reportée (`status="postponed"`, `postponed_to` dans le futur) ne doit pas compter comme urgente.

Pas de test UI sur `colleges.py` (pas de précédent dans le projet pour tester les pages NiceGUI directement) — la correction y est un simple branchement d'une fonction déjà testée, vérifié manuellement en lançant l'app.

## Vérification manuelle

1. Lancer l'app, ouvrir un cours avec suivi démarré depuis plus de 32 jours et au moins une révision en retard non faite → badge rouge visible.
2. Dans le dashboard, marquer la dernière révision en retard de ce cours comme faite (✓).
3. Revenir sur la page Collèges (refresh) → le badge doit avoir disparu, sans avoir cliqué sur "redémarrer le suivi".
4. Vérifier qu'un cours avec une révision réellement en retard et non traitée s'affiche toujours en rouge.
