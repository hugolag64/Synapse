# Déduplication cours par item_number Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Éliminer les doublons de cours (ex: "Arrêt cardiorespiratoire" et "ACR" pour ITEM 331) en dédupliquant `data_store.cours` par `item_number`, en conservant le cours dont le titre est le plus proche du titre EDN canonique.

**Architecture:** Deux interventions ciblées. (1) Un helper statique `DataStore._deduplicate_cours()` appelé aux 3 points d'assignation de `self.cours`. (2) La fonction `_find_course()` dans `ai_qcm/service.py` est corrigée pour ne pas retourner de façon aléatoire quand plusieurs cours matchent le même `item_number`.

**Tech Stack:** Python stdlib (`difflib.SequenceMatcher`), `backend.core.qcm.items_mapping.item_title` (déjà présent), pytest.

## Global Constraints

- Ne jamais supprimer de données Notion — la déduplication est locale (DataStore + SQLite). Les pages Notion restent intactes.
- Les cours sans `item_number` (vide ou None) ne sont PAS dédupliqués.
- Si deux cours ont même `item_number` mais colleges différents, conserver les deux (filtrer sur même college OU ignorer la contrainte college et toujours choisir le plus canonique — voir Task 1).
- `difflib` est stdlib, pas de nouvelle dépendance.

---

### Task 1 : `DataStore._deduplicate_cours()` + câblage aux 3 points d'assignation

**Files:**
- Modify: `backend/state/store.py:91-115` (après `_resolve_item_numbers`) et lignes 214, 449, 466
- Test: `tests/test_store_dedup.py` (à créer)

**Interfaces:**
- Produces: `DataStore._deduplicate_cours(cours: list[Cours]) -> list[Cours]` — méthode statique pure, sans side-effects

- [ ] **Step 1 : Écrire les tests unitaires**

Créer `tests/test_store_dedup.py` :

```python
"""Tests pour DataStore._deduplicate_cours()"""
import pytest
from unittest.mock import patch, MagicMock
from backend.state.store import DataStore
from backend.core.notion.models import Cours


def _make_cours(id_: str, title: str, item_number: str = "", college: list = None) -> Cours:
    return Cours(
        id=id_,
        title=title,
        item_number=item_number,
        college=college or [],
    )


class TestDeduplicateCours:
    def test_no_duplicates_unchanged(self):
        cours = [
            _make_cours("a", "Arrêt cardio-circulatoire", "331"),
            _make_cours("b", "Dyslipidémies", "223"),
        ]
        result = DataStore._deduplicate_cours(cours)
        assert len(result) == 2

    def test_no_item_number_kept(self):
        cours = [
            _make_cours("a", "Cours sans item", ""),
            _make_cours("b", "Autre sans item", ""),
        ]
        result = DataStore._deduplicate_cours(cours)
        assert len(result) == 2

    def test_duplicate_keeps_canonical(self):
        """Doit conserver le cours dont le titre matche mieux le titre EDN."""
        cours = [
            _make_cours("acr", "ACR", "331"),
            _make_cours("full", "Arrêt cardio-circulatoire", "331"),
        ]
        # items_mapping.item_title(331) → "Arrêt cardio-circulatoire"
        with patch(
            "backend.state.store.item_title",
            return_value="Arrêt cardio-circulatoire",
        ):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 1
        assert result[0].id == "full"

    def test_duplicate_with_empty_canonical_keeps_longer_title(self):
        """Si pas de titre EDN, garde le titre le plus long."""
        cours = [
            _make_cours("a", "ACR", "999"),
            _make_cours("b", "Arrêt cardio-circulatoire", "999"),
        ]
        with patch("backend.state.store.item_title", return_value=""):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 1
        assert result[0].id == "b"

    def test_three_duplicates_keeps_best(self):
        cours = [
            _make_cours("a", "ACR", "331"),
            _make_cours("b", "Arrêt cardiaque", "331"),
            _make_cours("c", "Arrêt cardio-circulatoire", "331"),
        ]
        with patch(
            "backend.state.store.item_title",
            return_value="Arrêt cardio-circulatoire",
        ):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 1
        assert result[0].id == "c"

    def test_mixed_items_and_no_item(self):
        cours = [
            _make_cours("a", "ACR", "331"),
            _make_cours("b", "Arrêt cardio-circulatoire", "331"),
            _make_cours("c", "Sans item", ""),
            _make_cours("d", "Dyslipidémies", "223"),
        ]
        with patch(
            "backend.state.store.item_title",
            side_effect=lambda n: "Arrêt cardio-circulatoire" if n == "331" else "",
        ):
            result = DataStore._deduplicate_cours(cours)
        assert len(result) == 3  # best 331 + sans item + 223
        ids = {c.id for c in result}
        assert "a" not in ids  # ACR éliminé
        assert "b" in ids
        assert "c" in ids
        assert "d" in ids
```

