# Synapse — point de reprise de session

Date : 27 juillet 2026  
Référence : `synapse_audit_reconnexion_algorithmes(1).md`

## État validé

- Le retour de session depuis Focus cockpit transmet désormais les activités,
  durée, confiance, difficulté, résultat QCM, catégorie et détail d’erreur au
  workflow de validation commun.
- Une erreur isolée est stockée comme signal. Elle ne crée plus directement de
  lacune ; une proposition apparaît à la seconde occurrence du même type sur
  le même item.
- La persistance des évaluations est centralisée dans
  `backend/core/evaluation/` :
  - `EvaluationInput` normalise les entrées QCM, auto-évaluation et OIC ;
  - `EvaluationOutcome` retourne l’identifiant persisté, les propositions de
    lacune et une recommandation consultative ;
  - `record_evaluation()` délègue aux stockages historiques sans double
    écriture ni migration.
- Les recommandations disponibles sont : `none`, `review_errors`,
  `practice_oic` et `consolidate`. Elles ne modifient ni le planning ni
  l’algorithme de maîtrise.
- Les tests sensibles aux dates sont alignés sur le fuseau métier Réunion.

## Vérification finale

`python -m pytest -q` : **480 tests réussis**, avec un avertissement de
dépréciation préexistant sur la boucle asyncio dans
`tests/test_delete_course_action.py`.

## Prochain chantier

Connecter la saisie QCM cockpit à `record_evaluation()` en réutilisant les
widgets existants. Ne pas introduire de nouvel écran ni recalculer la maîtrise.
Ensuite, raccorder progressivement les autres entrées QCM,
auto-évaluation et OIC à la même façade.

## Commits de référence

- `6e70061` — transmission complète du retour Focus ;
- `42d0c68` — lacunes différées après répétition ;
- `d56acdb` — façade de persistance Évaluation ;
- `8bf30f6` — couverture OIC ;
- `652b5db` — assertions de dates au fuseau Réunion.
