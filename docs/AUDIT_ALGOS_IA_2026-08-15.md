# Audit algorithmes & gestion IA — Synapse

**Date** : 15 août 2026
**Périmètre** : tous les modules de calcul (maîtrise, rétention, planification, scoring docimologique,
profilage d'erreurs, trajectoire) et toute la chaîne IA (routage, prompts, coûts, garde-fous, pipelines
UNESS/EDNpro).
**Méthode** : lecture du code + **mesure de la base réelle** (`data/synapse_local.db`, 37 Mo, snapshot du
15/08 09:21). Chaque chiffre de ce document provient d'une requête SQL reproductible — les requêtes sont
en annexe §8. Les constats des audits précédents ont été **revérifiés** : quatre d'entre eux ne tiennent
plus (voir §7), ils sont signalés comme tels.

---

## 1. Résumé exécutif

Le programme contient une quantité inhabituelle d'algorithmes corrects et bien écrits. Le problème n'est
presque jamais la formule : **c'est le branchement**. Trois constats dominent tout le reste.

**① Le score de maîtrise ne mesure rien.**
Sur 757 fiches, 99 ont un score. **98 d'entre elles sont des items auto-déclarés le 16/07/2026**, et
**85 valent exactement 28 ou 48** — c'est-à-dire la graine déclarée (`flou`=30, `correct`=50) moins les
2 points de dégradation du mois écoulé. Le score affiché est la déclaration de juillet, pas une mesure.
Cause racine : `count_evidence()` ne compte que `study_sessions` (34 lignes), `qcm_sessions` (7) et
`oic_attempts` (3). Donc `n_evidence ≈ 0`, donc `blend()` garde 100 % du poids sur la déclaration.

⚠️ **Nuance vérifiée le 15/08 (usage réel non encore démarré, rentrée le 30/08)** : le circuit est bien
câblé de bout en bout. Jouer une session dans l'app (`qcm_replay.py:568` ou `api/qcm.py:243`) appelle
`record_ai_practice_mastery` → `record_evaluation(source="qcm")` → **écrit dans `qcm_sessions`**, qui
*est* compté. Ce constat se résorbera donc largement de lui-même dès que les sessions seront jouées.
Ce qui **ne** se résorbera pas : la cécité aux alias (§3.1b) et l'inertie de `blend()` (§3.1c).

**② La boucle d'entraînement n'est jamais fermée.**
3 509 questions sont en base (2 352 EDNpro, 1 097 générées par IA) réparties en 600 sessions.
**594 sessions sur 600 sont en état `draft`** : jamais jouées. Total des tentatives : **37**, sur
8 sessions. Or *toute* la chaîne aval se nourrit de tentatives : `error_signals` (0 ligne) →
profil d'erreurs → `edn_recommendations` (0 ligne) → priorité Flash-Zero → Tuteur DP. Le système produit
du contenu et ne consomme pas de réponses ; les six algorithmes en aval tournent donc à vide.

