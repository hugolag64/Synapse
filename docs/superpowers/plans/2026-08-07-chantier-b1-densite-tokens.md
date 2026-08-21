# Chantier B1 — Densité & tokens : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Éliminer l'espace mort et l'aspect « carte grise » sur 8 pages du cockpit Synapse en appliquant partout un principe déjà utilisé ailleurs (Items, Révisions, Points faibles) : `--surface` est la couleur de survol, jamais un fond de repos ; une page liste occupe toute la largeur disponible.

**Architecture:** Chaque tâche est un changement CSS ou de libellé, vérifié par un test qui inspecte la source du fichier (`Path(...).read_text()`), sur le modèle déjà établi par `tests/test_items_sorting.py::test_items_list_is_not_capped_at_a_fixed_width` au chantier A. La seule tâche à logique fonctionnelle (retrait du sélecteur de difficulté QCM) reçoit un test qui inspecte le code source de la fonction plutôt que de monter l'UI NiceGUI (aucun test existant du dépôt ne monte réellement une page NiceGUI dans un navigateur headless — la convention établie est l'assertion sur la source).

**Tech Stack:** Python 3.12, NiceGUI (Quasar/Vue), CSS via chaînes `_CSS`/`ui.add_head_html`, pytest.

## Global Constraints

- Réponses et messages d'interface en français.
- Aucune modification de la logique pédagogique, des wizards (mnémo, validation de séance), de
  l'animation des collèges, ni du placement du Tuteur DP — réservés aux chantiers B2/B3/B4.
- `--surface` ne devient jamais un fond de repos ; il reste réservé à `:hover` sur les cartes
  individuellement cliquables. Les panneaux structurels (contenant leurs propres lignes déjà
  survolables) passent à `--bg` sans recevoir de nouvelle règle `:hover`.
- `semestres_cockpit.py`, `externat_cockpit.py`, `settings_cockpit.py` restent hors périmètre —
  ne pas les toucher.
