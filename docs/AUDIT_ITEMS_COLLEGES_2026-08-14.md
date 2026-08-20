# Audit complet — vues « Items » et « Collèges »

**Date** : 14 août 2026
**Périmètre** : `/items`, `/colleges`, `/cours/{id}` (fiche item) et toute la chaîne backend qui les alimente
**Méthode** : lecture de code **+ rejeu des pipelines sur les données réelles** (`data_cache.json` du 9 août 2026, `data/synapse_local.db`)
**Statut du code au moment de l'audit** : `main`, commit `8ee6909`

---

## 1. Résumé exécutif

Trois écrans partagent le même objet métier — l'item EDN — et en donnent **trois lectures différentes**.

Le problème dominant n'est pas cosmétique : **la vue Collèges n'affiche aucune maîtrise**, parce qu'elle dérive la maîtrise des `ReviewTask` et que le moteur en produit **0** sur la base actuelle. La moitié droite du tableau (Retard, Fragiles, Prochaine, Maîtrise, Statut) et la totalité des KPI du panneau Pilotage sont donc à zéro ou vides, sans qu'aucun élément d'interface ne signale que la donnée est absente plutôt que bonne.

Le second axe est le **mapping item → collège**. Le référentiel réellement utilisé (`items_edn.json`) est une projection à un seul collège d'un référentiel où 98 items sur 367 en ont plusieurs. Elle est en désaccord avec les données Notion sur **82 items** — et ce sont les données Notion qui ont raison. Ce mapping pilote le fil d'Ariane de la fiche item (125 fiches renvoient vers un collège qui ne les contient pas) et le choix de la « fiche canonique » d'un item.

Le reste — dédoublonnage incohérent entre les deux listes, filtres inertes, statut « Maîtrisé » non colorié, recalcul intégral à chaque clic — est réel mais secondaire tant que les deux premiers points ne sont pas traités.

**Chiffres clés mesurés**

