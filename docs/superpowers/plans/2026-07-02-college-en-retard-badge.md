# Badge "En retard" basé sur le vrai statut de révision — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire dépendre le badge "En retard" de la page Collèges du vrai statut des révisions J3/J7/J14/J30 (`review_history`) au lieu d'un simple seuil de 32 jours depuis la 1ère lecture.

**Architecture:** Ajouter une méthode `get_urgent_course_ids()` sur `ReviewService` (déjà source de vérité utilisée par le dashboard) qui retourne l'ensemble des `course_id` ayant une révision en retard non traitée. Brancher `colleges.py` dessus à la place de son calcul de date maison.

**Tech Stack:** Python, `unittest`/`unittest.mock` (tests existants), NiceGUI (non testé automatiquement ici).

## Global Constraints

- Périmètre limité à la page Collèges (`frontend/pages/colleges.py`). Ne pas toucher `semestres.py` ni activer le badge côté UE.
- Ne pas modifier `ReviewTask`, `generate_reviews()`, ni `get_urgent_tasks()` — la nouvelle méthode est une façade qui les réutilise tels quels.
- Suivre le style de mock déjà utilisé dans `tests/test_review_service.py` (`MagicMock(spec=Cours)`, patch de `backend.core.reviews.service.date`).
- Aucune modification de schéma DB, aucune migration.

---

### Task 1: `ReviewService.get_urgent_course_ids()`

**Files:**
- Modify: `backend/core/reviews/service.py:288-289` (insérer la nouvelle méthode entre `get_urgent_tasks` et `get_today_tasks`)
- Test: `tests/test_review_service.py` (ajouter 3 méthodes de test à la classe `TestReviewService`)

**Interfaces:**
- Consumes: `ReviewService.generate_reviews(context, history=...)` et `ReviewService.get_urgent_tasks(all_tasks)` — signatures existantes, inchangées.
- Produces: `ReviewService.get_urgent_course_ids(context: ReviewContext = "college", history: Optional[dict] = None) -> set[str]` — utilisé par Task 2.

- [ ] **Step 1: Écrire les 3 tests (qui échouent car la méthode n'existe pas encore)**

Ouvrir `tests/test_review_service.py` et ajouter, à l'intérieur de la classe `TestReviewService` (après `test_generate_reviews_categories`, même niveau d'indentation) :

