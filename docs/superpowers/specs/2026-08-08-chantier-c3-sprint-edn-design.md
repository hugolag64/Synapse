# Chantier C3 — Rendre visible ce que le Sprint EDN pilote

**Date** : 2026-08-08
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Troisième sous-chantier de C (fond pédagogique), suite de C1 (message trompeur `mastery.py`) et C2
(acquis antérieurs), tous deux terminés. Demande initiale de l'utilisateur : « Sprint EDN : logique
incomprise. »

**Découverte pendant l'exploration, même schéma qu'en C2 : un fichier mort et un vrai bug de
plomberie, pas un trou de conception.**

`frontend/components/sprint_countdown_widget.py` est un widget **Streamlit**, reliquat d'avant la
migration vers NiceGUI — confirmé mort par grep sur tout le dépôt : `render_sprint_countdown_widget`
n'est importé nulle part ailleurs.

Le composant réellement affiché (Dashboard, onglet « Aujourd'hui », via
`frontend/pages/dashboard/_cockpit_today.py:482-487`) est
`frontend/components/edn_insights_panel.py::render_edn_insights_panel`. Il consomme
`SprintConfig` (`backend/core/planning/sprint_countdown.py`), qui calcule pour chacune des 3 phases
(seuils 120/30 jours) : `phase`, `recommended_new_ratio`, `recommended_review_ratio`,
`recommended_qcm_dp_ratio`, `daily_target_items`, `focus_message`. Mais `edn_insights_model()`
(`edn_insights_panel.py:11-25`) n'extrait que `countdown`, `target`, `phase`, `coverage`,
`coverage_percent`, `mastery`, `overdue`, `remaining` — **les 5 champs qui décrivent concrètement ce
que la phase change au quotidien** (`recommended_new_ratio`, `recommended_review_ratio`,
`recommended_qcm_dp_ratio`, `daily_target_items`, `focus_message`) ne sont lus par aucun autre
fichier du dépôt à part le widget mort. L'utilisateur voit donc l'étiquette de phase changer (ex.
« Consolidation ») sans jamais voir ce que ça implique — d'où « logique incomprise ».

## Objectif

Le panneau Sprint EDN vivant affiche le message de focus et la répartition recommandée de chaque
phase, sans toucher au calcul des seuils ni des ratios. Le widget Streamlit mort est supprimé.

## Périmètre

### 1. Extension du modèle — `frontend/components/edn_insights_panel.py:11-25`

`edn_insights_model()` gagne 5 clés, lues directement sur `status` (déjà calculées par
`SprintConfig`, aucun changement backend) :

```python
def edn_insights_model(status) -> dict[str, str]:
    mastery = "—" if status.average_mastery is None else f"{status.average_mastery:g} %"
    total_items = int(status.total_items or 0)
    covered_items = int(status.covered_items or 0)
    coverage_percent = min(100, covered_items / total_items * 100 if total_items else 0)
    return {
        "countdown": f"J-{status.days_remaining}",
        "target": status.target_date.strftime("%d/%m/%Y"),
        "phase": str(status.phase.value).replace("_", " ").title(),
        "coverage": f"{status.covered_items}/{status.total_items}",
        "coverage_percent": f"{coverage_percent:.1f}",
        "mastery": mastery,
        "overdue": str(status.overdue_reviews),
        "remaining": str(status.remaining_reviews),
        "focus_message": status.focus_message,
        "new_ratio": f"{int(status.recommended_new_ratio * 100)}",
        "review_ratio": f"{int(status.recommended_review_ratio * 100)}",
        "qcm_dp_ratio": f"{int(status.recommended_qcm_dp_ratio * 100)}",
        "daily_target_items": str(status.daily_target_items),
    }
```

### 2. Deux nouvelles lignes dans le rendu — `frontend/components/edn_insights_panel.py:100-123`

