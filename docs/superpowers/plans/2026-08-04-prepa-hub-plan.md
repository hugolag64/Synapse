# Prépa Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une vue Prépa Linear/Synapse qui centralise EDNpro, Hypocampus et les futurs fournisseurs avec des raccourcis configurables.

**Architecture:** Stocker les fournisseurs et raccourcis comme données locales, puis rendre une page unique avec états de connexion, actions rapides, raccourcis par catégorie et derniers accès. Les cartes n’embarquent pas de logique spécifique au fournisseur ; elles consomment une liste de raccourcis structurée.

**Tech Stack:** Python, SQLite via `backend.core.reviews.local_store`, NiceGUI, CSS cockpit existant, pytest.

## Global Constraints

- UI blanche/grise, bordures fines, densité cockpit et un seul CTA primaire par carte.
- Les URLs sont configurables et ne doivent pas être dispersées dans le rendu.
- EDNpro affiche un état de connexion et ouvre la session externe dans un nouvel onglet ou la fenêtre dédiée prévue.
- Hypocampus est disponible comme fournisseur de raccourcis ; EDNi peut être affiché comme futur fournisseur sans faux état connecté.

---

### Task 1: Ajouter le catalogue local des fournisseurs et raccourcis

**Files:**
- Create: `backend/core/prep/__init__.py`
- Create: `backend/core/prep/catalog.py`
- Modify: `backend/core/reviews/local_store.py` pour la table `prep_shortcuts`
- Test: `tests/test_prep_catalog.py`

**Interfaces:**
- Produces `PrepProvider`, `PrepShortcut` and `list_prep_shortcuts(provider: str | None = None) -> list[PrepShortcut]`.
- Consumes application preferences for configurable URLs.

- [ ] **Step 1: Write the failing catalog tests**

```python
def test_default_ednpro_shortcuts_are_grouped_by_category():
    rows = list_prep_shortcuts("EDNpro")
    assert {row.category for row in rows} >= {"annales", "iconographie", "videos"}
    assert all(row.url.startswith("https://") for row in rows)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest tests/test_prep_catalog.py -q`

Expected: FAIL because the catalog does not exist.

- [ ] **Step 3: Implement migration and default seed data**

Store provider, category, title, description, URL, icon, enabled flag, sort order and last-used timestamp. Seed EDNpro routes from the live-confirmed URLs and Hypocampus with its root shortcut. Keep EDNi disabled until configured.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_prep_catalog.py -q`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/prep backend/core/reviews/local_store.py tests/test_prep_catalog.py
git commit -m "feat: add prep provider catalog"
```

### Task 2: Add the Prépa page and navigation entry

**Files:**
- Create: `frontend/pages/prepa.py`
- Modify: `frontend/cockpit_shell.py` to add the `Prépa` navigation item and active title mapping
- Modify: `main.py` or the existing page import registry
- Test: `tests/test_prepa_page.py`

**Interfaces:**
- Consumes `list_prep_shortcuts` and the EDNpro session status.
- Produces route `/prepa` and opens configured URLs in new tabs.

- [ ] **Step 1: Write page assembly tests**

```python
def test_prepa_groups_shortcuts_by_provider_and_category(monkeypatch):
    view = build_prepa_view(fake_shortcuts())
    assert view["providers"][0]["name"] == "EDNpro"
    assert "Annales" in view["categories"]
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest tests/test_prepa_page.py -q`

Expected: FAIL because the page assembly does not exist.

- [ ] **Step 3: Implement the Linear-style page**

Render compact provider rows, a shortcut grid, recent accesses and synchronization status. Use a single primary action per provider and neutral cards. External links use `new_tab=True`; the page never embeds EDNpro content.

- [ ] **Step 4: Register route and navigation**

Add `/prepa`, active-shell mapping, mobile navigation behavior and a `Prépa` label under the knowledge/preparation group without changing existing routes.

- [ ] **Step 5: Run focused UI tests**

Run: `pytest tests/test_prepa_page.py -q`.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/prepa.py frontend/cockpit_shell.py main.py tests/test_prepa_page.py
git commit -m "feat: add prepa hub"
```
