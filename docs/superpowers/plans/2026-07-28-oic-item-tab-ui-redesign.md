# OIC Item Tab UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recomposer l’onglet OIC de la fiche item en panneau dense, lisible et aligné Linear sans modifier la logique métier.

**Architecture:** Le renderer partagé `OICPanelController` reste l’unique point de rendu pour la fiche cockpit et le dialogue classic. Il expose une toolbar, une synthèse, des sections de rang et des lignes compactes ; les méthodes `load`, `load_cached` et les callbacks d’évaluation restent inchangés.

**Tech Stack:** Python 3.13, NiceGUI/Quasar, CSS custom avec tokens Synapse, pytest.

## Global Constraints

- Ne pas modifier la persistance OIC, LiSA, les niveaux ou le dialogue AnythingLLM.
- Utiliser les tokens Synapse et un rayon maximal de 8px.
- Ne pas introduire d’emoji structurel ni de défilement horizontal.
- Les états cache, chargement, vide, erreur et retry doivent rester explicites.

---

### Task 1: Verrouiller le contrat structurel du renderer

**Files:**
- Modify: `tests/test_course_detail_oic_tab.py`
- Modify: `frontend/components/oic_panel.py`

**Interfaces:**
- Consumes: `OICPanelController.render_progress`, `render_rows`.
- Produces: source structure containing the compact summary, rank sections,
  refresh action and explicit evaluate/mastery actions.

- [ ] **Step 1: Write failing source-contract tests**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_oic_panel_has_linear_summary_and_toolbar_contract():
    source = (ROOT / "frontend/components/oic_panel.py").read_text(encoding="utf-8")
    assert "Objectifs d’apprentissage" in source
    assert "Actualiser" in source
    assert "oic-panel-summary" in source

def test_oic_panel_keeps_explicit_evaluate_and_mastery_actions():
    source = (ROOT / "frontend/components/oic_panel.py").read_text(encoding="utf-8")
    assert "Évaluer cet OIC" in source
    assert "Basculer la maîtrise" in source
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_course_detail_oic_tab.py -q`

Expected: FAIL because the current renderer has no toolbar/summary contract.

- [ ] **Step 3: Implement the compact renderer**

Add a module CSS block with token-based classes. Render the toolbar and summary
before the rank sections. Keep the existing row callbacks, but replace the
large card treatment with a bordered list row and explicit controls:

```python
ui.label("Objectifs d’apprentissage").classes("oic-panel-title")
ui.button("Actualiser", icon="refresh", on_click=...).props("flat dense")
ui.element("div").classes("oic-panel-summary")
```

The summary must calculate total, mastered, and A/B counts from the already
loaded `rows`. Rank rows must show the code, title, optional rubrique, level,
mastery button and evaluation button without changing persistence calls.

- [ ] **Step 4: Run focused tests and existing OIC tests**

Run: `pytest tests/test_course_detail_oic_tab.py tests/test_knowledge_oic.py -q`

Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`

Expected: all tests pass; only the repository’s existing warnings may remain.
