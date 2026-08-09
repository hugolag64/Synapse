# Uniformisation de la vue OIC

## Objectif

Garantir une largeur stable pour les lignes OIC, quel que soit le niveau de maîtrise affiché ou la longueur du titre.

## Décision

La ligne OIC utilise trois zones : code fixe, contenu flexible et actions fixes. Le statut et les deux boutons restent alignés à droite ; sur mobile, les tracks sont réduites sans modifier les actions.

## Contraintes

- Aucun changement de chargement, de maîtrise ou d'évaluation OIC.
- Les titres longs restent tronqués dans la zone centrale.
- Le contrat CSS est vérifié par test source et par la suite complète.