- [ ] **Step 2 : Lancer les tests — vérifier qu'ils ÉCHOUENT**

```
pytest tests/test_store_dedup.py -v
```

Attendu : `AttributeError: type object 'DataStore' has no attribute '_deduplicate_cours'`

- [ ] **Step 3 : Ajouter l'import et la méthode dans `backend/state/store.py`**

En tête du fichier `backend/state/store.py`, ajouter l'import (après les imports existants) :

```python
import difflib
from backend.core.qcm.items_mapping import item_title
```

Puis, après la méthode `_resolve_item_numbers` (ligne ~115), ajouter :

```python
@staticmethod
def _deduplicate_cours(cours: list) -> list:
    """
    Déduplique par item_number : si plusieurs cours partagent le même numéro d'item,
    garde celui dont le titre est le plus proche du titre EDN canonique.
    Les cours sans item_number sont conservés sans modification.
    """
    def _norm_item(raw: str) -> str | None:
        try:
            return str(int(float(str(raw).strip())))
        except (ValueError, TypeError):
            return None

    def _title_score(course_title: str, canonical: str) -> float:
        if not canonical:
            return float(len(course_title))  # fallback : titre le plus long
        return difflib.SequenceMatcher(
            None,
            course_title.lower().strip(),
            canonical.lower().strip(),
        ).ratio()

    groups: dict[str, list] = {}
    no_item: list = []
    for c in cours:
        n = _norm_item(getattr(c, "item_number", "") or "")
        if n is None:
            no_item.append(c)
        else:
            groups.setdefault(n, []).append(c)

    result: list = list(no_item)
    for n, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        canonical = item_title(n)
        best = max(group, key=lambda c: _title_score(getattr(c, "title", "") or "", canonical))
        discarded = [getattr(c, "title", "?") for c in group if c is not best]
        logger.info(
            f"Doublon ITEM {n} : conservé '{best.title}', ignoré(s) : {discarded}"
        )
        result.append(best)

    return result
```

- [ ] **Step 4 : Câbler la déduplication aux 3 points d'assignation**

**Point 1 — `load_from_disk` (ligne ~214)** :

Remplacer :
```python
self.cours = [Cours(**c) for c in data.get("cours", [])]
```
Par :
```python
self.cours = self._deduplicate_cours([Cours(**c) for c in data.get("cours", [])])
```

**Point 2 — `refresh` (ligne ~449)** :

Remplacer :
```python
self.cours = new_cours
```
Par :
```python
self.cours = self._deduplicate_cours(new_cours)
```

**Point 3 — `merge_cours_delta` (ligne ~466)** :

Remplacer :
```python
self.cours = list(existing_map.values())
```
Par :
```python
self.cours = self._deduplicate_cours(list(existing_map.values()))
```

- [ ] **Step 5 : Lancer les tests — vérifier qu'ils PASSENT**

```
pytest tests/test_store_dedup.py -v
```

Attendu : tous verts.

- [ ] **Step 6 : Vérifier que les tests existants passent encore**

```
pytest tests/ -v --tb=short
```

Attendu : aucune régression.

- [ ] **Step 7 : Commit**

```bash
git add backend/state/store.py tests/test_store_dedup.py
git commit -m "feat: deduplicate DataStore.cours by item_number using EDN canonical title"
```

---

### Task 2 : Correction de `_find_course()` dans `ai_qcm/service.py`

**Files:**
- Modify: `backend/core/ai_qcm/service.py:38-88`
- Test: `tests/test_ai_qcm_service.py` (à créer)

**Interfaces:**
- Consumes: `item_title(n: str) -> str` depuis `backend.core.qcm.items_mapping`
- Produces: `_find_course(item_number, course_title, courses) -> (course_id, title, item_number)` — comportement inchangé sauf en cas de multi-match sur item_number

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_ai_qcm_service.py` :

```python
"""Tests pour _find_course() dans ai_qcm/service.py"""
import pytest
from unittest.mock import patch
from types import SimpleNamespace
from backend.core.ai_qcm.service import _find_course


def _c(id_, title, item_number=""):
    return SimpleNamespace(id=id_, title=title, item_number=item_number)


