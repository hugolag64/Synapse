# Import UNESS et conférences — feuille de route Gemini Batch

> **Pour les agents de développement :** ce document décrit une cible d’implémentation. Il ne
> constitue pas une modification de code réalisée dans le cadre de sa rédaction.

**Objectif :** mettre en place un traitement Gemini Batch traçable et peu coûteux pour les
imports d’annales UNESS et l’analyse des conférences, tout en conservant un traitement
synchrone pour la création interactive de QCM.

**Architecture :** les données UNESS sont d’abord aspirées et normalisées localement. Les
éléments officiels présents — réponses, items et rangs — sont conservés comme source de vérité.
Les éléments manquants sont placés dans des requêtes Batch Gemini distinctes, puis réinjectés
avec une provenance, une confiance et un statut de validation. Les résultats d’analyse de
conférence sont stockés comme enrichissements pédagogiques liés aux questions, sans écraser la
correction officielle.

**Stack :** Python 3.11, `requests`, SQLite local, Loguru, Gemini Developer API REST,
`generateContent`, Gemini Batch API, traitements de fond Synapse.

**Spécification source :** `docs/NOTE_CONFÉRENCES_DFASM_UNESS.md`.

## Contraintes globales

- Cette feuille de route ne demande aucune modification de code immédiate.
- Le mode Batch est obligatoire pour les traitements d’import UNESS et d’analyse de conférence.
- La création interactive de QCM reste hors Batch et utilise `generateContent` standard.
- Une donnée officielle UNESS ne peut jamais être écrasée par Gemini.
- Une inférence Gemini doit conserver le modèle, la version du prompt, la confiance, les
  éléments de preuve, la date et le statut de validation.
- Les fichiers audio, captures et réponses brutes ne doivent pas être écrits dans les logs
  applicatifs ni dans `ai_usage_logs`.
- Les clés API, cookies UNESS, URLs signées et tokens d’accès ne doivent apparaître ni dans les
  prompts persistés ni dans les logs.
- Le coût affiché doit être calculé à partir du vrai nom de modèle et du vrai mode de facturation,
  jamais à partir d’un tarif générique `flash` ou `flash_lite`.
- Les résultats Batch sont asynchrones : l’interface doit afficher `en attente`, `en cours`,
  `terminé`, `partiel`, `à valider` ou `échec`.
- Une relance doit être idempotente : elle ne doit pas créer un doublon si le même artefact,
  prompt, modèle et mode ont déjà produit un résultat exploitable.

---

## 1. Périmètre fonctionnel exact

### 1.1 Import d’une annale UNESS — Batch obligatoire

Le flux cible est :

```text
UNESS ouvert par l’utilisateur
    ↓
aspiration HTML + images + métadonnées locales
    ↓
normalisation déterministe des questions
    ↓
conservation des items/rangs officiellement présents
    ↓
Batch Gemini pour les corrections et médias nécessaires
    ↓
Batch Gemini pour les items absents
    ↓
Batch Gemini pour les rangs absents, après résolution des items
    ↓
validation des contrats et déduplication
    ↓
import dans la BDD QCM avec item, rang et provenance
```

Règles précises :

1. Une question UNESS dont `item_numbers` est présent dans la source conserve ces items avec
   `item_classification_source = official`.
2. Une question UNESS sans item ne doit pas être abandonnée et ne doit pas recevoir uniquement
   l’item global de la session par défaut.
3. Pour chaque question sans item, créer une requête d’identification Batch bornée par les items
   candidats de la matière/collège.
4. Gemini doit renvoyer uniquement des numéros d’items présents dans la liste de candidats,
   avec `confident`, `confidence`, `rationale` et éventuellement plusieurs items.
5. Une sortie ambiguë, hors référentiel ou sous le seuil de confiance passe en `needs_admin` et
   ne modifie pas l’item canonique.
6. Une question avec item connu mais sans rang officiel entre dans une seconde phase Batch de
   classification du rang.
7. La classification de rang réutilise les OIC disponibles pour l’item et renvoie `A`, `B` ou
   `null`, avec confiance, ambiguïté, codes OIC et justification.
8. Le rang officiel UNESS est toujours prioritaire sur Gemini, même si Gemini propose une autre
   valeur avec une forte confiance.
9. Les corrections Gemini et les explications IA sont des enrichissements. Elles ne remplacent
   pas les réponses officielles aspirées.
10. Une question avec image requise mais image absente reste conservée et reçoit un statut
    explicite `unsupported` ou `pending_human_validation` ; elle ne doit pas être corrigée à
    l’aveugle.