Dans `render_edn_insights_panel()`, sous le sous-titre existant (« Objectif DATE · phase X »),
ajouter le message de focus de la phase ; sous la barre de progression, ajouter la répartition
recommandée. Les deux réutilisent la classe `.edn-sprint-subtitle` déjà définie (texte discret,
`color:var(--text-muted)`) — aucune nouvelle règle CSS nécessaire.

```python
with ui.column().classes("gap-0"):
    ui.label(f"Sprint EDN · {model['countdown']}").classes("edn-sprint-title")
    ui.label(
        f"Objectif {model['target']} · phase {model['phase']}"
    ).classes("edn-sprint-subtitle")
    ui.label(model["focus_message"]).classes("edn-sprint-subtitle")
```

```python
with ui.element("div").classes("edn-sprint-progress-track mt-3"):
    ui.element("div").classes("edn-sprint-progress-fill").style(
        f"width:{model['coverage_percent']}%"
    )
ui.label(
    f"Répartition recommandée : {model['new_ratio']}% nouveaux · "
    f"{model['review_ratio']}% révisions · {model['qcm_dp_ratio']}% QCM/DP · "
    f"{model['daily_target_items']} items/j visés"
).classes("edn-sprint-subtitle mt-2")
```

### 3. Suppression du widget mort

`frontend/components/sprint_countdown_widget.py` supprimé entièrement. Vérifié par grep sur tout le
dépôt : aucun autre fichier n'importe `render_sprint_countdown_widget`, `SprintCountdownService` ou
`SprintPhase` depuis ce module (les deux derniers sont importés depuis
`backend.core.planning.sprint_countdown` directement par les vrais consommateurs, pas depuis le
widget).

## Hors périmètre

- Aucun changement à `SprintCountdownService.get_sprint_status()` : seuils (120j/30j), valeurs de
  ratio par phase, `daily_target_items` par phase, textes de `focus_message` — tous inchangés.
- `edn_target_date` reste configurable uniquement via `settings_cockpit.py`, déjà fonctionnel, non
  concerné par ce chantier.
- `project_to_exam` (scénarios de projection) et `build_gain_items` (priorités de gain) : déjà
  affichés dans le panneau, non modifiés.

## Risques

- **Test de contrat à étendre, pas casser.** `tests/test_edn_insights_ui.py::test_edn_insights_model_contains_progress_and_sprint_fields`
  construit un `SimpleNamespace` factice sans les 5 nouveaux attributs
  (`recommended_new_ratio`, `recommended_review_ratio`, `recommended_qcm_dp_ratio`,
  `daily_target_items`, `focus_message`) — `edn_insights_model()` lèvera une `AttributeError` dès
  qu'elle essaiera de les lire sur ce namespace. Le fixture factice doit être complété avec ces 5
  attributs avant que ce test puisse continuer à passer.
- **`tests/test_phase5_edn.py`** teste `SprintConfig`/`SprintPhase` directement (calcul backend) —
  non affecté puisque `get_sprint_status()` n'est pas modifié.

## Tests

- Étendre `tests/test_edn_insights_ui.py::test_edn_insights_model_contains_progress_and_sprint_fields` :
  le `SimpleNamespace` factice gagne `recommended_new_ratio=0.25`, `recommended_review_ratio=0.45`,
  `recommended_qcm_dp_ratio=0.30`, `daily_target_items=6`, `focus_message="🎯 Mode Consolidation..."` ;
  nouvelles assertions sur `model["focus_message"]`, `model["new_ratio"] == "25"`,
  `model["review_ratio"] == "45"`, `model["qcm_dp_ratio"] == "30"`,
  `model["daily_target_items"] == "6"`.
- Nouveau test : le corps source de `render_edn_insights_panel` contient `model["focus_message"]` et
  `model["new_ratio"]` (garde-fou que le rendu consomme bien les nouveaux champs du modèle, même
  technique de scoping texte que B4/C1/C2).
- Nouveau test : `frontend/components/sprint_countdown_widget.py` n'existe plus (`Path(...).exists()
  is False`), et rien dans le dépôt ne référence plus `render_sprint_countdown_widget` (grep sur
  tous les fichiers `.py`).
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la
  dernière.
