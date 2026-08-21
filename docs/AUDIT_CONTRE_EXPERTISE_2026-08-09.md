# Contre-audit — logique, algorithmes et IA

**Projet :** Synapse
**Date :** 9 août 2026
**Objet :** vérification indépendante de `AUDIT_LOGIQUE_ALGORITHMES_IA_2026-08-09.md`, avec confrontation systématique du code **et de la base réelle** (`data/synapse_local.db`).

---

## 0. Méthode et différence d'approche

L'audit initial lit le code et le compare aux captures d'écran. Il décrit correctement *ce que le code a l'intention de faire*.

Ce contre-audit ajoute une troisième source : **l'état réel de la base**. C'est ce qui change les conclusions. Plusieurs mécanismes décrits comme « fonctionnels mais à documenter » sont en réalité **inertes ou dégénérés en production**, et deux défauts majeurs ne figurent pas du tout dans l'audit initial.

Chiffres de référence (base au 9 août 2026) :

| Table | Lignes | Lecture |
|---|---:|---|
| `mastery_snapshots` (semaine W32) | 707 | dont **99 seulement** ont un score |
| `error_signals` | **0** | chaîne d'erreurs morte |
| `edn_recommendations` | **0** | recommandations mortes |
| `ai_practice_attempt_propositions` | **0** | correction propositionnelle jamais écrite |
| `ai_practice_attempts` | 30 | `score_mode` = `''` sur **100 %** des lignes |
| `oic_attempts` | 3 | pour 290 OIC LiSA chargés |
| `lisa_oic` (`mastered = 1`) | **0 / 290** | aucune couverture OIC acquise |
| `item_state` | 146 | `flou` 75, `correct` 71, **`solide` 0** |
| `ai_usage_logs` | 1358 | dont **608 écrites par les tests** |

---

## 1. Ce que l'audit initial établit correctement

Je confirme sans réserve, code à l'appui :

- **§4.1 / §4.2** — `colleges_cockpit.py:181` : `"pct": score if score is not None else (100 if started else 0)`. Le double sens de « Progression » est exact.
- **§6.2** — `forgetting_curve.py:21` définit `SCORE_FLOOR = 20` **jamais référencé** ailleurs, alors que `retention.py:8` impose `MASTERY_FLOOR = 25`. Divergence réelle, constante morte.
- **§16.1** — `service.py:37` appelle `model_for_task(task)` sans le paramètre `difficulty`. Le routage par difficulté (`routing.py:63`) est donc **inatteignable depuis `AIService`**. Confirmé.
- **§5.4** — la formule `w_seed = 1/(1+n)` et la critique « n ne mesure ni la diversité ni la qualité des preuves » sont justes.
- **§16.2** — troncature silencieuse à 12 000 caractères (`service.py:9`), sans journalisation de la longueur d'origine.

---

## 2. Corrections factuelles à apporter à l'audit initial

| § | Affirmation | Correction |
|---|---|---|
| 6.1 | « stabilité initiale : lecture 7 jours, QCM 21 jours » | Ce sont les **bases**, pas les stabilités initiales. `retention.py:78` : `initiale = base × (2 + qualité)`. Une lecture à q=0,5 démarre à **17,5 jours**, un QCM réussi à **63 jours**. Écart ×2,5 à ×3 par rapport au document. |
| 9.1 | « QRU : exact ou faux » | Vrai dans `compute_question_score_edn`, mais `score_closed_attempt` **ne passe jamais `question_kind`** (`scoring.py:68`). Tout est scoré en QRM. Un QRU raté vaut 0,2 pt au lieu de 0. |
| 9.1 | « indispensable absente → 0 » | `indispensable_choices` / `inacceptable_choices` ne sont **jamais transmis**. Ces pénalités absolues sont du code mort. |
| 11.2 | « `Item 93 · non_classe` est cohérent avec le fallback » | Ce n'est pas un fallback : c'est une **rupture de contrat de taxonomie** (cf. §3.2). Même alimentée, la chaîne produirait 100 % de `non_classe`. |
| 17 (tableau) | « Score QCM officiel : déterministe, validation non nécessaire » | Le moteur officiel n'est **pas branché** sur le parcours réel. La ligne devrait être « non appliqué ». |
| 19 P0 | « tracer le flux erreur QCM → point faible » | Le flux est déjà tracé ici : il est rompu en deux points identifiés. Ce n'est plus une investigation, c'est un correctif. |

