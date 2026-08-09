# Alignement de la grille des items Collèges

## Objectif

Garantir que l'en-tête et chaque ligne de la grille Collèges utilisent exactement les mêmes positions horizontales, y compris lorsque la cellule d'action contient un bouton.

## Cause

La dernière colonne est actuellement `auto`. Son contenu varie entre l'en-tête vide, les lignes sans tâche et les lignes avec bouton `Valider`. Le navigateur recalcule alors la largeur disponible de la première colonne `minmax(180px, 2fr)`, ce qui décale les colonnes suivantes.

## Décision

Remplacer la largeur `auto` de la colonne `action` par une largeur fixe de `88px` dans le contrat `DataGrid` et dans le template CSS partagé par `.cg-item-head` et `.cg-item`. Ajouter `min-width:0` aux enfants directs afin que les titres longs restent tronqués dans leur cellule sans modifier les tracks de la grille.

## Validation

- Un test source vérifie que `action` vaut `88px` et que le CSS partagé contient la même largeur.
- La suite ciblée Collèges puis la suite complète doivent rester vertes.
- Chromium doit montrer les libellés d'en-tête au même axe vertical que les cellules des lignes.