- Commit après chaque tâche, message en anglais préfixé `fix:`/`refactor:` (convention du dépôt).
- Les tests tournent avec `./.venv/Scripts/python.exe -m pytest` depuis la racine du dépôt (le
  Python global n'a pas pytest installé — utiliser le venv du projet).

## File Structure

| Fichier | Changement | Tâche |
|---|---|---|
| `frontend/pages/qcm_cockpit.py` | `.qc-wrap` max-width:none ; `.qc-history`/`.qc-selected` fond `--bg` | 1, 3 |
| `frontend/pages/annales.py` | `.ans-wrap` max-width:none ; `.ans-card` fond `--bg` ; 2 blocs Tailwind → tokens | 1, 3, 4 |
| `frontend/pages/annale_detail.py` | `.an-wrap` max-width:none ; `.an-part-card` fond `--bg` ; 1 bloc Tailwind → tokens | 1, 3, 4 |
| `frontend/pages/exam_simulator_page.py` | `.ex-wrap` max-width:none ; `.ex-card`/`.ex-panel-q` fond `--bg` | 1, 3 |
| `frontend/pages/prepa.py` | `.prep-wrap` max-width:none | 1 |
| `frontend/pages/weak_points_cockpit.py` | `.wp-wrap` width:100%; max-width:none | 1 |
| `frontend/pages/revue.py` | `.rh-wrap` max-width:none | 1 |
| `frontend/pages/stats_cockpit.py` | `.st-wrap` max-width:none | 1 |
| `frontend/pages/course_detail_cockpit.py` | `.ci-center` max-width:900px → 1100px | 2 |
| `frontend/components/command_palette.py` | retrait préfixe « + » (6 occurrences) | 5 |
| `frontend/components/course_quick_actions.py` | retrait préfixe « + » (1 occurrence) | 5 |
| `frontend/pages/externat_cockpit.py` | retrait préfixe « + » (1 occurrence) | 5 |
| `frontend/components/ai_practice_panel.py` | retrait du toggle de difficulté | 6 |
| `tests/test_b1_wrap_widths.py` | nouveau — couvre tâches 1 et 2 | 1, 2 |
| `tests/test_b1_card_backgrounds.py` | nouveau — couvre tâche 3 | 3 |
| `tests/test_b1_tailwind_residue.py` | nouveau — couvre tâche 4 | 4 |
| `tests/test_b1_button_labels.py` | nouveau — couvre tâche 5 | 5 |
| `tests/test_b1_qcm_difficulty.py` | nouveau — couvre tâche 6 | 6 |

---

### Task 1: Largeur — retrait des plafonds sur 8 pages-liste

**Files:**
- Modify: `frontend/pages/qcm_cockpit.py:250`
- Modify: `frontend/pages/annales.py:18`
- Modify: `frontend/pages/annale_detail.py:23`
- Modify: `frontend/pages/exam_simulator_page.py:22`
- Modify: `frontend/pages/prepa.py:15`
- Modify: `frontend/pages/weak_points_cockpit.py:31`
- Modify: `frontend/pages/revue.py:44`
- Modify: `frontend/pages/stats_cockpit.py:36`
- Test: `tests/test_b1_wrap_widths.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: rien (changement CSS pur, pas de fonction).

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b1_wrap_widths.py` :

```python
"""Les pages-liste du cockpit occupent toute la largeur disponible, sans plafond
artificiel — même correction qu'Items au chantier A."""
from pathlib import Path

_CAPPED_FILES = {
    "frontend/pages/qcm_cockpit.py": (".qc-wrap", "max-width:1200px"),
    "frontend/pages/annales.py": (".ans-wrap", "max-width:1200px"),
    "frontend/pages/annale_detail.py": (".an-wrap", "max-width:1200px"),
    "frontend/pages/exam_simulator_page.py": (".ex-wrap", "max-width:1100px"),
    "frontend/pages/prepa.py": (".prep-wrap", "max-width:980px"),
    "frontend/pages/revue.py": (".rh-wrap", "max-width:900px"),
    "frontend/pages/stats_cockpit.py": (".st-wrap", "max-width:900px"),
}


def test_list_pages_are_not_capped_at_a_fixed_width():
    for path, (_selector, old_cap) in _CAPPED_FILES.items():
        source = Path(path).read_text(encoding="utf-8")
        assert old_cap not in source, f"{path} still has {old_cap}"


def test_list_pages_declare_max_width_none():
    expectations = {
        "frontend/pages/qcm_cockpit.py": ".qc-wrap { width:100%; max-width:none;",
        "frontend/pages/annales.py": ".ans-wrap { width:100%; max-width:none;",
        "frontend/pages/annale_detail.py": ".an-wrap { width:100%; max-width:none;",
        "frontend/pages/exam_simulator_page.py": ".ex-wrap { width:100%; max-width:none;",
        "frontend/pages/prepa.py": ".prep-wrap { max-width:none;",
        "frontend/pages/revue.py": ".rh-wrap { max-width:none;",
        "frontend/pages/stats_cockpit.py": ".st-wrap { max-width:none;",
    }
    for path, expected in expectations.items():
        source = Path(path).read_text(encoding="utf-8")
        assert expected in source, f"{path} missing {expected!r}"


def test_weak_points_wrap_is_not_capped():
    source = Path("frontend/pages/weak_points_cockpit.py").read_text(encoding="utf-8")
    assert "width:860px" not in source
    assert ".wp-wrap { width:100%; max-width:none;" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_wrap_widths.py -v`
Expected: FAIL — les plafonds actuels sont toujours présents.

- [ ] **Step 3: Retirer les plafonds**

Dans `frontend/pages/qcm_cockpit.py:250`, remplacer :
```
.qc-wrap { width:100%; max-width:1200px; align-self:stretch; margin:0 auto; min-width:0; }
```
par :
```
.qc-wrap { width:100%; max-width:none; align-self:stretch; margin:0 auto; min-width:0; }
```

Dans `frontend/pages/annales.py:18`, remplacer :
```
.ans-wrap { width:100%; max-width:1200px; align-self:stretch; margin:0 auto; min-width:0; }
```
par :
```
.ans-wrap { width:100%; max-width:none; align-self:stretch; margin:0 auto; min-width:0; }
```

Dans `frontend/pages/annale_detail.py:23`, remplacer :
```
.an-wrap { width:100%; max-width:1200px; align-self:stretch; margin:0 auto; min-width:0; }
```
par :
```
.an-wrap { width:100%; max-width:none; align-self:stretch; margin:0 auto; min-width:0; }
```

Dans `frontend/pages/exam_simulator_page.py:22`, remplacer :
```
.ex-wrap { width:100%; max-width:1100px; margin:0 auto; padding:8px 0 40px; }
```
par :
```
.ex-wrap { width:100%; max-width:none; margin:0 auto; padding:8px 0 40px; }
```

Dans `frontend/pages/prepa.py:15`, remplacer :
```
.prep-wrap { max-width:980px; width:100%; }
```
par :
```
.prep-wrap { max-width:none; width:100%; }
```

Dans `frontend/pages/weak_points_cockpit.py:31`, remplacer :
```
.wp-wrap { width:860px; max-width:100%; margin:0 auto; display:flex; flex-direction:column; gap:18px; }
```
par :
```
.wp-wrap { width:100%; max-width:none; margin:0 auto; display:flex; flex-direction:column; gap:18px; }
```

Dans `frontend/pages/revue.py:44`, remplacer :
```
.rh-wrap { max-width:900px; width:100%; }
```
par :
```
.rh-wrap { max-width:none; width:100%; }
```

Dans `frontend/pages/stats_cockpit.py:36`, remplacer :
```
.st-wrap { max-width:900px; width:100%; }
```
par :
```
.st-wrap { max-width:none; width:100%; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_wrap_widths.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/qcm_cockpit.py frontend/pages/annales.py frontend/pages/annale_detail.py frontend/pages/exam_simulator_page.py frontend/pages/prepa.py frontend/pages/weak_points_cockpit.py frontend/pages/revue.py frontend/pages/stats_cockpit.py tests/test_b1_wrap_widths.py
git commit -m "fix: remove fixed width caps on list pages so they fill available space"
```

---

### Task 2: Vue Item spécifique — plafond de lecture relevé

**Files:**
- Modify: `frontend/pages/course_detail_cockpit.py:76`
- Test: `tests/test_b1_wrap_widths.py` (étendre)

**Interfaces:**
- Consumes: rien.
- Produces: rien.

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/test_b1_wrap_widths.py` :

```python
def test_item_detail_center_column_reading_width_is_raised_not_removed():
    """Contrairement aux pages-liste (Task 1), la colonne centrale du détail
    d'item garde un plafond : elle contient du texte long (note Obsidian,
    paragraphes) qu'un plein-écran rendrait moins lisible. Décision utilisateur :
    plafond relevé (900 → 1100px), pas supprimé."""
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "max-width:900px" not in source
    assert ".ci-center { flex:1 1 auto; min-width:0; max-width:1100px; }" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_wrap_widths.py::test_item_detail_center_column_reading_width_is_raised_not_removed -v`
Expected: FAIL — le plafond est toujours à 900px.

- [ ] **Step 3: Relever le plafond**

Dans `frontend/pages/course_detail_cockpit.py:76`, remplacer :
```
.ci-center { flex:1 1 auto; min-width:0; max-width:900px; }
```
par :
```
.ci-center { flex:1 1 auto; min-width:0; max-width:1100px; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_wrap_widths.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/course_detail_cockpit.py tests/test_b1_wrap_widths.py
git commit -m "fix: raise item detail reading column cap from 900px to 1100px"
```

---

### Task 3: Cards grises → tokens corrects

**Files:**
- Modify: `frontend/pages/annales.py:24`
- Modify: `frontend/pages/annale_detail.py:29`
- Modify: `frontend/pages/qcm_cockpit.py:293,303`
- Modify: `frontend/pages/exam_simulator_page.py:27,31`
- Test: `tests/test_b1_card_backgrounds.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: rien.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b1_card_backgrounds.py` :

```python
"""`--surface` est la couleur de survol, jamais un fond de repos. Deux traitements :
cartes individuellement cliquables (gardent leur :hover existant, seul le fond de
repos change) vs panneaux structurels (contiennent leurs propres lignes déjà
survolables : pas de nouveau :hover, sinon deux états de survol se superposent)."""
from pathlib import Path


def test_clickable_cards_rest_on_bg_and_keep_their_existing_hover():
    annales = Path("frontend/pages/annales.py").read_text(encoding="utf-8")
    assert ".ans-card { width:100%; padding:14px 16px; border:1px solid var(--border); border-radius:8px; background:var(--bg);" in annales
    assert ".ans-card:hover { background:var(--surface-hover); }" in annales

    annale_detail = Path("frontend/pages/annale_detail.py").read_text(encoding="utf-8")
    assert ".an-part-card { width:100%; padding:16px 18px; border:1px solid var(--border); border-radius:8px; background:var(--bg);" in annale_detail
    assert ".an-part-card:hover { background:var(--surface-hover); }" in annale_detail


def test_structural_panels_rest_on_bg_without_a_new_hover_rule():
    qcm = Path("frontend/pages/qcm_cockpit.py").read_text(encoding="utf-8")
    history_rule = qcm.split(".qc-history {")[1].split("}")[0]
    selected_rule = qcm.split(".qc-selected {")[1].split("}")[0]
    assert "background:var(--surface);" not in history_rule
    assert "background:var(--bg);" in history_rule
    assert "background:var(--surface);" not in selected_rule
    assert "background:var(--bg);" in selected_rule
    assert ".qc-history:hover" not in qcm  # aucune nouvelle règle de survol ajoutée
    assert ".qc-selected:hover" not in qcm

    exam = Path("frontend/pages/exam_simulator_page.py").read_text(encoding="utf-8")
    assert ".ex-card { background:var(--bg);" in exam
    assert ".ex-panel-q { background:var(--bg);" in exam
    assert ".ex-card:hover" not in exam
    assert ".ex-panel-q:hover" not in exam
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_card_backgrounds.py -v`
Expected: FAIL sur les 4 assertions positives (`background:var(--bg)` absent).

- [ ] **Step 3: Corriger les deux cartes cliquables**

Dans `frontend/pages/annales.py:24`, remplacer :
```
.ans-card { width:100%; padding:14px 16px; border:1px solid var(--border); border-radius:8px; background:var(--surface); transition:background var(--duration-fast) ease; }
```
par :
```
.ans-card { width:100%; padding:14px 16px; border:1px solid var(--border); border-radius:8px; background:var(--bg); transition:background var(--duration-fast) ease; }
```
(la ligne suivante `.ans-card:hover { background:var(--surface-hover); }` ne change pas.)

Dans `frontend/pages/annale_detail.py:29`, remplacer :
```
.an-part-card { width:100%; padding:16px 18px; border:1px solid var(--border); border-radius:8px; background:var(--surface); transition:background var(--duration-fast) ease; }
```
par :
```
.an-part-card { width:100%; padding:16px 18px; border:1px solid var(--border); border-radius:8px; background:var(--bg); transition:background var(--duration-fast) ease; }
```
(la ligne suivante `.an-part-card:hover { background:var(--surface-hover); }` ne change pas.)

- [ ] **Step 4: Corriger les quatre panneaux structurels**

Dans `frontend/pages/qcm_cockpit.py:293`, remplacer :
```
.qc-history { min-width:0; max-height:620px; overflow-x:hidden; overflow-y:auto; padding:14px; border:1px solid var(--border); border-radius:8px; background:var(--surface); }
```
par :
```
.qc-history { min-width:0; max-height:620px; overflow-x:hidden; overflow-y:auto; padding:14px; border:1px solid var(--border); border-radius:8px; background:var(--bg); }
```

Dans `frontend/pages/qcm_cockpit.py:303`, remplacer :
```
.qc-selected { min-width:0; width:100%; padding:18px; border:1px solid var(--border); border-radius:8px; background:var(--surface); }
```
par :
```
.qc-selected { min-width:0; width:100%; padding:18px; border:1px solid var(--border); border-radius:8px; background:var(--bg); }
```

Dans `frontend/pages/exam_simulator_page.py:27`, remplacer :
```
.ex-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); padding:20px; }
```
par :
```
.ex-card { background:var(--bg); border:1px solid var(--border); border-radius:var(--radius-lg); padding:20px; }
```

Dans `frontend/pages/exam_simulator_page.py:31`, remplacer :
```
.ex-panel-q { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-md); padding:20px; min-height:580px; display:flex; flex-direction:column; justify-between:space-between; }
```
par :
```
.ex-panel-q { background:var(--bg); border:1px solid var(--border); border-radius:var(--radius-md); padding:20px; min-height:580px; display:flex; flex-direction:column; justify-between:space-between; }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_card_backgrounds.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/annales.py frontend/pages/annale_detail.py frontend/pages/qcm_cockpit.py frontend/pages/exam_simulator_page.py tests/test_b1_card_backgrounds.py
git commit -m "fix: stop using the hover surface color as a resting card background"
```

---

### Task 4: Résidus Tailwind bruts → tokens

**Files:**
- Modify: `frontend/pages/annales.py:227,313`
- Modify: `frontend/pages/annale_detail.py:175`
- Test: `tests/test_b1_tailwind_residue.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: rien.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b1_tailwind_residue.py` :

```python
"""Les trois derniers blocs Tailwind bruts (jamais migrés lors de la construction
initiale de ces écrans) passent aux tokens du design system."""
from pathlib import Path