---

## 3. Défauts critiques — non identifiés ou sous-évalués

### 3.1 🔴 L'échelle de maîtrise est dégénérée : aucun cours n'atteint « à consolider » ni « maîtrisé »

C'est le défaut le plus grave, et il est absent de l'audit initial.

Distribution réelle, semaine W32 (707 cours) :

```
à préparer   480      score = None
à lire       128      score = None
critique      51
fragile       48
à consolider   0   ←
en construction 0   ←
maîtrisé       0   ←
```

Distribution des 99 scores existants :

```
score 29 → 44 cours
score 49 → 47 cours
8 autres cours répartis sur 25/31/35/38/41/44/46
```

**91 des 99 scores sont des graines déclarées, pas des scores calculés.** Le chemin `mastery.py:133-141` retourne directement `decayed_seed()` et court-circuite tout le calcul composite.

Cause racine : `item_state` ne contient que `flou` (75) et `correct` (71), **zéro `solide`**. Or `level_from_seed` (`models.py:102`) mappe `<40 → critique`, `<60 → fragile`, `>=60 → à consolider`. Avec un plafond de graine à 50 (`correct`), **le niveau « à consolider » est mathématiquement inatteignable par cette voie**.

Conséquences :
- 8 niveaux définis, 4 utilisés, dont 2 pour 99 % des cours notés ;
- la couleur, le tri, les « collèges fragiles » et le « focus » reposent tous sur une variable qui ne prend que deux valeurs ;
- l'utilisateur voit un programme entièrement rouge/orange, ce qui détruit la valeur informative du signal.

### 3.2 🔴 La chaîne erreur → point faible est rompue en **deux** endroits indépendants

L'audit la classe « à vérifier ». Elle est morte, et je peux nommer les deux ruptures.

**Rupture 1 — le parcours réel contourne l'API.**
`_record_error_signals` n'est appelé que depuis `backend/api/qcm.py:201`. Or l'interface enregistre les réponses par un appel **direct** au store : `frontend/components/qcm_replay.py:460 → local_store.record_ai_practice_attempt(...)`. La route API n'est jamais empruntée.

Preuve empirique irréfutable : 30 `ai_practice_attempts`, **0** `ai_practice_attempt_propositions`, **0** `error_signals`. Les deux écritures qui suivent l'appel API (`replace_ai_practice_attempt_propositions` puis `_record_error_signals`) n'ont jamais eu lieu.

**Rupture 2 — les taxonomies ne coïncident pas.**
Même si la route API était utilisée, `qcm.py:52` écrit comme catégorie la valeur du champ `discordance`, qui vaut `omission` ou `exces` (`scoring.py:79`). Le consommateur `error_profile.py:36` n'accepte que `oubli, raisonnement, piege_edn, rang_a, rang_b, inattention, temps, non_classe` et rabat tout le reste sur `non_classe`.

**100 % des signaux atterriraient en `non_classe`.** C'est l'explication exacte de la capture `Item 93 · non_classe`, que l'audit initial n'attribue qu'au hasard des données.

`omission`/`exces` est une observation docimologique, pas une catégorie cognitive. Il manque une couche de traduction (une omission sur un OIC de Rang A → `rang_a` ; un excès sur un distracteur classique → `piege_edn` ; etc.).

### 3.3 🔴 Le barème docimologique officiel n'est pas appliqué

`scoring.py` implémente le barème R2C (1 / 0,5 / 0,2 / 0). Le parcours réel ne l'utilise pas :

```python
# qcm_replay.py:455-465
correct = _same_closed_answer(response, question.get("answer",""), ...)
score_percent = 100.0 if correct else 0.0
```