class TestFindCourse:
    def test_single_match_by_item(self):
        courses = [_c("a", "Arrêt cardio-circulatoire", "331"), _c("b", "Dyslipidémies", "223")]
        cid, title, item = _find_course("331", "", courses)
        assert cid == "a"

    def test_no_match_returns_empty(self):
        courses = [_c("a", "Arrêt cardio-circulatoire", "331")]
        cid, title, item = _find_course("999", "Inconnu", courses)
        assert cid == ""

    def test_multi_match_item_prefers_canonical(self):
        """Quand deux cours ont même item_number, choisir le plus canonique."""
        courses = [
            _c("acr", "ACR", "331"),
            _c("full", "Arrêt cardio-circulatoire", "331"),
        ]
        with patch(
            "backend.core.ai_qcm.service.item_title",
            return_value="Arrêt cardio-circulatoire",
        ):
            cid, title, item = _find_course("331", "", courses)
        assert cid == "full"

    def test_multi_match_item_fallback_longer_title(self):
        """Sans titre EDN, le plus long titre gagne."""
        courses = [
            _c("a", "ACR", "999"),
            _c("b", "Arrêt cardio-circulatoire", "999"),
        ]
        with patch("backend.core.ai_qcm.service.item_title", return_value=""):
            cid, title, item = _find_course("999", "", courses)
        assert cid == "b"

    def test_title_match_fallback(self):
        """Sans item_number, fallback sur titre exact."""
        courses = [_c("a", "Dyslipidémies", "")]
        cid, title, item = _find_course("", "Dyslipidémies", courses)
        assert cid == "a"
```

- [ ] **Step 2 : Lancer les tests — vérifier qu'ils ÉCHOUENT sur le cas multi-match**

```
pytest tests/test_ai_qcm_service.py -v
```

Attendu : `test_multi_match_item_prefers_canonical` et `test_multi_match_item_fallback_longer_title` échouent (le code actuel retourne le premier match aléatoirement).

- [ ] **Step 3 : Modifier `_find_course()` dans `backend/core/ai_qcm/service.py`**

En tête du fichier, ajouter l'import :
```python
import difflib
from backend.core.qcm.items_mapping import item_title
```

Remplacer le bloc "Match par item_number" (lignes 48-62) :

```python
# 1. Match par item_number — collecte tous les matchs, choisit le plus canonique
if item_number:
    try:
        clean = str(int(float(item_number.strip())))
    except (ValueError, OverflowError):
        clean = item_number.strip().lstrip("0")

    matches = []
    for c in courses:
        raw_c = str(getattr(c, "item_number", "") or "").strip()
        try:
            c_item = str(int(float(raw_c)))
        except (ValueError, OverflowError):
            c_item = raw_c.lstrip("0")
        if c_item and c_item == clean:
            matches.append(c)

    if matches:
        if len(matches) == 1:
            best = matches[0]
        else:
            canonical = item_title(clean)
            def _score(c: object) -> float:
                t = (getattr(c, "title", "") or "").lower().strip()
                if not canonical:
                    return float(len(t))
                return difflib.SequenceMatcher(None, t, canonical.lower().strip()).ratio()
            best = max(matches, key=_score)
        return best.id, best.title, str(getattr(best, "item_number", "") or "")
```

- [ ] **Step 4 : Lancer les tests — vérifier qu'ils PASSENT**

```
pytest tests/test_ai_qcm_service.py -v
```

Attendu : tous verts.

- [ ] **Step 5 : Vérifier que les tests existants passent**

```
pytest tests/ -v --tb=short
```

Attendu : aucune régression.

- [ ] **Step 6 : Commit**

```bash
git add backend/core/ai_qcm/service.py tests/test_ai_qcm_service.py
git commit -m "fix: _find_course() picks EDN-canonical course on item_number multi-match"
```

---

## Vérification manuelle post-implémentation

1. Lancer l'app et aller sur la page Collèges / Stats — vérifier que l'ITEM 331 n'apparaît plus qu'une fois
2. Importer un fichier QCM markdown pour l'ITEM 331 → vérifier que le cours résolu est "Arrêt cardio-circulatoire" (ou le titre EDN le plus proche)
3. Vérifier les logs au démarrage : le message `"Doublon ITEM 331 : conservé '...', ignoré(s) : [...]"` doit apparaître

## Self-Review

**Spec coverage :**
- ✅ Déduplication à la source (DataStore) — Task 1
- ✅ Complément `_find_course()` — Task 2
- ✅ Critère de sélection : titre EDN canonique via `item_title()` — les deux tasks
- ✅ Cours sans item_number conservés intacts — `_deduplicate_cours` + `_find_course`
- ✅ Aucune donnée Notion supprimée

**Placeholder scan :** Aucun TBD/TODO dans le plan.

**Type consistency :**
- `item_title` importé et utilisé identiquement dans les deux tasks
- `_deduplicate_cours` est `@staticmethod` — appel `self._deduplicate_cours(...)` ou `DataStore._deduplicate_cours(...)` sont équivalents
