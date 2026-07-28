# Réparation des chemins PDF — Design

## Objectif

Permettre de remplacer facilement un chemin PDF obsolète, notamment pour les cours de dermatologie, depuis les surfaces où le PDF est utilisé.

## Décision

Réutiliser `open_pdf_wizard` comme unique parcours de recherche et de liaison. Ajouter une action **Modifier le PDF** même lorsqu’un chemin est déjà renseigné, dans la fiche cockpit, le panneau contextuel Aujourd’hui et le menu `CourseCard` classic.

Le wizard conserve son comportement actuel : recherche automatique si possible, sinon recherche manuelle ; la sélection écrit la nouvelle URI locale dans la propriété Notion appropriée et met à jour l’objet cours en mémoire. Aucun changement de backend, de format PDF ou d’algorithme de recherche n’est requis.

## Validation

Des tests de source vérifient que les trois surfaces exposent l’action de modification et réutilisent `open_pdf_wizard`. Les tests PDF existants restent la garantie du contrat de détection et de liaison.
