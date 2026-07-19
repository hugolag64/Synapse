# Unifier les flux de validation de séance

Date : 2026-07-19

## Problème

Trois review types (J3/J7/J14/J30/bonus/qcm_error/manuel) et le type
consolidation ont des flux de validation différents alors qu'ils devraient
se comporter de façon identique :

- **Reviews classiques** : le bouton "Valider" principal fait une validation
  instantanée en 1 clic (confiance 3/moyen, durée par défaut), sans dialog.
  Le dialog complet "Retour de séance" n'est accessible que via "Détailler…"
  dans le menu "⋯".
- **Consolidation** : le bouton "Valider" principal ouvre directement le
  dialog complet. Un bouton "Passer" (report 7j) est visible à côté.

Les deux chemins utilisent déjà le même composant de dialog
(`open_session_feedback_dialog` dans `frontend/pages/dashboard/_dialogs.py`) —
l'incohérence est dans quel chemin y mène par défaut, pas dans le dialog
lui-même.

En creusant, il y a aussi une duplication de composants d'affichage : trois
implémentations distinctes rendent une ligne/carte de review
(`render_review_row`, `render_review_card` dans
`frontend/pages/dashboard/_reviews.py`, et `_consolidation_card` dans
`frontend/pages/planning.py`), et la logique de complétion d'une
consolidation (`mark_consolidation_done` + `add_study_session`) est
dupliquée entre `dashboard/__init__.py::_on_done` et
`planning.py::_do_mark_consolidation`.

## Comportement cible

Toute ligne/carte de review, quel que soit son type, affiche :

```
[✓ Valider] [⏭ Passer] [⋯]
```

- **✓ Valider** — ouvre toujours le dialog complet "Retour de séance"
  (`open_session_feedback_dialog`), pour tous les types.
- **⏭ Passer** — report rapide (7 jours par défaut), visible sur tous les
  types (pas seulement consolidation).
- **⋯** — menu secondaire :
  - Confiance rapide (😰😟😐😊🔥) : validation instantanée sans dialog,
    conservée comme raccourci pour les jours où on veut aller vite.
  - Report fin : +1 jour / +3 jours / +1 semaine.
  - Lacune…
  - PDF / Fiche EDN (si disponibles pour le cours)
  - Ignorer (si applicable au contexte)
  - L'entrée "Détailler…" est supprimée : elle devient redondante puisque
    le bouton ✓ principal fait déjà ça.

Ce comportement s'applique aux trois surfaces : Dashboard (liste
RETARD/AUJOURD'HUI/Semaine), Mode Focus, et Planning (onglet Consolidation).

## Fusion des composants

- `render_review_row` (dashboard/_reviews.py) devient le composant
  canonique pour toute **liste** de reviews, dashboard et planning.py
  confondus.
- `planning.py` supprime `_consolidation_card` et appelle directement
  `render_review_row` pour son onglet Consolidation. Les items
  consolidation dans Planning gagnent au passage le menu Lacune, PDF/Fiche
  EDN, confiance rapide, etc., qu'ils n'avaient pas.
- `render_review_card` (Mode Focus, un seul item affiché à la fois) reste
  un composant séparé — densité d'affichage différente, usage différent —
  mais reçoit les mêmes règles de comportement (✓ → dialog toujours,
  Passer visible, "⋯" sans "Détailler…" redondant).

## Contrat de données / callbacks

`render_review_row` attend `on_done`, `on_postpone`, `on_ignore`,
`validate_fn` avec la signature :
`(task, card, activity_types, duration_minutes, confidence, difficulty, qcm_result=None, weak_category=None, weak_detail=None)`.

- Le dashboard (`dashboard/__init__.py::_on_done`) gère déjà les deux
  branches (`mark_consolidation_done` vs `mark_done`) correctement — rien
  à changer côté dashboard sur ce point.
- La logique dupliquée dans `planning.py::_do_mark_consolidation`
  (`mark_consolidation_done` + `add_study_session`) est extraite dans une
  fonction backend partagée (dans `backend/core/reviews/local_store.py`
  ou un module `consolidation.py` existant), appelée par les deux
  appelants (`dashboard/__init__.py::_on_done` et `planning.py`).
- `planning.py::_on_postpone` devient un wrapper à 3 arguments
  `(task, card, days)` — `card` ignoré (pas d'animation de sortie dans ce
  contexte) — pour matcher la signature attendue par `render_review_row`.
  `postpone_task` est appelé comme aujourd'hui.
- `on_ignore` : pas de notion d'"ignorer" pour la consolidation dans
  planning.py aujourd'hui — passé à `None`. Le bouton Ignorer sera
  simplement absent du menu dans ce contexte
  (`render_review_row` gère déjà `if on_postpone or on_ignore`).

## Vérification / rollout

Pas de tests UI automatisés existants pour ces flows (NiceGUI, rendu
serveur). Vérification :

1. Restart manuel de l'app après implémentation (le hot-reload s'est
   montré peu fiable lors du dernier chantier consolidation — `Ctrl+C`
   puis `python main.py`).
2. Vérification manuelle sur les 3 surfaces : Dashboard
   (RETARD/AUJOURD'HUI), Mode Focus, Planning → onglet Consolidation.
   Sur chacune : ✓ ouvre le dialog, ⏭ reporte de 7j, ⋯ propose confiance
   rapide + Lacune + PDF/Fiche EDN.
3. Si la fonction backend extraite (complétion consolidation) contient de
   la logique non triviale, ajouter un test unitaire ciblé ; sinon pas de
   nouveau test requis.

## Hors scope

La remarque plus large de l'utilisateur sur les "features top mais pas
interconnectées" dans le programme est un sujet distinct et plus vaste,
volontairement mis de côté ici. À traiter dans une session de brainstorming
dédiée.