**③ 70 % de la dépense IA est jetée à la poubelle par construction.**
`uness_correction_visual` : 63 appels, 0,676 $ sur 0,970 $ de dépense totale. Quand des images sont
jointes, `generate_uness_correction()` renvoie `requires_human_validation=True`, et
`gemini_autocorrect.py:224` **retourne `None` sans jamais parser ni stocker la réponse**. Les ~53 corrections
visuelles réussies (24,9 s et jusqu'à 12 000 tokens chacune) ont été payées puis détruites, sans file
d'attente de validation : la seule issue est de repayer l'appel.

Le reste de l'audit détaille 34 constats, classés par domaine, avec pour chacun une correction chiffrée.

### Tableau de bord (mesures du 15/08/2026)

| Indicateur | Valeur mesurée | Lecture |
|---|---|---|
| Fiches avec un score de maîtrise | 99 / 757 | 13 % |
| …dont issues d'une auto-déclaration | 98 / 99 | 99 % |
| Score maximal observé (8 semaines) | **58 / 100** | jamais « à consolider » (≥60) ni « maîtrisé » (≥80) |
| Sessions de pratique jouées | 6 / 600 | 1 % |
| Tentatives enregistrées | 37 | pour 3 509 questions |
| `error_signals` / `edn_recommendations` | 0 / 0 | chaîne d'erreurs vide |
| `oic_attempts` / `lisa_oic` | 3 / 290 | verrou Rang A jamais concluant |
| `anki_review_evidence` | 0 | pondération 25 % jamais exercée |
| Appels IA (01→11/08) | 827, 0,970 $ | dont 15,9 % d'échec sur la tâche visuelle |
| Tokens d'entrée `item_classification` | 1 426 986 pour 18 143 en sortie | ratio 79:1 |

---

## 2. Cartographie des algorithmes

| Module | Rôle | État réel mesuré |
|---|---|---|
| `reviews/mastery.py` (674 l.) | score de maîtrise 0-100 + niveau | **façade** : rejoue la déclaration (§3.1) |
| `knowledge/retention.py` | courbe d'oubli `2^(-t/S)` | correct, **ne pilote aucune décision** (§3.4) |
| `reviews/sm2.py` | intervalles SM-2 modifiés | actif, mais branches `trap` mortes (§3.6) |
| `reviews/service.py::_calculate_priority` | score de priorité | **un bonus de +35 s'applique à 100 % des cours** (§3.7) |
| `reviews/consolidation.py` | flux long terme auto-chaîné | **le seul flux réellement utilisé** (112 validations) |
| `reviews/reentry.py` | frontière de reprise 20/08 | supprime définitivement l'arriéré (§3.9) |
| `reviews/recommendation_service.py` | action suivante + budget | durées forfaitaires jamais recalibrées (§3.10) |
| `reviews/drift_detector.py` | détection de régression | **code mort — 0 appelant** (§3.11) |
| `practice/scoring.py` | barème docimologique R2C | formule juste, seuil `valide_rang_a` faux (§3.12) |
| `edn/error_profile.py` + `gap_suggestions.py` | erreurs → lacunes | alimenté par une table vide (§4) |
| `edn/trajectory.py::rank_gain_potential` | classement gain/effort | correct, alimenté à 50 % (§4.4) |
| `practice/flash_zero_service.py` | quiz matinal | **10 questions en dur, identiques chaque jour** (§4.3) |
| `ai/routing.py` + `service.py` + `gemini_client.py` | routage/transport IA | sain, mais pas de schéma ni de cache (§5) |
| `uness/item_classifier.py` | classification d'annales | fonctionne, **coût x5 évitable** (§5.3) |
| `ednpro/frequency.py` | fréquence des items aux annales | **la meilleure donnée du système, sous-exploitée** (§4.4) |
| `analytics/weekly_report.py` | revue hebdomadaire | lit `qcm_sessions` (7 l.) et ignore la pratique (§3.13) |

---

## 3. Constats — moteur de maîtrise et planification

### 3.1 — 🔴 CRITIQUE · Le score de maîtrise est l'auto-déclaration de juillet

**Mesure** (semaine `2026-W33`) : 99 fiches scorées, distribution des scores :

```
28 → 40 fiches     48 → 45 fiches     autres valeurs → 14 fiches
min 26 · max 58 · moyenne 39,1
```

40 + 45 = **85 fiches sur 99 (86 %) sur deux valeurs exactes**. `SEED_SCORES = {flou:30, correct:50}` moins
`DECAY_PER_30D = 2` sur les 30 jours écoulés depuis le 16/07 → 28 et 48. La distribution *est* la
déclaration. 98 des 99 fiches scorées ont une ligne dans `item_state` (146 lignes : 75 `flou`, 71 `correct`,
**0 `solide`**).

**Mécanisme** (`mastery.py:302`) :
```python
mastery_score = blend(seed.seed_score, mastery_score, seed.n_evidence)   # w = 1/(1+n_evidence)
```
`n_evidence` vient de `knowledge/service.py::count_evidence()`, qui n'interroge que trois tables :
`study_sessions` (34 lignes), `qcm_sessions` (7), `oic_attempts` (3).

**Ce qui alimente réellement ces trois tables** (vérifié le 15/08) :

| Activité de l'utilisateur | Table écrite | Comptée |
|---|---|---|
| Jouer une session QCM/DP dans l'app | `qcm_sessions` (via `record_evaluation(source="qcm")`) | ✅ |
| Valider une révision J / consolidation | `study_sessions` (via `source="auto_eval"`) | ✅ |
| Tenter un OIC | `oic_attempts` | ✅ |
| Session de pratique laissée en `draft` | *(rien)* | — |
| Révisions Anki (`anki_review_evidence`) | — | ❌ |

**Le circuit est donc correct** : le compteur est à zéro parce que 594 sessions sur 600 n'ont jamais été
jouées, pas parce qu'il regarde les mauvaises tables. Ce constat se résorbe avec l'usage.

**§3.1b — 🟠 Ce qui ne se résorbera pas : la cécité aux alias.**
`count_evidence(course_id)` filtre sur le `course_id` **exact**, sans passer par `data_store.alias_ids()`
— alors que tout le reste de `mastery.py` agrège les fiches d'un même item (162 items sur 365 ont 2 à
4 fiches). Conséquence : une session jouée depuis la fiche « Cardiologie » de l'item 234 dilue la graine
de cette fiche uniquement. La fiche « Réanimation » du **même item** continuera d'afficher la déclaration
de juillet, avec un score différent, indéfiniment. Deux fiches du même item divergeront d'autant plus que
tu travailleras.

**§3.1c — 🟡 L'inertie de `blend()` : compte ~4 activités par fiche avant que la déclaration lâche.**
`w = 1/(1+n_evidence)` : à la 1ʳᵉ preuve, la déclaration pèse encore **50 %**. Un item déclaré `flou`
(graine 28) qui obtient 85 % à son premier QCM affichera `blend(28, ~65, 1) ≈ 47` — soit toujours
« fragile ». Il faut 4 à 5 activités sur **chaque fiche** pour que la mesure prenne le dessus. Sur
367 items, c'est plusieurs mois avant que le tableau de bord reflète le travail réel.

**Correction** :
1. Passer `count_evidence()` par `data_store.alias_ids()` (une ligne) — sinon les items multi-fiches
   divergeront en permanence.
2. Accélérer la dilution : `w = 1/(1+n)²`, ou plafond dur « graine ignorée dès 3 preuves ».
3. Ajouter `anki_review_evidence` au compteur si l'usage d'Anki reprend.

### 3.2 — 🔴 CRITIQUE · L'échelle à 8 niveaux fonctionne comme une échelle à 4

Sur **8 semaines de snapshots** (`2026-W26` → `2026-W33`, 4 128 lignes, 825 fiches distinctes), les niveaux
observés sont : `à préparer` (2 537), `à lire` (1 166), `fragile` (239), `critique` (184), `à entraîner` (2).
**Zéro `maîtrisé`, zéro `à consolider`, zéro `en construction`.**

C'est mécanique : `maîtrisé` exige `mastery_score ≥ 80`, `à consolider` exige `≥ 60`, et le score maximal
jamais atteint est **58**. Le plafond vient de §3.1 (la graine `correct` plafonne à 50) et de l'absence de
bonus atteignables : `+15` annales exige des sessions d'annales scorées (**1 seule en base**), `+10` QCM
réussis exige `qcm_sessions` (7 lignes), `+10` confiance exige des sessions notées.

Conséquence produit : l'utilisateur ne peut **jamais** voir un item passer au vert. Un système de révision
dont l'échelle n'a pas de sortie haute décourage structurellement.

**Correction** : après le correctif §3.1, recalibrer les seuils sur la distribution réelle (par ex.
quantiles glissants plutôt que constantes 40/60/80), et **ajouter un chemin de sortie explicite** :
« 2 sessions d'annales ≥ 70 % sur l'item ⇒ maîtrisé », condition mesurable et atteignable.

### 3.3 — 🟠 Deux tables de preuves parallèles, la maîtrise lit la moins peuplée

`_qcm_rows_for_item()` (`mastery.py:84`) lit `qcm_sessions` → **7 lignes**. Les preuves réelles sont dans
`ai_practice_sessions`/`ai_practice_attempts` → 600 / 37. La pénalité « QCM récent faible » (`-15`,
`mastery.py:274`) et la moitié des preuves de rétention sont donc calculées sur un corpus quasi vide.

