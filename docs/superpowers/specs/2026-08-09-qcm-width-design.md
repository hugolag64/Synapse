# Largeur de la vue QCM

## Objectif

Faire occuper aux lignes `PAR COURS` toute la largeur du conteneur, comme l'en-tête, afin que les colonnes ITEM, cours, barre et score restent sur les mêmes axes.

## Cause

La grille CSS était correcte, mais les lignes NiceGUI conservaient une largeur intrinsèque de contenu (`378px` mesurés contre `547px` pour l'en-tête). Les tracks étaient donc recalculées dans un conteneur plus étroit.

## Décision

Ajouter `width:100%` et `box-sizing:border-box` au contrat partagé `.qc-head, .qc-row`, et borner les cellules directes avec `min-width:0`.