Preuve : `score_mode = ''` sur les 30 tentatives (le moteur officiel écrit `"edn"`).

Impact : une réponse à 1 discordance sur 5 propositions vaut **0 %** au lieu de 50 %. Tout ce qui consomme `score_percent` — maîtrise, rétention, `qcm_pass_rate`, seuil 14/20 — est faussé **à la baisse et de façon non linéaire**. C'est une cause directe du §3.1 (tout est critique/fragile).

Défaut secondaire dans le moteur lui-même : `scoring.py:78` attribue à *chaque proposition* le score de la *question* (`"points": score["score"]`). Une question à 0,5 pt donne 0,5 pt à chaque proposition juste. Sans signification.

### 3.4 🟠 Maîtrise et rétention ne sont pas seulement mal nommées : elles sont **la même variable**

L'audit recommande (§2, §19 P0) de séparer maîtrise et rétention. Il ne signale pas que le code les a déjà **fusionnées par écrasement** :

```python
# mastery.py:250-252
retention_snapshot = evaluate_retention(score, retention_evidence, today)
score = retention_snapshot.score   # ← le score de maîtrise EST la rétention décroissante
```

Trois conséquences mesurables :

1. **Plancher à 25 imposé au score de maîtrise.** `evaluate_retention` clampe à `MASTERY_FLOOR`. Aucun cours porteur de preuves ne peut descendre sous 25 : l'échelle annoncée 0-100 est en réalité 25-100, et la bande « critique » (25-39) est deux fois plus étroite que « fragile » (40-59).
2. **Régressions hebdomadaires fantômes.** Le score baisse mécaniquement chaque jour sans révision. Mesuré entre W31 et W32 : **10 cours « en régression », 0 « en progression »**, sans qu'aucune performance n'ait baissé. La bannière `_build_narrative` (`weekly_report.py:279`) affichera « ⚠ 10 cours en régression cette semaine » — un faux signal d'alarme récurrent, structurel.
3. On ne peut pas répondre à « ai-je progressé ? » puisque la seule variable disponible mélange apprentissage et écoulement du temps.

### 3.5 🟠 Le verrou Rang A punit l'absence de mesure

`mastery.py:258` protège du cas « pas de référentiel », mais pas du cas « référentiel chargé, jamais évalué » :

```python
if _has_rang_a_evidence:                       # = lisa_oic contient des OIC de rang A
    score_rang_a = score*0.5 + (couverture_A*100)*0.5
```

`_has_rang_a_evidence` teste `rang_a_total > 0` — c'est-à-dire **« le référentiel LiSA a été téléchargé »**, pas « l'étudiant a été évalué ». En base : 290 OIC chargés sur 20 cours, `mastered = 1` sur **0** d'entre eux, 3 tentatives OIC au total.

Donc pour ces 20 cours : `couverture_A = 0` → `score_rang_a = score / 2`.
Mécaniquement, **tout cours dont le score est < 80 devient « critique »** (`score_rang_a < 40`) et tout cours < 150 devient « fragile » (`< 75`), c'est-à-dire *tous*.

Vérifié en base sur ces 20 cours : 7 critiques, 8 fragiles, 0 au-dessus. Le nom de la variable ment sur son contenu ; renommer `_has_rang_a_evidence` en `_has_rang_a_referential` rendrait le bug visible à la lecture.

Correctif : conditionner à `count(oic_attempts) > 0` sur le cours, pas à la présence du référentiel.

### 3.6 🟠 `rank_gain_potential` : trois de ses six facteurs sont inertes

`trajectory.py:125-133` expose deux formules concurrentes :

```python
sans fréquence : score = 100 × (0,35·w + 0,35·gap + 0,20·err + 0,10·dispo)   # somme
avec fréquence : score = 100 × freq × gap × max(dispo,0,1) × max(w,0,1)      # produit
```

Vérification en base : les **367** lignes de `ednpro_item_frequency` ont toutes un `session_count` non nul (valeurs 0 à 15). **Tous les items empruntent donc la branche multiplicative** ; la branche additive est du code mort — et c'est pourtant elle que couvre `tests/test_edn_gain_priority.py`, qui teste un chemin jamais exécuté.