def test_annales_import_blocks_use_design_tokens():
    source = Path("frontend/pages/annales.py").read_text(encoding="utf-8")
    assert "border-slate-200" not in source
    assert "bg-slate-50" not in source
    assert "dark:bg-slate-900/40" not in source


def test_annale_detail_history_card_uses_design_tokens():
    source = Path("frontend/pages/annale_detail.py").read_text(encoding="utf-8")
    assert "border-slate-200" not in source
    assert "dark:border-slate-800" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_tailwind_residue.py -v`
Expected: FAIL — les classes Tailwind sont toujours présentes.

- [ ] **Step 3: Migrer les deux blocs d'annales.py**

Dans `frontend/pages/annales.py:227`, remplacer :
```python
                            with ui.column().classes("w-full p-3 border border-slate-200 dark:border-slate-800 rounded-md gap-1 bg-slate-50 dark:bg-slate-900/40"):
```
par :
```python
                            with ui.column().classes("w-full p-3 gap-1").style(
                                "border:1px solid var(--border); border-radius:var(--radius-md); background:var(--bg-alt);"
                            ):
```

Dans `frontend/pages/annales.py:313`, remplacer :
```python
                    with ui.column().classes("w-full gap-1 p-3 border border-slate-200 dark:border-slate-800 rounded-md mb-2"):
