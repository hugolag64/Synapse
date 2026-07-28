# Grille détaillée des items dans la vue Collèges

## Objectif

Utiliser l’espace disponible quand un collège est déplié et rendre visibles les signaux d’action par item : progression, statut, retard, fragilité, prochaine révision et score QCM.

## Design

Le détail d’un collège devient une grille alignée avec une ligne d’en-tête et une ligne par item. Les colonnes sont : `Item`, `Progression`, `Statut`, `Retard`, `Fragile`, `Prochaine révision`, `QCM`.

Les valeurs sont dérivées des mêmes tâches et scores déjà calculés pour la ligne du collège, sans nouvelle requête par item. Les actions existantes sont conservées : cliquer le titre ouvre la fiche, et le bouton `Valider` ouvre le dialogue de validation.

## Couleurs et états

Les états d’action utilisent les tokens existants : rouge pour les retards, orange pour fragile/critique, et les couleurs de maîtrise pour la progression et le QCM. `Non commencé` reste distinct mais utilise un contraste lisible ; le gris très pâle est réservé aux valeurs réellement absentes (`—`).

## Portée

La modification est limitée au cockpit Collèges (`frontend/pages/colleges_cockpit.py`). Aucun changement de modèle, de stockage ou de logique de synchronisation n’est nécessaire.

## Vérification

Ajouter des tests de caractérisation sur la préparation des lignes détaillées et vérifier que le module se compile ainsi que les tests frontend existants.