**Correction** : une vue SQL unique `evidence_unified(course_id, item_number, date, source, score_percent)`
qui fusionne `qcm_sessions`, `ai_practice_sessions` scorées et `review_history` validées. Tous les modules
(maîtrise, rétention, revue hebdo, trajectoire) lisent cette vue et cessent de diverger.

### 3.4 — 🟠 Le seul modèle d'oubli du programme ne pilote aucune décision

`retention.py` est le module le plus rigoureux du projet : stabilité par source
(`lecture` 7 j → `annale` 30 j), croissance/contraction selon la qualité, décroissance `2^(-t/S)`, plancher
à 25. Il produit `retention_score` pour 99 fiches (moyenne 38,2).

Or `retention_score` n'est lu que par `weekly_report` et l'écran Revue. **Il n'entre ni dans
`_calculate_priority()`, ni dans le choix des tâches du jour, ni dans `select_daily()`.** La priorité
utilise `mastery_score`, qui est une constante déclarée (§3.1). Autrement dit : le système sait modéliser
l'oubli et refuse de s'en servir pour décider.

**Correction (fort impact, faible coût)** : remplacer `mastery_score` par `retention_score` dans le bonus
de maîtrise de `_calculate_priority`, ou mieux, prioriser sur **`retention_score` projeté à J+7**
(`project_retention(score, stability, 7)`) : on révise ce qui *sera* oublié la semaine prochaine, pas ce qui
l'est déjà.

**Défauts techniques du module, à corriger au passage** :
- `_source_base_stability()` lève `ValueError` sur une source inconnue ; l'appel dans
  `get_course_mastery` (l. 310-311) **n'est pas protégé** → l'ajout d'un type de preuve ailleurs fait
  planter l'affichage de la maîtrise. Retourner une base par défaut et journaliser.
- La stabilité est intégralement recalculée depuis l'historique complet à chaque appel (pas d'état
  persistant) : coût O(preuves) × 757 fiches à chaque rendu.
- Le facteur d'espacement `elapsed_days / current_stability` annule le gain d'une révision rapprochée
  (`spacing_factor → 0`) : c'est défendable en SRS, mais cela signifie qu'une session de rattrapage
  intensive n'augmente pas la stabilité. À documenter ou à assouplir (plancher à 0,2).

### 3.5 — 🟠 Le verrou Rang A ne peut pas conclure : 3 tentatives OIC pour 290 objectifs

`rang_a_verdict()` exige 3 objectifs tentés (ou un tiers de la liste) pour se prononcer. En base :
`lisa_oic` = 290 objectifs, `oic_attempts` = **3 tentatives**. Donc `rang_a_conclusive` est faux
partout, donc `score_rang_a = mastery_score` (`mastery.py:326`), donc le « Socle Rang A » affiché est une
copie du score général — avec un libellé qui laisse croire à une mesure sur le référentiel officiel.

Le garde-fou lui-même est bon (c'est le correctif du 14/08). Le problème est **l'absence totale
d'alimentation** : rien dans l'UI ne pousse à tenter un OIC. C'est le chaînon manquant le plus rentable du
produit — voir la proposition F2 (§6.2), « 1 OIC = 1 micro-question ».

### 3.6 — 🟡 SM-2 : deux branches sur trois sont mortes, l'EF n'agit qu'à partir de la 3ᵉ révision

`sm2.py` reçoit `critical_trap` (`weak_points.severity ≥ 4`) et `recurrent_trap`
(`recurrence_count > 1`). **`weak_points` contient 3 lignes** → les deux branches ne se déclenchent
jamais. Par ailleurs :
- `repetition == 0 → 3 j`, `repetition == 1 → 7 j` sont **forcés** : le facteur de facilité calculé
  n'a d'effet qu'à partir de la 3ᵉ révision. Sur un usage de 6 semaines, presque aucune chaîne n'y arrive.
- `grade < 2` (confiance 1-2) → intervalle fixe de 3 j quel que soit l'historique : un item raté trois
  fois de suite revient au même rythme qu'un item raté une fois.
- Confiance 3 est traitée comme une réussite avec `new_ef = ef + 0.1 - 0.08 = ef + 0.02` : une hésitation
  **augmente** légèrement la facilité. C'est contraire à SM-2 classique (grade 3 ⇒ EF quasi stable ou en
  baisse).

**Correction** : `-0.02` pour grade 2 (confiance 3), et intervalle d'échec dégressif
(`3 j → 2 j → 1 j` selon `repetition_count` de la chaîne).

### 3.7 — 🔴 CRITIQUE · Le bonus « Sprint Rang A » de +35 s'applique à 100 % des cours

```python
# reviews/service.py:509
if mastery.score_rang_a is not None and mastery.score_rang_a < 75:
    score += 35.0
```
`score_rang_a` vaut `mastery_score` faute de mesure OIC (§3.5), et **aucune fiche n'a jamais dépassé 58**
(§3.2). Le bonus s'ajoute donc à *toutes* les tâches : c'est une constante additive, qui ne classe rien.
Pire, il écrase le barème voisin (`critique` +25, `fragile` +15) : le signal le plus fort du tri de
priorité est celui qui ne discrimine pas.

**Correction** : conditionner à `_rang_a_conclusive` (le bonus ne se déclenche que sur une mesure réelle),
et le ramener à +20 pour rester sous le poids « critique ».

### 3.8 — 🟠 Le « graphe sémantique » est un graphe d'appartenance à un collège

`course_edges` : **15 402 arêtes**, dont **14 842 `same_college` (96,4 %) au poids 0,8** et 560 `same_item`
au poids 1,0. Or :
```python
# reviews/service.py:239-250 — un voisin critique donne +10 × poids à la tâche
```
Comme `same_college` relie tous les cours d'un collège entre eux, **il suffit qu'un cours d'un collège soit
`critique` pour que tout le collège prenne +8**. Et dans le boost de stage (l. 517-519), la condition
`any(n.edge_type == "same_college")` est vraie pour tout cours ayant un collège → le ×1,2 est universel.

Deux boosts sur trois sont donc des constantes déguisées en signal.

