# Métriques explicites dans la vue Collèges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Séparer visuellement et fonctionnellement lecture, maîtrise et statut dans la grille Collèges, avec la règle métier qu’un collège validé est considéré comme entièrement lu.

**Architecture:** `frontend/pages/colleges_cockpit.py` produira pour chaque ligne des champs sémantiques indépendants (`lecture_label`, `mastery_score`, `status_label`). Le calcul de lecture recevra explicitement le statut de validation du collège ; aucun score de maîtrise ne sera dérivé de cette validation. Le panneau de pilotage utilisera les mêmes données agrégées que la grille.

**Tech Stack:** Python 3.11, NiceGUI, pytest, Chromium via Playwright.

## Global Constraints

- `Lecture` mesure seulement la lecture ; `Maîtrise` affiche uniquement un score calculé ou `—` ; `Statut` est un libellé pédagogique distinct.
- Un collège `valide` force la lecture présentée à 100 % sans modifier les dates, l’historique ou la maîtrise.
- La colonne `Fragile` est supprimée de la grille car redondante avec `Maîtrise` et `Statut`.
- Aucun changement n’est requis dans `backend/core/reviews/mastery.py`.
- Les tâches urgentes, prochaines révisions, scores QCM et filtres existants conservent leur source.
- Les fichiers utilisateur modifiés ou non suivis restent hors staging.

---

### Task 1: Définir le contrat sémantique des lignes et du pilotage

**Files:**
- Modify: `tests/test_colleges_cockpit_ui.py`
- Modify: `tests/test_colleges_cockpit_items.py` si les fixtures de lignes y sont partagées
- Test: `frontend/pages/colleges_cockpit.py::_college_item_rows` et `_pilotage_summary`

**Interfaces:**
- Produces: `_college_item_rows(..., college_validated: bool = False)` avec `lecture_label`, `reading_pct`, `mastery_score`, `status_text` et `status_key`.
- Produces: `_pilotage_summary(rows)` avec `mastery_avg`, `retention_avg`, `status_counts`, `started` et `pct`.

- [ ] **Step 1: Écrire les tests rouges**

Ajouter des cas explicites :

```python
def test_college_item_rows_separate_reading_from_mastery():
    courses = [_course("c1", "12", "Lu sans preuve")]
    rows = _college_item_rows(courses, [], mastery_by_course={})

    assert rows[0]["lecture_label"] == "Lu"
    assert rows[0]["reading_pct"] == 100
    assert rows[0]["mastery_score"] is None
    assert rows[0]["status_text"] == "Lu · maîtrise non évaluée"


def test_validated_college_marks_every_item_read_without_mastery_score():
    courses = [_course("c1", "12", "Non lu", started=False)]
    rows = _college_item_rows(courses, [], mastery_by_course={}, college_validated=True)

    assert rows[0]["lecture_label"] == "Lu"
    assert rows[0]["reading_pct"] == 100
    assert rows[0]["mastery_score"] is None
    assert rows[0]["status_key"] == "lu_sans_preuve"


def test_unread_course_is_not_presented_as_mastered():
    courses = [_course("c1", "12", "A lire", started=False)]
    rows = _college_item_rows(courses, [], mastery_by_course={})

    assert rows[0]["lecture_label"] == "Non lu"
    assert rows[0]["mastery_score"] is None
    assert rows[0]["status_text"] == "À lire"
    assert rows[0]["status_key"] == "a_lire"
```
- [ ] **Step 2: Exécuter les tests pour confirmer l’échec**

Run: `pytest tests/test_colleges_cockpit_ui.py -q`

Expected: FAIL because the current row contract exposes `pct` and `score`, but not independent reading and mastery fields.

- [ ] **Step 3: Ajouter les tests de résumé**

```python
def test_pilotage_summary_separates_mastery_and_retention():
    rows = [{
        "total": 2,
        "started": 2,
        "retard": 0,
        "fragile": 0,
        "no_pdf": 0,
        "mastery_by_course": {"c1": (80, "solide"), "c2": (None, None)},
        "retention_by_course": {"c1": 65, "c2": None},
        "courses": [],
    }]

    summary = _pilotage_summary(rows)

    assert summary["pct"] == 1
    assert summary["mastery_avg"] == 80
    assert summary["retention_avg"] == 65
    assert summary["status_counts"]["solide"] == 1
    assert summary["status_counts"]["lu_sans_preuve"] == 1
```

- [ ] **Step 4: Exécuter le test rouge du résumé**

Run: `pytest tests/test_colleges_cockpit_ui.py::test_pilotage_summary_separates_mastery_and_retention -q`

Expected: FAIL until the summary exposes the separated aggregates.

---

### Task 2: Implémenter les métriques explicites et le rendu aligné

**Files:**
- Modify: `frontend/pages/colleges_cockpit.py`
- Modify: `tests/test_colleges_cockpit_ui.py`

**Interfaces:**
- Consumes: les contrats rouges de Task 1.
- Produces: grille `Item / Lecture / Maîtrise / Statut / Retard / Prochaine / QCM / Action` et panneau global séparé.

