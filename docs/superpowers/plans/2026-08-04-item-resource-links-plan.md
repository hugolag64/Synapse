# Item Resource Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher dans le panneau Ressources du cockpit item les vidéos EDNpro dont le rattachement est traçable et suffisamment fiable.

**Architecture:** Créer un registre local de ressources externes alimenté par la collecte EDNpro. Les ressources globales restent dans Prépa ; seules les ressources portant une liaison item validée sont rendues dans `course_detail_cockpit.py`. Les liens ambigus restent consultables dans une file de vérification.

**Tech Stack:** Python, SQLite, NiceGUI, pytest.

## Global Constraints

- Ne jamais déduire une liaison item uniquement à partir d’un mot proche.
- Ne pas stocker de lien CDN signé ou de jeton de session ; stocker la page EDNpro stable.
- Afficher le fournisseur et la confiance/méthode de rattachement lorsque cela aide la décision.
- Ne pas afficher de recommandation personnalisée lorsqu’aucune liaison fiable n’existe.

---

### Task 1: Store and query external preparation resources

**Files:**
- Create: `backend/core/prep/resources.py`
- Modify: `backend/core/reviews/local_store.py` pour la table `prep_resources`
- Test: `tests/test_prep_resources.py`

**Interfaces:**
- Produces `upsert_prep_resource(...)`, `list_prep_resources_for_item(item_number: str) -> list[dict]` and `normalize_stable_resource_url(url: str) -> str`.
- Consumes resource rows from the EDNpro collector and question-level item links.

- [ ] **Step 1: Write failing tests for URL safety and item filtering**

```python
def test_signed_video_url_is_reduced_to_stable_page_url():
    assert normalize_stable_resource_url(
        "https://ednpro.app/videos/123?token=secret&expires=123"
    ) == "https://ednpro.app/videos/123"

def test_item_query_excludes_ambiguous_resources():
    rows = list_prep_resources_for_item("221")
    assert all(row["confidence"] >= 0.8 for row in rows)
```

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `pytest tests/test_prep_resources.py -q`

Expected: FAIL because the resource store does not exist.

- [ ] **Step 3: Implement migration and idempotent upsert**

Store provider, resource type, title, stable URL, item number, matching method, confidence, source page and last verified timestamp. Use a unique key on `(provider, stable_url, item_number)` and reject URLs containing obvious auth/query secrets.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_prep_resources.py -q`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/prep/resources.py backend/core/reviews/local_store.py tests/test_prep_resources.py
git commit -m "feat: store item-linked prep resources"
```

### Task 2: Render verified video links in the item cockpit

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py` in `_render_panel` under `Ressources`
- Modify: `frontend/components/context_panel.py` for the compact task drawer, if the same resource list is exposed there
- Test: `tests/test_item_resource_panel.py`

**Interfaces:**
- Consumes `list_prep_resources_for_item(item_number)`.
- Produces compact external links with provider/category labels and `new_tab=True`.

- [ ] **Step 1: Write failing rendering/data assembly tests**

```python
def test_item_resource_panel_shows_verified_ednpro_video():
    rows = build_item_resources("221", [
        {"provider": "EDNpro", "resource_type": "video", "title": "Athérome", "url": "https://ednpro.app/videos/221", "confidence": 1.0}
    ])
    assert rows[0]["label"] == "Athérome"
    assert rows[0]["provider"] == "EDNpro"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest tests/test_item_resource_panel.py -q`

Expected: FAIL because the resource assembly function does not exist.

- [ ] **Step 3: Implement the compact resource block**

Keep existing PDF, Obsidian and fiche links. Add a `Vidéos EDNpro` subsection only when verified rows exist, show title plus provider/category, and open the stable page URL in a new tab. Do not render raw signed URLs.

- [ ] **Step 4: Add empty and ambiguous states**

When there are no verified videos, keep the existing empty-resource behavior. Do not show an “inconnu” video as if it were item-specific.

- [ ] **Step 5: Run focused and cockpit regression tests**

Run: `pytest tests/test_item_resource_panel.py -q`.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/course_detail_cockpit.py frontend/components/context_panel.py tests/test_item_resource_panel.py
git commit -m "feat: show verified item video resources"
```