Trois conséquences dans la branche réellement active :

1. **`error_recurrence` n'apparaît pas dans la formule multiplicative.** Le nombre d'erreurs n'influence donc *jamais* le classement — indépendamment du fait que `error_signals` soit vide (§3.2). Double mort.
2. **`edn_weight` est une constante.** Les 367 items ont `priority = 'basique'`, donc `_EDN_PRIORITY_WEIGHTS` renvoie la même valeur (0,5) pour tous. Un facteur constant dans un produit ne change aucun ordre : le « poids EDN » annoncé en §7.2 de l'audit initial est décoratif.
3. **Les 32 items à `session_count = 0` obtiennent un score de exactement 0**, quel que soit leur déficit de maîtrise. Ils sont donc systématiquement relégués en fin de liste, puis départagés par ordre alphabétique d'`item_number` (`trajectory.py:147`). Un item mal maîtrisé mais jamais tombé à l'EDN devient invisible.

Le classement réel se réduit ainsi à `frequency × mastery_gap × availability` — trois facteurs sur six. Ce n'est pas nécessairement mauvais, mais ce n'est pas ce que l'interface et l'audit décrivent.

Correctif : une formule unique, avec `freq` comme cinquième terme additif (préserve les facteurs et évite les zéros absorbants), ou une moyenne géométrique `(freq·gap·dispo·w·err)^(1/5)` avec plancher sur chaque facteur.

### 3.7 🟠 La stabilité de rétention ignore l'espacement

`retention.py:81-90` — chaque preuve multiplie la stabilité par un facteur constant :

```python
growth = 1 + (base/60)·qualité      # QCM réussi : ×1,35
```

L'intervalle écoulé depuis la preuve précédente **n'intervient pas**. Dix QCM réussis le même jour multiplient la stabilité par 1,35¹⁰ ≈ **20**, exactement comme dix QCM espacés d'un mois. C'est la négation du principe d'espacement, alors que le module s'appelle « rétention » et que SM-2 tourne à côté.

Un garde-fou partiel existe pour les QCM (`mastery.py:401`, dédoublonnage par jour), mais **pas** pour les preuves `confidence`, ajoutées une par session sans dédoublonnage (`mastery.py:364`). Trois sessions le même jour → trois preuves.

Correctif : pondérer la croissance par `min(1, Δt / stabilité_courante)` — c'est le cœur de FSRS et de SM-2, déjà présent dans le projet.

### 3.8 🟡 SM-2 : une confiance « moyenne » est traitée comme un échec

`sm2.py:28` : `grade = confidence - 1`, puis `sm2.py:33` : `if grade < 3: # raté`.

Une confiance de **3/5** — le point neutre de l'échelle présentée à l'utilisateur — donne `grade = 2`, donc **échec** : `EF -0,2` et intervalle remis à 3 jours. Dans SM-2 canonique, le seuil de réussite est à 3 sur 0-5 ; ici il est remonté de fait à 4/5.

L'utilisateur qui répond honnêtement « moyen » voit son intervalle s'effondrer et sa maîtrise baisser. C'est une incitation à la sur-déclaration.

---

## 4. Audit IA — mesures réelles

L'audit initial (§16.5) propose de *mesurer* les performances IA. Ces mesures existent déjà : `ai_usage_logs`, 1358 lignes, 1er → 9 août.

### 4.1 Coût, latence et fiabilité par tâche

| Tâche | Modèle | Appels | Erreurs | Latence moy. | Coût $ | % coût |
|---|---|---:|---:|---:|---:|---:|
| `uness_correction_visual` | flash | 63 | **10 (16 %)** | **24,9 s** | 0,676 | **70 %** |
| `uness_correction` | flash_lite | 90 | 0 | 9,7 s | 0,130 | 13 % |
| `item_classification` | flash_lite | 505 | 0 | 1,9 s | 0,108 | 11 % |
| `item_classification` | **flash** | 38 | 0 | **13,7 s** | 0,014 | 1 % |
| `qcm` | flash_lite | 49 | 0 | 0,4 s | 0,011 | 1 % |
| `dp` | flash | 4 | 0 | 14,9 s | 0,020 | 2 % |

