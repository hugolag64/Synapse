# Chantier C2 — Marquer un item déjà vu avant Synapse (acquis antérieurs)

**Date** : 2026-08-08
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Deuxième sous-chantier de C (fond pédagogique), suite de C1 (message trompeur `mastery.py`,
terminé). Demande initiale de l'utilisateur : « pas de moyen de marquer un item déjà vu avant
Synapse (semestres précédents) autrement que « non fait » ».

**Découverte pendant l'exploration : ce n'est pas un trou fonctionnel, c'est du code mort.** Le
mécanisme existe déjà en entier côté backend (`backend/core/knowledge/{models,service,store}.py`) :
un `declared_level` (`solide` / `correct` / `flou`) par item, une « graine » de score qui se dégrade
avec le temps et se dilue devant les preuves réelles (`decayed_seed`, `blend` — `models.py`),
exactement conçu pour ce cas d'usage. Un bloc UI complet pour le déclarer existe déjà :
`_render_knowledge_block()` dans `frontend/pages/course_detail.py:91-145` (3 boutons
Solide/Correct/Flou). Mais `course_detail_page()` — la fonction que la route `/cours/{course_id}`
appelle (`main.py:271-273`) — fait un `return` inconditionnel dès la ligne 155 vers
`render_item_cockpit()` (le cockpit refonte). Tout le reste de `course_detail_page`, dont l'appel à
`_render_knowledge_block()` ligne 338, n'est **jamais exécuté**. Confirmé par grep sur tout le dépôt :
`course_detail_page` est le seul symbole de `course_detail.py` importé ailleurs (`main.py:40`), et
aucun autre fichier ne référence `_render_knowledge_block`, `_fmt_date`, `_fmt_min`, `_day_ago`,
`_NA_COLORS` ou `_render_course_timeline` par chemin qualifié.

Une page de triage en masse par collège existe aussi (`frontend/pages/triage.py`,
`@ui.page("/triage/{college}")`) mais n'est reliée depuis aucune autre page — accessible seulement
par URL directe. Décision utilisateur : reste hors périmètre pour C2.

## Objectif

Porter le contrôle « Niveau déclaré » (Solide/Correct/Flou) dans l'onglet Vue d'ensemble du cockpit
d'item, en réutilisant l'infrastructure backend existante sans la modifier. Supprimer le code mort
de `course_detail.py` qui a caché ce trou pendant des mois.

## Périmètre

### 1. Nouveau contrôle dans le cockpit — `frontend/pages/course_detail_cockpit.py`

Nouvelle fonction privée, placée juste avant `_tab_overview` (son unique appelante) :

```python
_DECLARED_LEVELS = (
    ("solide", "Solide", "positive"),
    ("correct", "Correct", "warning"),
    ("flou", "Flou", "negative"),
)


def _render_declared_level(course, mastery) -> None:
    from backend.core.knowledge import store as knowledge_store

    container = ui.column().classes("w-full gap-2 ci-section")

    def _render():
        state = knowledge_store.get_item_state(course.id, "college")
        container.clear()
        with container:
            with ui.row().classes("items-center gap-2"):
                ui.label("Niveau déclaré avant Synapse").classes("ci-label")
                if state is None:
                    ui.badge("À situer").props("color=grey outline")

            with ui.row().classes("items-center gap-1"):
                for level, label, color in _DECLARED_LEVELS:
                    selected = state is not None and state.declared_level == level

                    def _set(_level=level):
                        knowledge_store.set_item_state(
                            course.id, _level, context="college", source="triage"
                        )
                        review_service.invalidate_cache()
                        _render()

                    ui.button(label, on_click=_set).props(
                        f"unelevated rounded size=sm color={color}"
                        if selected else
                        "outline rounded size=sm color=grey"
                    )

    _render()
```

`review_service` est déjà importé en tête de `course_detail_cockpit.py` (ligne 31) ; seul
`knowledge_store` doit être ajouté (import local à la fonction, même style que les autres imports
tardifs déjà présents dans ce fichier, ex. `render_dp_tutor_action`).

**Couleurs conservées telles quelles.** `positive`/`warning`/`negative` (vert/orange/rouge)
représentent une auto-évaluation réellement bonne/moyenne/faible de l'élève sur l'item — c'est le
même type de signal sémantique que « Difficulté » ou « Résultat QCM », explicitement épargnés par la
règle indigo→primary des chantiers B1/B2. Aucune conversion de couleur ici.

**Pas de ligne de couverture OIC.** L'ancien bloc (`course_detail.py`) affichait aussi une ligne de
couverture OIC (rang A / rang B) sous les boutons. Elle est volontairement omise ici : le cockpit a
déjà un onglet OIC dédié (`render_oic_panel`, onglet « OIC ») qui couvre ce besoin en détail — la
dupliquer en résumé ici serait redondant. `mastery.oic_coverage_a` / `mastery.has_rang_a_badge` sont
d'ailleurs déjà calculés dans la snapshot passée à `_tab_overview`, donc aucune requête
supplémentaire ne serait de toute façon nécessaire si cette ligne était réintroduite plus tard.