- [ ] **Step 1: Ajouter le paramètre de validation au calcul de lecture**

Dans `_college_item_rows`, calculer :

```python
read = college_validated or bool(getattr(course, "date_1ere_lecture", None))
score, level = mastery_by_course.get(course.id, (None, None))
if not read:
    status_key, status_text = "a_lire", "À lire"
elif score is None:
    status_key, status_text = "lu_sans_preuve", "Lu · maîtrise non évaluée"
else:
    status_key, status_text = level or "en construction", status_label(level)
```

Conserver `score` comme score de maîtrise uniquement. Ajouter `reading_pct`, `lecture_label`, `mastery_score`, `status_key` et `status_text` dans la ligne ; ne plus utiliser `pct` comme valeur de maîtrise.

- [ ] **Step 2: Transmettre le statut du collège**

Dans `_compute`, calculer `college_validated = validation.manual_status == "valide"` avant de calculer `started`, `pct` et `unread`. Utiliser :

```python
started = total if college_validated else sum(
    1 for c in courses if getattr(c, "date_1ere_lecture", None)
)
```

Passer `college_validated` à `_college_item_rows` lors du rendu des items. Ne pas écrire de nouvelle date de lecture.

- [ ] **Step 3: Ajouter les agrégats de maîtrise et rétention**

Construire une carte `retention_by_course` à partir des attributs disponibles sur les tâches, sans inventer de valeur absente. `_pilotage_summary` calculera la moyenne uniquement des nombres présents et retournera `None` si aucune valeur n’existe. Les statuts compteront les cours avec score, `lu_sans_preuve` ou `a_lire` sans convertir un état de lecture en score.

- [ ] **Step 4: Remplacer la définition de grille et ses cellules**

Modifier `_COLLEGE_ITEM_GRID` et le template CSS pour obtenir les colonnes :

```python
GridColumn("item", "Item", "minmax(180px,2fr)"),
GridColumn("lecture", "Lecture", "76px"),
GridColumn("mastery", "Maîtrise", "76px"),
GridColumn("status", "Statut", "120px"),
GridColumn("late", "Retard", "86px"),
GridColumn("next", "Prochaine", "100px"),
GridColumn("qcm", "QCM", "56px"),
GridColumn("action", "", "auto"),
```

Le header et `.cg-item` doivent partager exactement le même `grid-template-columns`. La cellule `Lecture` affiche `Lu` ou `Non lu`; `Maîtrise` affiche le score ou `—`; `Statut` affiche `status_text`.

- [ ] **Step 5: Clarifier le panneau Pilotage global**

Conserver `Avancement de lecture` pour `started / total`. Ajouter des cartes séparées `Maîtrise moyenne` et `Rétention` ; afficher `—` lorsque la donnée n’existe pas. Remplacer la répartition basée sur `pct` par `summary["status_counts"]`.

- [ ] **Step 6: Adapter les tests source de grille**

Vérifier la présence de `Lecture`, `Maîtrise`, `Statut`, `Retard`, `Prochaine`, `QCM`, l’absence de la colonne source `Fragile`, et l’usage du même template CSS pour header et lignes.

- [ ] **Step 7: Exécuter les tests ciblés**

Run: `pytest tests/test_colleges_cockpit_ui.py tests/test_colleges_cockpit_items.py tests/test_college_validation.py tests/test_college_validation_ui.py -q`

Expected: PASS.

- [ ] **Step 8: Committer la tranche fonctionnelle**

```bash
git add frontend/pages/colleges_cockpit.py tests/test_colleges_cockpit_ui.py tests/test_colleges_cockpit_items.py
git commit -m "feat: separate college reading and mastery metrics"
git push origin main
```

---

### Task 3: Valider la livraison et documenter la QA

**Files:**
- Modify: `DEPLOYMENT_SESSION_2026-08-09.md`
- Modify: `docs/superpowers/plans/2026-08-09-colleges-metrics-implementation.md`
- Test: Chromium via Playwright sur `/colleges`

**Interfaces:**
- Consumes: la grille et le résumé livrés par Task 2.
- Produces: preuve de tests, QA navigateur et état de déploiement.

- [ ] **Step 1: Exécuter la suite complète**

Run: `pytest -q`

Expected: PASS, sans ajout des fichiers utilisateur existants au commit.

- [ ] **Step 2: QA navigateur**

Sur `http://192.168.1.5:8888/colleges` : vérifier la présence des colonnes, l’alignement header/lignes, une ligne `Lu` avec `Maîtrise —`, le panneau `Maîtrise moyenne` et `Rétention`, puis le comportement d’un collège validé si une donnée de test est disponible.

- [ ] **Step 3: Mettre à jour les MD**

Documenter les tests, le commit applicatif, le résultat Chromium et les limites éventuelles dans `DEPLOYMENT_SESSION_2026-08-09.md`. Cocher uniquement les étapes réellement validées.

- [ ] **Step 4: Committer le rapport**

```bash
git add DEPLOYMENT_SESSION_2026-08-09.md docs/superpowers/plans/2026-08-09-colleges-metrics-implementation.md
git commit -m "docs: record colleges metrics QA"
git push origin main
```