Lectures :

1. **La correction visuelle concentre tout le risque** : 5 % des appels, 70 % du coût, 16 % d'échec, 25 s de latence. C'est aussi la seule tâche qui exige une validation humaine (§16.1) — et ce gate est inerte (cf. mémoire projet, §7.5). Priorité IA n°1, loin devant l'optimisation des autres tâches.
2. **`item_classification` tourne sur deux modèles** (505 flash_lite + 38 flash) sans raison visible dans `routing.py`, qui la fixe à flash_lite. Les 38 appels flash coûtent 7× plus cher au token et sont 7× plus lents pour la même tâche. À tracer.
3. **Le prompt de classification est énorme** : 1,38 M tokens d'entrée pour 16 k de sortie sur 505 appels, soit **2 733 tokens d'entrée par classification** pour une réponse de 32 tokens. Ratio 85:1. C'est le premier gisement d'économie (mise en cache du contexte, ou réduction de la liste de candidats).
4. **Coût total réel : 0,97 $ sur 9 jours** (~3,3 $/mois au rythme actuel). Le coût n'est pas le problème ; la latence et le taux d'échec le sont.

### 4.2 🔴 La clé API Gemini fuit en clair dans la base et dans les logs

```
error = '429 Client Error: Too Many Requests for url:
https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key=AQ.Ab8RN6…'
```

7 lignes concernées dans `ai_usage_logs`, plus les mêmes chaînes dans `logs/ai_usage.log`.

Origine : `gemini_client.py:88` passe la clé en `params={"key": ...}` ; `requests` l'inclut dans l'URL, et `str(exc)` (`gemini_client.py:101`) la recopie telle quelle dans le log.

`data/` et `logs/` sont bien dans `.gitignore` (vérifié) — le risque immédiat est donc contenu. Il devient réel dès qu'une sauvegarde, un export de diagnostic ou un rapport de bug est partagé.

Correctifs, par ordre de solidité :
1. Passer la clé en **en-tête** `x-goog-api-key` plutôt qu'en paramètre d'URL ;
2. filtrer `str(exc)` par une regex `key=[^&\s]+` → `key=***` avant toute journalisation ;
3. purger les 7 lignes existantes.

### 4.3 🟠 45 % de la table `ai_usage_logs` est écrite par la suite de tests

608 lignes ont `duration_ms < 5` et des messages d'erreur factices (`network timeout` ×109, `Réponse Gemini vide` ×109, `temporary`), réparties du 1er au 9 août.

