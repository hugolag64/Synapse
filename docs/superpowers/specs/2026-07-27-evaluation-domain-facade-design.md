# Synapse — façade métier d’évaluation

Date : 27 juillet 2026  
Statut : conception validée par Hugo

## Objectif

Introduire une entrée métier unique pour les évaluations afin que les futurs
écrans cockpit, les parcours existants et les imports QCM appliquent les mêmes
règles de persistance et de détection de signaux répétés.

## Périmètre

- Normaliser les données reçues depuis une évaluation QCM, une auto-évaluation
  ou une validation OIC.
- Persister les données dans les tables existantes, sans double stockage ni
  migration de données.
- Retourner un résultat explicite contenant les conséquences métier : signal
  enregistré, proposition de lacune éventuelle et recommandation de révision.
- Préparer la saisie QCM cockpit à appeler cette unique façade.

## Hors périmètre

- Nouvelle interface ou onglet Évaluation central.
- Refonte des tables SQLite historiques.
- Modification du score ou des statuts de maîtrise.
- Création automatique de lacune à partir d’un unique signal.
- Évolution des seuils de répétition existants.

## Modèle d’entrée

`EvaluationInput` porte les informations communes :

- `source` : `qcm`, `auto_eval` ou `oic` ;
- identifiants et contexte de l’item ;
- score, résultats et confiance lorsque la source les fournit ;
- types d’erreur normalisés et détail facultatif ;
- métadonnées propres à la source, conservées par son adaptateur.

Chaque source reste responsable de ses données spécifiques : une session QCM
continue d’alimenter `qcm_sessions`, une auto-évaluation `study_sessions` et
un OIC `oic_attempts`.

## Façade et résultat

`record_evaluation(input: EvaluationInput) -> EvaluationOutcome` est la seule
commande consommée par les nouveaux parcours.

Elle délègue la persistance à l’adaptateur correspondant, applique les règles
de récurrence existantes, puis retourne :

- l’identifiant de l’évaluation persistée ;
- les identifiants de propositions de lacune éventuellement créées ou mises à
  jour ;
- une recommandation de révision déterministe, sans écrire de tâche ;
- les signaux ignorés lorsque les données sont insuffisantes.

L’appel est idempotent pour une même évaluation source lorsque l’adaptateur
dispose déjà d’une clé de déduplication. Une erreur d’écriture ne doit retourner
aucun succès partiel à l’interface appelante.

## Règles métier initiales

- Un signal d’erreur isolé est persisté sans créer de `weak_point`.
- La répétition passe par `pending_gap_proposals` et le seuil existant.
- Une réussite OIC, un score QCM ou une confiance déclarée ne modifient pas
  `mastery.py` dans ce lot.
- Les recommandations sont consultatives : aucun planning n’est modifié
  automatiquement.

## Tests d’acceptation

- Une entrée QCM persiste dans `qcm_sessions` et transmet les types d’erreur
  au mécanisme de proposition différée.
- Une entrée d’auto-évaluation persiste dans `study_sessions` sans créer de
  lacune immédiate.
- Une entrée OIC conserve son historique et sa progression existants.
- Les mêmes données d’entrée produisent le même `EvaluationOutcome` et aucune
  modification de maîtrise.