### 2. Intégration dans `_tab_overview` — `frontend/pages/course_detail_cockpit.py:596-667`

Le nouvel appel `_render_declared_level(course, mastery)` est inséré entre la grille 2 colonnes
(prédiction de maîtrise / notions reliées, qui se termine ligne 652) et le bloc « Pourquoi ce score »
(qui commence ligne 654). Ordre volontaire : l'utilisateur déclare son niveau, et voit
immédiatement l'effet juste en dessous — dès qu'un niveau est déclaré, `mastery.py:244` ajoute déjà
`"Niveau déclaré : {niveau}"` à `mastery.reasons`, affiché par le bloc « Pourquoi ce score ».

`_tab_overview(course, task, score, level, next_due, next_cycle, mastery, sessions)` reçoit déjà
`course` et `mastery` en paramètres — aucun changement de signature nécessaire.

### 3. Suppression du code mort — `frontend/pages/course_detail.py`

Tout ce qui suit le `return` de la ligne 155 est supprimé : le corps mort de `course_detail_page`
(lignes 156-606), la fonction `_render_course_timeline` (ligne 527, appelée uniquement depuis ce
corps mort), et les helpers `_fmt_date`, `_fmt_min`, `_day_ago`, `_NA_COLORS` (lignes 42-88,
utilisés uniquement par le corps mort — vérifié qu'aucun n'est appelé par
`_render_knowledge_block`). `_render_knowledge_block` elle-même (lignes 91-145) est supprimée : son
contenu est porté dans le cockpit (section 1), elle n'a plus de raison d'exister ici.

Le fichier final ne contient plus que :

```python
"""
course_detail.py — Synapse — Fiche Course Intelligence
-------------------------------------------------------
Route : /cours/{course_id}

Délègue entièrement à la vue cockpit (frontend/pages/course_detail_cockpit.py).
"""
from __future__ import annotations

from frontend.theme import frame


def course_detail_page(course_id: str) -> None:
    with frame("Fiche cours"):
        from frontend.pages.course_detail_cockpit import render_item_cockpit
        render_item_cockpit(course_id)
```

Tous les autres imports du fichier d'origine (`datetime`, `json`, `ui`, `logger`,
`render_traps_card`, `data_store`, `local_store`, `get_course_mastery`, `PROGRESSION_COLORS`,
`get_next_action`, `ReviewTask`, `obsidian_service`, `extract_traps`, `_settings`,
`knowledge_store`, `knowledge_service`, `review_service`) ne sont plus utilisés une fois le code mort
retiré — supprimés avec lui.

## Hors périmètre

- La page `/triage/{college}` n'est ni supprimée ni reliée depuis une autre page — décision
  utilisateur, reste accessible par URL directe uniquement.
- Aucun changement à `backend/core/knowledge/{models,service,store}.py` — l'infrastructure existante
  (graine, dégradation, dilution) est réutilisée telle quelle.
- Aucun changement à `mastery.py` au-delà de ce qui existe déjà (le calcul de la graine et sa fusion
  avec le score réel restent inchangés).

## Risques

- **Fichier `course_detail.py` très réduit après nettoyage** (de 606 lignes à ~15). C'est le résultat
  attendu, pas un accident — vérifié en amont qu'aucun autre module n'importe les symboles
  supprimés. À revérifier une dernière fois juste avant suppression (grep) pour parer à un import
  ajouté entre la conception et l'exécution.
- **Commentaire de test à mettre à jour, pas son assertion.** `tests/test_knowledge_course_detail_data.py`
  référence `_render_knowledge_block` de `course_detail.py` dans son docstring et ses commentaires
  (pas dans une assertion — le test appelle `knowledge_service.oic_coverage` directement, jamais
  `course_detail.py`). Le test continue de passer sans modification, mais le commentaire devient
  trompeur une fois la fonction déplacée ; à corriger pour rester exact.

## Tests

- Nouveau test dans `tests/test_knowledge_course_detail_data.py` (ou nouveau fichier dédié si plus
  clair à l'implémentation) : le corps source de `_render_declared_level` dans
  `course_detail_cockpit.py` contient les trois niveaux (`"solide"`, `"correct"`, `"flou"`) et appelle
  `knowledge_store.set_item_state` et `review_service.invalidate_cache`.
- Nouveau test : `_render_declared_level` (ou son appel) apparaît dans `_tab_overview`, entre les
  marqueurs de la grille 2 colonnes et du bloc « Pourquoi ce score » (même technique de scoping
  texte que B4/C1 — pas d'import du module page).
- Nouveau test : `frontend/pages/course_detail.py` ne contient plus `_render_knowledge_block` ni
  `_render_course_timeline`, et sa taille totale est très inférieure à 606 lignes (garde-fou
  approximatif contre une régression de suppression incomplète).
- Mise à jour du docstring/commentaires de `tests/test_knowledge_course_detail_data.py` pour
  référencer le nouvel emplacement (`course_detail_cockpit.py::_render_declared_level`) au lieu de
  `course_detail.py::_render_knowledge_block`.
- Suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la première tâche et après la
  dernière.