**Correction** : ne propager le boost de criticité que sur les arêtes `same_item` (560, sémantiquement
justes), et construire de vraies arêtes de proximité clinique — ce que permettrait un embedding local des
titres/OIC (proposition F5, §6.2) — avant de rebrancher `same_college`.

### 3.9 — 🔴 CRITIQUE · La frontière de reprise supprime l'arriéré au lieu de le replanifier

`reentry.py` : `DEFAULT_STUDY_RESUME_DATE = 2026-08-20` (configurable dans /settings).
```python
def filter_active_review_tasks(tasks, resume_date):
    return [t for t in tasks if t.due_date >= boundary]
```
Une tâche due le 10/08 a `due_date < 20/08` **pour toujours** : elle ne réapparaîtra jamais, même après la
date de reprise. Ce n'est pas une mise en pause, c'est une amnésie définitive.

Conséquence en cascade : `is_j_cycle_complete()` exige les **4** J validés pour autoriser l'entrée en
consolidation. Les cours dont les J ont été effacés par le filtre ne complèteront jamais leur cycle et
**ne seront donc jamais amorcés en consolidation** : ils sortent du système sans bruit. Mesure : 13 cours
ont au moins un J validé, **9 seulement ont le cycle complet** ; 112 validations de consolidation contre
51 validations de J au total.

**Correction** : remplacer le filtre par un **rebasage** — à la date de reprise, décaler toutes les
échéances antérieures sur les 14 jours suivants, pondérées par la priorité, plutôt que de les jeter.
Alternative minimale : assouplir `is_j_cycle_complete` en « J30 validé **ou** date de 1ʳᵉ lecture > 45 j ».

### 3.10 — 🟡 Le budget quotidien repose sur des durées forfaitaires jamais recalibrées

`get_next_action()` renvoie 15 / 20 / 25 / 30 / 35 min selon des règles fixes, et `apply_daily_budget()`
tronque la journée sur cette base. Or `study_sessions.duration_minutes` contient 34 durées réellement
observées, jamais relues. Le budget affiché est donc une convention, pas une prévision.

**Correction** : estimer la durée par régression simple sur l'historique (médiane par
`review_type × niveau`, repli sur le forfait quand n < 5). Coût : ~40 lignes, gain direct sur la
crédibilité du plan.

### 3.11 — 🟡 `drift_detector.py` : 63 lignes de code mort assises sur 4 128 snapshots

`detect_mastery_drift()` n'a **aucun appelant** en dehors de sa propre définition (vérifié sur `backend/`,
`frontend/`, `scripts/`). Il attend exactement le format que `mastery_snapshots` fournit déjà, avec
8 semaines d'historique disponible et son propre calcul de confiance
(`faible` < 4 pts, `indicative` < 7, `haute` ≥ 7).

**Correction** : le brancher sur le dashboard (« 3 items en régression cette semaine ») — c'est la
fonctionnalité la moins chère du backlog : le calcul, le stockage et l'affichage existent déjà séparément.

### 3.12 — 🟠 Barème EDN : la formule est juste, le verdict de validation ne l'est pas

`compute_question_score_edn()` implémente correctement le barème R2C
(0 discordance = 1 pt, 1 = 0,5, 2 = 0,2, ≥3 = 0 ; zéro sur indispensable manquée ou inacceptable cochée).
Deux réserves :

1. **`valide_rang_a = score_20 >= 14.0`** (`scoring.py:209`). Le commentaire dit « correspond aux 70 %
   requis EDN Rang A », mais la règle EDN porte sur les **questions de rang A**, pas sur la note globale.
   Un étudiant à 14/20 en ratant tout le rang A est déclaré « validé ». Il faut filtrer sur
   `proposition.rank == "A"` avant d'agréger — l'information est déjà transportée dans
   `ScoredAttempt.propositions[].rank`, elle est simplement ignorée à l'agrégation.
2. Les contraintes `indispensable_choices` / `inacceptable_choices` ne sont présentes que sur
   **185 questions sur 3 509** (5,3 %). Les pénalités absolues, qui sont l'essentiel de la docimologie EDN,
   ne s'appliquent donc quasiment jamais. À extraire systématiquement dans le prompt de correction UNESS
   (le schéma actuel ne les demande pas).

### 3.13 — 🟡 La revue hebdomadaire ignore 99 % de l'activité

`generate_weekly_report()` lit `study_sessions` (34 lignes) et `qcm_sessions` (7) — pas
`ai_practice_sessions` (600) ni `ai_practice_attempts`. Le « taux de réussite QCM » de la semaine est donc
calculé sur un corpus de 7 lignes historiques. Même correctif que §3.3 (vue unifiée).

### 3.14 — 🟡 N+1 requêtes dans le calcul de maîtrise

`get_course_mastery()` déclenche par cours : `oic_coverage` (1 requête), `get_qcm_sessions_by_course` ×
nombre d'alias, `get_lisa_oic` × alias, `get_anki_review_evidence`, `get_ai_practice_sessions`, plus
`get_oic_attempts` par OIC dans `_canonical_retention_evidence`. Sur 757 fiches (snapshot hebdomadaire,
génération de plan), cela fait plusieurs milliers d'allers-retours SQLite. `ReviewService` a un cache
mémoire journalier, mais `snapshot_courses()` et `get_unstarted_courses()` court-circuitent ce cache en
appelant `get_course_mastery` directement.

**Correction** : précharger les 5 tables concernées en dictionnaires (comme le fait déjà `consolidation.py`
avec `get_sessions_by_course()`), et passer ces maps en paramètre.

---

## 4. Constats — boucle d'erreurs, lacunes et priorisation EDN

### 4.1 — 🔴 CRITIQUE · La chaîne « erreur → lacune → entraînement ciblé » n'a jamais eu de première brique

```
tentative scorée → error_signals(0) → build_error_profile → suggest_gap_candidates
                → edn_recommendations(0) → weak_points(3) → Flash-Zero / Tuteur DP
```
Le correctif de ce matin (`8ee6909`) répare le point de rupture logique — une question non classée hérite
désormais de l'item de sa session. Mais la source reste **37 tentatives**, dont 35 avec un détail
propositionnel. Tant que les sessions ne sont pas jouées (§4.2), les six modules en aval resteront muets.

