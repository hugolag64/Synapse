# Paramètres organisés par domaines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer la vue Paramètres en six sections NiceGUI repliées par défaut, lisibles, accessibles et exclusives à l'ouverture, sans casser les actions métier existantes.

**Architecture:** `frontend/pages/settings_cockpit.py` conservera les fonctions métier et recevra un helper de composition pour les expansions de domaine. Chaque domaine encapsulera son contenu actuel ; les composants Calendar, UNESS, DP et LiSA/OIC resteront appelés depuis leur emplacement fonctionnel. Les tests source vérifieront la structure, les valeurs fermées par défaut et les branchements ; une QA Chromium vérifiera le comportement d'ouverture et la pleine largeur.

**Tech Stack:** Python 3.11, NiceGUI/Quasar `ui.expansion`, pytest, Chromium via Playwright.

## Global Constraints

- Les six domaines sont `Connexions`, `Apparence et accessibilité`, `Planification EDN`, `Données UNESS`, `LiSA / OIC`, `Diagnostics et télémétrie`.
- Chaque expansion est fermée par défaut et une seule expansion peut être ouverte à la fois.
- L'état ouvert/fermé n'est pas persisté dans les préférences.
- Les statuts `Connecté`, `Non configuré` et `Automatisation à connecter` restent distincts.
- Aucun appel réseau live supplémentaire ne doit être ajouté au rendu initial.
- La classe `se-wrap` reste pleine largeur et la page doit rester utilisable sous 820 px.
- Les fichiers utilisateur déjà modifiés ou non suivis ne doivent pas être ajoutés au commit.

---

### Task 1: Verrouiller le contrat de structure des domaines

**Files:**
- Create: `tests/test_settings_domains.py`
- Modify: `frontend/pages/settings_cockpit.py` uniquement si un nom de domaine ou un helper public doit être introduit

**Interfaces:**
- Produces: six identifiants stables de domaine et un contrat source testable pour la composition Paramètres.
- Consumes: les fonctions existantes `render_calendar_sources`, `render_uness_diagnostics`, `render_dp_coverage` et `render_settings_cockpit`.

- [ ] **Step 1: Écrire les tests qui doivent échouer**

Créer des tests source sans démarrer NiceGUI :

```python
from pathlib import Path


SOURCE = Path("frontend/pages/settings_cockpit.py").read_text(encoding="utf-8")


def test_settings_exposes_six_domain_expansions():
    for title in (
        "CONNEXIONS",
        "APPARENCE ET ACCESSIBILITÉ",
        "PLANIFICATION EDN",
        "DONNÉES UNESS",
        "LISA / OIC",
        "DIAGNOSTICS ET TÉLÉMÉTRIE",
    ):
        assert title in SOURCE
    assert SOURCE.count("ui.expansion(") >= 6


def test_settings_domains_are_closed_by_default_and_share_one_group():
    assert SOURCE.count("value=False") >= 6
    assert "group=" in SOURCE


def test_settings_keeps_existing_integrations_wired():
    for symbol in (
        "render_calendar_sources",
        "render_uness_diagnostics",
        "render_dp_coverage",
        "item_service.scrape_all_items",
    ):
        assert symbol in SOURCE


def test_settings_remains_full_width_and_responsive():
    assert ".se-wrap {" in SOURCE
    assert "width:100%" in SOURCE
    assert "max-width: 820px" in SOURCE
```

- [ ] **Step 2: Exécuter les tests et confirmer l'échec initial**

Run: `pytest tests/test_settings_domains.py -q`

Expected: FAIL because the current page uses plain `.se-domain` labels and does not yet expose six `ui.expansion` containers.

- [ ] **Step 3: Ajouter les constantes de domaine et le helper de composition**

Dans `settings_cockpit.py`, définir une structure locale stable :

```python
_SETTINGS_DOMAIN_GROUP = "settings-domains"


def _settings_domain(title: str, description: str, icon: str):
    return ui.expansion(
        title,
        icon=icon,
        value=False,
    ).props(f'group={_SETTINGS_DOMAIN_GROUP}') \
        .classes("se-domain-expansion w-full")
```

Le helper doit conserver l'objet `ui.expansion` comme contexte `with`, afin que le contenu existant soit rendu à l'intérieur de l'expansion. Le groupe NiceGUI/Quasar doit être identique pour les six domaines.

- [ ] **Step 4: Relancer les tests de structure**

Run: `pytest tests/test_settings_domains.py -q`

Expected: PASS for the helper, six titles, the group and the existing integration symbols.

- [ ] **Step 5: Committer le contrat de structure**

```bash
git add tests/test_settings_domains.py frontend/pages/settings_cockpit.py
git commit -m "test: define settings domain contract"
git push origin main
```

---

### Task 2: Encapsuler chaque domaine sans déplacer la logique métier

**Files:**
- Modify: `frontend/pages/settings_cockpit.py`
- Test: `tests/test_settings_domains.py`

**Interfaces:**
- Consumes: `_settings_domain(title, description, icon)` et `_SETTINGS_DOMAIN_GROUP` de Task 1.
- Produces: `render_settings_cockpit()` avec six expansions dans l'ordre de la spécification.

- [ ] **Step 1: Ajouter les assertions d'ordre et de contenu**

Compléter le test source :