```python
    def _mock_course_min(self, cid, date_1ere, nb_lectures=0):
        """Mock minimal réutilisable pour les tests de get_urgent_course_ids."""
        c = MagicMock(spec=Cours)
        c.id = cid
        c.title = f"Cours {cid}"
        c.item_number = "100"
        c.college = ["Test"]
        c.date_1ere_lecture = date_1ere
        c.nb_lectures = nb_lectures
        c.rappel_done = True
        c.url_pdf = "path"
        c.agregation_fiche_edn = None
        c.anki = False
        c.qcm_done = False
        c.course_status = "À lire"
        c.lecture_j3_college = None
        c.lecture_j7_college = None
        c.lecture_j14_college = None
        c.lecture_j30_college = None
        c.url_pdf_ue = None
        c.nb_lectures_ue = 0
        c.date_1ere_lecture_ue = None
        c.lecture_j3_ue = None
        c.lecture_j7_ue = None
        c.lecture_j14_ue = None
        c.lecture_j30_ue = None
        return c

    @patch('backend.core.reviews.service.date')
    @patch('backend.state.store.data_store')
    def test_get_urgent_course_ids_excludes_completed_reviews(self, mock_data_store, mock_date):
        """Un cours dont TOUTES les révisions en retard sont déjà 'done' ne doit pas être urgent."""
        mock_date.today.return_value = self.today_mock
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        course = self._mock_course_min("c1", date(2026, 4, 18))
        mock_data_store.cours = [course]

        # J3=04-21, J7=04-25, J14=05-02, J30=05-18 — toutes en retard par rapport
        # au today_mock (2026-05-22), mais toutes marquées faites.
        history = {
            "c1_college_J3_2026-04-21":  {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c1_college_J7_2026-04-25":  {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c1_college_J14_2026-05-02": {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c1_college_J30_2026-05-18": {"status": "done", "postponed_to": None, "postponed_count": 0},
        }

        urgent_ids = self.service.get_urgent_course_ids("college", history=history)

        self.assertNotIn("c1", urgent_ids)

    @patch('backend.core.reviews.service.date')
    @patch('backend.state.store.data_store')
    def test_get_urgent_course_ids_includes_real_overdue(self, mock_data_store, mock_date):
        """Un cours avec une révision réellement en retard et non traitée doit être urgent."""
        mock_date.today.return_value = self.today_mock
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        course = self._mock_course_min("c2", date(2026, 5, 10))
        mock_data_store.cours = [course]

        # J3=05-13 et J7=05-17 sont en retard par rapport à today_mock (2026-05-22)
        # et n'ont aucune entrée d'historique -> statut par défaut 'todo'.
        history: dict = {}

        urgent_ids = self.service.get_urgent_course_ids("college", history=history)

        self.assertIn("c2", urgent_ids)

    @patch('backend.core.reviews.service.date')
    @patch('backend.state.store.data_store')
    def test_get_urgent_course_ids_respects_postponed_future(self, mock_data_store, mock_date):
        """Une révision reportée à une date future ne doit pas compter comme urgente."""
        mock_date.today.return_value = self.today_mock
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        course = self._mock_course_min("c3", date(2026, 4, 1))
        mock_data_store.cours = [course]

        # J3=04-04 reporté au 2026-05-25 (futur par rapport à today_mock 2026-05-22).
        # J7/J14/J30 marquées faites pour isoler le cas testé.
        history = {
            "c3_college_J3_2026-04-04":  {"status": "postponed", "postponed_to": "2026-05-25", "postponed_count": 1},
            "c3_college_J7_2026-04-08":  {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c3_college_J14_2026-04-15": {"status": "done", "postponed_to": None, "postponed_count": 0},
            "c3_college_J30_2026-05-01": {"status": "done", "postponed_to": None, "postponed_count": 0},
        }

        urgent_ids = self.service.get_urgent_course_ids("college", history=history)

        self.assertNotIn("c3", urgent_ids)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_review_service.py -v -k get_urgent_course_ids`
Expected: 3 erreurs `AttributeError: 'ReviewService' object has no attribute 'get_urgent_course_ids'`

- [ ] **Step 3: Implémenter `get_urgent_course_ids`**

Dans `backend/core/reviews/service.py`, insérer entre `get_urgent_tasks` (ligne 285-288) et `get_today_tasks` (ligne 290) :

```python
    def get_urgent_course_ids(
        self,
        context: ReviewContext = "college",
        history: Optional[dict] = None,
    ) -> set[str]:
        """
        Retourne les course_id ayant au moins une révision J3/J7/J14/J30
        en retard et non traitée (ni done, ni reportée dans le futur, ni ignorée).
        """
        history = history if history is not None else get_all_history()
        tasks = self.generate_reviews(context, history=history)
        return {t.course_id for t in self.get_urgent_tasks(tasks)}
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_review_service.py -v -k get_urgent_course_ids`
Expected: `3 passed`

Puis vérifier l'absence de régression sur le test existant :

Run: `python -m pytest tests/test_review_service.py -v`
Expected: tous les tests passent (le test existant `test_generate_reviews_categories` inclus)

- [ ] **Step 5: Commit**

```bash
git add backend/core/reviews/service.py tests/test_review_service.py
git commit -m "feat: add ReviewService.get_urgent_course_ids based on real review status"
```

---

### Task 2: Brancher `colleges.py` sur `get_urgent_course_ids`

