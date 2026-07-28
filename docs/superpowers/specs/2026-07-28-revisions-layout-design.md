# Mise en page de la vue Révisions

## Objectif

Utiliser la largeur disponible de la vue Révisions, aligner toutes les lignes et rendre le badge de navigation cohérent avec le nombre réel de révisions en retard.

## Design

La liste devient une grille CSS à colonnes fixes partagées par l’en-tête et les lignes : `Cycle`, `Item`, `Cours`, `Maîtrise`, `Échéance`, `Action`. Elle occupe la colonne principale d’un layout à deux colonnes.

La colonne droite affiche un panneau de pilotage avec le nombre de révisions en retard, aujourd’hui, à venir, la répartition par cycle et une charge estimée. Les données proviennent du même jeu de tâches que la liste.

Le badge `Révisions` de la sidebar est calculé dynamiquement à partir du nombre de tâches en retard. Il n’est plus codé en dur.

## Portée

Modification limitée à `frontend/pages/todo_cockpit.py` et `frontend/cockpit_shell.py`, avec tests ciblés. Aucun changement de modèle ou de stockage.
