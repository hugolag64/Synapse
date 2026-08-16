# Versionnement des résultats QCM — Design

## Objectif

Conserver le résultat produit au moment de l’évaluation, puis les résultats
recalculés lorsqu’une donnée officielle arrive tardivement (rang, réponse
UNESS ou correction). Le score courant de `qcm_sessions` reste compatible avec
les écrans existants ; l’historique devient auditable.

## Décision d’architecture

Ajouter une table append-only `qcm_result_versions`, liée à `qcm_sessions`.
Chaque ligne contient une phase (`initial` ou `final`), une révision, les
métriques de score et de rang, la version du barème, la provenance, le motif et
un instant de création. Une même évaluation peut avoir un snapshot initial et
plusieurs snapshots finaux ; aucun snapshot existant n’est modifié.

`add_qcm_session_full()` crée automatiquement le snapshot `initial` dans la
même transaction que la ligne `qcm_sessions`. Une nouvelle fonction atomique
`record_qcm_result_final()` met à jour le résultat courant et ajoute un snapshot
`final`. Elle refuse une session inexistante et exige une provenance et un motif
non vides. Les champs historiques des sessions existantes sont rétrocompatibles
et ne sont pas réécrits lors de la migration.

## Données et intégrité

Le snapshot reprend score brut/pourcentage, dénominateur, bonnes/mauvaises
réponses, rangs A/B/inconnus, difficulté, type de session, erreur et commentaire.
`metadata_json` permet de conserver les détails de provenance sans stocker de
secret. Une contrainte garantit `phase ∈ {initial, final}` et un index permet de
retrouver rapidement la dernière révision finale.

## Flux

1. `record_evaluation()` écrit `qcm_sessions` comme aujourd’hui.
2. L’insertion crée le snapshot initial avec `source=live_evaluation`.
3. Une correction officielle tardive appelle `record_qcm_result_final()` avec
   les métriques recalculées et `source=official_data` ou `source=admin`.
4. Les écrans continuent de lire `qcm_sessions`; l’API de lecture expose les
   versions pour l’audit et les tests.

## Tests d’acceptation

- Une nouvelle session possède immédiatement exactement un snapshot initial.
- Une finalisation ajoute un snapshot final sans supprimer l’initial.
- Une seconde finalisation crée une révision finale supplémentaire.
- Le snapshot final contient les nouvelles métriques et devient le résultat
  courant de `qcm_sessions`.
- Une session inconnue, une phase invalide ou une provenance/motif vide est
  rejetée sans écriture partielle.
- Les bases existantes migrent sans perte et les tests historiques restent
  compatibles.