⚠️ **Nuance vérifiée le 15/08** : la chaîne est câblée. Les deux lecteurs de questions
(`frontend/components/qcm_replay.py:488` et `backend/api/qcm.py:208`) appellent bien
`score_and_record_closed_attempt` → `record_error_signals_for_attempt` → `error_signals`. Et
`backend/features/daily_routine.py:123` génère jusqu'à 3 questions Flash-Zero IA par jour dès que des
signaux existent. **Ce constat se résorbe donc de lui-même dès la première session jouée dans l'app.**

Deux réserves qui subsistent :
- l'alimentation ne passe **que** par le lecteur intégré. Un QCM corrigé ailleurs puis importé en
  markdown (`ai_qcm/parser.py`) ne produit **aucun** signal d'erreur propositionnel ;
- `filter_post_resume_signals` écarte tout signal antérieur à `study_resume_date` (défaut **20/08**).
  Rentrée le 30/08 ⇒ caler cette date sur le 30/08 dans /settings, sinon les clics de paramétrage
  d'avant-rentrée entreront dans le profil d'erreurs.

C'est le vrai ordre de priorité du produit : **faire jouer les questions déjà payées** avant d'écrire une
ligne d'algorithme supplémentaire.

### 4.2 — 🔴 CRITIQUE · 594 sessions sur 600 sont mortes en `draft`

| `practice_kind` | `completion_state` | Sessions | Terminées |
|---|---|---|---|
| QCM | draft | 550 | 0 |
| DP | draft | 44 | 0 |
| QCM | recorded | 5 | 5 |
| QCM | scored | 1 | 1 |

548 des 550 sessions QCM `draft` portent un `annale_id` : ce sont les annales UNESS importées et
classifiées (à un coût IA réel), prêtes à être jouées, et jamais ouvertes. 3 509 questions dorment,
2 526 sont rattachées à un item, 303 items distincts sont couverts.

**Proposition produit (F1, §6.2)** : une file « 5 questions du jour » tirée automatiquement du corpus
`draft`, priorisée par fréquence EDNpro × déficit de maîtrise. Aucun appel IA, aucune génération : le
contenu existe déjà et est payé.

### 4.3 — 🟠 Flash-Zero sert les 10 mêmes questions codées en dur, tous les jours

`canonical_flash_bank` = 10 `FlashZeroQuestion` en dur dans le fichier ; `flash_zero_ai_questions` = **0
ligne** en base ; `get_morning_quiz(count=10)` renvoie donc les 10 questions canoniques, mélangées par un
RNG semé sur la date. Le ciblage (`build_flash_zero_priority`) opère sur `error_signals` — vide.

Trois problèmes distincts :
1. La génération IA (`generate_daily_questions`) ne se déclenche que s'il existe des signaux d'erreur :
   verrou circulaire avec §4.1.
2. Le contenu médical est **figé dans le code source**, sans date de revue ni source. Une recommandation
   qui évolue (dépistage, seuils) devient un piège d'apprentissage silencieux.
3. Aucun suivi de ce qui a été répondu : rejouer les mêmes 10 questions n'apprend rien après J+3.

**Correction** : externaliser la banque en JSON versionné (`data/flash_zero_bank.json`) avec
`source` + `revised_at` par question, et alimenter la priorité depuis
`ai_practice_attempts` (les réponses fausses) au lieu de `error_signals` seul.

### 4.4 — 🟢 Le meilleur signal du système est sous-exploité

`ednpro_item_frequency` : **367 items, collectés le 10/08**, avec une répartition franchement
discriminante :

| Priorité | Items | Sessions moy. | Questions moy. |
|---|---|---|---|
| indispensable | 205 | 4,98 | 9,5 |
| important | 57 | 2,00 | 3,4 |
| basique | 67 | 1,00 | 1,5 |
| jamais_tombé | 38 | 0,00 | 0,0 |

C'est la seule donnée **externe, factuelle et fraîche** du programme : ce qui tombe réellement aux EDN.
Elle n'est utilisée qu'à un seul endroit — `rank_gain_potential` (25 % `edn_weight` + 15 %
`frequency_recurrence`), lui-même affiché dans un panneau du dashboard. Elle **n'entre pas** dans
`_calculate_priority()`, ni dans `select_daily()`, ni dans le choix des révisions du jour.

**Correction (fort impact, ~15 lignes)** : ajouter un facteur multiplicatif de fréquence au score de
priorité des révisions (`×1,25` indispensable, `×1,0` important, `×0,85` basique, `×0,6` jamais tombé).
38 items ne sont jamais tombés depuis la création de l'EDN : les réviser au même rythme que les 205 items
indispensables est le gaspillage le plus mesurable du plan actuel.

### 4.5 — 🟡 `rank_gain_potential` : pondération non normalisée et effort factice

- `estimated_minutes` est **codé en dur à 30** pour tous les items (`_cockpit_today.py:111`) → le
  diviseur `effort` vaut 1,0 partout : le classement « gain/effort » est un classement de gain pur.
- `availability = available_questions / 20` plafonné à 1 : les items disposant de plus de 20 questions
  EDNpro sont indistinguables entre eux, alors que c'est justement la dimension exploitable
  immédiatement (§4.2).
- La somme des poids (0,25 + 0,30 + 0,15 + 0,15 + 0,15) = 1,0 : correct, mais aucun test ne le garantit
  contre une future modification.

---

## 5. Constats — gestion de l'IA

### 5.1 — Photographie de la dépense (827 appels, 01→11/08, 0,970 $ déclarés)

| Tâche | Modèle | Appels | Échecs | Tokens in | Tokens out | Coût | Latence moy. |
|---|---|---|---|---|---|---|---|
| `item_classification` | flash_lite | 579 | 0 | 1 426 986 | 18 143 | 0,113 $ | 1,8 s |
| `uness_correction` | flash_lite | 90 | 0 | 458 362 | 319 197 | 0,130 $ | 9,7 s |
| **`uness_correction_visual`** | **flash** | **63** | **10 (15,9 %)** | 253 056 | 183 207 | **0,676 $** | **24,9 s** |
| `qcm` | flash_lite | 49 | 0 | 47 476 | 25 452 | 0,011 $ | 0,4 s |
| `item_classification` | flash | 38 | 0 | 18 966 | 1 578 | 0,014 $ | 13,7 s |
| `dp` | flash | 4 | 0 | 1 952 | 6 174 | 0,020 $ | 14,9 s |
| `gemini_generate` (non étiqueté) | flash_lite | 4 | 0 | 10 511 | 19 743 | 0,007 $ | 11,1 s |

