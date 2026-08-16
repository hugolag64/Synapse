# Inférence Gemini des rangs UNESS — Design

## Objectif

Qualifier automatiquement les questions d’annales UNESS qui n’ont pas de rang
officiel explicite, en fournissant à Gemini les OIC des items concernés, puis
laisser l’administrateur accepter l’inférence, la corriger ou la relancer. Une
inférence incertaine ne doit jamais modifier silencieusement le rang utilisé par
le lecteur ou la validité Rang A.

## Décision d’architecture

Le flux est composé de quatre unités séparées :

1. `rank_inference` construit et valide le contrat Gemini pour un lot de
   questions partageant un item et son contexte OIC.
2. `local_store` persiste les jobs, les tentatives, les résultats Gemini et les
   décisions administratives dans SQLite, avec une transition atomique de statut.
3. `rank_job_runner` scanne les questions UNESS sans rang, réclame un job avec un
   bail court, exécute Gemini hors de la boucle NiceGUI, puis écrit le résultat
   dans les métadonnées de la question et dans l’historique.
4. `rank_admin` expose les actions JSON et le panneau NiceGUI dans les réglages.

Le worker est appelé par la boucle de fond existante toutes les cinq minutes,
avec un petit lot borné. Une relance manuelle réinitialise le job sans supprimer
son historique. Il n’y a pas de nouveau démon ni de nouvelle dépendance.

## Sources et priorité

- Une question portant déjà un rang officiel `A` ou `B` est ignorée par le
  scanner et ne peut pas être écrasée par Gemini ou l’admin.
- Une question sans rang officiel est candidate uniquement si elle appartient à
  une session UNESS importée et possède au moins un item identifié.
- Les OIC sont récupérés depuis `lisa_oic`, via les cours locaux correspondant à
  l’item. Le prompt contient code, intitulé et rang de chaque OIC.
- Si aucun OIC local n’est disponible, aucun appel Gemini automatique n’est
  effectué : le job passe en `needs_oic` et reste visible dans la file pour
  permettre une actualisation LiSA ou une décision manuelle.
- Le résultat est passé à `resolve_rank`, qui applique la priorité déjà validée :
  officiel, Gemini suffisamment confiant et non ambigu, puis admin. Toute
  contradiction admin/Gemini est conservée dans les alternatives.

## Contrat Gemini

Chaque appel concerne un item et au maximum 20 questions. Le prompt demande
strictement :

```json
{
  "questions": [
    {
      "id": "question-uness-1",
      "rank": "A",
      "confidence": 0.92,
      "ambiguous": false,
      "oic_codes": ["OIC-001-01-A"],
      "rationale": "..."
    }
  ]
}
```

Le parseur ignore les identifiants inconnus, les rangs autres que `A`/`B`, les
confiances hors `[0, 1]`, les réponses ambiguës et les résultats sous `0,85`.
Ces réponses restent toutefois enregistrées dans le job pour permettre leur
lecture admin et leur relance.

## Persistance et transitions

`uness_rank_inference_jobs` contient une ligne par question :

- identité : `question_id`, `item_number`, `annale_id` ;
- état : `pending`, `running`, `retry_wait`, `needs_oic`, `needs_admin`,
  `approved`, `rejected`, `failed` ;
- verrou : `locked_at`, `worker_id` ;
- tentative : `attempts`, `next_retry_at`, `last_error` ;
- réponse : rang, confiance, ambiguïté, OIC cités, justification et JSON brut ;
- décision : rang admin, raison admin, auteur logique `admin`, date de décision ;
- dates `created_at` et `updated_at`.

`uness_rank_inference_events` conserve chaque transition et son payload
redacté. Les erreurs Gemini ne doivent jamais contenir de clé API ni d’URL
signée.

Le job est idempotent : un scan répété ne crée pas de doublon, un worker ne peut
pas réclamer un job déjà verrouillé, et un résultat accepté ne relance pas
Gemini. Les verrous expirés sont récupérables au cycle suivant. Les erreurs
réseau sont réessayées sur trois cycles avec un délai croissant ; un bouton
admin peut réarmer un job épuisé.

Lorsqu’une décision résout le rang, le service met à jour uniquement les
métadonnées `uness.question.rank*` de `ai_practice_questions`, sans modifier
l’énoncé, les propositions ni la correction officielle. L’événement conserve
le précédent et le nouveau payload. Le lecteur et le moteur de validité Rang A
continuent de passer par ces métadonnées et `rank_service`.

## API et interface admin

Les endpoints protégés par la convention admin locale existante sont :

- `GET /api/qcm/admin/rank-jobs?status=...` : compteurs et jobs paginés ;
- `POST /api/qcm/admin/rank-jobs/scan` : détecte les candidates sans appel IA ;
- `POST /api/qcm/admin/rank-jobs/{id}/retry` : réarme un job ;
- `POST /api/qcm/admin/rank-jobs/{id}/accept` : accepte le rang Gemini ;
- `POST /api/qcm/admin/rank-jobs/{id}/decide` : applique `A` ou `B` avec raison ;
- `POST /api/qcm/admin/rank-jobs/{id}/reject` : conserve la question sans rang.

Le panneau NiceGUI est ajouté aux réglages, sous une section « Rangs UNESS » :

- KPI `à traiter`, `en cours`, `sans OIC`, `incertains`, `résolus` ;
- filtre par état, item et annale ;
- aperçu question/OIC/réponse Gemini/confiance/justification ;
- boutons accepter, choisir A, choisir B, rejeter et relancer ;
- rafraîchissement après chaque action et indication du dernier passage worker.

L’écran n’expose jamais le rang comme officiel : le badge affiche la source
`Gemini`, `Admin` ou `Officiel`.

## Tests et critères d’acceptation

- Le parseur Gemini accepte uniquement le contrat prévu et rejette les réponses
  ambiguës, hors seuil ou étrangères au lot.
- Le scanner ne crée aucun job pour une question déjà officiellement classée et
  déduplique les questions sans rang.
- Un item sans OIC produit `needs_oic` sans appel Gemini.
- Le worker reprend un job verrouillé expiré et ne double pas un appel actif.
- Une erreur Gemini devient réessayable sans bloquer les autres jobs.
- Accepter une inférence écrit `rank_source=gemini`, la confiance, les OIC et la
  justification ; une décision manuelle écrit `rank_source=admin` et sa raison.
- Une décision manuelle contradictoire avec une inférence fiable est conservée
  comme alternative selon `resolve_rank`.
- Les endpoints refusent les identifiants inconnus et les rangs invalides.
- Le panneau admin reflète les statuts et n’affiche pas de question non ciblée.

## Hors périmètre de ce chantier

Le versionnage complet des résultats d’épreuve, la composition d’épreuves
officielles, les sauvegardes chiffrées et les cinq dashboards restent des
chantiers séparés de l’audit.