### 1.2 Analyse d’une conférence associée à une annale — Batch obligatoire

Entrées attendues :

- un identifiant d’annale ou de session UNESS déjà importé ou en cours d’import ;
- un fichier audio local de la conférence/correction ;
- zéro, une ou plusieurs captures d’écran ;
- le snapshot des questions UNESS concernées fourni par Synapse ;
- les items et rangs déjà connus à la date de soumission.

Le Batch doit produire un JSON structuré contenant au minimum :

- un résumé pédagogique de l’audio ;
- les notions, mécanismes, pièges et corrections explicitement abordés ;
- pour chaque question concernée, les passages de conférence associés ;
- des explications complémentaires reliées aux propositions ;
- les captures utilisées pour chaque question ;
- des timestamps ou plages temporelles lorsque le format audio le permet ;
- la confiance de chaque relation conférence ↔ question ;
- les éléments qui contredisent ou complètent la correction UNESS, sans les appliquer
  automatiquement.

La réponse doit être stockée comme une analyse versionnée liée à la conférence, l’annale, la
session QCM et les questions. La réexécution d’une analyse crée une nouvelle version et ne
détruit pas l’ancienne.

### 1.3 Création interactive de QCM — Batch interdit

Le parcours de création de QCM doit rester synchrone :

- appel `generateContent` standard ;
- réponse affichée immédiatement ;
- modèle configurable par difficulté ;
- journalisation normale des tokens et du coût ;
- aucun `batch_job_id` et aucune attente sur la file Batch.

Cette règle concerne notamment `AITask.QCM`. Elle ne doit pas être contournée parce qu’un
prompt contient des images ou un contexte volumineux.

---

## 2. Contrats de données à introduire

### 2.1 Table `ai_batch_jobs`

Créer une migration SQLite idempotente avec les colonnes suivantes :

| Colonne | Rôle |
|---|---|
| `id` | Identifiant local du job |
| `provider` | `gemini` |
| `provider_job_name` | Identifiant renvoyé par l’API Batch |
| `task` | `uness_import`, `uness_item_classification`, `uness_rank_inference`, `conference_analysis` |
| `model_id` | Nom exact, par exemple `gemini-3.5-flash-lite` |
| `billing_mode` | `batch` |
| `status` | `pending`, `submitted`, `running`, `succeeded`, `partial`, `needs_admin`, `failed`, `cancelled`, `expired` |
| `source_type` | `uness_annale` ou `conference` |
| `source_id` | `annale_id`, `session_id` ou identifiant de conférence |
| `request_count` | Nombre de requêtes dans le lot |
| `prompt_version` | Version immuable du contrat envoyé |
| `idempotency_key` | Empreinte artefact + requêtes + modèle + prompt |
| `submitted_at` | Date d’envoi |
| `completed_at` | Date de fin connue |
| `last_polled_at` | Dernière vérification distante |
| `next_poll_at` | Prochaine vérification prévue |
| `result_path` | Fichier JSONL local du résultat, sans audio intégré |
| `last_error` | Erreur redacted et bornée |
| `created_at` | Date de création |
| `updated_at` | Date de mise à jour |

Créer des index sur `(status, next_poll_at)`, `(source_type, source_id)` et
`(idempotency_key)`.

### 2.2 Table `ai_batch_requests`

Une ligne par requête logique du Batch :

| Colonne | Rôle |
|---|---|
| `id` | Identifiant local |
| `batch_job_id` | Relation vers `ai_batch_jobs` |
| `request_key` | Identifiant stable de question/conférence |
| `task` | Sous-tâche exacte |
| `question_id` | Question QCM concernée, nullable pour la synthèse globale |
| `item_number` | Item connu au moment de l’envoi, nullable si classification d’item |
| `status` | `pending`, `succeeded`, `needs_admin`, `failed` |
| `result_json` | Résultat JSON redacted et validé |
| `error` | Erreur redacted |
| `created_at` | Date de création |
| `updated_at` | Date de mise à jour |

Le payload complet ne doit pas être stocké en SQLite. Conserver uniquement un hash, les
identifiants nécessaires et le résultat contractuel.

### 2.3 Extensions de `ai_usage_logs`

Ajouter par migration les champs suivants :

- `provider_model` : modèle exact demandé ;
- `execution_mode` : `standard` ou `batch` ;
- `batch_job_id` : relation locale nullable ;
- `batch_request_id` : relation locale nullable ;
- `input_audio_tokens` ;
- `input_text_image_tokens` ;
- `thoughts_tokens` ;
- `total_tokens` ;
- `pricing_version` ;
- `usage_status` : `submitted`, `completed`, `failed` ;
- `estimated_cost_usd` ;
- `actual_cost_usd`.