Le routage lui-même (`routing.py`) est propre : politique pure, testable, avec escalade sur
`difficulty ∈ {difficile, concours}`. Rien à redire sur la conception. Les problèmes sont ailleurs.

### 5.2 — 🔴 CRITIQUE · 70 % de la dépense produit une sortie jetée sans trace

`generate_uness_correction()` positionne `requires_human_validation = bool(images)`, et le seul
consommateur fait :
```python
# uness/gemini_autocorrect.py:224
if response.requires_human_validation:
    return (None, "Correction visuelle générée : validation humaine requise avant import.", in_tok, out_tok)
```
La réponse n'est **ni parsée, ni écrite sur disque, ni mise en file**. Sur 63 appels visuels, ~53 ont
abouti à une correction complète, payée (0,676 $, soit 70 % de la dépense totale) et détruite dans la
foulée. Le message d'attente ne remonte nulle part dans l'UI (`grep` : une seule occurrence, celle-ci).

**Correction (P0, ~1 h)** : écrire la réponse dans `UNESS/pending_validation/<quiz>.json` avant de
retourner, et ajouter une entrée dans le panneau DIAGNOSTIC UNESS (« 12 corrections en attente de
validation → Ouvrir / Valider / Rejeter »). Le garde-fou est bon ; il lui manque juste la boîte aux
lettres.

### 5.3 — 🟠 `item_classification` : ratio 79:1 entre entrée et sortie, ~85 % évitable

579 appels, **1 426 986 tokens d'entrée** pour 18 143 en sortie, soit **2 465 tokens d'entrée par appel**.
Cause : `_build_prompt()` renvoie la **liste complète des items candidats** (jusqu'aux 367 items du
référentiel avec leur intitulé) à chaque appel, alors que cette liste est **identique pour toutes les
annales d'une même matière**.

Trois optimisations cumulables :
1. **Présélection locale** : un BM25 / TF-IDF sur le titre + l'extrait réduit les candidats à ~20 avant
   l'appel. Le garde-fou (`kept = [n for n in raw if n in candidate_numbers]`) reste valable. Gain : ~85 %
   des tokens d'entrée.
2. **Traitement par lot** : classer 10 annales dans un seul appel en partageant la liste. Gain : ~90 % sur
   les appels d'une même matière.
3. **Cache de contexte** Gemini sur le bloc de candidats (stable, réutilisé 579 fois).

À volume constant, 1,1 M de tokens d'entrée économisés. Le gain financier est modeste aujourd'hui
(~0,08 $), mais le gain en **latence** (1,8 s × 579) et en robustesse (moins de liste = moins de
sur-classification, le défaut historique de cette tâche) est direct.

### 5.4 — 🟠 La politique de retry ignore les erreurs qui surviennent réellement

`_is_retryable_error()` ne couvre que `Timeout`, `ConnectionError`, HTTP 429 et 5xx. Or les échecs
constatés en production sur la tâche visuelle sont d'un autre type :
`MAX_TOKENS`, `SAFETY`, « Réponse Gemini invalide », « Réponse Gemini vide », « Réponse incomplète :
2/3 questions » (`uness_correction_failures`). **Aucun n'est réessayé** par le client ; c'est
`gemini_autocorrect` qui refait sa propre boucle, uniquement sur « 429 » détecté par sous-chaîne de
message (l. 214).

Deux corrections :
- `MAX_TOKENS` doit déclencher un **redécoupage** (corriger quiz par quiz plutôt que le lot) et non un
  simple retry. Aucun `maxOutputTokens` n'est configuré, ce qui rend la coupure imprévisible.
- Le retry sur la chaîne « 429 » est fragile : exposer le code HTTP dans `GeminiClientError` et tester
  dessus.

### 5.5 — 🟠 Les tarifs facturés sont ceux d'une génération de modèles antérieure

```python
# ai/logger.py — "Tarifs au 1M tokens (Gemini 2.5 Flash / Flash Lite)"
FLASH_LITE: {input: 0.075, output: 0.30}   |   FLASH: {input: 0.50, output: 3.00}
```
Les modèles réellement configurés sont `gemini-3.1-flash-lite` et `gemini-3-flash-preview`
(`config/settings.py:125-126`). Les 827 coûts stockés dans `ai_usage_logs` sont donc calculés avec la
grille d'une autre génération : le total de 0,970 $ est indicatif, pas comptable.

**Correction** : externaliser la grille dans la configuration (`PRICING` par nom de modèle exact, pas par
famille), et afficher les tokens à côté du coût dans le panneau de suivi — les tokens, eux, sont exacts.

### 5.6 — 🟡 Le contexte documentaire sert à la fois de charge utile et d'étiquette de journal

`PracticeService._generate_with_model` fait `ctx_label = context or f"ITEM {n}"`, puis passe cette même
valeur comme `context=` — laquelle est à la fois injectée dans le prompt (`--- CONTEXTE DOCUMENTAIRE ---`)
**et journalisée** dans `ai_usage_logs.context` et `logs/ai_usage.log`.

Mesure : pour la tâche `dp`, `max(length(context)) = 838` caractères d'énoncé clinique écrits en clair
dans le journal, contre 9-25 caractères pour les autres tâches (« ITEM 221 »). Deux champs distincts
(`label` court pour le journal, `context` pour le prompt) règlent le problème.

### 5.7 — 🟠 `responseSchema` est supporté mais jamais utilisé, et le JSON est réparé à la main 3 fois

`GeminiClient.generate` accepte `response_schema` et le transmet à `generationConfig` — **aucun appelant
ne le fournit**. En conséquence, trois modules réimplémentent séparément la même réparation de JSON à
coups d'expressions régulières et de recherche d'accolades :
`practice/service.py::_parse_questions`, `flash_zero_service::_parse_flash_zero_question`,
`ednpro/rank_inference::_decode_json`.