**Files:**
- Modify: `frontend/pages/colleges.py:12` (retirer l'import `datetime` devenu inutile)
- Modify: `frontend/pages/colleges.py:83-86` (supprimer l'ancienne fonction `_is_urgent`)
- Modify: `frontend/pages/colleges.py:16-21` (ajouter les imports nécessaires)
- Modify: `frontend/pages/colleges.py:305` (calculer `_urgent_ids` et définir `_is_urgent` localement, une fois par affichage de `_show()`)

**Interfaces:**
- Consumes: `review_service.get_urgent_course_ids(context: str = "college") -> set[str]` (Task 1).

- [ ] **Step 1: Retirer l'import `datetime` inutilisé**

Dans `frontend/pages/colleges.py`, ligne 12, supprimer :

```python
import datetime
```

(Le seul usage de `datetime.*` dans ce fichier était dans `_is_urgent`, supprimée à l'étape suivante.)

- [ ] **Step 2: Ajouter les nouveaux imports**

Dans `frontend/pages/colleges.py`, après la ligne (désormais) :

```python
from backend.core.reviews.mastery import get_course_mastery, PROGRESSION_COLORS
```

ajouter :

```python
from backend.core.reviews.service import review_service
```

- [ ] **Step 3: Supprimer l'ancienne fonction `_is_urgent`**

Supprimer entièrement, dans `frontend/pages/colleges.py` :

```python
def _is_urgent(c) -> bool:
    if not c.rappel_done or not c.date_1ere_lecture:
        return False
    return (datetime.date.today() - c.date_1ere_lecture).days > 32
```

- [ ] **Step 4: Calculer `_urgent_ids` et redéfinir `_is_urgent` localement dans `_show()`**

Juste après :

```python
            courses = data_store.get_cours_for_college(tab)
            courses.sort(
                key=lambda x: x.created_time,
                reverse=(_s["sort"] == "newest"),
            )
```

ajouter :

```python
            _urgent_ids = review_service.get_urgent_course_ids("college")

            def _is_urgent(c) -> bool:
                return c.id in _urgent_ids
```

Les deux usages existants plus bas dans le fichier (`courses = [c for c in courses if _is_urgent(c)]` et `urgent = _is_urgent(cours)` dans la boucle de rendu) n'ont besoin d'aucun changement — ils appellent la même signature `_is_urgent(c) -> bool`.

- [ ] **Step 5: Vérifier qu'il n'y a plus de référence à l'ancien import ni à l'ancienne fonction**

Run: `grep -n "^import datetime\|def _is_urgent" "frontend/pages/colleges.py"`
Expected: aucune ligne pour `^import datetime` (la fonction `_is_urgent` n'apparaît que dans son unique définition, désormais imbriquée dans `_show()` — vérifier avec `grep -n "_is_urgent" frontend/pages/colleges.py` qu'il y a bien une définition (dans `_show`) et deux usages, sans doublon de définition au niveau module.

- [ ] **Step 6: Lancer la suite de tests complète pour s'assurer qu'aucune régression n'a été introduite**

Run: `python -m pytest tests/ -v`
Expected: tous les tests passent (aucun test n'importe `colleges.py`, donc aucune casse attendue côté tests automatisés ; cette étape vérifie surtout Task 1).

- [ ] **Step 7: Vérification manuelle dans l'application**

1. Lancer l'app (`python main.py` ou le lanceur habituel du projet).
2. Aller sur la page Collèges, repérer un cours avec suivi démarré depuis plus de 32 jours et au moins une révision J3/J7/J14/J30 en retard non faite → le badge rouge "En retard" doit être visible.
3. Aller dans le dashboard, marquer (✓) la dernière révision en retard de ce cours.
4. Revenir sur la page Collèges et rafraîchir → le badge doit avoir disparu, sans avoir cliqué sur "redémarrer le suivi".
5. Vérifier qu'un autre cours avec une révision réellement en retard et non traitée reste bien affiché en rouge.
6. Vérifier que le clic sur un badge "En retard" restant ouvre toujours la modale "Redémarrer le suivi" (comportement inchangé).

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/colleges.py
git commit -m "fix: base 'En retard' badge on real review completion status"
```

---

## Self-Review Notes

- **Spec coverage** : la méthode `get_urgent_course_ids` (Task 1) et son branchement dans `colleges.py` (Task 2) couvrent la totalité de la spec `docs/superpowers/specs/2026-07-02-college-en-retard-badge-design.md`. Les cas limites listés dans la spec (cours sans suivi démarré, cours non commencé côté mastery, historique vide) sont déjà couverts par le comportement existant de `generate_reviews` — aucun code défensif supplémentaire à ajouter, conformément à la spec.
- **Cohérence des types** : `get_urgent_course_ids(context: ReviewContext = "college", history: Optional[dict] = None) -> set[str]` est utilisé de façon identique dans les tests (Task 1) et dans `colleges.py` (Task 2, appelé sans argument `history` → fallback sur `get_all_history()`).
- **Pas de nouveau test UI** pour `colleges.py`, conforme à la spec (« pas de précédent dans le projet pour tester les pages NiceGUI directement ») — remplacé par la vérification manuelle de l'étape 7.