```
par :
```python
                    with ui.column().classes("w-full gap-1 p-3 mb-2").style(
                        "border:1px solid var(--border); border-radius:var(--radius-md);"
                    ):
```

- [ ] **Step 4: Migrer le bloc d'annale_detail.py**

Dans `frontend/pages/annale_detail.py:175`, remplacer :
```python
                    with ui.card().classes("w-full p-3 border border-slate-200 dark:border-slate-800 rounded-md"):
```
par :
```python
                    with ui.card().classes("w-full p-3").style(
                        "border:1px solid var(--border); border-radius:var(--radius-md);"
                    ):
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_tailwind_residue.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/annales.py frontend/pages/annale_detail.py tests/test_b1_tailwind_residue.py
git commit -m "refactor: migrate remaining hardcoded Tailwind gray classes to design tokens"
```

---

### Task 5: Retrait du préfixe « + » sur les libellés de bouton

**Files:**
- Modify: `frontend/components/command_palette.py:158-160,224-226`
- Modify: `frontend/components/course_quick_actions.py:44`
- Modify: `frontend/pages/externat_cockpit.py:124`
- Test: `tests/test_b1_button_labels.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: rien.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b1_button_labels.py` :

```python
"""Le préfixe « + » est redondant avec l'icône Quasar déjà affichée sur ces
boutons — retiré partout sauf sur le bouton mnémo/image (refonte complète prévue
au chantier B2, hors périmètre ici)."""
from pathlib import Path


