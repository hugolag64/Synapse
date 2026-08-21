# Audit complet — Vues QCM & Annales

**Date** : 15 août 2026 · **Version 2** (corrections + décisions actées)
**Périmètre** : `/qcm`, `/annales`, `/annales/{id}`, lecteur React `qcm_app`, moteur de barème, pipeline Gemini de correction UNESS, statistiques adossées aux questions.
**Objectif de référence** : se rapprocher de la difficulté réelle de l'EDN. **Une statistique qui ne change aucune décision de révision est un gadget.**

---

## Table des matières

- [Décisions actées](#décisions-actées)
- [Journal des corrections v1 → v2](#journal-des-corrections-v1--v2)
- [0. Méthode et niveau de preuve](#0-méthode-et-niveau-de-preuve)
- [1. Cartographie du système](#1-cartographie-du-système)
- [2. Photo de la base au 15/08/2026](#2-photo-de-la-base-au-15082026)
- [3. Notation : unifier sur le barème EDN R2C](#3-notation--unifier-sur-le-barème-edn-r2c)
- [4. Fidélité docimologique EDN](#4-fidélité-docimologique-edn)
- [5. Défauts bloquants — fiches détaillées](#5-défauts-bloquants--fiches-détaillées)
- [6. Pipeline Gemini : coût, fiabilité, marges](#6-pipeline-gemini--coût-fiabilité-marges)
- [7. Statistiques sur les questions](#7-statistiques-sur-les-questions)
- [8. UX et parcours utilisateur](#8-ux-et-parcours-utilisateur)
- [9. Couverture de tests](#9-couverture-de-tests)
- [10. Sécurité et intégrité des données](#10-sécurité-et-intégrité-des-données)
- [11. Plan d'exécution par lots](#11-plan-dexécution-par-lots)
- [12. Ce qu'il ne faut pas faire](#12-ce-quil-ne-faut-pas-faire)
- [Annexe A — Requêtes de vérification](#annexe-a--requêtes-de-vérification)
- [Annexe B — Index des fichiers du périmètre](#annexe-b--index-des-fichiers-du-périmètre)
- [Annexe C — Glossaire](#annexe-c--glossaire)

---

## Décisions actées

Prises le 15/08/2026, elles orientent tout le plan d'exécution.

| # | Sujet | Décision |
|---|---|---|
| **1** | **Barème** | Le **barème EDN R2C est le seul barème** dès qu'on fait du QCM ou une annale. L'échelle de maîtrise et le seuil du simulateur relèvent de la **validation d'item** — ils **sortent du périmètre QCM** et ne sont plus considérés comme des systèmes concurrents. |
| **2** | **Types & rang** | Une **QRU doit être notée en QRU**, pas en QRM. Les questions portent normalement la notion de **rang A / rang B** : cette information doit être capturée et exploitée. |
| **3a** | **Correction** | Pas de refonte : le défaut est un **paramètre oublié**, corrigé en 2 lignes. |
| **3b** | **Annales → maîtrise** | Comportement **attendu et déjà obtenu par le passé** : l'import Gemini détermine l'item, l'item nourrit la maîtrise. À **restaurer**. |
| **3c** | **Images / ZAP** | Les images **étaient** importées avec succès. La difficulté réelle portait sur la **Zone à Pointer**, pas sur les images. |
| **4a** | **Clé API** | La clé vit légitimement dans `.env`. Le problème est une **copie fuitée** dans `ai_usage_logs` — à purger. |
| **4b** | **Classification** | **Rester à la granularité question** : une annale couvre souvent un collège entier, voire tout le programme pour une annale EDN. Optimiser la **taille du prompt**, pas le regroupement. |
| **5** | **Durée & chrono** | Mesurer la durée réelle et calibrer le **chronomètre par format d'épreuve**. |
| **6** | **Vérité de correction** | **`reponse_uness` (correction officielle UNESS) fait foi pour le score.** Le verdict IA sert de signal de divergence et d'explication pédagogique — **jamais de note**. |

---

## Journal des corrections v1 → v2

Trois constats de la première version ne résistaient pas à la vérification. Ils sont
corrigés ci-dessous et dans le corps du document.

| Constat v1 | Statut | Réalité vérifiée |
|---|---|---|
| « 63 appels visuels perdus, ≈ 0,68 $ gaspillés » | ❌ **Faux** | Ces 63 appels (1–2 août) ont **réussi** et produit les **55 questions à image** en base. Le blocage date du **7 août** (`979be22`) et **aucun import UNESS n'a tourné depuis le 5 août** : la régression est réelle mais **jamais encore exercée**. Le gâchis est **prospectif**. |
| « Aucune annale ne nourrit la maîtrise (manque de conception) » | ⚠️ **Requalifié** | C'est une **régression datée**. Preuve en base : `qcm_sessions` #172 (1er août, 66,67 %, `course_id` vide) = la session d'annale #115. Le commit `854e332` du **3 août** a ajouté le garde-fou `if not evidence or not session.get("course_id")`. Avant, ça passait. |
| « Deux univers de données : `qcm_sessions` = 7 lignes saisies à la main » | ❌ **Faux** | Les 7 lignes ont toutes `platform = 'Synapse IA'` : `qcm_sessions` est le **registre d'évaluation unifié**, écrit par `record_evaluation` (saisie rapide **et** maîtrise IA). Il n'y a **pas deux univers** : il y a **une seule chaîne dont l'amont est coupé depuis le 3 août**. Ce constat **renforce** [D2](#d2--régression--les-annales-ne-nourrissent-plus-la-maîtrise) au lieu d'être un problème distinct. |
| « Classifier au niveau annale (÷7 d'appels) » | ❌ **Recommandation retirée** | Le code classe déjà **par question** ([`question_item_classifier.py:15`](backend/core/uness/question_item_classifier.py:15)), ce qui est **correct** : une annale EDN couvre tout le programme. Le levier est la **taille du prompt**, pas le regroupement. |

> **Leçon** : quatre affirmations spectaculaires sur cinq venaient d'une lecture du
> code sans recoupement avec l'historique Git ni avec les dates en base. Le
> code seul ne dit pas *quand* un comportement a changé.

---

## 0. Méthode et niveau de preuve

### Ce qui a été fait

1. **Lecture intégrale** des fichiers du périmètre ([annexe B](#annexe-b--index-des-fichiers-du-périmètre)).
2. **Interrogation directe** de `data/synapse_local.db` — aucun chiffre n'est estimé ([annexe A](#annexe-a--requêtes-de-vérification)).
3. **Traçage des chemins d'exécution** de bout en bout, pour distinguer le code exécuté du code mort.
4. **Recoupement avec l'historique Git** — ajouté en v2 après que trois constats se soient révélés être des régressions datées et non des manques de conception.

### Conventions

| Marqueur | Signification |
|---|---|
| ✅ **Vérifié** | Constaté dans le code, confirmé en base **et** daté dans Git quand c'est pertinent |
| ⚠️ **Probable** | Constaté dans le code, non observable en base faute de volume d'usage |
| 💡 **Proposition** | Recommandation, pas un constat |

### Réserves sur les données de référence EDN

Le barème des discordances (1 / 0,5 / 0,2 / 0), les propositions *indispensables* /
*inacceptables* et la distinction rang A / rang B sont les règles R2C, correctement
implémentées là où elles le sont.

**Deux valeurs codées restent sans source identifiée** :

- le seuil de « validation » à **14/20** ([`scoring.py:209`](backend/core/practice/scoring.py:209)) — l'EDN est un concours de **classement**, pas un examen à seuil. À documenter ou retirer.
- les **durées d'épreuve** — le lecteur applique 120 s/question uniformément. À caler sur le règlement en vigueur (décision 5), que cet audit n'a pas vérifié.

---

## 1. Cartographie du système

### 1.1 Les trois sources de questions

```
┌─────────────────────────────────────────────────────────────────┐
│  A. ANNALES UNESS (591 sessions / 98 % du corpus)               │
│  entrainement.uness.fr                                          │
│    └─ scripts/uness/collector.py      → bridge JSON + images    │
│       └─ UNESS/à_vérifier/session-*/                            │
│          └─ gemini_autocorrect.correct_directory()              │
│             └─ Gemini (flash-lite | flash si image)             │
│                └─ gemini_conversion.convert_with_bridge()       │
│                   └─ UNESS/vérifiés/*.json                      │
│                      └─ import_service.import_verified_directory│
│                         └─ ai_practice_sessions (1 / sous-partie)│
├─────────────────────────────────────────────────────────────────┤
│  B. GÉNÉRATION IA (49 appels `qcm`, 6 sessions)                 │
│  practice/service.PracticeService.create_new_session()          │
└─────────────────────────────────────────────────────────────────┘
                              │
                    (session terminée + scorée)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  REGISTRE D'ÉVALUATION UNIFIÉ                                   │
│  practice/mastery.record_ai_practice_mastery()                  │
│    └─ evaluation.service.record_evaluation()                    │
│       └─ local_store.add_qcm_session_full()                     │
│          └─ table qcm_sessions ──► bandeau /qcm, maîtrise item  │
│                                                                 │
│  Second écrivain : saisie rapide manuelle                       │
│  course_quick_actions._open_quick_qcm_dialog                    │
│    └─ record_quick_qcm_result() → même record_evaluation()      │
└─────────────────────────────────────────────────────────────────┘
```

**Correction importante (v2)** : `qcm_sessions` n'est **pas** une table de saisie
manuelle parallèle. C'est le **registre d'évaluation unifié**, alimenté par deux
écrivains qui passent tous deux par `record_evaluation`. La conception est bonne.
Le problème est que **la branche « pratique IA » est coupée depuis le 3 août**
([D2](#d2--régression--les-annales-ne-nourrissent-plus-la-maîtrise)), d'où un
registre à 7 lignes pour 600 sessions.

### 1.2 Les deux lecteurs concurrents

| Lecteur | Fichier | Quand est-il utilisé ? |
|---|---|---|
| **React** (actif) | `qcm_app/src/main.tsx` | Dès que `qcm_app/dist/index.html` existe — **c'est le cas** |
| **NiceGUI** (secours) | `qcm_replay.open_qcm_session` (587 l.) | Uniquement si le bundle manque |

[`practice_session_card.open_node_qcm:15`](frontend/components/practice_session_card.py:15)
teste `QCM_NODE_DIST.exists()`. Le bundle étant présent, **le lecteur NiceGUI
(~590 lignes) n'est jamais exécuté**. Les deux ont des règles différentes : le
NiceGUI exige toutes les réponses avant correction ([`qcm_replay.py:562`](frontend/components/qcm_replay.py:562)),
le React non.

### 1.3 Schéma de données du périmètre

| Table | Lignes | Rôle |
|---|---:|---|
| `ai_practice_sessions` | 600 | Session (= 1 sous-partie d'annale, ou 1 génération IA) |
| `ai_practice_questions` | 3 509 | Énoncé immuable + `import_metadata_json` |
| `ai_practice_session_questions` | — | Liaison (permet le rejeu à l'identique) |
| `ai_practice_attempts` | **37** | Une réponse datée |
| `ai_practice_attempt_propositions` | 35 | Détail propositionnel (sélectionnée / attendue / discordance) |
| `ai_practice_question_items` | 2 967 | Rattachement **question** → item EDN |
| `ai_practice_session_items` | — | Items secondaires d'un DP transverse |
| `ai_practice_anchors` | **0** | Questions ancrées (bouton présent, jamais utilisé) |
| `qcm_sessions` | **7** | **Registre d'évaluation** (sortie de `record_evaluation`) |
| `uness_annales` | 86 | Groupe « partiel » chapeautant n sous-parties |
| `uness_correction_failures` | 2 | Quiz en échec (les 2 résolus) |
| `uness_scanned_catalog` | — | Catalogue d'épreuves détectées non importées |
| `error_signals` | **0** | Profil d'erreurs par item |
| `qcm_results` | 0 | Table morte |
| `ednpro_qcm_sessions` / `_questions` / `_attempts` | 0 / 0 / 0 | Capture EDNpro — jamais alimentée |
| `ednpro_item_frequency` | 367 | Fréquence de chute par item |
| `continuous_exam_sessions` | — | État du « mode concours continu » |

---

## 2. Photo de la base au 15/08/2026

### 2.1 Volumétrie et usage

| Mesure | Valeur | Commentaire |
|---|---:|---|
| Sessions de pratique | **600** | |
| dont rattachées à une annale | **591** (98,5 %) | |
| dont **terminées** | **6** (1,0 %) | |
| dont sessions DP | 44 | **0 terminée** |
| Questions importées | **3 509** | |
| Tentatives enregistrées | **37** | |
| Lignes dans le registre d'évaluation | **7** | dont **1 seule** issue d'une annale (avant la régression du 3 août) |
| Ratio réponses / questions disponibles | **1,05 %** | |

> **Le corpus existe, l'usage n'existe pas.** 3 509 questions EDN en base, 37
> réponses. Ce n'est pas un problème de discipline : trois régressions successives
> (3 août, 7 août) et un paramètre oublié ont coupé, l'une après l'autre, les
> boucles qui rendaient l'effort visible. Un travail qui ne produit aucune trace
> est un travail qu'on ne refait pas.

### 2.2 Granularité des sessions

| Mesure | Valeur |
|---|---:|
| Questions par session (moyenne) | **2,95** |
| Sessions à **1 seule question** | **311** (52 %) |
| Session la plus fournie | 29 questions |
| Annales à ≥ 40 sous-parties | 7 (dont 2 à **58**) |

Un DP d'EDN comporte une quinzaine de questions enchaînées sur une même vignette.
Ici le découpage suit la structure de collecte Moodle, pas celle de l'épreuve :
**un partiel est éclaté en 58 micro-sessions de 3 questions**.

### 2.3 Nature des questions (échantillon de 3 000)

| `type_question` | n | % | Noté correctement ? |
|---|---:|---:|---|
| QRM | 1 439 | 48 % | ✅ oui |
| **QRU** | **747** | **25 %** | ❌ noté comme QRM — [§4.1](#41-les-qru-sont-notées-comme-des-qrm--747-questions) |
| QROC | 383 | 13 % | ❌ non noté — [§4.4](#44-les-qroc-tcs-et-zap-ne-sont-pas-notées) |
| DP | 310 | 10 % | ✅ oui (traité en QRM) |
| TCS | 50 | 2 % | ❌ barème propre non implémenté |
| *(absent → heuristique)* | 44 | 1,5 % | ⚠️ type **deviné**, non tracé |
| QRP/L | 21 | 0,7 % | ❌ traité en QRM |
| KFP | 6 | 0,2 % | ✅ oui |

**Environ 40 % du corpus est noté selon une règle qui n'est pas la sienne.**

### 2.4 Métadonnées critiques absentes

| Donnée | Présence | Impact |
|---|---:|---|
| Rang A / B sur les propositions | **0 / 13 143** | Aucune analyse rang A — alors que **toute la plomberie aval existe** ([§4.3](#43-aucun-rang-ab--0-proposition-sur-13-143--mais-la-plomberie-est-prête)) |
| `indispensable_choices` | **0 / 3 000** | Pénalité absolue jamais déclenchée |
| `inacceptable_choices` | **0 / 3 000** | Idem |
| `duration_seconds` | **0 / 37** | Aucune stat de rythme |
| `course_id` sur sessions d'annale | **0 / 591** | Bloque la maîtrise depuis le 3 août ([D2](#d2--régression--les-annales-ne-nourrissent-plus-la-maîtrise)) |

### 2.5 Images : le corpus visuel existe bel et bien

| Mesure | Valeur |
|---|---:|
| Questions portant au moins une image | **55** |
| Images **`provided_to_ai`** (analysées par Gemini) | **33** |
| Images `not_provided` | 27 |
| Questions `verified` avec image | **30** |
| Questions `unsupported` avec image | 25 |
| Sessions distinctes concernées | 26 |
| Dernier import d'une question à image | **2 août 2026, 09:14** |

Le pipeline visuel **a fonctionné**. Il est bloqué depuis le 7 août
([D4](#d4--régression--le-verrou-de-validation-visuelle-bloque-les-images-depuis-le-7-août)).

### 2.6 Catalogue d'annales

| Mesure | Valeur |
|---|---:|
| Annales importées | 86 |
| **avec au moins une sous-partie** | **35** (41 %) |
| **sans aucune sous-partie → masquées** | **51** (59 %) |
| Type `edn_complet` / `matiere` | 61 / 25 |
| Matière = Cardiologie | 52 |
| **Matière vide** | **9** ← déclenche le repli sur 367 items ([§6.2](#62-pourquoi-la-classification-coûte-si-cher)) |
| Années | 2023 (56), 2024 (12), 2025 (14), 2026 (4) |

---

## 3. Notation : unifier sur le barème EDN R2C

> **Décision 1** — Le barème EDN R2C est le seul barème pour les QCM et les
> annales. L'échelle de maîtrise et le seuil du simulateur relèvent de la
> validation d'item : **hors périmètre**.

### 3.1 Inventaire après application de la décision

**Dans le périmètre — à unifier :**

| # | Système | Emplacement | Règle | Sort |
|---|---|---|---|---|
| 1 | **Barème EDN R2C** | [`practice/scoring.py:102`](backend/core/practice/scoring.py:102) | 0 discordance = 1 pt · 1 = 0,5 · 2 = 0,2 · ≥3 = 0 | ✅ **Devient canonique** |
| 2 | Seuils plateforme | [`qcm/service.py:17`](backend/core/qcm/service.py:17) | PASSÉ ≥ 70 % · LIMITE ≥ 60 % · RATÉ < 60 % | ⚠️ **Dérivé** du score EDN, plus un calcul autonome |
| 4 | Score binaire | [`qcm_replay.py:148`](frontend/components/qcm_replay.py:148) | `correct / total` | ❌ **Supprimé** |

**Hors périmètre — conservés tels quels :**

| # | Système | Emplacement | Domaine |
|---|---|---|---|
| 3 | Échelle de maîtrise (80 / 55 / 30) | [`mastery_indicator.py:28`](frontend/components/mastery_indicator.py:28) | Validation d'item |
| 5 | Seuil « Rang A sécurisé » 75 % | [`exam_simulator_page.py:296`](frontend/pages/exam_simulator_page.py:296) | Validation d'item (et code mort, cf. [D5](#d5--le-simulateur-dépreuve-in-page-est-du-code-mort)) |

### 3.2 La frontière n'est pas étanche — un seul point de conversion

C'est le point d'attention de la décision 1. Le score QCM **sort** du périmètre
pour alimenter la maîtrise :

```
score EDN (/20)  ──► record_evaluation()  ──► qcm_sessions.score_percent
       │                                              │
   périmètre QCM                              validation d'item
   (barème R2C)                               (échelle 80/55/30)
```

💡 **Règle à poser** : la conversion doit avoir **un seul lieu** — la fonction
qui construit l'`EvaluationInput` dans [`practice/mastery.py:47`](backend/core/practice/mastery.py:47) —
et être nommée explicitement. Pas de reconversion implicite à chaque écran.

### 3.3 Contradiction visuelle résiduelle ✅ Vérifié

Dans `qcm_cockpit._draw_row`, deux échelles se croisent sur la même ligne :

```python
# ligne 432 — couleur issue de l'échelle de maîtrise (seuil « correct » = 55)
color = _LEVEL_COLOR.get(_level_from_score(avg), "var(--text-muted)")
...
# ligne 447 — badge issu du seuil plateforme (réussite = 70)
if avg is not None and avg < QCM_PASS_THRESHOLD:
    ui.label("à retravailler").classes("qc-badge")
```

**Un cours à 60 % s'affiche en couleur « correct » avec le badge « à retravailler »
à côté.** Toute la zone 55–70 % est dans cet état.

La décision 1 tranche : sur `/qcm`, **la couleur doit venir du barème EDN**, pas de
l'échelle de maîtrise. `_level_from_score` n'a rien à faire dans le cockpit QCM.

### 3.4 Le bandeau `/qcm` : vide, pas faux ✅ Vérifié — *reformulé en v2*

[`qcm_cockpit._render:676`](frontend/pages/qcm_cockpit.py:676) lit `qcm_sessions`,
le registre d'évaluation. Ce **n'est pas** une erreur de conception : c'est bien la
table qui doit alimenter le bandeau.

Le problème est qu'elle contient **7 lignes pour 600 sessions**, parce que la
branche « pratique IA → maîtrise » est coupée depuis le 3 août. **Réparer
[D2](#d2--régression--les-annales-ne-nourrissent-plus-la-maîtrise) répare
mécaniquement le bandeau.** Aucune refonte n'est nécessaire.

Reste un vrai défaut de conception dans la métrique elle-même : le
« taux de réussite ≥ 70 % » ([`:394`](frontend/pages/qcm_cockpit.py:394)) agrège
des épreuves non comparables — un 68 % sur un DP de cardiologie et un 68 % sur une
série de questions isolées transversale n'ont ni la même difficulté ni la même
valeur prédictive.

### 3.5 Exemple chiffré : la session #1

Session `id=1`, `score_percent = 66,67`, 3 questions.

| Écran | Aujourd'hui | Après décision 1 |
|---|---|---|
| `/qcm` — barre + score | `67 %`, couleur « correct » | `13,3/20`, couleur **barème EDN** |
| `/qcm` — badge | « à retravailler » | cohérent avec la couleur |
| `/annales/{id}` | `Note 13,3/20 (66,67 %)` | inchangé ✅ |
| Lecteur React | `13.3 / 20` · `2/3 bonnes réponses` · `66.67%` | `13,3/20` en principal |
| `qcm/service.score_label` | `LIMITE` | dérivé du score EDN |
| `mastery_indicator` | niveau `correct` | **hors périmètre** — validation d'item |

---

## 4. Fidélité docimologique EDN

### 4.1 Les QRU sont notées comme des QRM — 747 questions ✅ Vérifié

> **Décision 2** — une QRU doit être notée en QRU.

**Cause** — [`import_service._to_practice_question:503`](backend/core/uness/import_service.py:503)
réduit le type à deux valeurs :

```python
kind = QuestionKind.CLOSED if len(question.propositions) >= 2 else QuestionKind.OPEN
```

Le vrai type est pourtant **conservé** dans `import_metadata.uness.question.type_question`
([`import_service.py:454`](backend/core/uness/import_service.py:454)). Mais
[`attempt_service._question_kind:16`](backend/core/practice/attempt_service.py:16)
ne le lit jamais :

```python
raw = str(question.get("question_kind") or question.get("kind") or "QRM").upper()
return "QRU" if raw in {"QRU", "SINGLE"} else "QRM"
# reçoit toujours "CLOSED" → retourne toujours "QRM"
```

**Effet chiffré** — QRU à 1 bonne réponse attendue, l'étudiant coche 1 mauvaise proposition :

| | Discordances | Barème appliqué | Points |
|---|---:|---|---:|
| Réalité EDN (QRU) | — | tout ou rien | **0** |
| Code actuel (QRM) | 2 (1 omission + 1 excès) | grille discordances | **0,2** |

**💡 Correctif** :

```python
_UNESS_TO_SCORING_KIND = {
    "QRU": "QRU",
    "QRM": "QRM", "QRP/L": "QRM", "DP": "QRM", "KFP": "QRM",
}

def _question_kind(question: dict[str, Any]) -> str:
    uness_type = str(
        ((question.get("uness") or {}).get("question") or {}).get("type_question") or ""
    ).upper()
    if uness_type in _UNESS_TO_SCORING_KIND:
        return _UNESS_TO_SCORING_KIND[uness_type]
    raw = str(question.get("question_kind") or question.get("kind") or "QRM").upper()
    return "QRU" if raw in {"QRU", "SINGLE"} else "QRM"
```

### 4.2 Les pénalités absolues n'existent nulle part ✅ Vérifié

[`scoring.compute_question_score_edn:130-153`](backend/core/practice/scoring.py:130)
implémente **correctement** les deux règles couperet :

```python
missing_indispensables = indisp_set - user_set
if missing_indispensables:
    return {"score": 0.0, ..., "zero_reason": "indispensable_manquante"}

selected_inacceptables = inacc_set & user_set
if selected_inacceptables:
    return {"score": 0.0, ..., "zero_reason": "inacceptable_cochee"}
```

Mais [`attempt_service._question_constraint:20`](backend/core/practice/attempt_service.py:20)
cherche ces champs dans la question et dans `question["uness"]` — **et ils ne sont
renseignés nulle part**. Mesure : **0 / 3 000**.

Le tooltip de la correction ([`qcm_replay.py:317`](frontend/components/qcm_replay.py:317))
l'assume honnêtement — mais **la moitié la plus discriminante de la docimologie EDN
est absente**.

### 4.3 Aucun rang A/B — 0 proposition sur 13 143 — mais la plomberie est prête ✅ Vérifié

> **Décision 2** — le rang doit être capturé et exploité.

**Bonne nouvelle confirmée en v2 : toute la chaîne aval existe déjà.**

| Étage | Emplacement | État |
|---|---|---|
| Modèle d'évaluation | [`evaluation/models.py:28-32`](backend/core/evaluation/models.py:28) — `rank_a_questions`, `rank_a_correct`, `rank_b_*`, `rank_unknown_questions` | ✅ présent |
| Persistance | [`evaluation/service.py:35-39`](backend/core/evaluation/service.py:35) | ✅ écrit |
| Schéma SQL | `qcm_sessions.rank_a_questions` etc. ([`local_store.py:3517`](backend/core/reviews/local_store.py:3517)) | ✅ colonnes créées |
| Détail propositionnel | `ai_practice_attempt_propositions.rank` | ✅ colonne créée |
| Affichage | [`qcm_replay.py:364`](frontend/components/qcm_replay.py:364), [`main.tsx:293`](qcm_app/src/main.tsx:293), [`exam_simulator_page.py:235`](frontend/pages/exam_simulator_page.py:235) | ✅ prêt |
| **Source de la donnée** | `prompts/uness_correction_prompt.txt` | ❌ **le rang n'est jamais demandé** |

Mesure : les 7 lignes de `qcm_sessions` ont toutes `rank_a_questions = NULL`.

**Nuance à respecter** : la correction Moodle n'expose pas toujours le rang dans le
HTML. Il faut donc distinguer un rang **lu** d'un rang **inféré** :

```json
"rank": "A" | "B" | null,
"rank_source": "html" | "inféré"
```

Sans cette distinction, un rang deviné par le modèle contaminerait l'indicateur
« sécurisation rang A », qui est justement celui qui doit être fiable.

**Coût** : une passe de re-correction, ~90 appels flash-lite, ordre de grandeur 0,5 $.

### 4.4 Les QROC, TCS et ZAP ne sont pas notées ✅ Vérifié

> **Décision 3c** — la vraie difficulté était la Zone à Pointer, pas les images.
> C'est confirmé.

**633 questions ouvertes** en base (dont 383 QROC typées).

[`api/qcm.save_attempt:217`](backend/api/qcm.py:217) les enregistre avec
`score_percent=None`. Puis [`local_store.finalize_ai_practice_session:3009`](backend/core/reviews/local_store.py:3009) :

```python
scored = [row["score_percent"] for row in latest if row["score_percent"] is not None]
score = round(sum(scored) / len(scored), 2)
```

Elles sont **exclues du dénominateur**. Une session à moitié QROC est notée sur la
moitié de ses questions — signalé seulement par une mention discrète dans la
correction NiceGUI (le lecteur mort).

**La Zone à Pointer** est le cas le plus net.
[`gemini_conversion.py:24`](backend/core/uness/gemini_conversion.py:24) :

```python
_SHORT_ANSWER_TYPES = {"shortanswer"}
_ZONE_TYPES = {"qzone"}
...
if raw_type in _SHORT_ANSWER_TYPES or raw_type in _ZONE_TYPES:
    return "QROC"          # ← la ZAP devient une saisie libre
```

Le lecteur React l'assume explicitement ([`main.tsx:210`](qcm_app/src/main.tsx:210)) :
« *Réponse ouverte / QROC / Zone à désigner (saisie libre)* ». Une ZAP est donc
posée comme une question texte, et n'est pas notée.

Les **50 TCS** posent un problème distinct : leur barème repose sur une échelle de
Likert et une réponse modale de panel. Traités comme des QCM ordinaires, le score
produit n'a pas de sens.

**💡 Options, par coût croissant** :

| Option | Portée | Effort |
|---|---|---|
| **Afficher le dénominateur réel** (« noté sur 7 des 12 ») | Toutes | Minimal — à faire de toute façon |
| **Auto-évaluation guidée** après affichage de la réponse attendue | QROC, ZAP, TCS | Faible |
| **Notation IA** de la réponse libre | QROC | Élevé — à réserver |
| **ZAP native** (clic sur zone d'image) | ZAP | Élevé — nécessite les coordonnées, absentes du bridge |

### 4.5 Les propositions « incertaines » comptent comme fausses ✅ Vérifié

> **Décision 6** — `reponse_uness` fait foi ; une incertitude n'est pas une faute.

[`scoring._choice_data:29`](backend/core/practice/scoring.py:29) :

```python
expected = bool(raw.get("reponse_uness", raw.get("is_correct", raw.get("correct", False))))
```

Quand [`gemini_conversion._proposition:126`](backend/core/uness/gemini_conversion.py:126)
a classé la proposition `incertain`, `reponse_uness` vaut `None`. `bool(None)` →
`False` → traitée comme **« non attendue »**. Une incertitude *de correction*
devient une **faute de l'étudiant**.

**💡 Correctif** : trois états (`attendue` / `non attendue` / `inconnue`) et
**exclusion des propositions inconnues du calcul de discordance**.

### 4.6 Le chronomètre n'est pas calibré et ne contraint rien ✅ Vérifié

> **Décision 5** — chronomètre calibré par format d'épreuve.

[`qcm_app/src/main.tsx:119`](qcm_app/src/main.tsx:119) :

```typescript
const totalSeconds = useMemo(() => payload.questions.length * 120, [payload.questions.length])
```

**120 secondes par question, uniformément.** Et à l'expiration ([`:126`](qcm_app/src/main.tsx:126)) :

```typescript
if (prev <= 1) { clearInterval(timer); return 0 }
```

**Rien ne se passe.** Ni soumission automatique, ni alerte, ni verrouillage.

**💡 Correctif** : durée paramétrée **par format** (à caler sur le règlement en
vigueur), barre de progression temporelle, et à 0 : verrouillage + finalisation.

### 4.7 Robustesse de l'appariement des réponses ⚠️ Probable

Deux normalisations cohabitent :

| Fonction | Normalisation |
|---|---|
| [`scoring._selected_ids:52`](backend/core/practice/scoring.py:52) | `.casefold()` seul |
| [`qcm_replay._norm:16`](frontend/components/qcm_replay.py:16) | `re.sub(r"\s+", " ", ...).strip().lower()` |

Les deux lisent la même source (`proposition.texte`), donc le risque est faible
aujourd'hui. Mais une proposition contenant un retour à la ligne ferait échouer
l'appariement côté scoring → réponse comptée **non sélectionnée** → discordances
fantômes. **Une seule fonction de normalisation partagée.**

---

## 5. Défauts bloquants — fiches détaillées

### D1 — « Voir la correction » rouvre la session en mode réponse

| | |
|---|---|
| **Gravité** | 🔴 Critique — fonctionnalité inatteignable |
| **Statut** | ✅ Vérifié |
| **Nature** | Paramètre oublié — **pas un problème de conception** (décision 3a) |
| **Effort** | **2 lignes** |

Le paramètre existe ([`practice_session_card.py:15`](frontend/components/practice_session_card.py:15)) :

```python
def open_node_qcm(session_id: int, exam: bool = False, correction: bool = False) -> bool:
    ...
    if correction:
        suffix += "&correction=1"
```

Il est correctement utilisé dans [`ai_practice_panel.py:164`](frontend/components/ai_practice_panel.py:164) :
```python
if open_node_qcm(session_id, correction=True):
```

Mais **omis** dans les deux écrans principaux :
- [`qcm_cockpit.py:470`](frontend/pages/qcm_cockpit.py:470) — `if open_node_qcm(session_id):`
- [`annale_detail.py:349`](frontend/pages/annale_detail.py:349) — `if open_node_qcm(session_id):`

Côté React ([`main.tsx:307`](qcm_app/src/main.tsx:307)), sans `?correction=1` :
```typescript
const load = wantsCorrection ? fetchCorrection(sessionId) : fetchSession(sessionId)
```
→ rend le **Reader**.

**Correctif** : ajouter `correction=True` aux deux appels.

---

### D2 — RÉGRESSION : les annales ne nourrissent plus la maîtrise

| | |
|---|---|
| **Gravité** | 🔴 Critique — 98 % du corpus déconnecté |
| **Statut** | ✅ Vérifié **et daté** |
| **Nature** | **Régression du 3 août 2026** (`854e332`) — le comportement attendu existait avant |
| **Effort** | ~1 h |

**Ce qui marchait** — commit `c27ccf2` (29 juillet, *« feed AI practice scores into mastery »*) :

```python
elif kind in {"qcm", "dp", "kfp"}:
    evaluation = EvaluationInput(
        source="qcm",
        course_id=session["course_id"],     # "" accepté
        item_number=session["item_number"],
        ...
    )
```

**Preuve en base** : `qcm_sessions` **#172** — `platform='Synapse IA'`,
`course_id=''`, `item_number=''`, `score_percent=66.67`, `session_date='2026-08-01'`.
C'est la session d'annale **#115** (`DFGSM3_UE13.S6_Infectieux_2_220525 – mDP1`,
`annale_id=28`, score 66,67). **Une annale a bien nourri la maîtrise le 1er août.**

**Ce qui l'a cassé** — commit `854e332` (3 août, *« record practice mastery per
linked question item »*), [`practice/mastery.py:41-44`](backend/core/practice/mastery.py:41) :

```python
elif kind in {"qcm", "dp", "kfp"}:
    evidence = get_session_item_evidence(session_id)
    if not evidence or not session.get("course_id"):   # ← ajouté
        return None
```

Le refactor a introduit l'évidence **par question** (une bonne chose : il gère les
DP transverses) mais a **ajouté au passage** une exigence sur `course_id` qui
n'existait pas. Or **`course_id` est vide sur 591 sessions d'annale sur 591** — une
annale UNESS n'a pas de cours Notion associé, par construction.

**Conséquence en cascade** : plus de mise à jour de `item_state`, ni de
`mastery_snapshots`, ni du registre `qcm_sessions` — donc bandeau `/qcm` vide
([§3.4](#34-le-bandeau-qcm--vide-pas-faux--vérifié--reformulé-en-v2)).

**Correctif** (décision 3b — restaurer) : l'évidence par item **suffit**. `course_id`
n'a pas à être exigé pour une session d'annale :

```python
evidence = get_session_item_evidence(session_id)
if not evidence:
    return None
# course_id reste facultatif : une annale UNESS n'a pas de cours Notion.
```

---

### D3 — 51 annales sur 86 sont invisibles, sans explication

| | |
|---|---|
| **Gravité** | 🟠 Élevée — perte de confiance dans l'import |
| **Statut** | ✅ Vérifié |
| **Effort** | ~2 h |

[`annales.py:71`](frontend/pages/annales.py:71) :

```python
def _displayable_annales(rows: list[dict]) -> list[dict]:
    """Keep only annale groups with at least one imported sub-part."""
    return [row for row in rows if int(row.get("total_parts") or 0) > 0]
```

**51 annales sur 86 (59 %) ont zéro sous-partie** → filtrées silencieusement.
Le compteur de la page (`« Épreuves EDN · {len(rows)} »`, [`:664`](frontend/pages/annales.py:664))
affiche un total amputé sans le dire.

**Correctif** : les afficher avec un état **« collecte incomplète »**, un lien vers
la source et un bouton « relancer la collecte ». Un import à moitié raté doit être
visible et réparable.

---

### D4 — RÉGRESSION : le verrou de validation visuelle bloque les images depuis le 7 août

| | |
|---|---|
| **Gravité** | 🔴 Critique — mais **jamais encore exercée** |
| **Statut** | ✅ Vérifié **et daté** |
| **Nature** | **Régression du 7 août 2026** (`979be22`) |
| **Effort** | ~½ journée |

> **Correction v2** — la v1 affirmait « 63 appels perdus, ≈ 0,68 $ gaspillés ».
> **C'était faux.**

**Ce qui marchait** (décision 3c confirmée) — les 63 appels `uness_correction_visual`
des 1–2 août ont **réussi** et produit :

| Mesure | Valeur |
|---|---:|
| Questions à image importées | **55** |
| Images effectivement analysées (`provided_to_ai`) | **33** |
| Questions `verified` avec image | **30** |
| Dernier import à image | **2 août, 09:14** |

**Ce qui l'a cassé** — commit `979be22` (7 août, *« fix: require human validation
for visual UNESS corrections »*), [`ai/tasks.py:64-72`](backend/core/ai/tasks.py:64) :

```python
task = AITask.UNESS_CORRECTION_VISUAL if images else AITask.UNESS_CORRECTION
response = (service or _default_service()).generate(task, prompt, ..., images=images, ...)
return UnessCorrectionResult(
    response=response,
    requires_human_validation=bool(images),     # ← toujours True dès qu'il y a une image
    status="pending_human_validation" if images else "final",
)
```

[`gemini_autocorrect._correct_one_quiz:224`](backend/core/uness/gemini_autocorrect.py:224)
le transforme en **échec** :

```python
if response.requires_human_validation:
    return (None, "Correction visuelle générée : validation humaine requise avant import.", ...)
```

Le `None` signifie « échec » pour l'appelant ([`:301`](backend/core/uness/gemini_autocorrect.py:301)),
qui enregistre une ligne dans `uness_correction_failures` — **après avoir payé
l'appel**, et sur le modèle Flash (le plus cher), puisque
[`routing.model_for_task:73`](backend/core/ai/routing.py:73) route
`UNESS_CORRECTION_VISUAL` vers `AIModel.FLASH`.

**Pourquoi personne ne l'a vu** : **aucun import UNESS n'a tourné depuis le 5 août**
(dernier appel `uness_correction` en base). La régression dort. **Le prochain
partiel à images sera payé et rejeté.**

**Le défaut symétrique, lui, est de conception** — [`_quiz_images:57`](backend/core/uness/gemini_autocorrect.py:57) :

```python
candidate = folder / Path(filename).name
mime_type = _IMAGE_MIME_TYPES.get(candidate.suffix.lower())
if mime_type is None or not candidate.is_file():
    missing.append(str(filename))
    continue        # ← l'image absente sort de la liste
```

Image **absente du disque** → `images` vide → `bool(images)` faux → tâche
non-visuelle → **le quiz est corrigé à l'aveugle et importé**. Avertissement limité
à `"Images manquantes (ignorées)"` ([`:254`](backend/core/uness/gemini_autocorrect.py:254)).
C'est ce qui explique les **27 images `not_provided`** et les **25 questions
`unsupported`** en base.

| Situation | Comportement actuel | Cible |
|---|---|---|
| Image **présente** | ❌ Appel payé, quiz **rejeté** (depuis le 7 août) | ✅ Importer + drapeau « à valider » |
| Image **absente** | ❌ Corrigé **à l'aveugle** et importé | ✅ **Refuser** l'import |

---

### D5 — Le simulateur d'épreuve in-page est du code mort

| | |
|---|---|
| **Gravité** | 🟠 Élevée — ~150 lignes mortes |
| **Statut** | ✅ Vérifié |
| **Effort** | décision de conception (Lot 5) |

[`exam_simulator_page._start_exam:112-172`](frontend/pages/exam_simulator_page.py:112)
construit une session puis :

```python
session_id = create_ai_practice_session(spec=spec, questions=all_questions, model="exam-simulator-node")
ui.navigate.to(f"/qcm-app/?session={session_id}&exam=1")
```

`state["active_session"]` n'est **jamais** mis à `True`, `state["dps"]` jamais rempli.
Or [`_refresh_ui:64`](frontend/pages/exam_simulator_page.py:64) :

```python
if not state["active_session"]:
    _render_setup_view()
elif state["finished"]:
    _render_debrief_view()      # ← inatteignable
else:
    _render_exam_view()         # ← inatteignable
```

**Code mort** : `_render_exam_view` (:174), `_validate_and_advance` (:254),
`_next_question` (:265), `_render_debrief_view` (:280).

**Ce qui est perdu avec** : le seul **débriefing par discordance** de l'application
([:311](frontend/pages/exam_simulator_page.py:311)), le seul affichage de **badge de
rang** ([:235](frontend/pages/exam_simulator_page.py:235)), et l'anti-retour
côté serveur.

**Conséquence** : `compute_edn_score` ([`exam_simulator.py:60`](backend/core/uness/exam_simulator.py:60))
n'a plus qu'un appelant, lui-même mort — pourtant couvert par un test vert
([§9.2](#92-angles-morts)).

---

### D6 — Le profil d'erreurs est vide

| | |
|---|---|
| **Gravité** | 🟠 Élevée |
| **Statut** | ⚠️ Probable — à revérifier après usage réel |

`error_signals` = **0 ligne**.

Le correctif est en place — [`attempt_service.record_error_signals_for_attempt:87`](backend/core/practice/attempt_service.py:87)
retombe sur l'item de la session quand la question n'est pas classée :

```python
item_rows = local_store.get_ai_practice_question_items(question_id)
if not item_rows:
    item_rows = _session_item_fallback(session_id)
if not item_rows:
    logger.warning("Signal d'erreur abandonné : ni la question {} ni sa session ne portent d'item", question_id)
    return
```

Les 6 sessions terminées sont **antérieures** à ce correctif. L'absence de lignes
ne prouve donc pas que le bug persiste. **À revérifier après la première session
post-correctif** : le Tuteur DP ([`practice/service.create_tutor_dp_session:305`](backend/core/practice/service.py:305))
consomme `errors` et en dépend.

---

### D7 — Le mode « Anti-Biais » n'agit que sur `/annales`

| | |
|---|---|
| **Gravité** | 🟡 Moyenne · **Statut** ✅ Vérifié · **Effort** ~1 h |

`data_store.preferences["exam_mode"]` est écrit dans [`annales.py:520`](frontend/pages/annales.py:520)
et lu **uniquement** dans `annales.py:683, 685, 693` et `annale_detail.py:394, 407`.

Pas dans `/qcm`, pas dans les fiches item, pas dans le lecteur React. Les scores
restent visibles à un clic : le masquage donne l'illusion de protéger de l'ancrage.

---

### D8 — La durée est affichée mais jamais mesurée

| | |
|---|---|
| **Gravité** | 🟠 Élevée (stat EDN la plus utile) · **Statut** ✅ Vérifié · **Effort** ~2 h |

**Chaîne d'affichage complète et fonctionnelle** :

| Étage | Emplacement |
|---|---|
| Agrégation SQL | [`local_store.py:2822`](backend/core/reviews/local_store.py:2822) — `SUM(latest.duration_seconds)` |
| Formatage | [`qcm_cockpit._format_duration:138`](frontend/pages/qcm_cockpit.py:138) |
| Affichage `/qcm` | [`qcm_cockpit._history_metadata:158`](frontend/pages/qcm_cockpit.py:158) |
| Affichage annale | [`annale_detail.py:146`](frontend/pages/annale_detail.py:146) |
| Historique item | [`ai_practice_panel.py:385`](frontend/components/ai_practice_panel.py:385) |

**Chaîne de collecte : inexistante.** Ni [`api/qcm.py:208`](backend/api/qcm.py:208),
ni [`:217`](backend/api/qcm.py:217), ni [`qcm_replay._save:488`](frontend/components/qcm_replay.py:488)
n'envoient `duration_seconds`. Le lecteur React ne mesure rien.

**Mesure** : `NULL` sur **37 tentatives sur 37**.

---

### D9 — Copie de la clé API Gemini dans la base

| | |
|---|---|
| **Gravité** | 🔴 Critique · **Statut** ✅ Vérifié · **Effort** ~15 min |

> **Précision (décision 4a)** — la clé vit **légitimement** dans `.env`. Ce n'est
> pas le problème. Le problème est une **copie** qui a fuité ailleurs.

Quand Gemini renvoyait un 429, `requests` plaçait l'URL complète — **clé comprise** —
dans le message d'exception, journalisé tel quel. `ai_usage_logs` contient
**7 lignes** de la forme `...:generateContent?key=AQ...`.

La redaction existe et **fonctionne aujourd'hui** —
[`gemini_client._redact_provider_secrets:29`](backend/core/ai/gemini_client.py:29) :

```python
return re.sub(r"([?&]key=)[^&\s]+", r"\1***", str(message))
```

Ces lignes lui sont **antérieures** (1–2 août). Le risque résiduel tient à ce que le
fichier `.db` peut être copié, sauvegardé ou partagé.

**Actions** :

```bash
# 1. Purger la base
sqlite3 "data/synapse_local.db" "UPDATE ai_usage_logs SET error = '429 Too Many Requests (URL expurgée)' WHERE error LIKE '%key=%';"

# 2. Vérifier les journaux fichiers
grep -rl "key=AQ" logs/
```

**3.** Rotation de la clé dans la console Google — conseillée, mais appréciation
personnelle : le risque est faible si la base n'a jamais quitté la machine.

---

### D10 — Divergence entre la réponse notée et la réponse affichée

| | |
|---|---|
| **Gravité** | 🟡 Moyenne · **Statut** ⚠️ Probable · **Effort** ~2 h |

> **Décision 6** — `reponse_uness` (correction officielle UNESS) fait foi pour le
> score. Le verdict IA est un signal, jamais une note.

[`import_service._question_metadata:429-430`](backend/core/uness/import_service.py:429)
construit **deux** corrections :

```python
primary_answer  = _choice_answers(question, official=False)   # verdict IA / validé
official_answer = _choice_answers(question, official=True)    # reponse_uness
```

L'écran affiche `primary` comme « Réponse correcte »
([`_to_practice_question:507`](backend/core/uness/import_service.py:507)), tandis que
le **score** est calculé sur `reponse_uness`
([`scoring._choice_data:29`](backend/core/practice/scoring.py:29)).

En cas de désaccord — cas explicitement prévu, signalé par le badge
« ⚠ Divergence UNESS » — **l'étudiant peut être noté faux sur une réponse que
l'écran lui présente comme correcte**.

**Cible, par cas** :

| Cas | Aujourd'hui | Cible (décision 6) |
|---|---|---|
| Officiel disponible, IA d'accord | Score officiel, affichage IA | Score **et** affichage sur l'officiel |
| Officiel ≠ IA | Divergence signalée, mais l'écran montre la réponse IA comme « la correcte » | **Les deux affichées**, l'officielle marquée « fait foi » ; l'avis IA en commentaire pédagogique |
| Officiel absent (`incertain`) | Compté **faux** ([§4.5](#45-les-propositions--incertaines--comptent-comme-fausses)) | Proposition **neutralisée** — hors calcul de discordance |

---

### Récapitulatif

| # | Défaut | Gravité | Nature | Effort |
|---|---|---|---|---|
| D1 | Correction inatteignable | 🔴 | Paramètre oublié | 2 lignes |
| D2 | Annales ≠ maîtrise | 🔴 | **Régression 03/08** (`854e332`) | 1 h |
| D4 | Verrou visuel + images aveugles | 🔴 | **Régression 07/08** (`979be22`) + défaut de conception | ½ j |
| D9 | Copie de clé API en base | 🔴 | Fuite historique | 15 min |
| D3 | 51 annales invisibles | 🟠 | Conception | 2 h |
| D5 | Simulateur mort | 🟠 | Conception | Lot 5 |
| D6 | Profil d'erreurs vide | 🟠 | À revérifier | — |
| D8 | Durée jamais mesurée | 🟠 | Chaîne incomplète | 2 h |
| D7 | Anti-Biais partiel | 🟡 | Conception | 1 h |
| D10 | Réponse notée ≠ affichée | 🟡 | Conception | 2 h |

> **Trois des quatre défauts critiques sont des régressions des 3 et 7 août.**
> Ce ne sont pas des fonctionnalités manquantes : ce sont des fonctionnalités
> **perdues**, chacune introduite par un commit qui améliorait autre chose.

---

## 6. Pipeline Gemini : coût, fiabilité, marges

### 6.1 Consommation réelle mesurée (`ai_usage_logs`)

| Tâche | Modèle | Appels | Tokens entrée | Tokens sortie | Ratio E/S | Période |
|---|---|---:|---:|---:|---:|---|
| `item_classification` | flash-lite | 579 | **1 426 986** | 18 143 | **79 : 1** | 03/08 → 11/08 |
| `uness_correction` | flash-lite | 90 | 458 362 | 319 197 | 1,4 : 1 | 01/08 → 05/08 |
| `uness_correction_visual` | flash | 63 | 253 056 | 183 207 | 1,4 : 1 | 01/08 → 02/08 ✅ *réussis* |
| `qcm` (génération) | flash-lite | 49 | 47 476 | 25 452 | 1,9 : 1 | 01/08 → 07/08 |
| `item_classification` | flash | 38 | 18 966 | 1 578 | 12 : 1 | passe de correction |
| `dp` | flash | 4 | 1 952 | 6 174 | — | |
| `gemini_generate` | flash-lite | 4 | 10 511 | 19 743 | — | |
| **Total** | | **827** | **≈ 2 217 000** | **≈ 573 000** | | |

Coût estimé (tarifs relevés dans [`annales.py:97`](frontend/pages/annales.py:97) :
0,50 $/M entrée, 3,00 $/M sortie) : ≈ **2,8 $** au total.

> **Correction v2** : les 63 appels visuels **ne sont pas perdus**. Ils ont produit
> les 55 questions à image du corpus. Le gâchis à venir concerne les **prochains**
> imports ([D4](#d4--régression--le-verrou-de-validation-visuelle-bloque-les-images-depuis-le-7-août)).

**Constat dominant** : **84 % des tokens d'entrée servent à classifier des items**,
pour 18 k tokens de sortie. Un ratio 79:1 signale un prompt massif réémis à chaque appel.

### 6.2 Pourquoi la classification coûte si cher

> **Décision 4b** — rester à la granularité **question**. La recommandation v1
> (« classifier au niveau annale ») est **retirée**.

La classification opère à **deux niveaux**, et c'est correct :

| Niveau | Fonction | Rôle |
|---|---|---|
| Sous-partie | [`import_service._classify_exam_items:614`](backend/core/uness/import_service.py:614) | Item principal de la session |
| **Question** | [`question_item_classifier.classify_exam_questions:15`](backend/core/uness/question_item_classifier.py:15) | Item(s) de chaque question, plafonné à **2** |

C'est nécessaire : une annale de matière couvre un collège entier, une annale EDN
couvre tout le programme. Regrouper détruirait la finesse — et c'est justement cette
finesse qui alimente `get_session_item_evidence`.

**Le vrai coût est la taille du prompt.** [`item_classifier._build_prompt:42`](backend/core/uness/item_classifier.py:42)
envoie la liste complète des candidats :

```python
candidate_lines = "\n".join(f"- {c['item']} : {c['title']}" for c in candidates)
```

Et [`candidate_items_for_college:38`](backend/core/uness/item_classifier.py:38)
retombe sur les **367 items** dès que la matière n'est pas reconnue :

```python
if college_label:
    scoped = [e for e in all_items() if college_full(e.get("college", "")) == college_label]
    if scoped:
        return scoped
return all_items()      # ← 367 items
```

Or **9 annales ont une matière vide**, et les libellés libres ne matchent pas
toujours `_ABBR_TO_NOTION`. À ~2 300 tokens/appel × 617 appels, on retrouve
exactement le 1,45 M mesuré.

### 6.3 💡 Trois optimisations qui préservent la granularité question

| # | Optimisation | Gain | Risque |
|---|---|---|---|
| 1 | **Pré-filtre local** — TF-IDF énoncé+titre contre les 367 intitulés, ne transmettre que les ~15 meilleurs candidats | **÷ 15 sur le prompt** (~1,3 M tokens) | Nul : le garde-fou « choisis exclusivement dans la liste » ([`:87`](backend/core/uness/item_classifier.py:87)) reste actif |
| 2 | **Réparer le mapping matière → collège** — les 9 matières vides déclenchent le repli sur 367 | Supprime les pires appels | Nul |
| 3 | **Cache de contexte Gemini** sur la liste d'items (elle ne change jamais) | Marginal après 1+2 | Nul |

### 6.4 Ce qui fonctionne bien (à ne pas casser)

| Mécanisme | Emplacement | Pourquoi |
|---|---|---|
| **Compactage HTML Moodle** | [`_clean_moodle_html:89`](backend/core/uness/gemini_autocorrect.py:89) | Décompose la navigation, reconstruit un JSON compact. C'est ce qui rend la correction abordable (ratio 1,4:1 au lieu de ~20:1). |
| **Contrôle de complétude** | [`_expected_question_count:159`](backend/core/uness/gemini_autocorrect.py:159) + [`:237`](backend/core/uness/gemini_autocorrect.py:237) | A attrapé la seule vraie perte de données historique (`uness_correction_failures` #1 : « Réponse incomplète : 2/3 questions »). |
| **Parsing tolérant** | [`_parsed_response:76`](backend/core/uness/gemini_autocorrect.py:76) | `raw_decode` accepte du texte après un JSON valide — comportement réellement observé. |
| **Normalisation de titre** | [`_normalize_title:267`](backend/core/uness/gemini_conversion.py:267) | Gemini renvoie souvent la première ligne seule (`"mDP1\nTest"` → `"mDP1"`). |
| **Filtrage de l'artefact vignette** | [`convert_with_bridge:299`](backend/core/uness/gemini_conversion.py:299) | Écarte la vignette clinique renvoyée comme « question ». |
| **Isolation des erreurs par quiz** | [`_correct_one_quiz:258`](backend/core/uness/gemini_autocorrect.py:258) | Un quiz en erreur ne tue plus le lot. |
| **Neutralisation des verdicts non étayés** | [`_sanitize_unsupported_propositions:158`](backend/core/uness/gemini_conversion.py:158) | Efface un verdict produit sans l'image requise. Cohérent avec la décision 6. |

### 6.5 Fragilités

| # | Fragilité | Emplacement | Détail |
|---|---|---|---|
| F1 | **Deux couches de retry non coordonnées** | [`gemini_autocorrect.py:201`](backend/core/uness/gemini_autocorrect.py:201) + [`gemini_client.py:93`](backend/core/ai/gemini_client.py:93) | Le client retente déjà 3× ; l'autocorrect ajoute 5 tentatives avec `time.sleep(10·n)` → jusqu'à **100 s de blocage synchrone** et **15 appels** pour un seul quiz. |
| F2 | **Réponse tronquée non récupérable** | [`gemini_client.py:118`](backend/core/ai/gemini_client.py:118) | `MAX_TOKENS` lève correctement, mais rien ne redécoupe le quiz pour réessayer. |
| F3 | **Pas de vérification d'appariement titre↔réponse** | [`convert_with_bridge:287`](backend/core/uness/gemini_conversion.py:287) | Un `quiz_title` erroné mais présent dans le bridge fusionne avec le mauvais quiz, sans alerte. |
| F4 | **Fallback de type silencieux** | [`_type_question:100`](backend/core/uness/gemini_conversion.py:100) | 44 questions ont un type **deviné** (`QRU` si ≤ 1 bonne réponse). Rien ne l'indique en aval — problème direct pour la décision 2. |
| F5 | **Placeholder de métadonnées non suivi** | [`gemini_conversion.py:29`](backend/core/uness/gemini_conversion.py:29) | `metadonnees_a_verifier` est bien posé ([:329](backend/core/uness/gemini_conversion.py:329)) mais **aucun écran ne liste les annales incomplètes** → les 9 matières vides. |

### 6.6 Le prompt de correction : ce qu'il faut y ajouter

`prompts/uness_correction_prompt.txt` (5,5 ko) est de bonne facture : schéma strict,
verdict IA distinct de la correction officielle, désaccord explicite avec
commentaire obligatoire, gestion documentée des médias.

Ajouts, par ordre d'impact :

| Priorité | Champ | Débloque | Décision |
|---|---|---|---|
| **1** | `"rank": "A" \| "B" \| null` **par proposition** | Toute l'analyse rang A | 2 |
| **1 bis** | `"rank_source": "html" \| "inféré"` | Empêche un rang deviné de contaminer l'indicateur | 2 |
| 2 | `"indispensable": bool` / `"inacceptable": bool` | Les pénalités absolues ([§4.2](#42-les-pénalités-absolues-nexistent-nulle-part)) | 1 |
| 3 | `"type_question_source": "html" \| "inféré"` | Rend visible le fallback F4 | 2 |
| 4 | `"oic_codes": [...]` par question | Rattachement fin aux objectifs | — |

---

## 7. Statistiques sur les questions

### 7.1 Inventaire : collecté vs exploité

| Donnée | Stockée ? | Exploitée ? | Détail |
|---|:---:|:---:|---|
| Discordance par proposition | ✅ | ❌ | Affichée question par question, **jamais agrégée** |
| `type_question` | ✅ | ❌ | Ni pour la note ([§4.1](#41-les-qru-sont-notées-comme-des-qrm--747-questions)), ni pour les stats |
| Rang A / B | ❌ | — | 0 / 13 143 — **plomberie aval complète** |
| Catégorie d'erreur | ✅ | ❌ | `error_signals` vide |
| Durée par question | ❌ | *affichée* | 0 / 37 ([D8](#d8--la-durée-est-affichée-mais-jamais-mesurée)) |
| Fréquence EDNpro | ✅ | ⚠️ | 367 items — sur `/items`, `/colleges`, fiche cours — **pas sur `/qcm` ni `/annales`** |
| Ancrages | ✅ | ❌ | **0 ligne**, bouton présent ([`qcm_replay.py:520`](frontend/components/qcm_replay.py:520)) |
| Confiance de classification | ✅ | ✅ | Pondération dans [`item_evidence.py:41`](backend/core/practice/item_evidence.py:41) — **bon point** |
| Désaccord IA / UNESS | ✅ | ✅ | Badge « ⚠ Divergence UNESS » — **bon point** |

### 7.2 Ce qui est affiché et ne décide rien

| Métrique | Emplacement | Pourquoi c'est un gadget |
|---|---|---|
| « QCM faits cette semaine » vs objectif 3 | [`stats.py:726`](frontend/pages/stats.py:726) | Compte des cases cochées dans Notion (`qcm_done`), pas des performances |
| « QCM réussi / moyen / raté » | [`stats.py:511`](frontend/pages/stats.py:511) | Auto-déclaratif, 3 crans, non relié au barème |
| « Taux de réussite ≥ 70 % » | [`qcm_cockpit.py:394`](frontend/pages/qcm_cockpit.py:394) | Agrège des épreuves non comparables |
| « n/m sous-parties » | [`annales.py:688`](frontend/pages/annales.py:688) | Mesure l'avancement de l'**import**, pas l'apprentissage |

### 7.3 💡 Les cinq statistiques qui changeraient une décision

| # | Indicateur | Définition | Prérequis | Décision déclenchée |
|---|---|---|---|---|
| 1 | **Sécurisation rang A** | % de propositions rang A vraies effectivement cochées, par item — **en ne comptant que les rangs `rank_source = "html"`** | Décision 2 | *Cet item est-il sûr pour le concours ?* |
| 2 | **Profil de discordance** | Ratio `omission` / `exces` | **Aucun** — donnée en base | *Je révise* (omission) vs *j'apprends à me retenir* (excès) |
| 3 | **Rythme réel vs cible** | Secondes/question par format | [D8](#d8--la-durée-est-affichée-mais-jamais-mesurée) | *Je sais, mais trop lentement* |
| 4 | **Couverture × fréquence** | Items « indispensables » EDNpro **et** jamais travaillés | **Aucun** — 367 × 303 items en base | *Voilà quoi bosser demain* |
| 5 | **Courbe de reprise** | Score au rejeu d'une même session à J+n | **Aucun** — `replay_ai_practice_session` existe | *Est-ce que ça tient ?* |

**Trois des cinq (2, 4, 5) sont réalisables immédiatement**, sans appel IA ni
migration. Le n° 4 n'est qu'une jointure entre `ednpro_item_frequency` (367) et
`ai_practice_question_items` (303 items distincts couverts).

### 7.4 La fréquence EDNpro : disponible et non branchée

`ednpro_item_frequency` contient pour les **367 items** : `priority`
(`indispensable` / `jamais_tombe`), `session_count`, `question_count`, `years_json`.

Le composant `ednpro_frequency_badge` est branché sur
[`items.py:370`](frontend/pages/items.py:370),
[`colleges_cockpit.py:681`](frontend/pages/colleges_cockpit.py:681) et
[`course_detail_cockpit.py:462`](frontend/pages/course_detail_cockpit.py:462) —
**mais ni sur `/qcm` ni sur `/annales`**. L'information « ceci tombe tous les ans »
n'atteint jamais l'écran où l'on choisit quoi travailler.

---

## 8. UX et parcours utilisateur

### 8.1 Friction, par ordre de coût

| # | Friction | Preuve | Effet |
|---|---|---|---|
| 1 | **Granularité absurde** | 311 sessions à 1 question ; 2 annales à 58 sous-parties | Le « mode concours continu » ([`annale_detail.py:287`](frontend/pages/annale_detail.py:287)) enchaîne **58 dialogues** |
| 2 | **Six points d'entrée** | [`qcm_cockpit.py:380`](frontend/pages/qcm_cockpit.py:380) (4) + [`annales.py:551`](frontend/pages/annales.py:551) (1) + [`exam_simulator_page.py:106`](frontend/pages/exam_simulator_page.py:106) (1) | Aucun ne dit **quoi** travailler |
| 3 | **Aucun tri par urgence** | [`annales.py:657`](frontend/pages/annales.py:657) trie par titre | Le choix repose sur la mémoire |
| 4 | **Bandeau vide** | [§3.4](#34-le-bandeau-qcm--vide-pas-faux--vérifié--reformulé-en-v2) | Les chiffres du haut ne bougent pas — **corrigé par D2** |
| 5 | **Suppression irréversible** | [`annales.py:697`](frontend/pages/annales.py:697) | Emporte sous-parties et historique, sans annulation |
| 6 | **Deux lecteurs divergents** | [§1.2](#12-les-deux-lecteurs-concurrents) | Règles de finalisation différentes |
| 7 | **Picker limité à 8 résultats** | [`qcm_cockpit.py:125`](frontend/pages/qcm_cockpit.py:125) (`limit: int = 8`) | Sans indication qu'il y en a d'autres |
| 8 | **Filtre statut construit, jamais branché** | [`qcm_cockpit.py:108`](frontend/pages/qcm_cockpit.py:108) `HISTORY_STATUS_OPTIONS` ; [`:611`](frontend/pages/qcm_cockpit.py:611) force `status="all"` | Le filtre À faire / Terminées est inaccessible |

### 8.2 Le parcours idéal, aujourd'hui impossible

> « J'ai 45 minutes. Fais-moi travailler ce qui tombe le plus à l'EDN et que je
> maîtrise le moins, en conditions d'épreuve, puis dis-moi ce que j'ai raté et
> pourquoi. »

| Brique | État |
|---|---|
| Corpus de questions EDN | ✅ 3 509 questions |
| Fréquence de chute par item | ✅ `ednpro_item_frequency` (367) |
| Niveau de maîtrise par item | ⚠️ `item_state` (146) — privé de sa source par [D2](#d2--régression--les-annales-ne-nourrissent-plus-la-maîtrise) |
| Composition d'une épreuve calibrée | ❌ **manquant** |
| Chronomètre par format | ❌ 120 s uniformes |
| Anti-retour | ⚠️ visuel seulement |
| Débriefing par discordance | ❌ code mort ([D5](#d5--le-simulateur-dépreuve-in-page-est-du-code-mort)) |
| Débriefing par rang | ❌ pas de rang ([§4.3](#43-aucun-rang-ab--0-proposition-sur-13-143--mais-la-plomberie-est-prête)) |

**Toutes les données existent. Il manque la brique de composition et le débriefing.**

---

## 9. Couverture de tests

44 fichiers couvrent le périmètre — bonne couverture **en surface**, angles morts
alignés sur les défauts trouvés.

### 9.1 Ce qui est couvert

| Domaine | Fichiers |
|---|---|
| Barème | `test_practice_scoring.py`, `test_scoring_edn.py`, `test_exam_simulator_scoring.py` |
| API QCM | `test_qcm_api.py`, `test_qcm_api_completion.py` |
| Rejeu / correction | `test_qcm_replay.py`, `test_qcm_cockpit_replay.py`, `test_qcm_cockpit_persistence.py` |
| Import UNESS | `test_uness_import.py`, `test_gemini_conversion.py`, `test_uness_models.py`, `test_uness_normalizer.py` |
| Correction Gemini | `test_gemini_autocorrect.py`, `test_gemini_client.py`, `test_uness_correction_failures.py` |
| Pages | `test_annales_page.py`, `test_annale_detail_page.py`, `test_qcm_cockpit_ui.py` |
| Maîtrise | `test_practice_mastery.py`, `test_practice_question_items.py` |

### 9.2 Angles morts

Chacun correspond exactement à un défaut réel de cet audit.

| Angle mort | Défaut non détecté |
|---|---|
| Rien ne vérifie que `type_question` **traverse** l'import jusqu'au scoring | [§4.1](#41-les-qru-sont-notées-comme-des-qrm--747-questions) — 747 QRU mal notées |
| Rien ne vérifie que `correction=True` est passé depuis `/qcm` et `/annales` | [D1](#d1--voir-la-correction-rouvre-la-session-en-mode-réponse) |
| Rien ne vérifie qu'une session **d'annale** produit un enregistrement de maîtrise | [D2](#d2--régression--les-annales-ne-nourrissent-plus-la-maîtrise) — `test_practice_mastery.py` teste avec un `course_id` renseigné |
| `test_exam_simulator_scoring.py` teste `compute_edn_score` — fonction **morte** | [D5](#d5--le-simulateur-dépreuve-in-page-est-du-code-mort) : test vert sur du code inatteignable |
| Rien ne distingue image **présente** vs **absente** | [D4](#d4--régression--le-verrou-de-validation-visuelle-bloque-les-images-depuis-le-7-août) |
| Aucun test de cohérence inter-écrans sur l'unité de score | [§3](#3-notation--unifier-sur-le-barème-edn-r2c) |

> **Leçon transversale** : les tests valident chaque brique isolément et aucune
> **jonction**. Les quatre défauts 🔴 sont tous des défauts de jonction — et trois
> d'entre eux ont été **introduits par des commits accompagnés de tests verts**
> (`854e332` et `979be22` ajoutaient chacun leurs propres tests).

**💡 Trois tests de non-régression à écrire en priorité** :

```python
def test_annale_session_records_mastery_without_course_id(): ...   # verrouille D2
def test_qru_question_is_scored_all_or_nothing(): ...              # verrouille §4.1
def test_quiz_with_local_image_is_imported(): ...                  # verrouille D4
```

---

## 10. Sécurité et intégrité des données

| # | Point | Gravité | Détail |
|---|---|---|---|
| S1 | **Copie de clé API en base** | 🔴 | 7 lignes dans `ai_usage_logs` — cf. [D9](#d9--copie-de-la-clé-api-gemini-dans-la-base). La clé dans `.env` est légitime. |
| S2 | **Suppression en cascade sans annulation** | 🟠 | `delete_uness_annale` emporte sessions, tentatives, corrections |
| S3 | **Aucune sauvegarde de `synapse_local.db`** | 🟠 | Relevé le 2 août, toujours ouvert. 3 509 questions et tout l'historique sur un fichier unique. |
| S4 | `ui.html(..., sanitize=False)` | 🟡 | [`exam_simulator_page.py:237`](frontend/pages/exam_simulator_page.py:237) — contenu local, et code mort |
| S5 | **Exposition d'images par chemin** | ✅ | **Bien géré** : [`api/qcm.py:190`](backend/api/qcm.py:190) passe par `resolve_local_media_path` |
| S6 | Sous-process sans timeout | 🟡 | [`annales.py:232`](frontend/pages/annales.py:232) et [`:432`](frontend/pages/annales.py:432) |

---

## 11. Plan d'exécution par lots

Ordonné par **rendement** : chaque lot rend le suivant mesurable.

### Lot 1 — Restaurer ce qui marchait
**≈ 1 journée · 0 appel IA**

Trois des quatre actions sont des **retours en arrière ciblés** sur des régressions
datées, pas des développements.

| Action | Fichier | Critère d'acceptation |
|---|---|---|
| Passer `correction=True` | `qcm_cockpit.py:470`, `annale_detail.py:349` | Depuis `/qcm`, « Voir la correction » ouvre la correction |
| **Restaurer** la maîtrise depuis les annales (D2) | `practice/mastery.py:43` | Terminer une sous-partie crée une ligne `qcm_sessions` **et** un `mastery_snapshot` ; le bandeau `/qcm` bouge |
| **Lever** le verrou visuel (D4) | `ai/tasks.py:70`, `gemini_autocorrect.py:224` | Un quiz à image présente s'importe avec un drapeau « à valider » |
| **Refuser** l'import quand l'image manque (D4) | `gemini_autocorrect._quiz_images:57` | Plus de correction à l'aveugle |
| Envoyer `duration_seconds` | `qcm_app/src/main.tsx`, `api/qcm.py:200` | Non nul sur toute nouvelle tentative |
| Purger la copie de clé | SQL + `logs/` | `SELECT COUNT(*) ... WHERE error LIKE '%key=%'` → 0 |
| Écrire les 3 tests de non-régression | `tests/` | Les trois passent, et échouent si on remet les gardes |
| Revérifier `error_signals` | — | Non vide après 1 session jouée |

### Lot 2 — Unifier la notation sur le barème EDN R2C
**≈ 1 journée · 0 appel IA · décisions 1, 2, 6**

| Action | Critère d'acceptation |
|---|---|
| Créer `format_edn_score()` — point d'entrée unique d'affichage | Aucun écran du périmètre ne calcule un score localement |
| Brancher `/qcm`, `/annales`, `annale_detail`, API, lecteur | La session #1 affiche **la même note** partout |
| Retirer `_level_from_score` du cockpit QCM | Plus aucune ligne « correct + à retravailler » |
| Supprimer `build_session_result` (score binaire) | Référence disparue du code |
| **Nommer le point de conversion** vers la validation d'item | Un seul lieu, dans `practice/mastery.py` |
| **QRU notée en QRU** ([§4.1](#41-les-qru-sont-notées-comme-des-qrm--747-questions)) | Une QRU ratée = 0, pas 0,2 |
| **Neutraliser les propositions incertaines** ([§4.5](#45-les-propositions--incertaines--comptent-comme-fausses)) | `reponse_uness IS NULL` hors discordances |
| **`reponse_uness` fait foi** ([D10](#d10--divergence-entre-la-réponse-notée-et-la-réponse-affichée)) | Score et affichage sur la même source ; les deux montrées si divergence |
| Afficher le **dénominateur réel** quand des QROC sont exclues | « noté sur 7 des 12 questions » |
| Documenter ou retirer le seuil 14/20 | Décision tracée |

### Lot 3 — Rang A et pénalités absolues
**≈ 1 journée + 1 passe de re-correction (~0,5 $) · décision 2**

| Action | Critère d'acceptation |
|---|---|
| Ajouter `rank` + `rank_source` au prompt | Schéma JSON mis à jour |
| Propager : `gemini_conversion._proposition` → `models.py:274` → `import_service._question_metadata` → `ai_practice_attempt_propositions.rank` | Le rang arrive jusqu'à l'affichage |
| Alimenter `rank_a_questions` / `rank_a_correct` dans `EvaluationInput` | **Plomberie déjà en place** — ne reste que le remplissage |
| Re-corriger les annales importées | > 80 % des propositions portent un rang ; part `rank_source="html"` mesurée |
| Ajouter `indispensable` / `inacceptable` et **activer** les pénalités | Une indispensable omise → 0 pt (**le code existe déjà**) |
| Indicateur « sécurisation rang A » (rangs `html` uniquement) | Visible sur `/qcm` et `/items` |

### Lot 4 — Coût Gemini
**≈ ½ journée · décision 4b**

| Action | Gain |
|---|---|
| **Pré-filtre local** des candidats (367 → ~15), granularité question conservée | ÷ 15 sur le prompt |
| **Réparer le mapping matière → collège** (9 matières vides) | Supprime les pires appels |
| Unifier les deux couches de retry 429 (F1) | Supprime jusqu'à 100 s de blocage/quiz |
| Écran « annales à métadonnées incomplètes » (F5) | Résout la cause des matières vides |
| Tracer `type_question_source` (F4) | Rend visibles les 44 types devinés |

### Lot 5 — Composition d'épreuve
**≈ 2 jours · décision 5**

Remplace le simulateur mort ([D5](#d5--le-simulateur-dépreuve-in-page-est-du-code-mort)).

| Brique | Détail |
|---|---|
| Choix du **format** | DP ×3 / série de questions isolées / mixte |
| **Sélection** | `fréquence EDNpro × faiblesse mesurée × ancienneté` dans les 3 509 questions |
| **Chronomètre par format**, avec verrouillage et finalisation à 0 | |
| **Anti-retour** côté serveur | |
| **Débriefing** par discordance **et** par rang | Récupérer la logique de `_render_debrief_view` **avant** de la supprimer |

Effet secondaire : rend jouables comme épreuve unique les 58 sous-parties d'un partiel.

### Lot 6 — Réparation du catalogue
**≈ ½ journée**

| Action | Critère |
|---|---|
| Afficher les 51 annales sans sous-partie (D3) | Les 86 sont visibles, les incomplètes marquées |
| Bouton « relancer la collecte » | Une annale incomplète est réparable sans ligne de commande |
| Étendre `exam_mode` à `/qcm`, fiches item, lecteur (D7) | Le masquage devient effectif |

### Lot 7 — Statistiques utiles
**≈ 1 journée · 0 appel IA**

Les cinq indicateurs de [§7.3](#73--les-cinq-statistiques-qui-changeraient-une-décision).
Commencer par le **n° 4 (couverture × fréquence)** : simple jointure, et c'est celui
qui répond directement à « je bosse quoi demain ? ». Brancher au passage le badge de
fréquence EDNpro sur `/qcm` et `/annales`.

---

## 12. Ce qu'il ne faut pas faire

| ❌ Anti-action | Pourquoi |
|---|---|
| **Ajouter des compteurs hebdomadaires** | [`stats.py:726`](frontend/pages/stats.py:726) en a déjà, sans information sur le niveau |
| **Refondre le bandeau `/qcm`** | Il n'est pas faux, il est **vide**. Réparer D2 suffit. |
| **Refondre le flux de correction** | C'est un paramètre oublié, 2 lignes (décision 3a) |
| **Classifier au niveau annale** | Une annale EDN couvre tout le programme (décision 4b) |
| **Multiplier les seuils de couleur** | Le problème n'est pas qu'il en manque |
| **Générer plus de questions par IA** | 3 509 dorment. Le goulot est le chemin d'usage, pas le stock. |
| **Réparer le lecteur NiceGUI** | ~590 lignes jamais exécutées : le supprimer ou l'assumer, pas les deux |
| **Faire confiance à un test vert** | Trois régressions critiques sont arrivées **avec** leurs tests verts ([§9.2](#92-angles-morts)) |

---

## Annexe A — Requêtes de vérification

```sql
-- §2.1 Volumétrie et usage
SELECT COUNT(*) FROM ai_practice_sessions;                                    -- 600
SELECT COUNT(*) FROM ai_practice_sessions WHERE annale_id IS NOT NULL;        -- 591
SELECT practice_kind, COUNT(*) n, SUM(completed_at IS NOT NULL) done
  FROM ai_practice_sessions GROUP BY 1;                                       -- QCM 556/6, DP 44/0
SELECT COUNT(*) FROM ai_practice_questions;                                   -- 3509
SELECT COUNT(*) FROM ai_practice_attempts;                                    -- 37
SELECT COUNT(*) FROM error_signals;                                           -- 0
SELECT COUNT(*) FROM ai_practice_anchors;                                     -- 0

-- §1.1 / §3.4 Le registre d'évaluation (correction v2)
SELECT id, platform, course_id, item_number, score_percent, rank_a_questions, session_date
  FROM qcm_sessions;
-- 7 lignes, TOUTES platform='Synapse IA' → registre, pas saisie manuelle
-- #172 : course_id='', 66.67, 2026-08-01 → l'annale #115, avant la régression du 3/08

-- §2.2 Granularité
SELECT AVG(total_questions), MIN(total_questions), MAX(total_questions)
  FROM ai_practice_sessions;                                                  -- 2.95 / 1 / 29
SELECT COUNT(*) FROM ai_practice_sessions WHERE total_questions <= 1;         -- 311

-- §2.4 Métadonnées absentes
SELECT COUNT(*) FROM ai_practice_attempts WHERE duration_seconds IS NOT NULL; -- 0
SELECT COUNT(*) FROM ai_practice_sessions
  WHERE annale_id IS NOT NULL AND TRIM(COALESCE(course_id,'')) = '';          -- 591

-- §2.6 Catalogue
SELECT CASE WHEN n > 0 THEN 'avec parts' ELSE 'sans parts' END, COUNT(*)
  FROM (SELECT a.id,
               (SELECT COUNT(*) FROM ai_practice_sessions s WHERE s.annale_id = a.id) n
        FROM uness_annales a)
  GROUP BY 1;                                                                 -- avec 35 / sans 51

-- §6.1 Consommation Gemini (avec période — décisif pour dater les régressions)
SELECT task, model, COUNT(*) n, SUM(input_tokens), SUM(output_tokens),
       MIN(created_at), MAX(created_at)
  FROM ai_usage_logs GROUP BY 1, 2 ORDER BY 3 DESC;
-- uness_correction_visual : 63 appels, 01/08 → 02/08 → ANTÉRIEURS au verrou du 07/08

-- D9 Fuite de clé
SELECT COUNT(*) FROM ai_usage_logs WHERE error LIKE '%key=%';                 -- 7
```

**Datation des régressions** — indispensable, c'est ce qui manquait à la v1 :

```bash
git log --oneline -L 41,45:backend/core/practice/mastery.py   # → 854e332 (03/08) puis c27ccf2 (29/07)
git log --oneline -S "requires_human_validation" -- backend/core/ai/tasks.py  # → 979be22 (07/08)
git show -s --format="%h %ad %s" --date=short 854e332 979be22 c27ccf2
```

**Types de question, rang et images** (non requêtable en SQL pur) :

```python
import sqlite3, json, collections
con = sqlite3.connect("data/synapse_local.db"); con.row_factory = sqlite3.Row
tq, ranks, props, imgs = collections.Counter(), 0, 0, collections.Counter()
for r in con.execute("SELECT import_metadata_json FROM ai_practice_questions LIMIT 3000"):
    u = (json.loads(r[0] or "{}").get("uness") or {})
    q = u.get("question") or {}
    tq[q.get("type_question")] += 1
    for p in u.get("propositions") or []:
        props += 1
        if p.get("rank") or p.get("rang"):
            ranks += 1
    for i in q.get("images") or []:
        imgs[(i.get("metadata") or {}).get("verification_status")] += 1
print(tq.most_common())   # QRM 1439, QRU 747, QROC 383, DP 310, TCS 50, None 44, QRP/L 21, KFP 6
print(props, ranks)       # 13143 propositions, 0 avec rang
print(imgs)               # provided_to_ai 33, not_provided 27
```

---

## Annexe B — Index des fichiers du périmètre

### Frontend

| Fichier | Lignes | Rôle | État |
|---|---:|---|---|
| [`frontend/pages/qcm_cockpit.py`](frontend/pages/qcm_cockpit.py) | 686 | Vue `/qcm` | Actif — [D1](#d1--voir-la-correction-rouvre-la-session-en-mode-réponse), [§3.3](#33-contradiction-visuelle-résiduelle--vérifié) |
| [`frontend/pages/annales.py`](frontend/pages/annales.py) | 711 | Vue `/annales` + import | Actif — [D3](#d3--51-annales-sur-86-sont-invisibles-sans-explication) |
| [`frontend/pages/annale_detail.py`](frontend/pages/annale_detail.py) | 428 | Vue `/annales/{id}` | Actif — [D1](#d1--voir-la-correction-rouvre-la-session-en-mode-réponse) |
| [`frontend/pages/exam_simulator_page.py`](frontend/pages/exam_simulator_page.py) | 321 | Onglet « Examens Blancs » | **~150 l. mortes** — [D5](#d5--le-simulateur-dépreuve-in-page-est-du-code-mort) |
| [`frontend/components/qcm_replay.py`](frontend/components/qcm_replay.py) | 587 | Lecteur + correction NiceGUI | **Secours jamais exécuté** |
| [`frontend/components/practice_session_card.py`](frontend/components/practice_session_card.py) | 63 | Boutons + routage lecteur | Actif |
| [`frontend/components/ai_practice_panel.py`](frontend/components/ai_practice_panel.py) | 603 | Génération IA depuis une fiche cours | Actif — seul appelant correct de `correction=True` |
| [`frontend/components/course_quick_actions.py`](frontend/components/course_quick_actions.py) | 1 200+ | Saisie rapide QCM (2ᵉ écrivain du registre) | Actif |
| [`frontend/components/ednpro_frequency_badge.py`](frontend/components/ednpro_frequency_badge.py) | 70 | Badge de fréquence | Actif — **non branché sur `/qcm`** |
| [`qcm_app/src/main.tsx`](qcm_app/src/main.tsx) | 325 | Lecteur React | **Actif (chemin réel)** |
| [`qcm_app/src/components/MedicalImageViewer.tsx`](qcm_app/src/components/MedicalImageViewer.tsx) | 130 | Visionneuse d'images | Actif |

### Backend

| Fichier | Lignes | Rôle | État |
|---|---:|---|---|
| [`backend/api/qcm.py`](backend/api/qcm.py) | 284 | API du lecteur React | Actif |
| [`backend/core/practice/scoring.py`](backend/core/practice/scoring.py) | 218 | **Barème EDN canonique** | Actif — correct mais sous-alimenté |
| [`backend/core/practice/attempt_service.py`](backend/core/practice/attempt_service.py) | 135 | Persistance d'une réponse | Actif — [§4.1](#41-les-qru-sont-notées-comme-des-qrm--747-questions) |
| [`backend/core/practice/mastery.py`](backend/core/practice/mastery.py) | 67 | Pont vers la maîtrise | Actif — **[D2](#d2--régression--les-annales-ne-nourrissent-plus-la-maîtrise) (régression 03/08)** |
| [`backend/core/practice/item_evidence.py`](backend/core/practice/item_evidence.py) | 58 | Agrégation par item | Actif — bon |
| [`backend/core/evaluation/service.py`](backend/core/evaluation/service.py) | 74 | Registre d'évaluation unifié | Actif — bon |
| [`backend/core/evaluation/models.py`](backend/core/evaluation/models.py) | 69 | `EvaluationInput` (rang inclus) | Actif — **plomberie rang prête** |
| [`backend/core/qcm/service.py`](backend/core/qcm/service.py) | 165 | Seuils et couleurs | Actif — à dériver du barème |
| [`backend/core/uness/gemini_autocorrect.py`](backend/core/uness/gemini_autocorrect.py) | 412 | Orchestration correction | Actif — **[D4](#d4--régression--le-verrou-de-validation-visuelle-bloque-les-images-depuis-le-7-août) (régression 07/08)** |
| [`backend/core/uness/gemini_conversion.py`](backend/core/uness/gemini_conversion.py) | 350 | Fusion réponse IA ↔ bridge | Actif — bon ; ZAP → QROC ([§4.4](#44-les-qroc-tcs-et-zap-ne-sont-pas-notées)) |
| [`backend/core/uness/import_service.py`](backend/core/uness/import_service.py) | 759 | Import canonique | Actif — [§4.1](#41-les-qru-sont-notées-comme-des-qrm--747-questions), [D10](#d10--divergence-entre-la-réponse-notée-et-la-réponse-affichée) |
| [`backend/core/uness/item_classifier.py`](backend/core/uness/item_classifier.py) | 89 | Classification (prompt) | Actif — [§6.2](#62-pourquoi-la-classification-coûte-si-cher) |
| [`backend/core/uness/question_item_classifier.py`](backend/core/uness/question_item_classifier.py) | 36 | Classification **par question** | Actif — **conception correcte** |
| [`backend/core/uness/exam_simulator.py`](backend/core/uness/exam_simulator.py) | 248 | Chargement DP + score | **Partiellement mort** |
| [`backend/core/ai/tasks.py`](backend/core/ai/tasks.py) | 144 | Points d'entrée IA | Actif — [D4](#d4--régression--le-verrou-de-validation-visuelle-bloque-les-images-depuis-le-7-août) |
| [`backend/core/ai/gemini_client.py`](backend/core/ai/gemini_client.py) | 161 | Transport HTTP | Actif |
| [`backend/core/reviews/local_store.py`](backend/core/reviews/local_store.py) | 5 692 | Persistance | Actif |
| `prompts/uness_correction_prompt.txt` | 5,5 ko | Prompt de correction | Actif — [§6.6](#66-le-prompt-de-correction--ce-quil-faut-y-ajouter) |

### Commits de référence

| Commit | Date | Effet |
|---|---|---|
| `c27ccf2` | 29/07 | *feed AI practice scores into mastery* — **branche la maîtrise** |
| `854e332` | 03/08 | *record practice mastery per linked question item* — **casse D2** |
| `979be22` | 07/08 | *require human validation for visual UNESS corrections* — **casse D4** |

---

## Annexe C — Glossaire

| Terme | Définition |
|---|---|
| **Discordance** | Écart entre les propositions cochées et l'ensemble attendu (différence symétrique). Une omission et un excès comptent chacun pour 1. |
| **QRU** | Question à réponse unique — barème tout ou rien. |
| **QRM** | Question à réponses multiples — barème par discordances (1 / 0,5 / 0,2 / 0). |
| **QROC** | Question à réponse ouverte et courte. |
| **ZAP** | Zone à pointer — désignation d'une zone sur une image. Actuellement dégradée en QROC. |
| **TCS** | Test de concordance de script — barème propre par réponse modale de panel. |
| **QRP/L** | Question à réponse à partir d'une liste. |
| **DP** | Dossier progressif — vignette clinique suivie de questions enchaînées. |
| **KFP** | Key Feature Problem. |
| **Proposition indispensable** | Proposition vraie dont l'omission annule la question (0 pt). |
| **Proposition inacceptable** | Proposition fausse dont la sélection annule la question (0 pt). |
| **Rang A / Rang B** | Niveau attendu : A = socle exigible de tous, B = approfondissement de spécialité. |
| **Bridge** | JSON produit par le collecteur, associant le HTML Moodle brut d'un quiz à ses images téléchargées. |
| **Sous-partie** | Une session Synapse = un quiz Moodle d'un partiel. Jusqu'à 58 par partiel. |
| **Registre d'évaluation** | Table `qcm_sessions`, alimentée par `record_evaluation` — sortie commune de la pratique IA et de la saisie rapide. |

---

*Audit v2 réalisé le 15 août 2026 sur la branche `main` (dernier commit `8ee6909`).
Mesures issues de `data/synapse_local.db` à cette date, régressions datées via `git log`.*