Règle anti-double comptage : la soumission Batch peut être loguée avec `usage_status =
submitted` et zéro coût, mais seul le log `completed` avec les vrais `usageMetadata` entre dans
les agrégats de coût.

---

## 3. Tarification et télémétrie

### 3.1 Registre de prix

Remplacer la grille actuelle indexée uniquement par `FLASH`/`FLASH_LITE` par un registre indexé
par le nom exact du modèle et le mode de facturation.

Chaque entrée doit pouvoir distinguer :

- input texte/image ;
- input audio ;
- output texte, incluant les tokens de réflexion lorsqu’ils sont facturés ;
- tarif standard ;
- tarif Batch ;
- date d’effet ;
- URL de la source tarifaire.

Modèles de test documentés pour la première conférence :

- `gemini-3.5-flash-lite` pour l’analyse multimodale économique ;
- `gemini-3.5-flash` pour les cas nécessitant davantage de raisonnement ;
- `gemini-3.1-flash-lite` uniquement si explicitement choisi par la configuration.

Le nom du modèle configuré doit être enregistré dans chaque log. Aucun calcul ne doit déduire
le tarif à partir d’un simple alias interne.

### 3.2 Calcul du coût

Appliquer la formule :

```text
coût = input_audio_tokens × tarif_audio
     + input_text_image_tokens × tarif_texte_image
     + (output_tokens + thoughts_tokens facturés) × tarif_sortie
```

Pour Batch, utiliser les tarifs Batch du modèle exact. Si le fournisseur ne renvoie pas une
ventilation par modalité, conserver le total fournisseur, marquer la ventilation comme estimée
et ne pas la présenter comme une mesure exacte.

Le journal doit permettre de répondre à ces questions sans recalcul manuel :

- combien a coûté une annale complète ;
- combien a coûté la correction visuelle ;
- combien a coûté la résolution des items ;
- combien a coûté l’inférence des rangs ;
- combien a coûté l’analyse de chaque conférence ;
- quelle part du coût vient des relances ou échecs.

---

## 4. Flux Batch UNESS détaillé

### Phase A — capture et préparation

- Vérifier que la collecte est effectuée depuis une session UNESS ouverte par l’utilisateur.
- Stocker l’artefact HTML brut, les métadonnées et les images dans le dossier local de collecte.
- Calculer un hash de chaque artefact et de chaque image.
- Normaliser les questions, propositions, types, réponses officielles et rangs présents.
- Refuser les données sensibles avant toute soumission Gemini.
- Construire un snapshot immuable de l’annale envoyé au Batch.

### Phase B — correction et médias

- Créer une requête par quiz ou unité de correction suffisamment petite pour isoler les erreurs.
- Envoyer les images réellement nécessaires à la question concernée.
- Préserver les identifiants UNESS de questions et propositions dans la requête et la réponse.
- Valider que Gemini n’a ni supprimé ni ajouté de question.
- Marquer les sorties visuelles comme nécessitant une validation humaine lorsque le support est
  incomplet, ambigu ou uniquement interprété par l’IA.

### Phase C — résolution des items absents

- Exécuter après normalisation et avant la file de rangs.
- Une requête logique correspond à une question sans item officiel.
- Fournir au modèle la matière/collège, l’énoncé, les propositions, le contexte DP et la liste
  fermée des candidats.
- Interdire l’invention de numéros d’items.
- Accepter au maximum deux items par question, sauf règle métier explicitement documentée.
- Enregistrer `official`, `gemini` ou `needs_admin` comme source de classification.
- Réexécuter uniquement les questions non résolues ou explicitement relancées.

### Phase D — résolution des rangs absents

- Scanner les questions importées dont le rang n’est pas officiellement `A` ou `B`.
- Ignorer les questions sans item résolu ; elles restent dans la file `needs_item`.
- Grouper les questions par item pour partager les OIC et réduire le nombre de requêtes.
- Fournir les OIC disponibles et leurs rangs comme contexte de référence.
- Accepter seulement `A`, `B` ou `null` avec confiance et justification.
- Appliquer le seuil existant d’inférence et conserver les cas ambigus pour validation humaine.
- Ne jamais remplacer un rang officiel.

### Phase E — import final

- Importer dans la BDD QCM uniquement les questions dont le contrat structurel est valide.
- Conserver les données officielles et les enrichissements IA dans des champs séparés.
- Lier chaque question aux items canoniques résolus.
- Conserver le rang et sa provenance au niveau de la question et de la tentative si le schéma le
  prévoit.