def test_command_palette_buttons_drop_the_plus_prefix():
    source = Path("frontend/components/command_palette.py").read_text(encoding="utf-8")
    assert '"+ Lacune"' not in source
    assert '"+ QCM"' not in source
    assert '"+ Séance"' not in source
    assert '"Lacune"' in source
    assert '"QCM"' in source
    assert '"Séance"' in source


def test_course_quick_actions_reading_label_drops_the_plus_prefix():
    source = Path("frontend/components/course_quick_actions.py").read_text(encoding="utf-8")
    assert '"+ Lecture"' not in source
    assert '"label": "Lecture"' in source


def test_externat_new_stage_button_drops_the_plus_prefix():
    source = Path("frontend/pages/externat_cockpit.py").read_text(encoding="utf-8")
    assert '"+ Nouveau stage"' not in source
    assert '"Nouveau stage"' in source


def test_mnemo_button_is_untouched_pending_b2_rework():
    """Ce bouton garde son emoji et son préfixe pour l'instant : sa refonte
    complète (thème réactif, zéro emoji) est prévue au chantier B2."""
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")
    assert "💡 + Mnémo / Image" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_button_labels.py -v`
Expected: FAIL sur les 3 premiers tests (le préfixe est toujours présent) ; le 4ᵉ passe déjà (aucun changement fait sur ce fichier dans cette tâche).

- [ ] **Step 3: Retirer le préfixe dans command_palette.py**

Dans `frontend/components/command_palette.py`, remplacer les lignes 158-160 :
```python
                        ("+ Lacune",  "report_problem", "orange", lambda: _quick_action("lacune", dlg)),
                        ("+ QCM",     "quiz",           "indigo", lambda: _quick_action("qcm",    dlg)),
                        ("+ Séance",  "school",         "blue",   lambda: _quick_action("séance", dlg)),