| Mesure | Valeur |
|---|---|
| Cours en base | 707 (582 avec collège **et** numéro d'item) |
| Items EDN distincts couverts | 365 / 367 |
| Items ayant plusieurs fiches | 162 (115×2, 39×3, 8×4) |
| `ReviewTask` générées (contexte collège) | **0** |
| Cours avec une maîtrise connue — vue Collèges | **0 / 582** |
| Cours avec une maîtrise connue — vue Items | 97 / 582 (100 % issus d'un niveau déclaré) |
| Cours avec `date_1ere_lecture` | 8 / 707 |
| Items déclarés perdant leur niveau par la règle « à préparer » | 50 / 146 |
| Lignes en double dans `/items` | 217 |
| Items dont le collège de référence n'existe sur aucune fiche | 82 (125 fiches) |
| Collèges retenus par le filtre « Sans PDF » | 39 / 39 |
| Tests existants sur ces modules | 44, **tous au vert** |

---

## 2. Méthode

Chaque constat de ce document est soit une lecture directe du code (référence `fichier:ligne`), soit une **mesure reproductible** obtenue en rejouant le code de production dans le venv du projet, sur la base réelle, en lecture seule. Les scripts de mesure sont reproduits en annexe § 9.

Aucune écriture n'a été effectuée sur `data/synapse_local.db`, sur Notion ni sur le vault Obsidian pendant l'audit.

Les affirmations qui n'ont **pas** pu être vérifiées sont signalées explicitement par la mention *(non vérifié)*.

---

## 3. Photographie des données

```
cours total                              707
  ├─ avec collège ET item_number         582
  └─ sans collège (pré-externat)         125

items EDN distincts (fiches à collège)   365     référentiel : 367
  ├─ 1 fiche                             203
  ├─ 2 fiches                            115
  ├─ 3 fiches                             39
  └─ 4 fiches                              8
items absents de Notion                    2     items 8 et 10 (collège « Humanités »)

cours avec url_pdf                       119 / 582
cours avec date_1ere_lecture               8 / 582
cours avec nb_lectures > 0                 6 / 582

review_history                           250 lignes (246 done, contexte collège)
study_sessions                            34 lignes / 13 cours distincts
qcm_sessions                               7
lisa_oic                                 290 lignes / 20 cours distincts
ai_practice_sessions                     600 (581 avec item_number)
item_state (niveaux déclarés)            146 (71 « correct », 75 « flou »)
college_status                             9 collèges « valide »
ednpro_item_frequency                    367 / 367
```

Cette photographie explique la plupart des constats qui suivent : **le corpus est massivement « déclaré » et très peu « mesuré »**. Toute logique qui exige une preuve forte (PDF lié, première lecture, cycle J complet) est donc inerte sur presque tous les items.

---

## 4. Constats

Sévérité : **S1** = l'écran ment ou ne fonctionne pas · **S2** = résultat faux ou incohérent entre vues · **S3** = friction UX ou dette · **S4** = cosmétique.

### Axe A — Cohérence des pipelines de maîtrise

---

#### C01 · **S1** · La vue Collèges n'affiche aucune maîtrise

**Constat.** La vue Collèges ne calcule pas la maîtrise : elle la **récupère depuis les `ReviewTask`**.

```python
# frontend/pages/colleges_cockpit.py:364
mastery_by_course: dict[str, tuple] = {}
for t in all_tasks:
    mastery_by_course.setdefault(t.course_id, (t.mastery_score, t.mastery_level))
```

Or `generate_reviews(context="college")` retourne **0 tâche** sur la base actuelle. Cause : [backend/core/reviews/service.py:164](backend/core/reviews/service.py:164) saute tout cours sans `date_1ere_lecture` (8 cours sur 707), et 7 de ces 8 sont ensuite exclus par `get_historically_completed_course_ids`.

**Mesure.**
```
taches: 0
cours avec maitrise connue (vue College): 0
cours sans date_1ere_lecture: 699 / 707
cours "historiquement completes" (exclus): 146
```

**Impact.** Pour les 582 items : colonne Maîtrise = `—`, Statut = « À lire » ou « Lu · maîtrise non évaluée », Retard = « à jour », Prochaine = `—`, Fragiles = 0. Le panneau Pilotage affiche `0 en retard · 0 collèges fragiles · maîtrise moyenne — · rétention —`. **Rien ne distingue « aucune donnée » de « tout va bien »** : un collège jamais ouvert et un collège parfaitement révisé s'affichent à l'identique.

**Correction.** Découpler la maîtrise de l'existence d'une tâche : calculer la maîtrise par item (cf. C03) et n'utiliser les `ReviewTask` que pour ce qu'elles sont — l'échéancier (Retard / Prochaine).

---

#### C02 · **S1** · 50 items déclarés perdent leur niveau avant même d'être évalués

**Constat.** `get_course_mastery` renvoie « à préparer » avec `score=None` dès qu'il n'y a ni PDF ni première lecture — **avant** de consulter la graine déclarée :

```python
# backend/core/reviews/mastery.py:182
if not has_pdf and not has_first_read:
    return CourseProgressSnapshot(..., level="à préparer", mastery_score=None, ...)
```

La lecture de la graine n'intervient qu'après, en [mastery.py:193](backend/core/reviews/mastery.py:193), sous un commentaire qui affirme exactement l'inverse : *« C'est ce qui rend planifiables les items des anciens collèges validés. »*

**Mesure.** Sur les 146 items portant un `item_state` : **96 conservent leur score, 50 le perdent**.

**Impact.** Un tiers du travail de déclaration des anciens collèges est invisible dans toutes les vues, et ces 50 items ne peuvent jamais entrer dans une planification.

**Correction.** Déplacer le test de la graine **avant** la règle « pas de PDF ». Règle cible : un niveau déclaré produit toujours un score, quel que soit l'état des ressources ; l'absence de PDF est un défaut de ressource, pas un défaut de connaissance.

---

#### C03 · **S2** · Trois chemins de calcul de la maîtrise pour le même item

| Vue | Chemin | Séances utilisées |
|---|---|---|
| `/items` | `review_service._get_mastery_cached` ([items.py:259](frontend/pages/items.py:259)) | fusionnées *par accident* (cache réchauffé par `generate_reviews`) |
| `/colleges` | lecture des `ReviewTask` ([colleges_cockpit.py:364](frontend/pages/colleges_cockpit.py:364)) | fusionnées |
| `/cours/{id}` | `get_course_mastery` direct ([course_detail_cockpit.py:328](frontend/pages/course_detail_cockpit.py:328)) | **non fusionnées** |

Le cas `/items` mérite attention : la page passe des séances **brutes** à `_get_mastery_cached`, mais `generate_reviews` (appelé quelques lignes plus haut) a déjà rempli le cache avec les séances **fusionnées**. Le résultat est correct *par effet de bord du cache*. Le jour où le cache est vidé entre les deux appels, la liste calcule la maîtrise sur une fraction des preuves, sans erreur visible.

**Mesure.** **11 fiches** ont un historique de séances différent selon la vue.

**Correction.** Une seule fonction publique `get_item_mastery(item_number)` qui fusionne les alias en interne, appelée par les trois écrans. Supprimer l'usage de `_get_mastery_cached` (méthode privée) depuis `frontend/pages/items.py`.

---

#### C04 · **S2** · L'origine du score n'est jamais affichée dans les listes

**Constat.** `mastery_indicator` sait afficher « déclaré » vs « mesuré » via `evidence_count` — c'est même l'objet de `provenance_label` / `provenance_tooltip`. Ni `/items` ([items.py:381](frontend/pages/items.py:381)) ni `/colleges` ne passent ce paramètre.

**Mesure.** Répartition réelle des niveaux dans `/items` : `à préparer 468 · fragile 52 · critique 45 · à lire 17`. Les **97 items scorés sont tous fragile ou critique**, et 100 % de ces scores proviennent d'une graine déclarée, pas d'un échec constaté.

**Impact.** La liste présente 97 items en rouge/ambre comme des faiblesses mesurées. C'est un faux signal d'alarme, précisément celui que le composant a été écrit pour éviter.

**Correction.** Passer `evidence_count=mastery.evidence_count` dans les deux listes.

---

### Axe B — Mapping des items

---

#### C05 · **S2** · Le référentiel utilisé est une projection dégradée

**Constat.** Deux référentiels coexistent :

| Fichier | Contenu | Utilisé par |
|---|---|---|
| `data/nexternat_items.json` | 367 items, **59 collèges**, écriture + relecture | uniquement des scripts (`scripts/*.py`) |
| `data/items_edn.json` | 367 items, **1 collège par item**, 34 abréviations | `items_mapping.resolve()` → tout le runtime |

Or dans le vrai référentiel : **269 items ont 1 collège d'écriture, 68 en ont 2, 20 en ont 3, 9 en ont 4, 1 en a 5**. `items_edn.json` en garde un seul, arbitrairement.

**Mesure.** Sur 365 items : **283 ont une fiche portant le collège de `items_edn.json`, 82 n'en ont aucune.** Croisé avec `nexternat_items.json`, le classement Notion est cohérent avec le référentiel complet dans **~100 %** des cas (les 8 résidus sont des variantes de nommage : « Gastroentérologie » vs « Hépato-Gastro-entérologie », « Maladies infectieuses » vs « Infectiologie », « Cardiologie » vs « Cardiovasculaire »).

**Conclusion.** Ce n'est pas Notion qui est mal classé — c'est le référentiel runtime qui est trop pauvre.

**Correction.** Faire de `items_mapping` un service multi-collèges : `item_colleges(n) -> tuple[str, ...]` alimenté par `nexternat_items.json`, avec une table de correspondance nom-référentiel → nom-Notion. Conserver `resolve()` en compatibilité (premier collège) le temps de la migration des appelants.

---

#### C06 · **S2** · Le fil d'Ariane de la fiche item renvoie vers un collège qui ne la contient pas

**Constat.**

```python
# frontend/pages/course_detail_cockpit.py:385
college = referential_college(course) or ((course.college or [""])[0] if course.college else "")
...
# :422
ui.link(college, f"/items?college={college}")
```

La cible `/items?college=X` filtre sur `X in course.college` — l'appartenance **Notion**. Quand `referential_college` renvoie un collège absent de toutes les fiches de l'item, la liste d'arrivée ne contient pas l'item d'où l'on vient.

**Mesure.** **125 fiches** (82 items) sont dans ce cas. Exemples :

| Item | Fil d'Ariane | Collèges réels |
|---|---|---|
| 255 | Nutrition 🍔 | Endocrinologie, Gynécologie-Obstétrique |
| 128 | Gériatrie 👴 | Endocrinologie, Rhumatologie |
| 124 | Gynécologie-Obstétrique 👶 | Endocrinologie, Gynécologie médicale, Urologie |
| 343 | Médecine Intensive - Réanimation 🚨 | Neurologie, Pédiatrie |

**Note.** Le collège cible existe toujours côté Notion (0 cas de liste vide) : l'utilisateur n'atterrit donc pas sur une page d'erreur, mais sur une liste **d'où son item a disparu** — plus déroutant qu'une erreur franche.

**Correction.** Après C05, viser le collège de référence **s'il est porté par au moins une fiche de l'item**, sinon le collège de la fiche ouverte. Encoder l'URL avec `urllib.parse.quote` comme le fait déjà [colleges_cockpit.py:442](frontend/pages/colleges_cockpit.py:442).

---

#### C07 · **S2** · `dedupe_by_item` ne déduplique rien

**Constat.** `get_cours_for_college` applique `dedupe_by_item` **après** avoir filtré sur un collège. Le dédoublonnage ne s'exerce donc qu'entre fiches d'un même item **partageant le même collège**.

**Mesure.** Doublons intra-collège dans les données réelles : **0**. La fonction est un no-op aujourd'hui.

Les « 207 lignes en double réparties sur 28 collèges » de la docstring ([course_aliases.py:83](backend/core/knowledge/course_aliases.py:83)) correspondent aux doublons **globaux** (mesurés : 217, soit 582 fiches − 365 items), qui ne sont pas ce que la fonction élimine.

**Correction.** Soit corriger la docstring (le no-op est un filet de sécurité légitime), soit — plus utile — décider ce que « une ligne » signifie dans chaque écran (cf. C08).

---

#### C08 · **S2** · `/items` ne déduplique pas du tout

**Constat.**

```python
# frontend/pages/items.py:233
courses = [c for c in data_store.cours if c.college]
```

Aucun appel à `dedupe_by_item`, contrairement à la vue Collèges qui passe par `get_cours_for_college`.

**Mesure.** **582 lignes rendues pour 365 items distincts, soit 217 doublons.** Un item à 4 fiches apparaît 4 fois, avec 4 scores potentiellement différents.

**Impact.** L'écran s'appelle « Items » et son sous-titre annonce « Tous les items médicaux ». Il liste des fiches. Un item multi-collèges se compte plusieurs fois dans tout tri, tout filtre et toute lecture visuelle de la liste.

**Correction.** Passer `/items` sur un modèle « une ligne = un item » : agrégation par `normalized_item`, colonne Collège = union des collèges de l'item (`colleges_of_item`, déjà écrit et inutilisé dans les vues).

---

#### C09 · **S2** · Le dénominateur du panneau Pilotage est gonflé de 60 %

**Constat.** `_pilotage_summary` somme `r["total"]` sur tous les collèges ([colleges_cockpit.py:281](frontend/pages/colleges_cockpit.py:281)). Un item présent dans 3 collèges est compté 3 fois.

**Mesure.** Le panneau affiche **« 154 / 583 cours lus · 26 % »** pour **365 items réels**.

**Correction.** Calculer les agrégats sur l'ensemble des items distincts, pas sur la somme des lignes par collège.

---

#### C10 · **S3** · La fiche canonique est choisie par défaut dans 35 cas sur 162

**Constat.** `canonical_course` ([course_aliases.py:59](backend/core/knowledge/course_aliases.py:59)) revendique le référentiel comme autorité, puis retombe sur `min(created_time, id)` quand il ne trouve pas de correspondance.

**Mesure.** **35 des 162 items multi-fiches** utilisent le fallback « fiche la plus ancienne ».

Point secondaire : la correspondance est un test de sous-chaîne bidirectionnel (`referential_college in c or c in referential_college`). Aucune collision détectée sur les 39 collèges Notion actuels, mais la règle est fragile par construction.

**Correction.** Après C05, la correspondance devient exacte sur l'ensemble des collèges de l'item ; documenter le fallback comme un choix déterministe assumé plutôt que comme une autorité.

---

#### C11 · **S3** · Trois mécanismes d'alias coexistent

| Mécanisme | Clé de regroupement | Emplacement |
|---|---|---|
| `data_store.alias_ids` | `str(int(float(item_number)))` | [store.py:627](backend/state/store.py:627) |
| `oic_course_ids` | égalité de chaînes sur `display_item_number or item_number` | [course_detail_cockpit.py:390](frontend/pages/course_detail_cockpit.py:390) |
| `dedupe_by_item` | `normalized_item` | [course_aliases.py:83](backend/core/knowledge/course_aliases.py:83) |

**Mesure.** **0 divergence** aujourd'hui — les `item_number` sont tous des entiers propres (`'1'`, `'100'`, …). La divergence apparaîtra au premier `'42.0'`, `'ITEM 42'` ou `'42 bis'`.

**Correction.** Faire de `course_aliases` le point de passage unique ; remplacer le calcul local de `oic_course_ids` par `data_store.alias_ids(course.id)`.

---

#### C12 · **S4** · Deux items du référentiel sont absents

Items **8** (« Les discriminations ») et **10** (« Approches transversales du corps »), collège « Humanités ». Couverture : 365/367. À créer dans Notion si ces items sont au programme.

---

### Axe C — Algorithmes

---

#### C13 · **S2** · La couverture OIC ignore les fiches sœurs

**Constat.** `mastery.py` sait agréger les OIC entre fiches d'un item (`_oic_rows_for_item`, [mastery.py:94](backend/core/reviews/mastery.py:94)), mais le calcul qui **compte** ne l'utilise pas :

```python
# backend/core/reviews/mastery.py:140
_cov = oic_coverage(course.id)      # une seule fiche
```

C'est `_cov` qui alimente `_rang_a_conclusive`, `score_rang_a`, et donc le verrou qui force un item en « fragile » (< 75 %) ou « critique » (< 40 %).

**Atténuation actuelle.** `item_service.scrape_all_items` écrit les OIC sur **toutes** les fiches d'un item, et `set_item_oic_mastery` propage l'état de maîtrise. Tant que toutes les écritures passent par `backend/core/lisa/item_service.py`, les données restent alignées. La lecture reste néanmoins structurellement fausse — elle dépend d'une discipline d'écriture, pas d'une garantie.

**Mesure de contexte.** `lisa_oic` : 290 lignes sur **20 cours distincts** seulement. Le verrou Rang A est donc quasi inactif aujourd'hui.

**Correction.** `oic_coverage` doit accepter une liste d'identifiants et travailler sur `_oic_rows_for_item(course)`.

---

#### C14 · **S2** · La fiche item calcule sa maîtrise sur des séances non fusionnées

**Constat.**

```python
# frontend/pages/course_detail_cockpit.py:318
sessions = local_store.get_sessions_by_course().get(course_id, [])
...
# :328
mastery = get_course_mastery(course, "college", sessions, postpone_cnt)
```

`get_course_mastery` est appelé **hors du cache** du service et **sans** `_sessions_across_item_fiches`. Sont également per-fiche : `qcm_summary`, `qcm_sessions`, `lacunes`, `review_hist`, `manual_reviews`, et donc l'onglet Historique et la métrique « Dernière révision ».

**Impact.** Le même item peut afficher un score différent selon qu'on le regarde depuis la liste ou depuis sa fiche — et un score différent encore selon **par quelle fiche** on l'ouvre.

**Correction.** Consommer la même fonction `get_item_mastery` que C03, et fusionner les cinq lectures par alias.

---

#### C15 · **S2** · La colonne « Dernière révision » de `/items` n'est pas agrégée

`_last_review_info(r["sessions"])` ([items.py:375](frontend/pages/items.py:375)) reçoit les séances brutes de la fiche, alors que la maîtrise de la même ligne est calculée sur l'agrégat. Deux colonnes voisines, deux périmètres de preuve.

---

#### C16 · **S3** · La validation automatique d'un collège est hors d'atteinte

**Constat.** `assess_college_validation` exige les **quatre** révisions J3, J7, J14, J30 en statut `done`, **pour chaque item du collège** ([college_validation.py:96](backend/core/knowledge/college_validation.py:96)).

**Mesure.** Avec 246 révisions `done` au total :

| Collège | Items | Preuves | Cycle J complet |
|---|---|---|---|
| Cardiovasculaire ❤️ | 23 | 22 | **1** |
| Dermatologie 🧴 | 16 | 15 | **3** |
| Endocrinologie 🫘 | 21 | 19 | **0** |

**Impact.** La ligne affiche en permanence « cycle J 1/23 » — un ratio qui se lit comme un échec alors qu'il mesure une exigence que le mode de travail réel (consolidation, annales, sessions IA) ne renseigne jamais. `automatic_ready` n'est jamais vrai ; seule la validation manuelle fonctionne.

**Arbitrage requis** (§ 8, Q1) : soit assouplir le critère (les preuves suffisent), soit compter aussi les révisions de consolidation, soit assumer l'affichage et le libeller autrement.

---

#### C17 · **S3** · 56 % des items portent le badge de priorité maximale

**Constat.** `_priority_from_session_count` ([ednpro/frequency.py:66](backend/core/ednpro/frequency.py:66)) : `≥3 sessions → indispensable`.

**Mesure.** `indispensable 205 · basique 67 · important 57 · jamais_tombe 38` sur 367.

**Impact.** Un signal porté par la majorité du corpus ne hiérarchise plus. Le tri « Priorité annale » de `/items` place 205 items ex æquo en tête, départagés ensuite par le seul numéro d'item.

**Arbitrage requis** (§ 8, Q2) : seuils absolus plus hauts, ou classement relatif (quartiles sur `session_count` × `question_count`).

---

#### C18 · **S4** · Une fréquence absente est affichée « JAMAIS TOMBÉ »

`_priority_key` ([ednpro_frequency_badge.py:29](frontend/components/ednpro_frequency_badge.py:29)) replie `None` sur `jamais_tombe`, pendant que `frequency_badge_tooltip` dit correctement « Fréquence EDNpro indisponible ». Le badge affirme un fait ; le tooltip avoue l'ignorance.

Sans effet aujourd'hui (couverture 367/367), mais l'affirmation est fausse par construction. Ajouter un état `inconnu` neutre.

---

### Axe D — Interface

---

#### C19 · **S2** · Les chips « Fragile / critique » et « En retard » sont inertes dès qu'un collège est sélectionné

**Constat.**

```python
# frontend/pages/items.py:168
if college != "Tous":
    selected = [r for r in rows if college in (r["course"].college or [])]
elif mode == "fragile":
    ...
```

Le collège court-circuite le mode. Or `_draw_chips` affiche quand même le chip cliqué comme **actif**.

**Impact.** Le parcours principal de la vue — arriver depuis Collèges via `?college=`, puis cliquer « En retard » — ne filtre rien tout en signalant visuellement l'inverse. Le chip « Tous » ne réinitialise pas non plus le collège.

**Correction.** Rendre les filtres cumulables (collège ∧ mode), ou remettre `college` à « Tous » quand un mode est choisi. La première option est la plus proche de l'intention.

---

#### C20 · **S3** · Le filtre « Sans PDF » retient tous les collèges

**Constat.** `no_pdf = any(not c.url_pdf for c in courses)` ([colleges_cockpit.py:404](frontend/pages/colleges_cockpit.py:404)) : vrai dès qu'**un seul** cours du collège n'a pas de PDF.

**Mesure.** **39 collèges sur 39** retenus (119 PDF pour 582 cours). Le chip ne filtre rien. Le KPI « sans PDF » du panneau compte des collèges, pas des cours, et affichera donc 39.

**Correction.** Basculer sur un compte : `no_pdf_count` par collège, filtre sur `> 0`, tri possible, KPI en nombre de **cours** sans PDF (463).

---

#### C21 · **S3** · Le statut « Maîtrisé » est le seul non colorié

**Constat.** `status_class("maîtrisé")` produit `maitrisé` (le `é` n'est pas translittéré). Aucune règle `.cg-item-status.maitrisé` dans le CSS. À l'inverse, `.solide` et `.correct` sont définies mais **jamais émises** — `mastery.py` ne produit que `à préparer · à lire · en construction · à consolider · fragile · critique · maîtrisé`.

**Impact.** Le meilleur état possible s'affiche en gris neutre, indistinguable de « Correct ».

**Correction.** Aligner les deux vocabulaires (§ 8, Q3) : une seule échelle, ou une table de conversion explicite entre l'échelle pédagogique (`mastery.py`) et l'échelle de santé (`mastery_indicator._level_from_score`).

---

#### C22 · **S3** · La répartition des statuts du panneau Pilotage est incomplète

**Constat.** Le panneau liste six clés en dur ([colleges_cockpit.py:501](frontend/pages/colleges_cockpit.py:501)) : `a_lire`, `lu_sans_preuve`, `en construction`, `à consolider`, `fragile`, `solide`.

- `solide` **n'est jamais produit** → barre toujours à 0 ;
- `critique`, `maîtrisé`, `à préparer` **sont produits mais absents du panneau**.

**Impact.** Les barres ne somment jamais au total, et les items critiques — les plus urgents — n'apparaissent pas dans la répartition censée les faire ressortir.

**Correction.** Construire la liste depuis `STATUS_LABELS` plutôt que la répéter, dans un ordre pédagogique fixe.

---

#### C23 · **S3** · Le bouton « Confirmer » déplie aussi le collège

`row_el.on("click", _toggle_expand)` ([colleges_cockpit.py:563](frontend/pages/colleges_cockpit.py:563)) et le bouton de validation ([colleges_cockpit.py:577](frontend/pages/colleges_cockpit.py:577)) est un enfant de `row_el` : le clic remonte. Valider un collège le déplie simultanément. Même mécanique pour la pastille « en retard › » (masquée par la navigation).

**Correction.** `.on("click", handler, [])` avec `stopPropagation`, ou sortir les actions de la zone cliquable.

---

#### C24 · **S3** · La colonne TYPE de `/items` ne porte presque aucune information

`_type_tag` ([items.py:204](frontend/pages/items.py:204)) : `LACUNE` si lacune active, sinon `PDF` si `url_pdf`, sinon `NOTE`.

**Mesure.** 119 PDF, **3 lacunes actives en base**, donc ~460 lignes « NOTE ». La colonne occupe 70 px pendant que Titre et Collège sont tronqués à deux lignes (`-webkit-line-clamp:2`).

**Correction.** Supprimer la colonne ou la remplacer par un signal réellement discriminant (nombre de fiches de l'item, ou présence de ressources).

---

#### C25 · **S3** · Aucun compteur de résultats, aucune pagination

`/items` rend ses 582 lignes d'un seul bloc, sans indiquer combien de lignes sont affichées ni combien existent. Chaque clic de filtre reconstruit intégralement la liste (`list_col.clear()` puis boucle).

**Correction.** Afficher « N items affichés / M » dans le sous-titre, et virtualiser au-delà de ~150 lignes.

---

### Axe E — Performance

---

#### C26 · **S3** · Tout est recalculé à chaque interaction

`_render()` ([colleges_cockpit.py:733](frontend/pages/colleges_cockpit.py:733)) est appelé par `_toggle_expand`, `_toggle` (filtres) et `_confirm_college`. Il rejoue `_compute()` en entier : `get_all_history`, `generate_reviews`, les 39 validations de collège, puis redessine toutes les lignes — donc perte du scroll et de l'état visuel.

Aggravant : `generate_reviews` est appelé **avec `history=` explicite**, ce qui active `explicit_data` et **contourne le cache** ([service.py:126](backend/core/reviews/service.py:126)). Chaque dépliage est un recalcul complet du moteur de révisions.

**Correction.** Ne recalculer que sur mutation réelle (validation) ; pour dépliage et filtres, réutiliser les lignes déjà calculées et ne redessiner que la zone concernée. Ne pas passer `history=` quand le cache convient.

---

#### C27 · **S3** · Deux boucles quadratiques latentes

```python
# frontend/pages/colleges_cockpit.py:410
retention_by_course = {
    cid: getattr(next((task for task in all_tasks if task.course_id == cid), None), "retention_score", None)
    for cid in ids
}
```
`O(cours × tâches)` par collège. Indolore à 0 tâche, ruineux dès que le moteur repartira (C01).

De même, `assess_college_validation` scanne l'intégralité de `history` pour **chaque cours** ([college_validation.py:87](backend/core/knowledge/college_validation.py:87)) → `O(582 × |history|)` par rendu.

**Correction.** Indexer une fois : `tasks_by_course: dict[str, list]` et `history_by_course: dict[str, set[str]]`.

---

#### C28 · **S3** · La fiche item relance le moteur complet à chaque ouverture

[course_detail_cockpit.py:342](frontend/pages/course_detail_cockpit.py:342) : `generate_reviews(context="college", history=...)` (cache contourné) **plus** `plan_consolidation()`, pour n'en retenir que les tâches d'un seul cours. Le code le reconnaît ligne 311 : *« cette page est déjà lente »*.

**Correction.** Une lecture ciblée `get_tasks_for_course(course_id)` servie par le cache.

---

### Axe F — Tests

---

#### C29 · **S3** · 44 tests au vert, aucun ne détecte les constats ci-dessus

```
tests/test_colleges_cockpit.py  test_colleges_cockpit_items.py  test_colleges_cockpit_ui.py
tests/test_course_aliases.py    test_items_sorting.py           test_college_validation.py
→ 44 passed in 1.66s
```

Les fixtures fournissent des tâches et des maîtrises qui n'existent pas en production. Il manque un niveau : **un test d'intégration sur données réalistes** vérifiant les invariants inter-vues.

**Correction.** Ajouter `tests/test_items_colleges_coherence.py` (cf. § 6, lot 4).

---

## 5. Tableau de synthèse

| # | Constat | Sévérité | Axe |
|---|---|---|---|
| C01 | Vue Collèges sans aucune maîtrise (0 tâche générée) | S1 | Cohérence |
| C02 | 50 items déclarés perdent leur niveau | S1 | Cohérence |
| C03 | Trois chemins de calcul de maîtrise | S2 | Cohérence |
| C04 | Origine du score (déclaré/mesuré) jamais affichée | S2 | Cohérence |
| C05 | Référentiel runtime mono-collège, faux sur 82 items | S2 | Mapping |
| C06 | Fil d'Ariane vers un collège sans l'item (125 fiches) | S2 | Mapping |
| C07 | `dedupe_by_item` est un no-op | S2 | Mapping |
| C08 | `/items` ne déduplique pas (217 doublons) | S2 | Mapping |
| C09 | Dénominateur Pilotage gonflé de 60 % | S2 | Mapping |
| C10 | Fiche canonique par défaut dans 35 cas | S3 | Mapping |
| C11 | Trois mécanismes d'alias | S3 | Mapping |
| C12 | Items 8 et 10 absents | S4 | Mapping |
| C13 | Couverture OIC non agrégée | S2 | Algorithmes |
| C14 | Fiche item : séances non fusionnées | S2 | Algorithmes |
| C15 | « Dernière révision » non agrégée | S2 | Algorithmes |
| C16 | Validation automatique inatteignable | S3 | Algorithmes |
| C17 | 56 % d'items « indispensables » | S3 | Algorithmes |
| C18 | Fréquence absente affichée « jamais tombé » | S4 | Algorithmes |
| C19 | Chips inertes quand un collège est filtré | S2 | Interface |
| C20 | Filtre « Sans PDF » retient 39/39 | S3 | Interface |
| C21 | Statut « Maîtrisé » non colorié | S3 | Interface |
| C22 | Répartition des statuts incomplète | S3 | Interface |
| C23 | « Confirmer » déplie le collège | S3 | Interface |
| C24 | Colonne TYPE sans information | S3 | Interface |
| C25 | Ni compteur ni pagination | S3 | Interface |
| C26 | Recalcul intégral à chaque clic | S3 | Performance |
| C27 | Deux boucles quadratiques latentes | S3 | Performance |
| C28 | Fiche item : moteur complet à l'ouverture | S3 | Performance |
| C29 | Tests aveugles aux constats | S3 | Tests |

---

## 6. Plan d'action

Chaque lot est livrable et vérifiable indépendamment. L'ordre est contraint : le lot 1 conditionne la lisibilité de tous les autres.

### Lot 1 — Rendre la maîtrise réelle et unique · **C01 C02 C03 C04 C14 C15**

> Objectif : un item a **une** maîtrise, calculée sur **toutes** ses preuves, affichée à l'identique dans les trois écrans.

| # | Action | Fichiers |
|---|---|---|
| 1.1 | Déplacer la lecture de la graine avant la règle « ni PDF ni 1ère lecture » | `backend/core/reviews/mastery.py:182` |
| 1.2 | Créer `get_item_mastery(course) -> CourseProgressSnapshot` : fusion des séances par alias en interne, mise en cache par item | `backend/core/reviews/mastery.py` |
| 1.3 | Vue Collèges : calculer la maîtrise via 1.2 au lieu de la lire dans les `ReviewTask` ; les tâches ne servent plus qu'à Retard / Prochaine | `frontend/pages/colleges_cockpit.py:364` |
| 1.4 | Vue Items : remplacer `review_service._get_mastery_cached` par 1.2 | `frontend/pages/items.py:259` |
| 1.5 | Fiche item : consommer 1.2 ; fusionner par alias `qcm_summary`, `qcm_sessions`, `lacunes`, `review_hist`, `manual_reviews` | `frontend/pages/course_detail_cockpit.py:318-328` |
| 1.6 | Passer `evidence_count` à `mastery_indicator` dans les deux listes | `items.py:381`, `colleges_cockpit.py` |
| 1.7 | « Dernière révision » sur les séances agrégées | `items.py:375` |

**Critères d'acceptation**
- Le nombre de cours avec un score est **identique** dans les trois vues.
- Les 96 + 50 = 146 items déclarés portent un score.
- Un item multi-fiches affiche le même score quelle que soit la fiche ouverte.
- Aucune ligne « fragile » ou « critique » sans mention « déclaré » quand `evidence_count == 0`.

---

### Lot 2 — Réparer le mapping · **C05 C06 C07 C08 C09 C10 C11 C12**

> Objectif : un seul référentiel, multi-collèges, et une définition unique de « une ligne ».

| # | Action | Fichiers |
|---|---|---|
| 2.1 | Table de correspondance `nom référentiel → nom Notion` (59 → 39), validée sur les données réelles | `backend/core/qcm/items_mapping.py` |
| 2.2 | `item_colleges(n) -> tuple[str, ...]` alimenté par `nexternat_items.json` ; `resolve()` conservé en compatibilité | idem |
| 2.3 | `canonical_course` : correspondance exacte sur l'ensemble des collèges de l'item | `backend/core/knowledge/course_aliases.py:59` |
| 2.4 | Fil d'Ariane : collège de référence **s'il est porté par une fiche de l'item**, sinon collège de la fiche ; encoder l'URL | `course_detail_cockpit.py:385,422` |
| 2.5 | `/items` : une ligne = un item ; colonne Collège = `colleges_of_item` | `frontend/pages/items.py:232` |
| 2.6 | Pilotage : agrégats sur items distincts | `colleges_cockpit.py:281` |
| 2.7 | Remplacer `oic_course_ids` par `data_store.alias_ids` | `course_detail_cockpit.py:390` |
| 2.8 | Corriger la docstring de `dedupe_by_item` | `course_aliases.py:83` |
| 2.9 | Créer les items 8 et 10 dans Notion *(action manuelle)* | — |

**Critères d'acceptation**
- 0 item dont le fil d'Ariane mène à une liste qui ne le contient pas (vs 82 aujourd'hui).
- `/items` affiche 365 lignes, pas 582.
- Le Pilotage annonce un total de 365.
- Un seul mécanisme d'alias subsiste dans le code.

---

### Lot 3 — Corriger l'interface · **C13 C19 C20 C21 C22 C23 C24 C25 C18**

| # | Action | Fichiers |
|---|---|---|
| 3.1 | `oic_coverage` sur la liste des alias | `backend/core/knowledge/service.py:143`, `mastery.py:140` |
| 3.2 | Filtres cumulables collège ∧ mode dans `/items` | `items.py:157` |
| 3.3 | « Sans PDF » : compte par collège, filtre `> 0`, KPI en cours | `colleges_cockpit.py:404,489` |
| 3.4 | Vocabulaire de statut unifié + classe CSS `maitrise` | `status_badge.py`, `colleges_cockpit.py` (CSS) |
| 3.5 | Répartition des statuts construite depuis `STATUS_LABELS` | `colleges_cockpit.py:501` |
| 3.6 | `stopPropagation` sur les actions imbriquées dans les lignes | `colleges_cockpit.py:563,577,596` |
| 3.7 | Supprimer ou remplacer la colonne TYPE | `items.py:204` |
| 3.8 | Compteur « N / M » et virtualisation au-delà de 150 lignes | `items.py` |
| 3.9 | État `inconnu` pour une fréquence absente | `ednpro_frequency_badge.py:29` |

---

### Lot 4 — Performance et filet de tests · **C26 C27 C28 C29**

| # | Action | Fichiers |
|---|---|---|
| 4.1 | `_render()` ciblé : dépliage et filtres ne recalculent plus `_compute()` | `colleges_cockpit.py:733` |
| 4.2 | Ne pas passer `history=` quand le cache convient | `colleges_cockpit.py:355`, `course_detail_cockpit.py:342` |
| 4.3 | Index `tasks_by_course` et `history_by_course` | `colleges_cockpit.py:410`, `college_validation.py:87` |
| 4.4 | `get_tasks_for_course(course_id)` servie par le cache | `backend/core/reviews/service.py` |
| 4.5 | `tests/test_items_colleges_coherence.py` | nouveau |

**Contenu attendu du test d'intégration 4.5**
1. Le nombre de cours scorés est identique dans les trois vues.
2. Pour chaque item multi-fiches, la maîtrise est identique quelle que soit la fiche.
3. `/items` ne contient aucun doublon d'`item_number`.
4. Le total du Pilotage égale le nombre d'items distincts.
5. Pour chaque fiche, le collège du fil d'Ariane est porté par au moins une fiche de l'item.
6. Toute clé de statut produite par `mastery.py` possède un libellé **et** une classe CSS.

---

### Ce qui n'est volontairement pas dans le plan

- **C16 (validation automatique)** et **C17 (seuils de priorité)** : ce sont des décisions pédagogiques, pas des bugs. Voir § 8.
- La refonte visuelle des deux écrans : les grilles, la densité et la grammaire de statut sont cohérentes avec le reste du cockpit. Le problème est la donnée qu'elles affichent, pas leur forme.

---

## 7. Ce qui fonctionne bien

À conserver tel quel :

- **Le module `course_aliases`** est le bon abstraction : `group_courses_by_item`, `merge_course_map` et `alias_map` sont justes, testés et documentés avec les mesures réelles. Le problème est qu'ils sont sous-utilisés, pas qu'ils soient faux.
- **La mémoïsation de `alias_map`** dans `data_store.alias_ids` ([store.py:627](backend/state/store.py:627)) évite correctement un coût quadratique.
- **`item_service.scrape_all_items`** : un scrape par item et non par fiche, réconciliation préservant `mastered` et `oic_level` — exactement la bonne granularité.
- **Le mapping des fréquences EDNpro** : 367/367, clés cohérentes avec `item_number`, `removeprefix("ITEM ")` défensif. Zéro anomalie mesurée.
- **`mastery_indicator`** et sa notion de provenance : le composant résout précisément le problème du score déclaré. Il suffit de l'utiliser.
- **La couverture de tests unitaires** est réelle (44 tests, exécution en 1,7 s). Elle a juste besoin d'un étage d'intégration au-dessus.

---

## 8. Arbitrages à trancher avant implémentation

**Q1 — Que signifie « collège validé » ?**
Aujourd'hui : les quatre révisions J3/J7/J14/J30 `done` pour chaque item — jamais atteint (1/23 sur Cardio).
Options : (a) les preuves d'exposition suffisent ; (b) compter aussi consolidation, annales et sessions IA comme éléments du cycle ; (c) garder l'exigence mais renommer l'indicateur pour qu'il ne se lise pas comme un échec.

**Q2 — Comment hiérarchiser la priorité annale ?**
Aujourd'hui : `≥3 sessions → indispensable`, soit 205 items sur 367.
Options : (a) relever les seuils absolus ; (b) classement relatif par quartiles combinant `session_count` et `question_count` ; (c) garder la donnée brute et n'afficher un badge que dans le quartile supérieur.

**Q3 — Une ou deux échelles de statut ?**
Deux vocabulaires coexistent : pédagogique (`à préparer → maîtrisé`, 7 valeurs) et santé (`solide/correct/fragile/critique`, 4 valeurs).
Options : (a) une seule échelle ; (b) deux échelles avec une table de conversion explicite et testée.

**Q4 — `/items` liste-t-il des items ou des fiches ?**
Le lot 2 suppose « des items ». Si tu veux garder la vue par fiche pour naviguer collège par collège, il faut un basculement explicite plutôt qu'une ambiguïté silencieuse.

---

## 9. Annexes — reproduire les mesures

Toutes les mesures ci-dessus sont reproductibles en lecture seule depuis la racine du projet.

**Photographie des données et regroupement par item**

```bash
.venv/Scripts/python.exe -X utf8 -c "import json;from collections import Counter,defaultdict;d=json.load(open('data_cache.json',encoding='utf-8'));w=[c for c in d['cours'] if c.get('college')];g=defaultdict(list);[g[str(int(float(c['item_number'])))].append(c) for c in w if c.get('item_number')];print('fiches',len(w),'items',len(g),'doublons',sum(len(v)-1 for v in g.values()));print(sorted(Counter(len(v) for v in g.values()).items()))"
```

**Nombre de tâches générées et maîtrise par vue**

```python
from backend.state.store import data_store
data_store.load_from_disk(force=True)
from backend.core.reviews.local_store import get_all_history, get_sessions_by_course, get_postpone_counts, get_qcm_done_course_ids
from backend.core.reviews.service import review_service

tasks = review_service.generate_reviews(context="college", history=get_all_history(), active_only=True)
print("tâches:", len(tasks), "| cours avec maîtrise (vue Collèges):", len({t.course_id for t in tasks}))

sm, pm, qd = get_sessions_by_course(), get_postpone_counts(), get_qcm_done_course_ids()
scored = sum(
    1 for c in data_store.cours if c.college
    and review_service._get_mastery_cached(c, "college", sm.get(c.id, []), pm.get(c.id, 0), c.id in qd).score is not None
)
print("cours avec score (vue Items):", scored)
```

**Désaccord référentiel / Notion**

```python
from backend.core.qcm.items_mapping import resolve
# pour chaque item : resolve(item)[1] ∈ union des collèges de ses fiches ?
# → 283 en accord, 82 en désaccord
```

**Fils d'Ariane orphelins**

```python
from backend.core.knowledge.course_aliases import referential_college, group_courses_by_item
# pour chaque item : referential_college ∈ union des collèges de ses fiches ?
# → 82 items / 125 fiches en échec
```

**Graines perdues par la règle « à préparer »**

```python
from backend.core.knowledge.service import get_seed_snapshot
from backend.core.reviews.mastery import get_course_mastery
# pour chaque cours de item_state : seed_score is not None mais mastery.score is None
# → 96 conservés, 50 perdus
```

---

*Audit réalisé sur `main@8ee6909`. Toutes les mesures datent du 14 août 2026 et reflètent l'état de `data_cache.json` (synchronisé le 9 août 2026) et de `data/synapse_local.db`.*
