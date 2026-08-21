# Conception — Analyse Batch des dossiers UNESS post-conférence (audio)

> **Pour les agents de développement :** ce document décrit une cible d'implémentation. Il ne
> constitue pas une modification de code réalisée dans le cadre de sa rédaction.

**Objectif :** une fois qu'une conférence DFASM1 est liée à son dossier UNESS et que
l'enregistrement audio de la conférence est disponible, déclencher automatiquement une analyse
Gemini Batch qui, pour chaque question du dossier, propose l'item EDN concerné, le rang (A/B) et
un avis de validité de la correction officielle éclairé par ce que le professeur a dit à l'oral —
sans jamais écraser les données officielles UNESS.

**Périmètre :** ce document couvre uniquement le flux post-conférence (audio → analyse). Il ne
touche ni à l'aspiration des dossiers UNESS (bot Playwright existant, inchangé), ni au lien
conférence ↔ dossier UNESS (déjà implémenté), ni à l'import général des annales UNESS hors
conférence. La conversion de l'import général vers Gemini Batch reste hors périmètre et est
seulement esquissée dans `docs/superpowers/plans/2026-08-20-uness-conferences-gemini-batch.md`
(document de référence, non encore implémenté), dont ce chantier reprend les contraintes mais
n'implémente qu'une tranche verticale scopée aux conférences.

**Spécification source :** `docs/NOTE_CONFÉRENCES_DFASM_UNESS.md`, section « Enregistrement et
analyse de la conférence » et « Décision d'exécution Gemini ».

## Contraintes globales

- Aucune modification de l'aspiration existante : le dossier UNESS reste collecté par
  `scripts/uness/collector.py` (bot Playwright), déclenché manuellement comme aujourd'hui, puis
  importé via le scan des JSON vérifiés (`import_service.py`). Ce chantier suppose que le dossier
  est déjà importé dans `uness_annales` avant que l'analyse conférence ne démarre.
- Le lien conférence ↔ dossier (`conferences.uness_session_id`) reste confirmé manuellement via
  le panneau « Dossier UNESS à confirmer » existant. Rien ne change à ce mécanisme.
- L'analyse conférence utilise obligatoirement l'API Gemini Batch (traitement différé, moins
  cher), jamais `generateContent` synchrone.
- Une donnée officielle UNESS (`reponse_uness`, rang officiel s'il existe) ne peut jamais être
  écrasée par un résultat Gemini, qu'il vienne de l'import ou de l'analyse conférence.
- Le résultat de l'analyse conférence (item, rang, validité) est un enrichissement consultable.
  Il ne modifie jamais automatiquement `UnessProposition.statut` ni `reponse_finale`. Seule une
  validation manuelle de l'utilisateur (mécanisme `valide_manuellement` /
  `validation_utilisateur` déjà existant) peut faire passer une information de l'analyse
  conférence vers la vérification officielle.
- Les informations issues de la conférence, de l'UNESS et de l'IA d'import restent distinguables
  à l'affichage et en base : l'analyse conférence est stockée dans des tables séparées, jamais
  fusionnée avec `verdict_ia` / `confiance_ia` (champs déjà utilisés par la vérification IA de
  l'import, à ne pas réutiliser pour l'audio).
- Le fichier audio et son contenu ne doivent jamais apparaître dans les logs applicatifs ni dans
  `ai_usage_logs` — seul le chemin local est conservé.
- Une resoumission est idempotente : même conférence, même dossier, même audio (hash identique),
  même modèle et même version de prompt ne créent pas de second job tant qu'un résultat
  exploitable existe déjà.

---

## 1. Déclenchement

Le job d'analyse se déclenche automatiquement, sans bouton, dès que les deux conditions
suivantes sont réunies pour une conférence :

1. `conferences.uness_session_id` est renseigné (dossier confirmé) ;
2. `conferences.audio_path` est renseigné (audio uploadé et validé).