```
par :
```python
                        ("Lacune",  "report_problem", "orange", lambda: _quick_action("lacune", dlg)),
                        ("QCM",     "quiz",           "indigo", lambda: _quick_action("qcm",    dlg)),
                        ("Séance",  "school",         "blue",   lambda: _quick_action("séance", dlg)),
```

Remplacer les lignes 224-226 :
```python
                    ("+ Lacune",    "report_problem", "orange", lambda: _open_lacune_for_course(course, dlg)),
                    ("+ QCM",       "quiz",           "indigo", lambda: _open_qcm_for_course(course, dlg)),
                    ("+ Séance",    "school",         "blue",   lambda: _open_session_for_course(course, dlg)),
```
par :
```python
                    ("Lacune",    "report_problem", "orange", lambda: _open_lacune_for_course(course, dlg)),
                    ("QCM",       "quiz",           "indigo", lambda: _open_qcm_for_course(course, dlg)),
                    ("Séance",    "school",         "blue",   lambda: _open_session_for_course(course, dlg)),
```

- [ ] **Step 4: Retirer le préfixe dans course_quick_actions.py et externat_cockpit.py**

Dans `frontend/components/course_quick_actions.py:44`, remplacer :
```python
        "label": "+ Lecture",
```
par :
```python
        "label": "Lecture",
