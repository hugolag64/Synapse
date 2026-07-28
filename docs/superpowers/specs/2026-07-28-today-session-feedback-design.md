# Retour de séance depuis Aujourd’hui cockpit — Design

## Objectif

Rendre l’auto-évaluation de fin de séance accessible depuis le bouton `Terminer` du panneau contextuel Aujourd’hui cockpit et la faire passer par le pipeline de maîtrise existant.

## Décision

Le bouton `Terminer` ouvre le wizard partagé `open_session_feedback_dialog`. Le wizard reste la source des champs d’auto-évaluation ; son callback appelle le `_on_done` de la page avec les champs complets. `_on_done` continue d’appeler `complete_review`, qui persiste la validation et enregistre l’évaluation via `record_evaluation(source="auto_eval")`.

Aucun changement n’est apporté à l’algorithme de maîtrise, aux seuils de lacunes, au backend, au chemin classic ou au design du wizard.

## Validation

Un test de caractérisation vérifie que la page Aujourd’hui importe/appelle le wizard partagé et lui transmet le callback `_on_done`. Les tests existants de `complete_review` et `record_evaluation` garantissent ensuite la persistance et l’alimentation de la maîtrise.