**Correction** : définir un schéma par tâche (questions, correction UNESS, classification), le passer à
l'API, et supprimer les trois parseurs tolérants au profit d'un `json.loads` strict. Cela élimine par
construction la classe d'erreurs « La réponse IA n'est pas un JSON valide » — et rend inutile le
mécanisme de rattrapage question par question (`_recover_partial_questions`), qui multiplie les appels
par `total_questions` quand un lot est incomplet.

### 5.8 — 🟠 Aucune vérification de véracité sur le contenu médical généré

1 097 questions générées par IA (`gemini+uness`, `chatgpt+uness`) sont stockées puis servies comme
matériel d'entraînement. Les seuls garde-fous existants sont :
- le drapeau `uncertain` de Flash-Zero (banque vide, donc jamais exercé) ;
- `desaccord_officiel` / `confiance_ia` dans le prompt de correction UNESS — bien conçu, mais rien dans
  le code ne **filtre** ni ne **remonte** les propositions à faible confiance ou en désaccord avec la
  correction officielle.

Pour un usage EDN, c'est le risque principal du projet : mémoriser une réponse fausse coûte plus cher que
ne pas réviser. **Proposition** : bloquer l'affichage d'une question dont `confiance_ia < 0,7` ou
`desaccord_officiel = true` derrière un bandeau « à vérifier », et exposer un compteur dans /settings.
Le champ existe déjà dans le schéma du prompt ; il suffit de le lire.

### 5.9 — 🟡 Aucune déduplication de génération

`replay_session()` existe, mais rien n'empêche de générer deux fois une session sur le même
item/objectif/difficulté. Avec 303 items déjà couverts par 3 509 questions, la première question à poser
avant tout appel IA est « existe-t-il déjà des questions non jouées sur cet item ? » — la réponse est oui
dans 99 % des cas (§4.2).

---

## 6. Plan d'action

### 6.1 Corrections, par ordre de rentabilité

| # | Correction | § | Effort | Impact |
|---|---|---|---|---|
| **C1** | `count_evidence()` par alias d'item + dilution accélérée de la graine | 3.1b/c | 1 h | 🔴 évite que deux fiches d'un même item divergent à vie |
| **C2** | Persister les corrections visuelles en attente de validation | 5.2 | 1 h | 🔴 récupère 70 % de la dépense IA |
| **C3** | Conditionner le bonus +35 à `rang_a_conclusive` | 3.7 | 10 min | 🔴 rend le tri de priorité opérant |
| **C4** | Rebaser l'arriéré au lieu de le filtrer (reentry) | 3.9 | 3 h | 🔴 évite la perte silencieuse de cours |
| **C5** | Facteur de fréquence EDNpro dans `_calculate_priority` | 4.4 | 30 min | 🟠 aligne le plan sur ce qui tombe |
| **C6** | Prioriser sur `retention_score` projeté à J+7 | 3.4 | 1 h | 🟠 active le seul modèle d'oubli |
| **C7** | Vue `evidence_unified` + bascule des 4 lecteurs | 3.3 / 3.13 | 4 h | 🟠 supprime la divergence des preuves |
| **C8** | Boost de criticité limité aux arêtes `same_item` | 3.8 | 20 min | 🟠 supprime deux constantes déguisées |
| **C9** | `valide_rang_a` calculé sur les propositions de rang A | 3.12 | 1 h | 🟠 fiabilise les notes affichées |
| **C10** | Brancher `detect_mastery_drift` sur le dashboard | 3.11 | 2 h | 🟠 63 lignes de code mort réveillées |
| **C11** | Présélection locale des candidats de classification | 5.3 | 3 h | 🟡 −85 % de tokens, −latence |
| **C12** | `responseSchema` par tâche, suppression des 3 parseurs | 5.7 | 4 h | 🟡 supprime une classe d'échecs |
| **C13** | Grille tarifaire par modèle exact + tokens affichés | 5.5 | 30 min | 🟡 rend le suivi de coût exact |
| **C14** | `label` ≠ `context` dans le journal IA | 5.6 | 20 min | 🟡 hygiène des journaux |
| **C15** | Durées estimées par régression sur l'historique | 3.10 | 2 h | 🟡 budget quotidien crédible |
| **C16** | SM-2 : grade 2 pénalisant, échec dégressif | 3.6 | 1 h | 🟡 |
| **C17** | `_source_base_stability` tolérante + repli | 3.4 | 10 min | 🟡 évite un plantage d'affichage |

### 6.2 Fonctionnalités proposées

**F1 — « Les 5 du jour » (priorité absolue).**
Une file quotidienne de 5 questions tirées des **594 sessions `draft` déjà payées**, choisies par
`fréquence EDNpro × (100 − rétention projetée) × disponibilité`. Un écran, un bouton, zéro appel IA.
C'est la brique qui ferme la boucle : elle alimente `ai_practice_attempts` → `error_signals` → profil
d'erreurs → lacunes → Tuteur DP, c'est-à-dire six modules déjà écrits qui attendent leur première ligne
de données. *Sans elle, tout le reste de cet audit reste théorique.*

**F2 — « 1 OIC = 1 micro-question ».**
290 objectifs officiels en base, 3 tentatives. Générer (ou piocher) une question par OIC de rang A, et
enregistrer la tentative dans `oic_attempts`. Trois OIC tentés suffisent à rendre le verdict Rang A
concluant (§3.5) — c'est-à-dire à faire exister le seul indicateur du programme réellement adossé au
référentiel officiel. Impact : débloque `score_rang_a`, le badge Rang A, et le bonus de priorité C3.

**F3 — Calibration de la confiance (score de Brier).**
Les sessions enregistrent `confidence` (1-5) et, désormais, un score réel. Mesurer l'écart entre les deux
donne une métrique unique et très parlante : « tu te crois solide sur les items où tu fais 45 % ».
C'est le type de retour qu'aucune plateforme concurrente ne donne, et il est calculable avec les colonnes
existantes dès que F1 produit des données.