- Dédupliquer sur l’empreinte de la question sans supprimer les provenances distinctes.
- Déclencher la maîtrise uniquement selon les règles déjà validées du moteur QCM.

---

## 5. Flux Batch conférence détaillé

### Préparation

- L’utilisateur associe un fichier audio et des captures à une annale/session UNESS.
- Synapse récupère le snapshot des questions, propositions, items, rangs et corrections.
- Les données officielles sont marquées comme `source_uness_official` dans le contexte fourni.
- Le fichier audio est transmis via le mécanisme de fichier Gemini adapté à sa taille ; éviter
  l’inclusion Base64 dans une requête trop volumineuse.

### Requête

- Utiliser une requête globale par conférence lorsque le volume tient dans la fenêtre de contexte.
- Inclure l’audio une seule fois pour éviter de payer plusieurs fois le même contenu.
- Inclure uniquement les captures liées aux questions concernées.
- Demander une réponse JSON avec identifiants de questions stables.
- Interdire toute modification automatique de la réponse officielle, du rang officiel ou de
  l’item officiel.

### Résultat

- Vérifier que toutes les questions attendues sont présentes ou explicitement marquées sans
  relation.
- Stocker le résumé global dans l’analyse de conférence.
- Stocker les enrichissements par question avec confiance et extraits/timestamps.
- Envoyer les relations faibles ou contradictoires dans une file de validation humaine.
- Autoriser une nouvelle version de l’analyse sans écraser la version précédente.

---

## 6. Exécution en arrière-plan

Le worker de fond doit :

1. soumettre les jobs `pending` respectant leur clé d’idempotence ;
2. interroger les jobs `submitted` et `running` dont `next_poll_at` est arrivé ;
3. télécharger et stocker le résultat JSONL d’un job terminé ;
4. valider chaque réponse avant persistance métier ;
5. passer le job en `succeeded`, `partial` ou `needs_admin` ;
6. écrire les usages réels et coûts après réception des métadonnées ;
7. relancer les erreurs transitoires avec backoff borné ;
8. ne pas relancer un job déjà terminé avec succès ;
9. laisser une erreur permanente visible et actionnable.

La boucle ne doit jamais attendre activement plusieurs minutes dans le thread de l’interface.
Le polling doit être borné à quelques jobs par cycle et s’exécuter hors de la boucle NiceGUI.

---

## 7. Déclenchement du premier test

La première version peut être déclenchée par une commande locale dédiée, sans attendre la
création d’un écran complet :

```text
python scripts/analyze_uness_conference.py \
  --annale-id 123 \
  --audio "C:\\chemin\\correction.mp3" \
  --screenshots "C:\\chemin\\captures" \
  --model gemini-3.5-flash-lite
```

La commande doit :

- vérifier que l’annale existe ;
- vérifier que les questions sont importées ou signaler les données manquantes ;
- afficher l’ID local du job et l’ID Gemini Batch ;
- ne pas attendre la fin du traitement ;
- permettre ensuite de consulter le statut et le coût depuis la télémétrie existante.

Une commande de consultation doit permettre de retrouver un job par annale, conférence ou
identifiant Batch.

---

## 8. Découpage d’implémentation pour Claude Code

### Tâche 1 — Contrats et tests de télémétrie

**Fichiers :**

- Modifier : `backend/core/ai/routing.py`
- Modifier : `backend/core/ai/logger.py`
- Modifier : `backend/core/reviews/local_store.py`
- Tester : `tests/test_ai_telemetry.py`

**Livrable :** calcul exact par modèle/mode, enregistrement des tokens de réflexion et absence
de double comptage Batch.

### Tâche 2 — Migration SQLite des jobs Batch

**Fichiers :**

- Modifier : `backend/core/reviews/local_store.py`
- Créer : `tests/test_ai_batch_store.py`

**Livrable :** création, recherche, idempotence, transition d’état, verrouillage, retry et
persistance des résultats sans stocker les médias bruts en base.

### Tâche 3 — Transport Gemini multimodal et Batch

**Fichiers :**

- Modifier : `backend/core/ai/gemini_client.py`
- Modifier : `backend/core/ai/service.py`
- Créer : `backend/core/ai/batch_client.py`
- Tester : `tests/test_gemini_client.py`
- Créer : `tests/test_gemini_batch_client.py`

**Livrable :** upload audio, requêtes multimodales, création de job Batch, polling, récupération
JSONL, redaction des secrets et extraction des métadonnées d’usage.