Les tests écrivent donc dans **`data/synapse_local.db`**, la base de production. Deux conséquences :
- toute analytique IA (taux d'erreur, latence, coût) est faussée : le « 44 % d'échec sur `gemini_generate`/flash » est entièrement artificiel ;
- plus grave, rien ne garantit que la pollution se limite à cette table.

Correctif : fixture `conftest.py` redirigeant `DB_PATH` vers un fichier temporaire, et purge des lignes de test.

### 4.4 🟠 Défauts du client Gemini

`gemini_client.py` :

| Ligne | Défaut | Conséquence |
|---|---|---|
| 76-78 | Aucun `responseSchema` malgré `responseMimeType: application/json` | Le JSON est demandé mais pas contraint. La sortie structurée native de Gemini supprimerait l'essentiel des échecs de parsing, sans reprise ni prompt défensif. |
| 107-108 | `finishReason` jamais lu | Une réponse coupée (`MAX_TOKENS`) ou filtrée (`SAFETY`) est traitée soit comme valide-mais-tronquée, soit comme « invalide » générique. Défaillance silencieuse. |
| 63 | Ni `maxOutputTokens` ni `thinkingConfig` | Sur `gemini-3-flash-preview`, le raisonnement est actif par défaut et consomme le budget de sortie. « Réponse Gemini vide » en est un symptôme classique. |
| 119-121 | `thoughtsTokenCount` non compté | Le coût des tokens de raisonnement n'est jamais facturé dans `cost_usd` : **le coût réel est sous-estimé**. |
| `logger.py:27-32` | Grille tarifaire **Gemini 2.5** | Les modèles utilisés sont `gemini-3.1-flash-lite` et `gemini-3-flash-preview`. Tous les montants ci-dessus sont indicatifs, calculés sur des tarifs de la génération précédente. |
| 84 | Backoff `0,5 s → 1,0 s`, sans jitter | Trop court pour un 429 Gemini (7 occurrences). Les deux reprises échouent typiquement dans la même fenêtre de quota. |
| 97 | `time.sleep` bloquant | Gèle le thread NiceGUI appelant jusqu'à 1,5 s + 3 × timeout. |

---

## 5. Performance — un point absent de l'audit initial

`get_course_mastery` est appelé pour les 707 cours (`snapshot_courses`, vues collèges). Par cours il déclenche :

- `get_seed_snapshot` → `count_evidence` **+** `first_evidence_date` (2 requêtes) ;
- `oic_coverage` (1) ;
- `get_anki_review_evidence` (1) ;
- `get_qcm_sessions_by_course` — appelé **deux fois**, `mastery.py:206` et `mastery.py:391` (2) ;
- `get_ai_practice_sessions` — également **deux fois**, `mastery.py:226` et `mastery.py:419` (2) ;
- `get_lisa_oic` (1), puis **`get_oic_attempts` une fois par OIC** (`mastery.py:406`) — N+1 imbriqué.

Soit **~9 requêtes par cours au minimum, ≈ 6 400 requêtes SQL** pour un recalcul complet, dont quatre strictement redondantes. C'est la chaîne de lenteur déjà notée en mémoire projet, ici quantifiée et localisée.

---

## 6. Ce que je ferais dans cet ordre

L'audit initial classe P0 « séparer les métriques » et « masquer les UUID ». Je place la correction des **chaînes rompues** avant tout travail de nommage ou d'UI : renommer une métrique fausse ne la rend pas vraie, et refondre l'interface au-dessus d'un score qui ne prend que deux valeurs revient à peindre une façade sur un mur creux.

### P0 — Rétablir la vérité des données (aucune UI concernée)

1. **Brancher le barème officiel sur le parcours réel** — faire passer `qcm_replay.py` par `score_closed_attempt`, ou appeler la route API. Débloque §3.3, §3.2-rupture-1, et la moitié de §3.1.
2. **Réparer la taxonomie d'erreurs** — table de traduction `omission|exces` × rang OIC × type de question → catégories `error_profile`. Sans elle, la réparation du point 1 produit 100 % de `non_classe`.
3. **Corriger le verrou Rang A** — conditionner à l'existence de tentatives OIC, pas à celle du référentiel. Renommer la variable.
4. **Purger la fuite de clé API** + en-tête `x-goog-api-key` + filtre de journalisation.
5. **Isoler la base de test** de la base de production.

### P1 — Rendre l'échelle informative

6. **Dissocier `mastery.score` et `retention.score`** en deux champs distincts du snapshot. La maîtrise cesse de décroître toute seule ; la rétention porte la décroissance. Supprime les régressions fantômes du rapport hebdomadaire et rend l'échelle 0-100 réellement 0-100.
7. **Recalibrer les seuils de niveau** une fois 1 et 6 faits, sur la distribution réelle. Objectif : que les 8 niveaux soient tous atteignables, et que « à consolider » cesse d'être inaccessible.
8. **Unifier `rank_gain_potential`** en une formule unique où les six facteurs pèsent réellement, et supprimer le zéro absorbant sur `session_count = 0`.
9. **Remonter le seuil de réussite SM-2** : `grade >= 2` (confiance 3/5) traité comme réussite faible plutôt que comme échec.

### P2 — Fiabiliser l'IA

10. **`responseSchema` natif** sur toutes les tâches structurées ; suppression des reprises de parsing devenues inutiles.
11. **Lire `finishReason`** et distinguer explicitement `tronqué` / `filtré` / `vide` — trois états produit différents, un seul message aujourd'hui.
12. **Traiter `uness_correction_visual` à part** : c'est 70 % du coût, 16 % d'échec et 25 s de latence. Batch asynchrone + file de validation humaine, jamais en synchrone dans l'UI.
13. **Réduire le prompt de `item_classification`** (2 733 tokens pour 32 en sortie) et mettre à jour la grille tarifaire vers Gemini 3.

### P3 — Performance et calibration

14. Précalculer les preuves de rétention **en lot** pour tous les cours (une requête par table au lieu de 9 par cours) ; supprimer les 4 requêtes dupliquées.
15. Pondérer la croissance de stabilité par l'intervalle réel (§3.7).
16. Mesurer la calibration une fois que des données propres existent — pas avant : calibrer sur des scores binaires biaisés à la baisse produirait un modèle faux avec une apparence de rigueur.

---

## 7. Réponses aux questions ouvertes de l'audit (§20)

| Question | Position argumentée |
|---|---|
| 1. Sens de « Progression » | Trois libellés distincts, pas un arbitrage : **Avancement** (lu/total, cardinal), **Maîtrise** (score, sans décroissance), **Rétention** (score projeté aujourd'hui). Le mot « Progression » devrait disparaître de l'interface. |
| 2. Score heuristique ou probabilité calibrée ? | Heuristique **assumé et documenté** tant que la base ne contient ni scores partiels ni résultats d'annales fiables. Une probabilité calibrée sur 30 tentatives binaires serait une fausse précision. |
| 3. Une correction IA non validée peut-elle influencer la maîtrise ? | **Non.** Elle peut alimenter la rétention (exposition) mais pas la maîtrise (compétence), qui doit rester adossée à un barème déterministe. |
| 4. Minuterie et verrouillage en mode concours ? | Oui aux deux, mais **après** P0 : un mode concours qui persiste des scores binaires faux aggrave le problème au lieu de le révéler. |
| 5. URLs directes Hypocampus par item ? | Non tranchable depuis le code ; à établir empiriquement (une session authentifiée, dix items témoins). N'affiche le bouton que si le taux de résolution est de 100 % sur l'échantillon. |
| 6. Le focus hebdomadaire crée-t-il des tâches ? | Pas automatiquement. Il repose aujourd'hui sur 3 `weak_points` et des catégories dominées par `non_classe` : générer des tâches à partir de ce signal produirait un plan arbitraire. À rouvrir après P0-2. |
| 7. Progression par collège, item ou OIC ? | Les trois, avec trois libellés et trois définitions écrites — c'est précisément l'absence de cette séparation qui produit le §3.1. |

---

## Synthèse

L'audit initial est juste sur le fond : le socle est déterministe, explicable, et le problème central est bien la confusion entre métriques. Il sous-estime cependant la gravité de la situation parce qu'il n'interroge pas la base.

En pratique, au 9 août 2026 :

- **la moitié des mécanismes audités ne tourne pas** — barème officiel contourné, signaux d'erreur nuls, recommandations nulles, couverture OIC nulle ;
- **l'échelle de maîtrise ne discrimine plus** : deux valeurs pour 91 % des cours notés, trois niveaux sur huit inatteignables ;
- **deux algorithmes ne portent pas le signal qu'ils annoncent** : le verrou Rang A punit l'absence de mesure au lieu de l'échec, et le potentiel de gain n'utilise réellement que trois de ses six facteurs ;
- **la clé API Gemini est en clair dans la base**, et les tests écrivent dans la base de production.

La conséquence pour la refonte annoncée est directe : figer les contrats de données ne suffit pas, il faut d'abord **rebrancher les producteurs de données**. Tant que `error_signals` et `ai_practice_attempt_propositions` restent vides et que `score_mode` reste vide, toute normalisation visuelle affichera proprement des chiffres faux.
