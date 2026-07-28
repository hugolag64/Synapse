# Correction du dialogue Mode focus (cockpit)

## Objectif

Le Mode focus cockpit (`frontend/components/focus_mode_cockpit.py`, Étape 16 du handoff) existe déjà et rend fidèlement `15-mode-focus.png`, mais n'a jamais suivi le processus de vérification des autres écrans (introduit dans un commit fourre-tout du 27/07, zéro test, checklist du handoff toujours non cochée). En le testant au navigateur : le dialogue reste bloqué dans sa transition d'entrée Quasar (`q-transition--scale-enter-active` ne se résout jamais, `no-pointer-events` traîne) — un clic pourtant bien placé peut atterrir sur le fond et fermer toute la session (minuteur en cours perdu), et Échap ne ferme pas le dialogue malgré l'affordance « Quitter le focus `esc` » affichée.

## Design

Le dialogue classic (`frontend/pages/dashboard/_reviews.py::open_focus_mode`) utilise `.props("maximized persistent")`. La version cockpit utilise `.props("full-width full-height")` — sans `maximized` (le prop Quasar dédié aux dialogues plein écran, avec sa propre transition, contrairement à `full-width`/`full-height` qui gardent la transition « standard » à échelle, inadaptée à un contenu qui occupe déjà tout l'écran via `.fm-overlay { position:fixed; inset:0; }`) et sans `persistent` (qui bloque la fermeture accidentelle par clic sur le fond). Fix : aligner sur `.props("maximized persistent")`, identique au classic. Aucun changement visuel attendu (`.fm-overlay` peint déjà tout l'écran indépendamment du wrapper Quasar).

À l'occasion, `_fmt_timer` et `_elapsed_minutes` (actuellement des closures internes à `open_focus_mode_cockpit`, donc non testables isolément) passent en fonctions de module pures — même refactor mineur que celui déjà fait sur les autres composants cockpit pour les rendre testables (`type_tag`/`due_info` dans `study_task_row.py`).

## Portée

Modifié : `frontend/components/focus_mode_cockpit.py` (prop du dialogue + extraction de deux fonctions pures). Nouveau : `tests/test_focus_mode_cockpit.py` (tests unitaires des deux fonctions + assertion source sur le prop du dialogue, même pattern que les autres tests `*_cockpit_ui.py`). Aucun changement de logique métier, de contrat (`state.focus_tasks` etc.) ni du rendu visuel.
