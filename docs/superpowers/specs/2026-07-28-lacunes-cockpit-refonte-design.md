# Refonte de l'écran Lacunes (cockpit)

## Objectif

Recentrer l'écran Lacunes et aligner sa carte sur les tokens cockpit et le spec du handoff (README §9, `09-lacunes.png`), dont l'implémentation de l'étape 11 puis le spec [[2026-07-28-weak-points-actions-design]] avaient dérivé : nav interne en sidebar, panneau « Pilotage » en pleine largeur, carte reprenant encore les classes Tailwind du composant classic (`weak_point_card.py`) plutôt que les variables `--*` du cockpit.

Ce document **remplace** [[2026-07-28-weak-points-actions-design]] sur la mise en page (sidebar + panneau pilotage + carte classic) ; il en conserve l'intention (actions métier disponibles directement sur la carte) mais change le comment.

## Design

### Structure

La topbar (titre, sous-titre compteurs, boutons « Synchroniser Obsidian » / « Ajouter ») est inchangée. En dessous :

- La sidebar de navigation interne (Vue d'ensemble / Lacunes / Ancrages / À revoir / Résolues) devient une **rangée de chips horizontales**, même pattern que la page Items (`it-chip`) : sélection unique, compteur en mono à droite du libellé. La logique de filtrage (`filter_weak_points_view`) et les 5 vues existantes sont conservées telles quelles, seule leur présentation change.
- Le panneau « Pilotage des lacunes » (KPIs + répartition par source) est **supprimé** : redondant avec l'écran Statistiques, et il justifiait la mise en page pleine largeur non centrée qui casse la cohérence avec le reste du cockpit.
- Le contenu passe d'une grille deux colonnes (`wp-content-body`) à une **colonne unique centrée**, `max-width: 860px` — plus étroit que Items/QCM (1100–1200px) parce qu'une liste à une seule colonne de lignes courtes reste plus lisible resserrée ; c'est un choix délibéré, pas un oubli.

### Ligne de lacune

Le composant carte du classic (`WeakPointCard` — bordure gauche colorée, pill de statut, ombre, Tailwind) reste utilisé tel quel par le kanban classic (`weak_points.py`), **non modifié**. Le cockpit reçoit un nouveau composant dédié, `frontend/components/weak_point_row.py`, sur les tokens `--*` :

- Ligne plate ~50px, radius 6px, `hover:background:var(--surface)` — même grammaire que `study_task_row` (Révisions).
- Colonne gauche : point de statut (`--danger` critique, `--warning` active/à revoir/récurrente, `--success` résolue).
- Centre : titre en une ligne (troncature), et en dessous la ligne de statut déjà produite par `_status_line()` (inchangée) — colorée **uniquement** si l'urgence le justifie (`--danger` si critique, `--warning` si à revoir), sinon `--text-muted`. Une seule dimension porte la couleur, cohérent avec la règle d'or n°3 du handoff.
- Droite : au repos, collège + id en mono (`--text-dim`) ; au survol (ou focus clavier), ces métadonnées cèdent la place à un cluster d'icônes d'action (transition opacité, pas de layout shift) : Ouvrir dans Obsidian (si lié), Revoir le cours, Résoudre/Réactiver, et un menu `···` reprenant les actions secondaires actuelles (rendre récurrente, marquer à revoir, sévérité, supprimer). Les handlers sont ceux déjà écrits dans `weak_point_card.py` (mêmes appels `local_store`/`weak_points_sync`), seulement déplacés/réadaptés au nouveau composant — aucune règle métier ne change.
- Ligne résolue : opacité 0.55 sur l'ensemble de la ligne, comme aujourd'hui.

### Étape supprimée

`_draw_pilotage`, `_weak_point_summary` (si sans autre appelant après retrait du panneau) et les classes CSS `wp-sidebar*`, `wp-nav*`, `wp-pilotage*`, `wp-content-body`, `wp-kpis`, `wp-source-*` sont retirées de `weak_points_cockpit.py`.

## Portée

Modifiés : `frontend/pages/weak_points_cockpit.py` (layout : chips à la place de la sidebar+pilotage, colonne centrée, appel au nouveau composant de ligne).
Nouveau : `frontend/components/weak_point_row.py` (ligne cockpit token-based, actions au survol).
Non touchés : `frontend/components/weak_point_card.py` et `frontend/pages/weak_points.py` (chemin classic, kanban + drag inchangés) ; aucun changement backend/stockage.