### Tâche 4 — Import UNESS avec item puis rang

**Fichiers :**

- Modifier : `backend/core/uness/import_service.py`
- Modifier : `backend/core/uness/question_item_classifier.py`
- Modifier : `backend/core/uness/rank_job_runner.py`
- Modifier : `backend/core/uness/rank_inference.py`
- Tester : `tests/test_uness_import.py`
- Tester : `tests/test_ednpro_pipeline.py` pour les non-régressions

**Livrable :** items officiels conservés, items absents résolus par question, rangs traités
ensuite, données officielles protégées, cas sans confiance envoyés à l’administration.

### Tâche 5 — Worker d’application des résultats Batch UNESS

**Fichiers :**

- Créer : `backend/core/uness/batch_import.py`
- Modifier : `backend/core/background.py`
- Tester : `tests/test_uness_batch_import.py`

**Livrable :** pipeline idempotent correction → item → rang → import final, avec reprise après
redémarrage et erreurs isolées par requête.

### Tâche 6 — Analyse Batch des conférences

**Fichiers :**

- Créer : `backend/core/conferences/models.py`
- Créer : `backend/core/conferences/batch_analysis.py`
- Créer : `scripts/analyze_uness_conference.py`
- Tester : `tests/test_conference_batch_analysis.py`

**Livrable :** association audio/captures/annale, snapshot QCM, réponse JSON versionnée,
relations question ↔ conférence et statut de validation humaine.

### Tâche 7 — Protection du parcours de création QCM

**Fichiers :**

- Modifier si nécessaire : `backend/core/ai/tasks.py`
- Modifier si nécessaire : `backend/core/ai/service.py`
- Tester : `tests/test_ai_tasks.py`
- Tester : `tests/test_ai_routing.py`

**Livrable :** `AITask.QCM` reste toujours synchrone, sans création de job Batch et sans
régression de la réponse immédiate.

### Tâche 8 — Observabilité et documentation utilisateur

**Fichiers :**

- Modifier : `frontend/pages/settings_cockpit.py`
- Modifier : `docs/NOTE_CONFÉRENCES_DFASM_UNESS.md`
- Tester : `tests/test_annales_page.py`

**Livrable :** affichage du modèle exact, mode standard/Batch, coût estimé/réel, statut des
jobs, annale concernée et nombre de questions traitées.

---

## 9. Critères d’acceptation finaux

- Une annale UNESS avec item et rang officiels les conserve sans appel IA pour ces deux champs.
- Une annale sans item crée des requêtes d’identification question par question en Batch.
- Une annale avec item connu mais rang absent crée ensuite des requêtes de rang en Batch.
- Une question sans item fiable reste importable mais apparaît comme `needs_item` ou
  `needs_admin`, jamais avec un item inventé.
- Une correction visuelle sans capture disponible n’est jamais présentée comme vérifiée.
- Une conférence peut être envoyée avec un audio, des captures et les QCM associés.
- L’audio n’est envoyé qu’une fois par requête globale de conférence lorsque le contexte le
  permet.
- Le résultat de conférence relie explicitement les notions aux identifiants de questions.
- La création d’un QCM utilisateur reste immédiate et ne produit aucun job Batch.
- Chaque résultat réussi contient les tokens, le modèle exact, le mode, le coût et la version
  tarifaire.
- Les sommes affichées par tâche, annale et conférence correspondent aux logs de complétion.
- Un redémarrage de Synapse reprend les jobs Batch sans doublonner les résultats.
- Les tests couvrent les transitions nominales, les erreurs, les relances, les sorties invalides,
  les données officielles prioritaires et le non-recours au Batch pour `AITask.QCM`.

## 10. Vérifications à exécuter avant toute mise en service

```text
pytest tests/test_ai_telemetry.py tests/test_ai_batch_store.py -q
pytest tests/test_gemini_client.py tests/test_gemini_batch_client.py -q
pytest tests/test_uness_import.py tests/test_uness_batch_import.py -q
pytest tests/test_conference_batch_analysis.py tests/test_ai_tasks.py tests/test_ai_routing.py -q
pytest -q
```

La première conférence doit être testée avec un artefact de faible durée et un petit nombre de
questions. Avant d’utiliser un enregistrement complet, vérifier :

- le statut Batch distant ;
- la présence des métadonnées d’usage ;
- le coût calculé ;
- l’absence de secret dans les logs ;
- la correspondance exacte des identifiants de questions ;
- la non-modification des items/rangs officiels ;
- l’absence de création de Batch lors d’une création interactive de QCM.