```python
def test_settings_domain_order_matches_the_spec():
    titles = (
        "CONNEXIONS",
        "APPARENCE ET ACCESSIBILITÉ",
        "PLANIFICATION EDN",
        "DONNÉES UNESS",
        "LISA / OIC",
        "DIAGNOSTICS ET TÉLÉMÉTRIE",
    )
    positions = [SOURCE.index(title) for title in titles]
    assert positions == sorted(positions)


def test_settings_domain_descriptions_are_present():
    for description in (
        "Fournisseurs et calendriers",
        "Thème et préférences d'affichage",
        "Dates et Sprint EDN",
        "Import et normalisation",
        "Objectifs de connaissance",
        "Couverture et consommation",
    ):
        assert description in SOURCE
```

- [ ] **Step 2: Exécuter les tests pour confirmer le nouveau manque**

Run: `pytest tests/test_settings_domains.py -q`

Expected: FAIL until the six descriptions and the exact composition order are present.

- [ ] **Step 3: Encapsuler les connexions et l'apparence**

Dans `render_settings_cockpit()` :

```python
with _settings_domain("CONNEXIONS", "Fournisseurs et calendriers", "link"):
    # lignes _connection_rows() et render_calendar_sources(...)

with _settings_domain("APPARENCE ET ACCESSIBILITÉ", "Thème et préférences d'affichage", "palette"):
    # mode sombre, fuseau horaire et sélecteur existants
```

Conserver les classes `.se-row`, `.se-status`, `.se-appearance-row` et les callbacks existants. Le statut de chaque fournisseur doit rester visible dans le contenu ouvert.

- [ ] **Step 4: Encapsuler la planification et les données UNESS**

Déplacer uniquement les blocs de rendu existants sous :

```python
with _settings_domain("PLANIFICATION EDN", "Dates et Sprint EDN", "event"):
    # dates, sauvegarde et visibilité du Sprint

with _settings_domain("DONNÉES UNESS", "Import et normalisation", "school"):
    # import URL, collecte, scan JSON vérifiés
```

Les closures `_save_planning_preferences`, `_toggle_sprint_visibility`, `_prepare_import`, `_launch_collector`, `_scan_verified` et `_open_tag_dialog` doivent continuer à référencer les mêmes contrôles NiceGUI.

- [ ] **Step 5: Encapsuler LiSA/OIC et les diagnostics**

Déplacer le bloc LiSA/OIC sous :

```python
with _settings_domain("LISA / OIC", "Objectifs de connaissance", "school"):
    # item_service.scrape_all_items et sa progression
```

Regrouper sous une sixième expansion `DIAGNOSTICS ET TÉLÉMÉTRIE` les expansions existantes `COUVERTURE DP PAR ITEM` et `CONSOMMATION, TÉLÉMÉTRIE & PARTIELS IMPORTÉS`, sans supprimer leur contenu ni leurs boutons.

- [ ] **Step 6: Adapter le CSS des expansions**

Ajouter uniquement les styles nécessaires : bordure, fond, espacement, icône et résumé. Utiliser les tokens existants et conserver `.se-wrap { max-width:none; width:100%; }`. Ajouter un media query sous 820 px pour réduire le padding sans créer de largeur fixe.

- [ ] **Step 7: Relancer les tests source**

Run: `pytest tests/test_settings_domains.py tests/test_calendar_sources_panel.py -q`

Expected: PASS.

- [ ] **Step 8: Committer la refonte de composition**

```bash
git add frontend/pages/settings_cockpit.py tests/test_settings_domains.py
git commit -m "feat: organize settings by collapsible domains"
git push origin main
```

---

### Task 3: Vérifier le rendu navigateur et documenter la livraison

**Files:**
- Modify: `DEPLOYMENT_SESSION_2026-08-09.md`
- Modify: `docs/superpowers/plans/2026-08-09-parametres-domaines-implementation.md`
- Test: Chromium via Playwright sur `/settings`

**Interfaces:**
- Consumes: le rendu de `render_settings_cockpit()` livré par Task 2.
- Produces: preuve de QA, limites documentées et commit de livraison.

- [ ] **Step 1: Exécuter les tests ciblés**

Run: `pytest tests/test_settings_domains.py tests/test_calendar_sources_panel.py -q`

Expected: PASS.

- [ ] **Step 2: Exécuter la suite complète**

Run: `pytest -q`

Expected: PASS, sans modification des fichiers utilisateur non suivis.

- [ ] **Step 3: Tester `/settings` au navigateur**

Avec Chromium via Playwright :

1. Charger `http://192.168.1.5:8888/settings`.
2. Attendre le rendu initial.
3. Vérifier l'absence de `Traceback`, `Internal Server Error` et exception visible.
4. Vérifier la présence des six titres et l'absence de leur contenu métier avant ouverture.
5. Ouvrir `CONNEXIONS`, puis `PLANIFICATION EDN` ; vérifier que la première section se referme.
6. Vérifier que les boutons d'import, de sauvegarde et de rafraîchissement restent accessibles après ouverture.
7. Vérifier que le conteneur principal occupe toute la largeur disponible.

- [ ] **Step 4: Mettre à jour le rapport et le plan**

Ajouter dans `DEPLOYMENT_SESSION_2026-08-09.md` la date, l'URL, les routes testées, le résultat et les limites restantes. Cocher dans ce plan les étapes réellement exécutées ; ne pas déclarer la tranche terminée si une vérification navigateur échoue.

- [ ] **Step 5: Committer le rapport**

```bash
git add DEPLOYMENT_SESSION_2026-08-09.md docs/superpowers/plans/2026-08-09-parametres-domaines-implementation.md
git commit -m "docs: record settings domain QA"
git push origin main
```