Un worker de fond (même cadence/mécanisme que `rank_job_runner.py`) scanne périodiquement les
conférences éligibles sans job `succeeded`/`submitted`/`running` en cours et crée une ligne
`conference_analysis_jobs` en statut `pending`, avec une `idempotency_key` = empreinte de
`(conference_id, uness_session_id, audio_hash, model_id, prompt_version)`.

Une relance manuelle reste possible uniquement sur un job `failed` ou `needs_admin`, via un
bouton « Relancer l'analyse » dans le panneau conférence. Elle crée une nouvelle ligne de job
(le job précédent n'est jamais muté), ce qui préserve l'historique.

## 2. Upload audio

Ajouté sur la ligne de conférence déjà liée à un dossier, dans
`frontend/components/conferences_admin.py` :

- sélection d'un fichier local (mp3, m4a ou wav) ;
- validation du format et d'une taille maximale raisonnable avant écriture sur disque ;
- stockage dans `data/conferences/audio/{conference_id}.{ext}` ;
- calcul et enregistrement d'un hash du fichier (`audio_hash`) pour l'idempotence et pour
  détecter un ré-upload (nouveau hash → nouveau job possible même si un job précédent a déjà
  réussi, car l'utilisateur a peut-être corrigé le fichier) ;
- rejet explicite (message clair, rien n'est stocké) si le fichier est corrompu, vide ou d'un
  format non supporté.

## 3. Contenu de la requête Batch

Une requête globale par conférence (audio inclus une seule fois, si le volume tient dans la
fenêtre de contexte du modèle ; sinon, cette limite doit être détectée et le job passe en
`failed` avec un message explicite plutôt que de tronquer silencieusement le contenu) :

- le fichier audio, transmis via le mécanisme de fichier Gemini adapté à sa taille ;
- le snapshot des questions du dossier : énoncé, propositions, réponse officielle UNESS quand
  elle existe, item et rang officiels quand ils existent ;
- pour les questions sans item officiel : la liste fermée des items candidats du collège associé
  à la conférence (même logique de bornage que `question_item_classifier.py`) ;
- pour les questions avec item connu mais sans rang officiel : les OIC disponibles pour cet item
  et leurs rangs (même logique que `rank_inference.py`) ;
- consigne explicite : ne jamais proposer un item hors de la liste candidate, ne jamais modifier
  un item ou un rang déjà officiel, et motiver l'avis de validité de la correction avec les
  passages audio correspondants.

Réponse JSON attendue, par question :

- item(s) proposé(s) si absent, avec confiance et justification (au plus deux items, comme la
  règle déjà en vigueur pour l'import) ;
- rang proposé si absent (`A`, `B` ou `null`), avec confiance et justification ;
- verdict de validité de la correction officielle : `concordant`, `desaccord` ou `incertain`,
  avec confiance, justification et extrait/plage temporelle de l'audio ;

Plus un résumé pédagogique global de la conférence (notions, mécanismes, pièges).

## 4. Application du résultat

À la réception d'un résultat Batch validé contre son contrat :

- **Item manquant** : écrit dans les champs item existants de la question (`UnessQuestion`),
  avec `item_classification_source = gemini_conference`. Sous le seuil de confiance ou item hors
  liste candidate → statut `needs_item`/`needs_admin`, aucune valeur inventée, comportement
  identique à la règle déjà en vigueur pour l'import.
- **Rang manquant** : même principe, écrit uniquement si l'item est résolu et le rang absent,
  jamais si un rang officiel existe déjà.
- **Validité de la correction** : jamais écrite dans `verdict_ia`/`confiance_ia`/`explication_ia`
  (champs de la vérification IA d'import). Stockée dans une nouvelle table
  `conference_question_analysis`, consultable séparément, sans effet automatique sur
  `UnessProposition.statut` ni `reponse_finale`.
- **Résumé global** : nouvelle ligne dans `conference_analyses` (append-only, versionné — une
  réexécution n'écrase jamais une analyse précédente, la plus récente est affichée par défaut).

Le job passe en `succeeded` si toutes les questions ont un résultat exploitable, `partial` si une
partie seulement, `needs_admin` si le contrat est respecté mais qu'au moins un point nécessite
une validation humaine avant d'être exploitable, `failed` en cas d'erreur non transitoire.

## 5. Modèle de données (nouveau)

### `conferences` — colonnes ajoutées

| Colonne | Rôle |
|---|---|
| `audio_path` | Chemin local du fichier audio, nullable |
| `audio_uploaded_at` | Date d'upload, nullable |
| `audio_hash` | Empreinte du fichier, pour idempotence et détection de ré-upload |

### `conference_analysis_jobs`

| Colonne | Rôle |
|---|---|
| `id` | Identifiant local |
| `conference_id` | Référence `conferences.id` |
| `uness_session_id` | Référence `uness_annales.id` (dénormalisé depuis la conférence au moment de la création, pour garder trace même si le lien change ensuite) |
| `status` | `pending`, `submitted`, `running`, `succeeded`, `partial`, `needs_admin`, `failed` |
| `model_id` | Nom exact du modèle utilisé |
| `provider_job_name` | Identifiant renvoyé par l'API Batch Gemini |
| `idempotency_key` | Empreinte conférence + dossier + audio + modèle + prompt |
| `prompt_version` | Version immuable du contrat envoyé |
| `submitted_at` / `completed_at` / `last_polled_at` / `next_poll_at` | Suivi du cycle de vie |
| `result_path` | Fichier JSONL local du résultat (sans audio intégré) |
| `last_error` | Erreur redacted et bornée |
| `created_at` / `updated_at` | Horodatage |

Index sur `(status, next_poll_at)`, `(conference_id)`, `(idempotency_key)`.

### `conference_analyses`

| Colonne | Rôle |
|---|---|
| `id` | Identifiant local |
| `conference_id` / `uness_session_id` | Références |
| `batch_job_id` | Référence `conference_analysis_jobs.id` |
| `model_id` / `prompt_version` | Traçabilité |
| `summary_text` | Résumé pédagogique global |
| `created_at` | Horodatage — plusieurs lignes possibles par conférence, la plus récente fait foi à l'affichage |

### `conference_question_analysis`

| Colonne | Rôle |
|---|---|
| `id` | Identifiant local |
| `conference_analysis_id` | Référence `conference_analyses.id` |
| `question_id` | Question UNESS concernée |
| `verdict` | `concordant`, `desaccord`, `incertain` |
| `confidence` | Score de confiance |
| `rationale` | Justification |
| `transcript_excerpt` | Extrait ou plage temporelle de l'audio |
| `created_at` | Horodatage |

### `ai_usage_logs` — extension minimale

Ajout des colonnes strictement nécessaires pour ne pas fausser les coûts déjà suivis :
`provider_model`, `execution_mode` (`standard`/`batch`), `batch_job_id` (nullable, référence
`conference_analysis_jobs.id`). Le reste de l'extension plus large décrite dans le document de
référence Gemini Batch (tokens audio, tarification par modalité) n'est repris que si nécessaire
pour calculer un coût correct de ce job précis ; pas de sur-ingénierie du registre de prix
générique dans ce chantier.

## 6. Worker de fond

Étend le pattern déjà en place (`rank_job_runner.py`, boucle dans `background.py`) :

1. scanner les conférences éligibles (audio + dossier liés, pas de job actif) et créer les jobs
   `pending` ;
2. soumettre les jobs `pending` en respectant leur clé d'idempotence ;
3. interroger les jobs `submitted`/`running` dont `next_poll_at` est arrivé ;
4. télécharger et valider le résultat JSONL d'un job terminé ;
5. appliquer le résultat selon les règles de la section 4, puis passer le job en `succeeded`,
   `partial` ou `needs_admin` ;
6. écrire les usages réels/coûts après réception des métadonnées Gemini ;
7. relancer les erreurs transitoires avec un backoff borné, laisser une erreur permanente visible
   et actionnable (`failed` + `last_error`) sans retry automatique infini.

La boucle ne doit jamais bloquer le thread de l'interface NiceGUI.

## 7. Interface utilisateur

- `frontend/components/conferences_admin.py` : contrôle d'upload audio sur la ligne de
  conférence déjà liée à un dossier ; badge de statut du job (`en attente`, `en cours`,
  `terminé`, `partiel`, `à valider`, `échec`) ; bouton « Relancer l'analyse » visible uniquement
  sur `failed`/`needs_admin`.
- Nouveau panneau « Analyse conférence (IA) », affiché près de la révision du dossier UNESS
  (probablement dans `frontend/pages/annales.py` ou une vue détail de conférence à créer) :
  résumé pédagogique global, puis par question le verdict de validité, la confiance, la
  justification et l'extrait audio — visuellement distinct du panneau de vérification IA
  d'import existant, pour respecter l'exigence de provenance séparée.

## 8. Erreurs et garde-fous

- Item/rang hors liste candidate ou sous le seuil de confiance → `needs_admin`, jamais de valeur
  inventée, même règle que l'import existant.
- Échec de soumission ou de récupération Batch → job `failed`, aucune application partielle des
  résultats déjà reçus tant que le job entier n'est pas validé contre son contrat.
- Contenu audio trop volumineux pour la fenêtre de contexte → détecté explicitement, job `failed`
  avec message clair, pas de troncature silencieuse.
- Fichier audio corrompu ou format non supporté → rejeté à l'upload, rien n'est stocké.
- Clé d'idempotence → bloque toute resoumission tant qu'un résultat exploitable existe déjà pour
  la même empreinte ; un nouvel upload audio (hash différent) débloque une nouvelle analyse.
- Aucune donnée officielle (`reponse_uness`, item officiel, rang officiel) n'est jamais
  écrasée : vérifié par un contrat de validation avant toute écriture, comme
  `assert_verified_exam` le fait déjà pour l'import.
- Audio et contenu brut jamais loggés ; seuls chemin, hash et métadonnées d'usage Gemini
  (tokens, coût) sont conservés.

## 9. Tests

- `tests/test_conferences_audio_upload.py` : validation de format/taille, calcul et stockage du
  hash, détection d'éligibilité (audio + dossier liés → création de job).
- `tests/test_conference_batch_analysis.py` : validation du contrat de réponse Batch, respect de
  la priorité des données officielles, passage en `needs_admin` sur confiance basse ou item hors
  liste, non-écrasement d'un rang/item déjà officiel.
- `tests/test_conference_analysis_worker.py` : transitions d'état du job, idempotence, retry
  borné sur erreur transitoire, isolation d'un échec permanent.
- Non-régression : `tests/test_conferences_service.py` (ou équivalent existant pour le lien
  conférence ↔ dossier) et les tests d'import UNESS existants ne doivent pas changer de
  comportement.

## 10. Critères d'acceptation

- Un audio uploadé sur une conférence déjà liée à un dossier déclenche automatiquement un job
  d'analyse, sans action supplémentaire.
- Le job utilise l'API Gemini Batch, jamais `generateContent` synchrone.
- Une question avec item et rang officiels ne reçoit aucune proposition Gemini sur ces deux
  champs.
- Une question sans item reçoit une proposition bornée aux candidats du collège, jamais un item
  hors référentiel.
- Le verdict de validité de la correction est consultable, clairement distinct de la
  correction officielle et de la vérification IA d'import, et ne modifie jamais automatiquement
  le statut de la proposition.
- Un ré-upload audio (hash différent) permet une nouvelle analyse ; un ré-upload identique ne
  crée pas de doublon de job.
- La création interactive de QCM reste inchangée : aucun job Batch n'en découle.
- Un redémarrage de Synapse reprend les jobs en cours sans dupliquer de résultat.
