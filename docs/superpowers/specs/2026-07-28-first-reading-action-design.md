# Action première lecture — Design

## Objectif

Rendre l’action de première lecture accessible depuis le bouton principal de la fiche item cockpit lorsque `date_1ere_lecture` est absente.

## Décision

Dans la fiche cockpit, l’action principale dépend de l’état : `Commencer l’étude` si aucune première lecture n’existe, `Ouvrir le cours` si le suivi existe mais qu’aucune révision n’est due, et `Réviser maintenant` si une tâche est due. Le démarrage réutilise `open_start_tracking_dialog`, qui écrit la date et calcule J3/J7/J14/J30.

`Modifier les dates` reste une action secondaire de correction. Aucun changement de calcul, de backend ou de chemin classic.