**F4 — Projection de note EDN calibrée.**
`project_to_exam()` projette une *couverture*, pas une *note*. Avec le barème R2C déjà implémenté
(§3.12) et les annales UNESS jouées, on peut projeter une note sur 20 avec intervalle de confiance,
pondérée par la fréquence réelle des items. C'est la question que se pose l'utilisateur, et toutes les
briques existent séparément.

**F5 — Vraies arêtes de proximité clinique.**
Remplacer les 14 842 arêtes `same_college` par une similarité calculée sur les intitulés d'OIC
(TF-IDF local, aucun appel réseau, ~200 lignes). Cela rend enfin exploitable le mécanisme de propagation
de criticité de `reviews/service.py` (§3.8), et ouvre la porte aux DP transversaux ciblés.

**F6 — Garde-fou de véracité.**
Bandeau « à vérifier » sur toute question dont `confiance_ia < 0,7` ou `desaccord_officiel = true`, plus
un compteur dans /settings. Le prompt de correction UNESS produit déjà ces champs ; personne ne les lit
(§5.8).

### 6.3 Ordre d'exécution suggéré

```
Semaine 1 : C1 → C3 → C2 → F1          (le moteur mesure, le plan trie, la boucle se ferme)
Semaine 2 : C4 → C5 → C6 → C10          (le plan devient juste et lisible)
Semaine 3 : F2 → C9 → C7                (le Rang A devient réel, les preuves convergent)
Ensuite   : C11-C17, F3 → F4 → F5 → F6
```

---

## 7. Constats d'audits antérieurs revérifiés

Conformément à la règle « vérifier avant d'agir », les items ouverts de
`docs/ROADMAP_BACKEND_ALGOS.md` ont été retestés contre le code du 15/08 :

| Constat antérieur | Statut au 15/08 |
|---|---|
| `edn_weight=0.7` codé en dur au dashboard | ❌ **Périmé** — `_EDN_PRIORITY_WEIGHTS` lit `ednpro_item_frequency` (`_cockpit_today.py:53-64`) |
| `exam_simulator.py:160` force `rank="A"` | ❌ **Périmé** — le rang est lu depuis la proposition (l. 156) |
| Gate `requires_human_validation` inerte | ⚠️ **Partiellement périmé** — il est branché (`gemini_autocorrect.py:224`) mais **détruit la réponse** (§5.2) |
| `insert_error_signal` jamais appelé | ⚠️ **Périmé sur le code** (`attempt_service.py:128`), **exact sur les données** (table vide, §4.1) |
| Jumeau du verrou Rang A dans `mastery.py:279` | ❌ **Périmé** — les deux branches testent `_rang_a_conclusive` (l. 345-351) |
| `error_signals` / `edn_recommendations` vides | ✅ **Confirmé** — 0 ligne chacune |
| `anki_review_evidence` jamais alimentée | ✅ **Confirmé** — 0 ligne, pondération 25 % morte |
| Corrections visuelles : ~50 % d'échec, ~60 s | ⚠️ **Corrigé à la baisse** — 15,9 % d'échec, 24,9 s de moyenne (mesuré sur 63 appels) |

---

## 8. Annexe — requêtes de vérification

```sql
-- §3.1/§3.2 — distribution réelle des scores de maîtrise
SELECT mastery_score, COUNT(*) FROM mastery_snapshots
WHERE week='2026-W33' AND mastery_score IS NOT NULL GROUP BY 1 ORDER BY 1;

-- §3.1 — part des scores adossés à une auto-déclaration
SELECT COUNT(*) FROM mastery_snapshots m JOIN item_state i ON i.course_id=m.course_id
WHERE m.week='2026-W33' AND m.mastery_score IS NOT NULL;

-- §4.2 — état de consommation du corpus de pratique
SELECT practice_kind, completion_state, COUNT(*), SUM(annale_id IS NOT NULL)
FROM ai_practice_sessions GROUP BY 1,2;

-- §5.1 — coût, échecs et latence par tâche IA
SELECT task, model, COUNT(*) n, SUM(error IS NOT NULL AND error<>'') err,
       SUM(input_tokens), SUM(output_tokens), ROUND(SUM(cost_usd),4), ROUND(AVG(duration_ms))
FROM ai_usage_logs GROUP BY 1,2 ORDER BY n DESC;

-- §3.8 — nature réelle du « graphe sémantique »
SELECT edge_type, COUNT(*), ROUND(AVG(weight),3) FROM course_edges GROUP BY 1;

-- §4.4 — pouvoir discriminant des fréquences EDNpro
SELECT priority, COUNT(*), ROUND(AVG(session_count),2) FROM ednpro_item_frequency GROUP BY 1;

-- §3.9 — cycles J complets vs consolidations
SELECT review_type, COUNT(*) FROM review_history GROUP BY 1;

-- §5.6 — contenu clinique écrit dans le journal IA
SELECT task, MAX(LENGTH(context)) FROM ai_usage_logs WHERE context IS NOT NULL GROUP BY 1;
```

---

## 9. Conclusion

Le projet n'a pas un problème d'algorithmes : il a un problème de **circuit**. Les formules sont écrites,
souvent bien écrites — SM-2 modifié, courbe d'oubli à stabilité variable, barème R2C, profilage d'erreurs
explicable, classement gain/effort. Ce qui manque, systématiquement, c'est le fil entre le module qui
produit un signal et celui qui devrait le consommer :

- la maîtrise rejoue une déclaration tant qu'aucune session n'est jouée — et continuera de diverger
  entre les fiches d'un même item même après (§3.1b) ;
- la rétention modélise l'oubli et ne décide de rien ;
- le détecteur de dérive n'a pas d'appelant ;
- la fréquence réelle aux EDN ne pèse pas sur le plan ;
- 594 sessions attendent d'être jouées pendant que le système en génère de nouvelles ;
- et la moitié de la dépense IA sert à produire des corrections qui sont détruites à l'arrivée.

Trois corrections d'une heure chacune (**C1, C2, C3**) et une fonctionnalité d'un jour (**F1**) rebranchent
l'essentiel. Le reste devient alors mesurable — ce qui, aujourd'hui, n'est pas le cas : aucune des
métriques affichées à l'utilisateur ne repose sur une observation de son travail réel.
