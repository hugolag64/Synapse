# Shell responsive du cockpit (Étape 17, session 1/3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter 3 paliers responsive au shell cockpit partagé (`frontend/cockpit_shell.py`) : sidebar inchangée ≥900px, icônes forcées 768–900px, sidebar remplacée par topbar+bottom nav <768px — sans toucher au contenu d'aucune page individuelle.

**Architecture:** Deux nouveaux éléments toujours construits dans `cockpit_frame()` (topbar mobile, bottom nav), visibilité pilotée entièrement par media queries CSS (aucune logique Python conditionnelle sur la largeur). Les media queries réutilisent les valeurs déjà écrites pour le mode « mini » existant plutôt que d'inventer un nouveau système.

**Tech Stack:** NiceGUI (Python), CSS media queries, pytest (tests source-assertion, même pattern que `tests/test_todo_cockpit_ui.py`/`tests/test_weak_points_cockpit_ui.py` — pas de harnais de test NiceGUI dans ce repo).

## Global Constraints

- `ui.add_head_html` au build synchrone uniquement (déjà le cas, non touché).
- Grammaire de statut : une seule couleur porteuse de sens (page active = `--accent`, rien d'autre).
- Rayons plafond 8px, transitions ≤180ms — non concerné ici (pas de nouveau rayon/transition ajouté).
- Aucun émoji comme icône — les glyphes de la bottom nav réutilisent exactement ceux déjà utilisés dans `_NAV_GROUPS` (◉ ▦ ↻ ≡ ⚑).
- Référence de spec : `docs/superpowers/specs/2026-07-28-cockpit-shell-responsive-design.md`.
- Le chemin classic (`frontend/theme.py::frame()`) n'est pas concerné par ce plan.

---

## File Structure

- **Modify** `frontend/cockpit_shell.py` — 3 blocs CSS ajoutés à `_SIDEBAR_CSS` (icônes forcées 768–900px, topbar+bottomnav <768px) ; nouvelle constante `_BOTTOM_NAV` ; nouvelle fonction `_bottom_nav_item()` ; `cockpit_frame()` construit et peuple les deux nouveaux éléments.
- **Modify** `tests/test_cockpit_shell.py` — tests source-assertion sur les nouvelles media queries et le nouveau markup.

---

### Task 1: Tests des media queries et du markup mobile

**Files:**
- Modify: `tests/test_cockpit_shell.py`

**Interfaces:**
- Consumes : lit le texte source de `frontend/cockpit_shell.py` (Task 2) par assertions de chaîne.
- Produces : rien consommé par d'autres tâches.

- [ ] **Step 1: Ajouter les tests (échoueront — le CSS/markup n'existe pas encore)**

Ajouter à la fin de `tests/test_cockpit_shell.py` :

```python
def test_shell_forces_icon_only_sidebar_between_768_and_900():
    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()

    assert "@media (min-width: 768px) and (max-width: 899.98px) {" in source
    assert ".cockpit-sidebar { width:56px; }" in source
    assert ".cockpit-main { margin-left:56px; }" in source
    assert ".cockpit-chevron { display:none; }" in source


def test_shell_replaces_sidebar_with_topbar_and_bottomnav_below_768():
    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()

    assert "@media (max-width: 767.98px) {" in source
    assert ".cockpit-sidebar { display:none; }" in source
    assert ".cockpit-main { margin-left:0; padding:68px 16px 76px; }" in source
    assert ".cockpit-topbar-mobile { display:flex; }" in source
    assert ".cockpit-bottomnav { display:flex; }" in source


def test_mobile_topbar_reuses_command_palette_for_search():
    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()

    assert '.on("click", open_command_palette)' in source
    assert source.count("open_command_palette") >= 2  # sidebar desktop + topbar mobile


def test_bottom_nav_has_five_entries_matching_readme():
    from frontend.cockpit_shell import _BOTTOM_NAV

    routes = [route for _glyph, _label, route, _active_key in _BOTTOM_NAV]
    assert routes == ["/", "/planning", "/todo", "/items", "/lacunes"]

    active_keys = [active_key for _glyph, _label, _route, active_key in _BOTTOM_NAV]
    assert active_keys == ["Aujourd'hui", "Planning", "Révisions", "Items", "Points faibles"]


def test_bottom_nav_item_highlights_active_page():
    from frontend.cockpit_shell import _BOTTOM_NAV

    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()
    assert "def _bottom_nav_item(" in source
    assert '"cockpit-bottomnav-item" + (" active" if active_key == active else "")' in source
    assert len(_BOTTOM_NAV) == 5
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cockpit_shell.py -v`
Expected: FAIL — `AssertionError` sur les nouvelles chaînes CSS, `ImportError: cannot import name '_BOTTOM_NAV'`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cockpit_shell.py
git commit -m "test: media queries et markup mobile du shell cockpit"
```

---

### Task 2: Implémenter les 3 paliers responsive

**Files:**
- Modify: `frontend/cockpit_shell.py`

**Interfaces:**
- Consumes : `open_command_palette` (déjà importé) ; `active` (déjà calculé en tête de `cockpit_frame()` via `_TITLE_TO_NAV`).
- Produces : `_BOTTOM_NAV: list[tuple[str, str, str, str]]`, `_bottom_nav_item(glyph: str, label: str, route: str, active_key: str, active: str) -> None` (validés par la Task 1) ; `cockpit_frame(page_title: str)` — signature et usage (context manager) inchangés.

- [ ] **Step 1: Ajouter les 3 blocs CSS à la fin de `_SIDEBAR_CSS`**

Remplacer la fin de la chaîne `_SIDEBAR_CSS` (après la ligne `.cockpit-sidebar.mini .cockpit-chevron { transform:rotate(180deg); }` et avant le `"""` de fermeture) :

```python
.cockpit-sidebar.mini .cockpit-chevron { transform:rotate(180deg); }

/* ── Topbar + bottom nav mobile (masqués par défaut, activés <768px) ── */
.cockpit-topbar-mobile { display:none; position:fixed; top:0; left:0; right:0; height:52px; z-index:1000;
  align-items:center; justify-content:space-between; gap:10px; padding:0 16px;
  background:var(--bg-alt); border-bottom:1px solid var(--border); }
.cockpit-search-icon { display:flex; align-items:center; justify-content:center;
  width:32px; height:32px; border-radius:6px; color:var(--text-muted); cursor:pointer; font-size:16px; }
.cockpit-search-icon:hover { background:var(--surface); color:var(--text); }

.cockpit-bottomnav { display:none; position:fixed; bottom:0; left:0; right:0; height:56px; z-index:1000;
  align-items:stretch; justify-content:space-around; background:var(--bg-alt); border-top:1px solid var(--border); }
.cockpit-bottomnav-item { flex:1 1 0; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:2px; color:var(--text-muted) !important; text-decoration:none !important; font-size:9.5px; cursor:pointer; }
.cockpit-bottomnav-item .glyph { font-size:17px; }
.cockpit-bottomnav-item.active { color:var(--accent) !important; }

/* ── Palier 768–900px : icônes forcées, indépendant du toggle manuel ── */
@media (min-width: 768px) and (max-width: 899.98px) {
  .cockpit-sidebar { width:56px; }
  .cockpit-main { margin-left:56px; }
  .cockpit-sidebar .cockpit-group-label,
  .cockpit-sidebar .cockpit-nav-item .lbl,
  .cockpit-sidebar .cockpit-badge-count,
  .cockpit-sidebar .cockpit-search .lbl,
  .cockpit-sidebar .cockpit-search kbd,
  .cockpit-sidebar .cockpit-wordmark { display:none !important; }
  .cockpit-sidebar .cockpit-search { justify-content:center; }
  .cockpit-chevron { display:none; }
}

/* ── Palier <768px : sidebar remplacée par topbar + bottom nav ── */
@media (max-width: 767.98px) {
  .cockpit-sidebar { display:none; }
  .cockpit-main { margin-left:0; padding:68px 16px 76px; }
  .cockpit-topbar-mobile { display:flex; }
  .cockpit-bottomnav { display:flex; }
}
"""
```

- [ ] **Step 2: Ajouter `_BOTTOM_NAV` et `_bottom_nav_item`**

Ajouter après la fonction `_nav_item` (avant `@contextmanager` / `def cockpit_frame`) :

```python
_BOTTOM_NAV = [
    ("◉", "Aujourd'hui", "/", "Aujourd'hui"),
    ("▦", "Planning", "/planning", "Planning"),
    ("↻", "Révisions", "/todo", "Révisions"),
    ("≡", "Items", "/items", "Items"),
    ("⚑", "Lacunes", "/lacunes", "Points faibles"),
]


def _bottom_nav_item(glyph: str, label: str, route: str, active_key: str, active: str) -> None:
    cls = "cockpit-bottomnav-item" + (" active" if active_key == active else "")
    with ui.link(target=route).classes(cls):
        ui.label(glyph).classes("glyph")
        ui.label(label)
```

- [ ] **Step 3: Construire et peupler la topbar mobile et la bottom nav dans `cockpit_frame()`**

Juste après la ligne `side = ui.element("aside").classes("cockpit-sidebar")` (avant `main = ui.element("div").classes("cockpit-main")`), ajouter :

```python
    topbar_mobile = ui.element("div").classes("cockpit-topbar-mobile")
    bottomnav = ui.element("nav").classes("cockpit-bottomnav")
```

Après le bloc `with side: ...` existant (donc juste avant `with main:`), ajouter :

```python
    with topbar_mobile:
        with ui.row().classes("items-center gap-2"):
            ui.label("S").classes("cockpit-logo")
            ui.label("Synapse").classes("cockpit-wordmark")
        ui.label("⌕").classes("cockpit-search-icon").on("click", open_command_palette)

    with bottomnav:
        for glyph, label, route, active_key in _BOTTOM_NAV:
            _bottom_nav_item(glyph, label, route, active_key, active)
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cockpit_shell.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/cockpit_shell.py
git commit -m "feat: shell cockpit responsive — icônes forcées 768-900px, topbar+bottom nav <768px"
```

---

### Task 3: Vérification navigateur aux 3 paliers

**Files:** aucun (vérification manuelle).

**Interfaces:** N/A.

Note : la session précédente (Mode focus) a montré que ce navigateur d'automatisation peut avoir un onglet non composité (`document.visibilityState === "hidden"`, `computer{screenshot}` en échec) — dans ce cas, s'appuyer sur `getComputedStyle`/`getBoundingClientRect` (qui reflètent l'état CSS réel indépendamment du compositing) plutôt que sur une capture d'écran, et ne pas conclure à un bug applicatif sur la seule base d'un rendu visuel qui semble figé.

- [ ] **Step 1: Démarrer le serveur** (`preview_start`, config `synapse`)

- [ ] **Step 2: Palier ≥900px (desktop, inchangé)**

`resize_window` 1280×800. Naviguer sur `/`. Vérifier via `javascript_tool` : `getComputedStyle(document.querySelector('.cockpit-sidebar')).width` = `"200px"`, `.cockpit-topbar-mobile`/`.cockpit-bottomnav` ont `display:none`. Cliquer le chevron (bascule manuelle) : la sidebar passe à 56px comme avant — non-régression du mode mini existant.

- [ ] **Step 3: Palier 768–900px**

`resize_window` 820×800 (ou équivalent). Vérifier : `.cockpit-sidebar` largeur 56px, `.cockpit-chevron` a `display:none`, labels de nav masqués (`.cockpit-nav-item .lbl` non visible), `.cockpit-main` `margin-left` = 56px, `.cockpit-topbar-mobile`/`.cockpit-bottomnav` toujours `display:none`.

- [ ] **Step 4: Palier <768px**

`resize_window` 375×812 (mobile). Vérifier : `.cockpit-sidebar` `display:none`, `.cockpit-topbar-mobile` et `.cockpit-bottomnav` `display:flex`, 5 entrées dans la bottom nav, l'entrée correspondant à la page courante a la classe `active` (couleur `--accent`). Cliquer l'icône recherche de la topbar → la palette de commandes s'ouvre (même vérification que le `⌕` desktop). Cliquer une entrée de la bottom nav (ex. Lacunes) → navigation vers `/lacunes`, l'entrée active suit.

- [ ] **Step 5: Vérifier qu'aucun contenu de page n'est masqué par les barres fixes**

Sur `/` en 375×812, vérifier que le haut du contenu (`.cockpit-main`) n'est pas sous la topbar et que le bas (dernier élément visible) n'est pas sous la bottom nav — comparer `getBoundingClientRect().top` du premier enfant de `.cockpit-main` à la hauteur de la topbar (52px), et `getBoundingClientRect().bottom` du dernier contenu visible à `window.innerHeight - 56` (hauteur bottom nav).

- [ ] **Step 6: Confirmer zéro exception serveur** (`preview_logs`, niveau erreur) et relancer la suite complète

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: tous les tests passent (aucune régression sur les autres écrans, qui n'ont pas été modifiés).

---

### Task 4: Mettre à jour le suivi de la refonte

**Files:**
- Modify: `design_handoff_synapse_refonte/CLAUDE.md`

**Interfaces:** N/A (documentation).

- [ ] **Step 1: Ajouter l'entrée de journal**

Ajouter à la fin de la section Journal (après l'entrée « 2026-07-28 — Étape 16 Mode focus ») :

```markdown
- **2026-07-28 — Étape 17 Responsive, session 1/3 (shell).** Modifié : `frontend/cockpit_shell.py`. Voir `docs/superpowers/specs/2026-07-28-cockpit-shell-responsive-design.md` et `docs/superpowers/plans/2026-07-28-cockpit-shell-responsive.md`.
  - **Découpage en 3 sessions** (validé avec l'utilisateur) : shell (cette session, bénéficie à tous les écrans d'un coup) · panneau contextuel → drawer 900–1200px par écran · mise en page mobile dédiée Aujourd'hui (README §16). Sessions 2 et 3 restent à faire.
  - **768–900px** : sidebar forcée en icônes (56px) indépendamment du toggle manuel existant (chevron masqué dans cette plage) — réutilise les valeurs déjà écrites pour `.cockpit-sidebar.mini`, appliquées directement à la classe de base via media query.
  - **<768px** : sidebar remplacée par une topbar (logo + recherche → palette de commandes existante) et une bottom nav 5 entrées (Aujourd'hui/Planning/Révisions/Items/Lacunes, mêmes glyphes que la sidebar). Décision produit (validée) : pas de lien « Vue classic » sur mobile — resterait accessible depuis Paramètres si besoin un jour, non câblé ici.
  - **Aucune page individuelle modifiée** — le nouveau comportement est hérité automatiquement via `cockpit_frame()`, conformément à la note déjà présente dans le docstring du module (« L'overlay mobile <768px sera traité en session 17 »).
```

- [ ] **Step 2: Commit**

```bash
git add design_handoff_synapse_refonte/CLAUDE.md
git commit -m "docs: étape 17 session 1/3 (shell responsive) — journal"
```