```

Dans `frontend/pages/externat_cockpit.py:124`, remplacer :
```python
            ui.button("+ Nouveau stage", on_click=lambda: _open_stage_dialog(ui.navigate.reload)).props(
```
par :
```python
            ui.button("Nouveau stage", on_click=lambda: _open_stage_dialog(ui.navigate.reload)).props(
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_button_labels.py -v`
Expected: 4 passed

- [ ] **Step 6: Vérifier l'absence de régression sur les tests existants de command_palette**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_command_palette.py -v`
Expected: PASS (ces tests ne portent pas sur le libellé exact des boutons d'action rapide)

- [ ] **Step 7: Commit**

```bash
git add frontend/components/command_palette.py frontend/components/course_quick_actions.py frontend/pages/externat_cockpit.py tests/test_b1_button_labels.py
git commit -m "fix: drop redundant plus-sign prefix from button labels that already show an icon"
```

---

### Task 6: QCM — suppression du sélecteur de difficulté

**Files:**
- Modify: `frontend/components/ai_practice_panel.py:51-63,107-118`
- Test: `tests/test_b1_qcm_difficulty.py` (créer)

**Interfaces:**
- Consumes: `PracticeDifficulty` (enum, `backend/core/practice/models.py`) — valeurs `STANDARD`,
  `EDN`, `DIFFICULT`, `CONCOURS`. Non modifiée par cette tâche.
- Produces: rien de nouveau — `_open_generation_dialog` garde sa signature
  `_open_generation_dialog(course, refresh) -> None`.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b1_qcm_difficulty.py` :

```python
"""L'écran de lancement d'une session QCM générée par IA ne propose plus de
choisir la difficulté : seul l'EDN est préparé, le sélecteur n'a jamais d'utilité
réelle. L'enum PracticeDifficulty (backend) n'est pas touchée — elle sert au
service et à des tests indépendants de cet écran."""
import inspect

from frontend.components import ai_practice_panel


def test_generation_dialog_no_longer_builds_a_difficulty_toggle():
    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "difficulty = ui.toggle(" not in source
    assert "PracticeDifficulty.STANDARD.value" not in source
    assert "PracticeDifficulty.DIFFICULT.value" not in source
    assert "PracticeDifficulty.CONCOURS.value" not in source


def test_generation_dialog_hardcodes_edn_difficulty():
    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "difficulty=PracticeDifficulty.EDN," in source


def test_existing_generation_dialog_behavior_is_preserved():
    """Non-régression : le test déjà présent au chantier précédent continue de
    passer (comportement des sliders questions ouvertes/fermées inchangé)."""
    source = inspect.getsource(ai_practice_panel._open_generation_dialog)
    assert "value=0" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_qcm_difficulty.py -v`
Expected: FAIL sur les 2 premiers tests (le toggle est toujours présent).

- [ ] **Step 3: Retirer le toggle et fixer EDN en dur**

Dans `frontend/components/ai_practice_panel.py`, supprimer les lignes 55-63 :
```python
        difficulty = ui.toggle(
            {
                PracticeDifficulty.STANDARD.value: "Standard",
                PracticeDifficulty.EDN.value: "EDN",
                PracticeDifficulty.DIFFICULT.value: "Difficile",
                PracticeDifficulty.CONCOURS.value: "Concours",
            },
            value=PracticeDifficulty.EDN.value,
        ).props("spread no-caps unelevated").classes("w-full ai-practice-kind-toggle mt-2")
```

Remplacer la ligne 117 :
```python
                    difficulty=PracticeDifficulty(str(difficulty.value)),
```
par :
```python
                    difficulty=PracticeDifficulty.EDN,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b1_qcm_difficulty.py -v`
Expected: 3 passed

- [ ] **Step 5: Vérifier l'absence de régression sur les tests QCM existants**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_qcm_cockpit_ui.py tests/test_ai_practice.py tests/test_ai_routing.py -v`
Expected: PASS — `test_ai_generation_opens_the_session_and_defaults_to_closed_questions`
(qui vérifie déjà `'value=0' in source`) continue de passer puisque ce slider n'est pas touché.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ai_practice_panel.py tests/test_b1_qcm_difficulty.py
git commit -m "fix: remove the unused difficulty selector from QCM AI session generation"
```

---

## Vérification finale

- [ ] **Suite complète**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: aucune nouvelle défaillance par rapport à la ligne de base établie avant la Task 1 (1110
tests passés en sortie du chantier A). Relever la ligne de base avec la même commande avant de
commencer, comparer après la Task 6.

- [ ] **Vérification manuelle dans l'application**

Lancer l'application et confirmer visuellement, pour chacune des pages touchées :

1. QCM, Annales, Épreuves, Examen blanc, Prépa, Points faibles, Revue hebdo, Statistiques
   occupent toute la largeur de l'écran, sans bande morte sur un écran large.
2. Revue hebdo, Statistiques, Prépa ne collent plus à gauche.
3. La colonne centrale de la vue Item spécifique s'élargit un peu plus qu'avant sans devenir
   inconfortable à lire.
4. Les lignes de la liste Annales et les cartes de sous-partie (détail annale) ont un fond blanc
   au repos, gris clair uniquement au survol.
5. Les panneaux Historique/Session sélectionnée (QCM) et les cartes de l'Examen blanc ont un fond
   blanc, sans survol de zone parasite.
6. Les boutons Lacune/QCM/Séance/Lecture/Nouveau stage n'ont plus de « + » dans leur libellé.
7. L'écran de génération de session QCM IA ne propose plus de choix de difficulté.
