# Interactions et pilotage des points faibles

## Objectif

Rendre chaque lacune actionnable dans le cockpit et utiliser la largeur disponible avec un panneau de pilotage.

## Design

Le cockpit réutilise `WeakPointCard`, qui contient déjà les actions métier : résoudre/réactiver, passer à revoir, rendre récurrente, modifier la sévérité et supprimer. Le bouton `+ Ajouter` devient `Créer une lacune`.

La zone de contenu passe en pleine largeur et adopte deux colonnes : liste interactive à gauche, panneau de pilotage à droite. Le panneau affiche les totaux par statut, les niveaux critiques et les sources des lacunes.

## Portée

La logique de stockage et les actions existantes sont conservées. La modification porte sur `frontend/pages/weak_points_cockpit.py` et ses tests ciblés.
