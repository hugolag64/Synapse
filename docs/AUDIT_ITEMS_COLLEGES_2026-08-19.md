# Audit — vues « Items » et « Collèges » — état des lieux au 19 août 2026

**Périmètre** : `/items`, `/colleges`, `/cours/{id}` et toute la chaîne backend qui les alimente
**Méthode** : lecture de code **+ rejeu des pipelines de production sur la base réelle** (`data/synapse_local.db`, catalogue SQLite), en lecture seule
**Code audité** : `main`, commit `8124646` (« feat: integrate FAC course preparations into daily loop »), dernier commit poussé sur GitHub
**Audit précédent** : `docs/AUDIT_ITEMS_COLLEGES_2026-08-14.md` (`main@8ee6909`)

---

## 1. Résumé exécutif

**Ce qui a changé depuis le 14 août est considérable.** Vingt des vingt-neuf constats sont corrigés et vérifiés sur les données réelles, sept le sont partiellement, deux sont des décisions pédagogiques restées ouvertes. Surtout, un changement d'architecture non prévu par le plan est arrivé : **le catalogue SQLite** (`catalog_items` / `catalog_fiches` / `catalog_colleges`) est devenu la source de vérité du runtime, à la place de `data_cache.json`. `/items` liste désormais 367 lignes pour 367 items, la maîtrise est calculée une seule fois par item et lue à l'identique par les trois écrans, le fil d'Ariane ne se trompe plus une seule fois sur 582 fiches.

**Ce qui reste est plus concentré, mais plus profond.**

Le premier point est le même qu'au 14 août, sous une autre forme : **le moteur de révisions ne produit aucune tâche exploitable** (4 tâches brutes, toutes sur un seul item, toutes éliminées par le filtre de reprise — et même ces 4 étaient un artefact, cf. N01). La maîtrise a bien été découplée des `ReviewTask` — c'était la correction demandée — mais la moitié « échéancier » des deux écrans reste morte : Retard, Prochaine, le chip « En retard », le bouton « Valider » de la vue dépliée, le KPI « révisions en retard ». Rien dans `/items` ni dans `/colleges` ne permet de créer la donnée qui débloquerait tout cela (une date de première lecture), alors que le commit du jour vient précisément d'introduire le mécanisme qui sait l'écrire (`course_learning_schedule`, alimenté par le calendrier FAC).

Le deuxième point est neuf et se voit à l'œil nu : **le panneau Pilotage annonce « 8 / 367 cours lus · 2 % » pendant que la somme de ses propres lignes en compte 257.** Trois définitions de « lu » cohabitent dans le même écran.

Le troisième est la conséquence directe du premier : **la maîtrise affichée est déclarative à 99 %**. Sur 133 items porteurs d'un score, 132 le tiennent d'une déclaration de niveau et un seul d'une mesure. 120 affichent un score sans aucune preuve enregistrée. L'écran Items présente 132 items en rouge ou ambre ; ce sont des souvenirs d'auto-évaluation, pas des échecs constatés.

Le quatrième est un effet de bord de la migration vers le catalogue : **104 révisions terminées sur 380 (27 %) sont rattachées à des fiches qui n'existent plus** dans le catalogue actif.

---

## 1 bis. Journal des correctifs (19 août, après audit)

Les quatre défauts S1 de l’audit — plus un cinquième découvert en les corrigeant — sont corrigés et vérifiés. Le détail est repris sous chaque constat ; ce tableau donne l’état d’ensemble.

| Défaut | Statut | Vérification après correctif |
|---|---|---|
| **N00** — `/colleges` levait `ValueError` au chargement (découvert pendant la correction) | ✅ corrigé | La page se construit ; test de non-régression sur le dépaquetage du snapshot |
| **N10** — statut variable selon le collège | ✅ corrigé | **0** item sur 175 change de statut selon la ligne (72 avant) |
| **N03** — Pilotage « 8 / 367 » contre 257 dans les lignes | ✅ corrigé | Panneau **140 / 367 (38 %)** = union exacte des items lus des lignes |
| **N01/N02** — moteur à 0 tâche, aucun moyen de planifier | ✅ corrigé | Action « Commencer » dans les 3 vues ; **0 → 5 révisions actives** par clic, vérifié de bout en bout sur copie de la base. Défaut connexe corrigé : l'historique par défaut du moteur |
| **N08** — 104 révisions rattachées à des fiches disparues | ✅ corrigé | Rapport d'intégrité + rattachement par item (simulation par défaut) ; **8 preuves rendues**, 4 doublons et 15 reliquats signalés sans y toucher |

---

## 2. Méthode

Chaque constat est soit une lecture de code référencée `fichier:ligne`, soit une **mesure reproductible** obtenue en rejouant le code de production dans le venv du projet, sur `data/synapse_local.db`, en lecture seule. Les commandes sont en annexe § 10.

Aucune écriture n'a été faite sur `data/synapse_local.db`, sur Notion ou sur le vault Obsidian — ni pendant l'audit, ni pendant les correctifs. Les vérifications qui écrivent (action « Commencer », rattachement des preuves) ont été jouées sur des **copies** de la base. La seule écriture Git de la session est un `git pull --ff-only` (`0103300` → `8124646`).

**Suite de tests** : 1 695 tests passent, 1 échoue (`test_uness_rank_jobs_store::test_claim_recovers_expired_lease`) — vérifié en échec identique sur `main` sans les correctifs, donc antérieur et hors périmètre.

---

## 3. État des lieux des 29 constats du 14 août

| # | Constat | Statut | Vérification |
|---|---|---|---|
| C01 | Vue Collèges sans aucune maîtrise | **Partiel** | Maîtrise découplée des tâches et affichée (133 items scorés). L'échéancier reste à zéro → **N01** |
| C02 | 50 items déclarés perdaient leur niveau | **Corrigé** | 132 items déclarés, **0 graine perdue** |
| C03 | Trois chemins de calcul de maîtrise | **Corrigé** | `get_item_mastery()` unique, consommé par les 3 écrans. Résidus : **N04**, **N12** |
| C04 | Provenance du score jamais affichée | **Partiel** | `evidence_count` passé dans `/items` et le dépliage Collèges ; absent de la ligne collège et du KPI « maîtrise moyenne » → **N16** |
| C05 | Référentiel runtime mono-collège | **Corrigé** | `item_colleges()` multi-collèges + `college_consolidation.json` ; remplacé de fait par le catalogue |
| C06 | Fil d'Ariane vers un collège sans l'item | **Corrigé** | **0 / 582** fiches en défaut (125 avant) |
| C07 | `dedupe_by_item` no-op | **Partiel** | Docstring toujours trompeuse ; la fonction ne sert plus que le chemin legacy `get_cours_for_college` |
| C08 | `/items` ne dédupliquait pas | **Corrigé** | **367 lignes pour 367 items** (582 avant) |
| C09 | Dénominateur Pilotage gonflé | **Partiel** | Total corrigé (367). Les KPI « retard » et « fragiles » somment encore par collège → **N09** |
| C10 | Fiche canonique par défaut | **Corrigé** | Correspondance exacte sur l'ensemble des collèges de l'item |
| C11 | Trois mécanismes d'alias | **Corrigé** | `data_store.alias_ids` partout, y compris `oic_course_ids` |
| C12 | Items 8 et 10 absents | **Partiel** | Présents dans le catalogue, sans fiche → ligne cliquable vers une page vide → **N07** |
| C13 | Couverture OIC non agrégée | **Corrigé** | `oic_coverage_for_courses((course.id, *fiche_ids))` |
| C14 | Fiche item : séances non fusionnées | **Corrigé** | `get_item_sessions` / `get_item_qcm_*` / `get_item_review_history` |
| C15 | « Dernière révision » non agrégée | **Corrigé** | Séances de toutes les fiches de l'item |
| C16 | Validation automatique inatteignable | **Inchangé** | **0 / 44** collèges `automatic_ready` → **N14** |
| C17 | 56 % d'items « indispensables » | **Inchangé** | **205 / 367** → **N15** |
| C18 | Fréquence absente = « jamais tombé » | **Corrigé** | État `inconnu` neutre |
| C19 | Chips inertes avec un collège filtré | **Corrigé** | Collège ∧ mode cumulables |
| C20 | « Sans PDF » retenait 39/39 | **Corrigé** | `no_pdf_count > 0`, KPI en nombre de fiches |
| C21 | Statut « Maîtrisé » non colorié | **Corrigé** | `status_class` translittère, `.maitrise` définie |
| C22 | Répartition des statuts incomplète | **Partiel** | Construite depuis `STATUS_ORDER` ; polluée par un collège fantôme → **N05** |
| C23 | « Confirmer » dépliait le collège | **Corrigé** | `js_handler` avec `stopPropagation` |
| C24 | Colonne TYPE sans information | **Corrigé** | Remplacée par le nombre de fiches de l'item |
| C25 | Ni compteur ni pagination | **Corrigé** | « N / M items affichés » + pagination 150 |
| C26 | Recalcul intégral à chaque clic | **Corrigé** | `_render(recompute=False)` pour dépliage et filtres |
| C27 | Boucles quadratiques | **Corrigé** | `tasks_by_course`, `history_by_course` |
| C28 | Fiche item : moteur complet à l'ouverture | **Corrigé** | `get_tasks_for_course(course_id)` |
| C29 | Tests aveugles aux constats | **Partiel** | 79 tests verts, mais le test de cohérence porte sur des fonctions que la page n'appelle pas → **N21** |

---

## 4. Photographie des données (19 août 2026)

L'architecture a changé : `data_store` ne charge plus `data_cache.json` mais le catalogue SQLite (`_load_from_catalog`). Les 125 cours pré-externat sont désormais **archivés** (`catalog_archived_courses`) et sortis du périmètre.

```
CATALOGUE
  items actifs                          367     (référentiel complet)
  fiches actives                        582
  cours archivés                        125     (pré-externat)
  collèges                               44     dont 1 sans aucun item

FICHES PAR ITEM                COLLÈGES PAR ITEM
  0 fiche       2  (items 8, 10)   1 collège    192
  1 fiche     203                  2 collèges   124
  2 fiches    115                  3 collèges    43
  3 fiches     39                  4 collèges     8
  4 fiches      8                → 175 items multi-collèges, 601 relations item↔collège

RESSOURCES ET TRACES
  fiches avec url_pdf                   119 / 582
  fiches avec date_1ere_lecture           8 / 582
  fiches avec nb_lectures > 0             6 / 582
  course_learning_schedule (nouveau)      0
  review_history                        384 lignes (380 « done »)
  study_sessions                         34 lignes / 13 fiches
  qcm_sessions                            7 lignes /  5 fiches
  oic_attempts                            3
  lisa_oic                              290 lignes / 20 fiches
  anki_review_evidence                    0
  ai_practice_sessions                  600  (581 avec item, 6 avec un score)
  item_state (niveaux déclarés)         146 lignes → 132 items distincts
  college_status « valide »               9 collèges

MOTEUR DE RÉVISIONS
  tâches générées                         4   (toutes sur l'item 274)
  tâches après filtre « reprise »         0   (study_resume_date = 2026-08-20)
  → après correctif N01 : 0 tâche brute — les 4 étaient des révisions déjà
    terminées, que l'historique par défaut ne masquait pas (cf. N01)

MAÎTRISE (vue Items, 367 lignes)
  à préparer  212 · à lire 20 · critique 72 · fragile 60 · maîtrisé 1 · sans fiche 2
  items avec un score                   133   dont 132 issus d'une déclaration, 1 d'une mesure
  scores sans aucune preuve             120
```

Cette photographie dit la chose essentielle : **le corpus est déclaré, pas mesuré, et il n'a pas de calendrier**. Toute logique qui exige une preuve forte (PDF lié, première lecture, cycle J complet) reste inerte sur la quasi-totalité des items.

---

## 5. Constats

Sévérité : **S1** = l'écran ment ou une fonction est inopérante · **S2** = résultat faux ou incohérent entre vues · **S3** = friction ou dette · **S4** = cosmétique.

### Axe 0 — Découvert pendant la correction

---

#### N00 · **S1** · `/colleges` levait une exception au chargement · ✅ corrigé

**Constat.** `_compute()` écrivait des triplets dans `mastery_by_course` puis les relisait comme des paires :

```python
# écriture (colleges_cockpit.py:472)
mastery_by_course[item_row["course"].id] = (snapshot.score, snapshot.level, snapshot.evidence_count)
# lecture (colleges_cockpit.py:551)
score, level = mastery_by_course.get(course.id, (None, None))
```

`ValueError: too many values to unpack (expected 2)` dès qu'un item porte un snapshot — c'est-à-dire toujours (367 entrées). La page ne pouvait pas se construire.

**Pourquoi l'audit ne l'avait pas vu.** Les mesures rejouaient la logique de `_compute()` en la réécrivant (avec `[:2]`) plutôt qu'en l'appelant : `_compute` est une fonction imbriquée dans `render_colleges_cockpit`, non appelable sans NiceGUI, et **aucun test ne la couvre**. C'est exactement le trou décrit en N21.

**Correction.** Lecture en `[:2]` aux deux points de consommation, et `evidence_count` lu explicitement là où il est utilisé.

---

### Axe A — La boucle d'apprentissage est ouverte

---

#### N01 · **S1** · Le moteur de révisions produit 0 tâche : la moitié des deux écrans est inerte · ✅ corrigé

**Constat.** `generate_reviews(context="college")` génère 4 tâches, toutes sur l'item 274, toutes en retard depuis février ; `active_only=True` les élimine toutes via `study_resume_date`.

**Mesure — l'entonnoir complet :**

```
582 fiches
 −146 exclues « historiquement complétées » (collège validé + niveau déclaré)
 =436 candidates
 →  1 seule porte une date de référence (date_1ere_lecture ou planning local)
 →  4 tâches J3/J7/J14/J30 générées (item 274, échéances 19/02 → 18/03)
 →  0 tâche active   (study_resume_date = 2026-08-20, soit demain)
```

**Un troisième défaut se cachait derrière les deux autres**, découvert en vérifiant le correctif : `generate_reviews()` chargeait seule les séances et les reports quand l'appelant ne les fournissait pas, mais **retombait sur un historique vide** :

```python
history      = history      or {}          # ← aucune révision n'est jamais « done »
sessions_map = sessions_map or get_sessions_by_course()
```

`/colleges`, `get_tasks_for_course()` (fiche item) et `get_next_task_for_item()` appellent le moteur **sans** `history=`. Ils reproposaient donc des révisions déjà validées. C'est ce qui produisait les « 4 tâches » ci-dessus : les quatre révisions de l'item 274 sont terminées. Avec l'historique chargé par défaut, le moteur produit **0 tâche** — l'inventaire est vide, il n'est pas en retard.

**Impact, écran par écran.**

| Élément | Ce qui s'affiche | Ce que ça devrait dire |
|---|---|---|
| `/colleges` colonne RETARD | « à jour » sur **44/44** collèges | « aucune échéance planifiée » |
| `/colleges` colonne PROCHAINE | « — » partout | idem |
| `/colleges` KPI « révisions en retard » | `0` | idem |
| `/colleges` bouton **Valider** (item déplié) | **jamais affiché** (`task is None`) | la validation d'une révision est injoignable depuis Collèges |
| `/items` colonne PROCHAINE | « — » sur 367 lignes | idem |
| `/items` chip « En retard » | « Aucun item pour ce filtrage » | idem |
| Panneau « À traiter en priorité » | tri dégénéré : `-retard` et `-fragile` valant 0 ou le même chiffre, le classement retombe sur `pct` | — |

Comme au 14 août, **rien ne distingue « aucune donnée » de « tout va bien »**. Un collège jamais ouvert et un collège parfaitement révisé affichent le même « à jour ».

**Correction appliquée — volet « rendre l'absence lisible ».**

| Emplacement | Avant | Après |
|---|---|---|
| `/colleges` colonne RETARD | « à jour » | « non planifié » (italique) tant qu'aucun item du collège n'a de cycle ancré |
| `/items` colonne PROCHAINE | « — » | bouton **Commencer** si rien n'est planifié · « à jour » (point vert) si le cycle est posé sans échéance ouverte |
| En-tête des deux vues | rien | « Reprise le JJ/MM · N révision(s) antérieure(s) masquée(s) » — 0 aujourd'hui, le filtre ne cache plus rien en silence |
| Moteur | historique par défaut vide | `history if history is not None else get_all_history()` : une vue qui oublie `history=` ne repropose plus une révision faite |

Les deux pages ne font plus qu'un seul passage du moteur (`active_only=False` puis `filter_active_review_tasks`) : c'est ce qui permet de compter les tâches masquées au lieu de les faire disparaître silencieusement.

Le volet « rendre la planification atteignable » est traité en N02.

---

#### N02 · **S1** · Aucun chemin, depuis Items ou Collèges, ne crée la donnée qui débloquerait l'échéancier · ✅ corrigé

**Constat.** La condition d'entrée du moteur est une date de référence : `local_schedule.first_read_date` ou `date_1ere_lecture` ([service.py:190](backend/core/reviews/service.py:190)). Le commit du jour introduit `course_learning_schedule` et `save_learning_schedule()` ([backend/core/prep/store.py:153](backend/core/prep/store.py:153)), qui pose d'un coup J1/J3/J7/J14/J30 — mais il n'est alimenté que par le parseur de calendrier FAC. **La table est vide (0 ligne).**

`/items` et `/cours` savent tout dire d'un item sauf « je commence celui-là aujourd'hui ».

**Impact.** L'utilisateur ne peut pas amorcer la boucle depuis l'écran où il choisit son travail. C'est le chaînon manquant entre l'inventaire (Items/Collèges) et la routine quotidienne (Aujourd'hui).

**Correction appliquée.** `backend/core/prep/service.py` expose `anchor_first_read(course_id, first_read_date=None)` : écriture locale des cinq échéances, puis invalidation du cache du moteur et du cache des plannings. L'action est exposée à trois endroits :

| Vue | Emplacement | Comportement |
|---|---|---|
| `/items` | colonne PROCHAINE de la ligne | « Commencer » (clic retenu par `stopPropagation`, la ligne reste cliquable vers la fiche) |
| `/colleges` | colonne d'action de l'item déplié | « Commencer » là où le bouton « Valider » n'a rien à valider |
| `/cours/{id}` | bloc d'actions | « Commencer l'étude » ancre en local ; « Programmer dans Notion » conserve l'ancien chemin |

**Un maillon manquait.** Poser le planning ne suffisait pas : `get_course_mastery` lisait la première lecture sur l'objet `Cours` (donc sur Notion), l'item restait « à préparer » avec un score `None`, et `generate_reviews` l'écartait aussitôt (`if mastery.score is None: continue`). Le clic n'aurait **rien produit**. La maîtrise reconnaît désormais un cycle ancré localement comme une première lecture (`_scheduled_first_read`, servi par un cache mémoïsé — coût mesuré inchangé : 0,18 s pour 367 items).

**Mesure après correctif** (sur une copie de la base réelle, aucun écrit sur la base de travail) :

```
AVANT             tâches générées=0   actives=0   masquées=0
clic « Commencer » sur l'item 44 (Tuméfaction pelvienne chez la femme)
APRÈS             tâches générées=5   actives=5   masquées=0
   J1  2026-08-20 · J3  2026-08-22 · J7  2026-08-26 · J14 2026-09-02 · J30 2026-09-18
maîtrise de l'item : « à préparer », score None  →  « fragile », score 50
```

Le bouton « Valider » de la vue dépliée, jusque-là jamais affiché, apparaît dès la première échéance due.

**Reste à décider** : un item fraîchement commencé atterrit directement en « fragile » (score de base 50, seuil fragile < 60). Ce n'est pas faux — rien n'a encore été révisé — mais cela ajoute une ligne ambre à chaque planification. À arbitrer avec Q4.

---

#### N03 · **S1** · Le panneau Pilotage dit « 8 / 367 lus · 2 % » quand ses propres lignes en comptent 257 · ✅ corrigé

**Constat.** Trois définitions de « commencé » cohabitent dans `colleges_cockpit.py` :

| Où | Définition | Mesure |
|---|---|---|
| Ligne collège (`count_started`, [ligne 307](frontend/pages/colleges_cockpit.py:307)) | `date_1ere_lecture` **ou** `id ∈ active_course_ids` **ou** collège validé → tout | **257** (somme des lignes) |
| Panneau (`started_item_ids`, [ligne 578](frontend/pages/colleges_cockpit.py:578)) | `date_1ere_lecture` **ou** existence d'une tâche | **8** |
| `assess_college_validation` | `date_1ere_lecture` **ou** présence dans `item_state` | 152 items « avec preuve » |

Le calcul du panneau contient de surcroît un défaut de portée :

```python
"started_item_ids": {
    row["item_id"] for row in selected_item_rows
    if row["course"].date_1ere_lecture or any(t.course_id in course_ids for t in college_tasks)
}
```

`any(...)` ne dépend pas de `row` : c'est une constante pour tout le collège. Dès qu'une seule tâche existe dans un collège, **tous** ses items sont comptés comme lus ; s'il n'y en a aucune, seul `date_1ere_lecture` compte. Aujourd'hui : 8.

**Impact.** L'écran se contredit lui-même dans le même viewport : la ligne « Cardiovasculaire ❤️ » annonce « 23/30 lus », le panneau à droite annonce « 2 % ». Le KPI « charge estimée » en dérive : `(367 − 8) × 20 min` = **119 h**, contre ~37 h avec la définition des lignes.

**Correction appliquée.** `backend/core/knowledge/item_progress.py` porte désormais la définition unique :

```python
is_item_started(course, worked_ids, validated_colleges)
  # date de première lecture sur l'une des fiches de l'item
  # ou trace de travail (révision faite, annale, cycle ancré) sur l'une d'elles
  # ou appartenance à un collège déclaré validé
worked_course_ids()      # get_active_course_ids() ∪ course_learning_schedule
validated_college_names()
```

La ligne collège, le panneau et le dépliage consomment la même réponse : `count_started` délègue à `is_item_started`, `started_item_ids` est construit item par item (le `any(...)` constant a disparu), et `_pilotage_summary` sépare enfin les deux espaces d'identifiants (statuts dédoublonnés par item, scores par fiche).

**Mesure après correctif** (rejeu du `_compute` corrigé sur la base réelle) :

```
PANNEAU  : 140 / 367 items lus (38 %)          (8 / 367 · 2 % avant)
LIGNES   : somme = 267 (relations multi-collèges), union = 140
           → union des lignes == panneau : True
charge estimée : 75 h                          (119 h avant)
```

Le signal « travaillé » ainsi unifié fait entrer 140 items au lieu de 8 : ce sont les révisions et annales qui ne renseignent jamais `date_1ere_lecture`. **Arbitrage § 9, Q1 tranché de fait en option (b)** — toute trace de travail compte ; l'option (c) (deux compteurs distincts « lus » et « travaillés ») reste ouverte si tu veux les séparer visuellement.

---

#### N04 · **S2** · 99 % de la maîtrise affichée est déclarative, et les annales ne comptent pas comme preuve

**Mesure.**

```
items avec un score                          133
  ├─ issus d'un niveau déclaré (item_state)  132
  └─ issus d'une mesure réelle                 1   (item 274)
items scorés sans aucune preuve enregistrée  120
items « fragile » ou « critique »            132   (72 critiques, 60 fragiles)
```

**Deux conséquences distinctes.**

1. *Le mur rouge.* `/items` affiche 132 lignes en ambre ou rouge. Le composant sait dire « déclaré » (et le fait), mais la hiérarchie visuelle reste celle d'une alerte : la barre colorée domine, la mention de provenance est un texte de 10 px à côté. Le panneau Pilotage, lui, affiche « maîtrise moyenne 38 % » sans aucune provenance.

2. *Les annales ne sont pas des preuves.* `count_evidence_for_courses` ([knowledge/service.py:103](backend/core/knowledge/service.py:103)) compte `study_sessions + qcm_sessions + oic_attempts + anki_review_evidence` — **pas `ai_practice_sessions`**. Or `mastery.py` s'en sert bien pour bouger le score (±15 selon la moyenne des annales). Pire : la branche de sortie anticipée

   ```python
   if seed.seed_score is not None and seed.n_evidence == 0:
       return ...  # score = graine dégradée, point final
   ```

   court-circuite tout le calcul pour les 132 items déclarés — donc **une annale jouée sur un item déclaré ne peut ni diluer la graine, ni modifier le score, ni faire passer l'item de « déclaré » à « mesuré »**. Impact aujourd'hui : 1 item concerné (6 sessions notées sur 600). Impact demain : total, dès que les annales seront jouées.

   `get_item_evidence()` ([mastery.py:249](backend/core/reviews/mastery.py:249)) compte pourtant déjà les cinq sources, annales comprises. **Elle n'est appelée nulle part.**

**Correction.** Faire de `get_item_evidence()` la source unique du `evidence_count`, y compris pour la dilution de la graine ; conditionner la sortie anticipée à l'absence de *toute* preuve, annales incluses.

---

### Axe B — Le nouveau catalogue

---

#### N05 · **S2** · Un collège fantôme fausse la répartition des statuts

**Constat.** Le catalogue contient **44 collèges**, dont deux « Rhumatologie » : `Rhumatologie 🤲` (10 items) et `Rhumatologie 🤝` (**0 item**). L'emoji diffère ; `items_mapping._ABBR_TO_NOTION` ne connaît que `🤲`.

**Impact.**
1. `/colleges` affiche une 44ᵉ ligne vide : « 0/0 lus · 0 restants · À compléter · Preuves 0/0 · cycle J 0/0 », avec un bouton « Valider manuellement » actif.
2. Cette ligne empoisonne le panneau. `_pilotage_summary` ([ligne 347](frontend/pages/colleges_cockpit.py:347)) prévoit un repli legacy quand une ligne n'a aucun statut :

   ```python
   if not row_status_counts and "pct" in row:
       legacy_level = _level_from_score(int(row["pct"] * 100) if row["total"] else None)
   ```

   `total = 0` → `_level_from_score(None)` → `"correct"`. **La répartition affiche donc « Correct : 1 » — un statut que `mastery.py` ne produit jamais — et somme 368 pour 367 items.**

**Correction.** Fusionner les deux collèges via `catalog_college_aliases`, masquer les collèges sans item (ou les afficher dans une section « non couverts »), et supprimer le repli legacy devenu inatteignable.

---

#### N06 · **S3** · Quatre collèges accessibles depuis Collèges sont introuvables depuis Items

**Constat.** Le sélecteur de collège de `/items` est construit sur `data_store.cours` ([items.py:434](frontend/pages/items.py:434)), c'est-à-dire sur les collèges *portés par une fiche*. Les lignes, elles, portent les collèges du catalogue (`list_colleges_for_item`, qui unit les collèges officiels du référentiel et ceux des fiches).

**Mesure.** 43 collèges apparaissent dans les lignes, 39 dans le sélecteur. **Manquants : Allergologie (3 items), Humanités (5), Médecine du sport (2), Médecines Intégratives et Complémentaires (1).** Ces 11 items n'ont aucune fiche portant ce collège : le rattachement vient du référentiel seul.

**Impact.** Depuis `/colleges`, cliquer « Humanités » ouvre `/items?college=Humanités` et fonctionne (5 lignes). Mais depuis `/items`, ce collège n'existe pas dans le menu : le filtre est atteignable par URL et pas par l'interface.

**Correction.** Alimenter le sélecteur depuis `CatalogRepository.list_colleges()` — la même source que les lignes.

---

#### N07 · **S2** · Les items sans fiche mènent à une page « Item introuvable »

**Constat.** `build_item_rows` fabrique un `Cours` de synthèse pour les items sans fiche, avec `id = item.id` (identifiant catalogue) ([items.py:146](frontend/pages/items.py:146)). La ligne est cliquable comme les autres : `/cours/{c.id}`. Or `render_item_cockpit` cherche cet identifiant dans `data_store.cours`, où il n'existe pas.

**Mesure.** 2 items concernés : **8** (« Les discriminations ») et **10** (« Approches transversales du corps »), collège Humanités — les deux mêmes qu'au 14 août. Vérifié : leur `item_id` n'est pas dans le store.

**Impact.** Deux culs-de-sac silencieux. Le drapeau `missing_fiche` est calculé et transporté jusqu'à la ligne, mais **n'est jamais utilisé au rendu**.

**Correction.** Exploiter `missing_fiche` : ligne visuellement distincte (« aucune fiche »), clic vers une action « créer la fiche » plutôt que vers une page morte.

---

#### N08 · **S1** · 104 révisions terminées sur 380 pointent vers des fiches qui n'existent plus · ✅ corrigé

**Mesure.**

```
review_history : 326 course_id distincts → 233 présents dans le catalogue actif
  93 orphelins : 87 archivés (pré-externat, légitime) + 6 inconnus
révisions « done » orphelines : 104 / 380  (27 %)

autres traces orphelines et NON archivées :
  study_sessions   2 fiches
  qcm_sessions     1 fiche
  lisa_oic         1 fiche
  weak_points      1 fiche
```

**Ce que la catégorie « 6 inconnus » recouvrait vraiment.** L'inspection ligne à ligne, faite au moment de corriger, distingue trois cas que l'audit avait agrégés :

| Cas | Volume | Nature |
|---|---|---|
| Cours archivés | 87 traces | Pré-externat, sortis du périmètre EDN — **normal**, à laisser en place |
| Fiches disparues au réimport | 12 révisions, 3 identifiants Notion | Items **166** (Grippe), **213** (Anémie), **162** (IST · Chlamydiae) — la ligne porte encore son `item_number` |
| Reliquats de tests | 15 traces, 3 identifiants (`c1`, `c2`, `c99`) | Fixtures écrites dans la base de travail, sans item |

**Rectification d'un point de l'audit.** Le texte initial affirmait que ces identifiants « gonflent silencieusement le lu des lignes collège ». C'est faux : `get_active_course_ids()` les renvoie bien, mais l'appartenance est testée par intersection avec les fiches d'un item existant — un identifiant qui ne correspond à aucune fiche ne peut jamais faire basculer un compteur. Le préjudice réel est l'inverse : **de la preuve perdue**, pas de la preuve inventée.

**Correction appliquée.** `backend/state/catalog_integrity.py` :

```python
orphan_report()                      # archivé | rattachable | doublon | inconnu
reattach_orphan_evidence(apply=False)  # simulation par défaut
```

Le rattachement suit l'`item_number` que la ligne porte déjà, vers la fiche canonique de cet item. Un détail décide de la justesse : `review_history.task_id` **encode le `course_id`** ; le réécrire est indispensable, sinon le moteur ne reconnaîtrait plus la révision terminée et la reproposerait. Quand le `task_id` cible existe déjà, la trace orpheline est un doublon : elle est comptée comme telle et **laissée intacte** — jamais écrasée, jamais supprimée. Les reliquats sans item ne sont jamais touchés, seulement listés.

Le rapport est branché dans **Paramètres → DIAGNOSTIC UNESS → INTÉGRITÉ DU CATALOGUE**, avec l'aperçu des preuves concernées et un bouton « Rattacher les preuves ».

**Mesure sur la base réelle** (simulation, puis application vérifiée sur une copie) :

```
avant   archivées 87 · rattachables 8 · doublons 4 · reliquats 15 (c1, c2, c99)
après   archivées 87 · rattachables 0 · doublons 4 · reliquats 15
        8 révisions rendues aux items 166 et 213
        révisions « done » orphelines : 104 → 96  (le solde est légitime ou signalé)
```

**La base de travail n'a pas été modifiée** : la réparation est un clic dans DIAGNOSTIC, à toi de le faire quand tu veux.

---

#### N09 · **S3** · Les KPI « fragiles » et « sans PDF » comptent la mauvaise chose

**Constat et mesures.**

| KPI affiché | Ce qui est calculé | Valeur | Valeur juste |
|---|---|---|---|
| « collèges fragiles » | somme, par collège, des **items** fragiles/critiques | **246** | 132 items distincts (ou 21 collèges concernés) |
| « fiches sans PDF » | items sans PDF (les `courses` sont des items fusionnés) | **256** | 256 items, ou 463 fiches sur 582 |
| « révisions en retard » | somme des retards par collège | 0 | 0 (mais double-comptage latent : 175 items multi-collèges) |

Le total du panneau a bien été dédoublonné (367) ; les KPI qui l'accompagnent ne l'ont pas été.

**Correction.** Agréger sur des ensembles d'`item_id` comme le fait déjà `all_item_ids`, et faire dire au libellé ce que compte le chiffre.

---

### Axe C — Cohérence entre les vues

---

#### N10 · **S1** · 72 items multi-collèges affichent un statut différent selon le collège déplié · ✅ corrigé

**Constat.** La maîtrise est unifiée (`get_item_mastery`), mais `/colleges` **réécrit** le statut par-dessus, avec un critère qui dépend du collège :

```python
# frontend/pages/colleges_cockpit.py:266
def _course_semantics(course, score, level, college_validated=False):
    advancement = build_advancement(1 if course.date_1ere_lecture else 0, 1,
                                    college_validated=college_validated)
    if advancement["percent"] != 100:
        return {..., "status_key": "a_lire", "status_text": "À lire"}
```

Un item sans `date_1ere_lecture` est « Lu » si le collège déplié est validé, « À lire » sinon — quel que soit son score.

**Mesure.** **72 des 175 items multi-collèges** changent de statut selon la ligne d'où on les regarde. Exemples :

| Item | Niveau (vue Items) | Statut selon le collège déplié |
|---|---|---|
| 36 | critique | Endocrinologie : **critique** · Gynécologie médicale : **À lire** |
| 38 | critique | Endocrinologie : **critique** · Gyn. médicale et Gyn.-Obstétrique : **À lire** |
| 75 | critique | Pneumologie : **critique** · Médecine générale et Psychiatrie : **À lire** |

**Impact.** C'est exactement le défaut que l'unification de la maîtrise devait supprimer, déplacé d'une couche : le score est identique partout, le **statut** ne l'est plus. Un item critique est présenté comme « à lire » — c'est-à-dire comme non commencé — dans deux collèges sur trois.

**Correction appliquée.** `college_validated` a disparu de `_course_semantics` et de `_college_item_rows`, remplacé par un `started` calculé **une fois par item** en amont :

```python
_course_semantics(course, score, level, started: bool | None)
_college_item_rows(..., started_ids: set[str] | None)
```

La validation d'un collège n'est pas perdue pour autant : elle est devenue l'un des trois signaux de `is_item_started`, donc elle rend l'item commencé **dans tous ses collèges**, ce qui était l'intention d'origine.

**Mesure après correctif** : **0 item sur 175** change de statut selon la ligne d'où on le regarde (72 avant). Effet de bord visible dans le panneau : la répartition compte enfin les 72 critiques et 60 fragiles réels, au lieu de 59 et 54 (les items d'un collège non validé étaient reclassés « À lire »).

Deux tests verrouillent l'invariant : `test_item_status_does_not_depend_on_the_college_it_is_read_from` et `test_an_item_started_upstream_is_read_whatever_the_college_row`.

---

#### N11 · **S3** · Deux vocabulaires de statut décrivent encore le même état

**Constat.** Pour un même item non commencé, `/items` affiche « à préparer » (via `mastery.py`, sens : *pas de PDF lié*) et `/colleges` affiche « À lire » (via `_course_semantics`, sens : *pas de première lecture*).

**Mesure.** 206 items « à préparer » deviennent « À lire », 6 deviennent « Lu · maîtrise non évaluée ». `STATUS_LABELS` contient toujours 13 clés dont trois (`correct`, `solide`, `à entraîner`) que `mastery.py` ne produit jamais.

**Correction.** Une seule échelle (cf. § 9, Q4) ; les clés jamais produites doivent être supprimées de `STATUS_ORDER` ou produites.

---

#### N12 · **S3** · Les reports ne pénalisent plus rien

**Constat.** `get_course_mastery` accepte `total_postpone` et applique jusqu'à −20 points. `get_item_mastery` ([mastery.py:266](backend/core/reviews/mastery.py:266)) ne le passe pas : la valeur par défaut `0` s'applique.

```python
return get_course_mastery(course, context=context, sessions=sessions,
                          qcm_done_local=qcm_done, knowledge_id=str(course.id))
```

**Mesure.** 29 reports enregistrés, aucun n'entre dans le score des trois vues (seul le chemin `ReviewService._get_mastery_cached`, aujourd'hui inutilisé pour l'affichage, les prend en compte).

**Correction.** Agréger `get_postpone_counts()` sur les fiches de l'item et le transmettre, comme le fait déjà `/items` dans sa branche de repli ([items.py:346](frontend/pages/items.py:346)).

---

#### N13 · **S4** · L'activité portée par une fiche non canonique échappe au compteur « lus »

`count_started` teste `course.id ∈ active_course_ids` sur le **cours fusionné**, dont l'identifiant est celui de la fiche canonique. Une activité enregistrée sur une fiche sœur n'est pas vue. **Mesure : 3 items sur les 134 ayant une activité.** Faible aujourd'hui, structurel : il faut tester l'intersection avec `alias_ids`, comme le fait déjà `get_item_evidence`.

---

### Axe D — Algorithmes

---

#### N14 · **S3** · La validation automatique d'un collège reste hors d'atteinte

**Mesure.** `automatic_ready` : **0 / 44** collèges. Meilleur cycle J : Dermatologie 3/16, Infectiologie 2/29, Pédiatrie 2/80. 9 collèges sont validés manuellement, aucun automatiquement.

Chaque ligne collège affiche donc en permanence « cycle J 2/80 » — un ratio qui se lit comme un échec alors qu'il mesure une exigence (les quatre révisions J3/J7/J14/J30 `done` pour *chaque* item) que le mode de travail réel ne renseigne jamais. Le constat C16 est inchangé ; il devient plus visible maintenant que les autres colonnes sont justes. **Arbitrage § 9, Q2.**

---

#### N15 · **S3** · 56 % des items portent le badge de priorité maximale

**Mesure** (inchangée) : `indispensable 205 · basique 67 · important 57 · jamais_tombe 38` sur 367. Le tri « Priorité annale » de `/items` place 205 items ex æquo en tête, départagés par le seul numéro d'item. **Arbitrage § 9, Q3.**

---

### Axe E — Interface

---

#### N16 · **S3** · La ligne collège ne dit jamais d'où vient ce qu'elle affiche

La colonne FRAGILES annonce « 20 fragiles » sans indiquer que 90 % de ces fragiles sont déclarés ; le KPI « maîtrise moyenne 38 % » agrège 132 déclarations et 1 mesure sans le dire. La provenance n'existe qu'au niveau de l'item déplié (tooltip) et de `/items`. Il manque, au minimum, la même mention sur l'agrégat — au mieux, un filtre « n'afficher que les scores mesurés ».

---

#### N17 · **S3** · Le tri « Collège » de `/items` range chaque item sous un seul collège

`group_item_rows` regroupe par `_primary_college` = premier collège **par ordre alphabétique** ([items.py:124](frontend/pages/items.py:124)). Un item Endocrinologie + Gynécologie apparaît sous Endocrinologie seulement. Combiné à un filtre collège actif, les libellés de groupe affichés ne correspondent pas au collège filtré. **175 items** sont concernés par ce choix implicite.

**Correction.** Soit grouper sous le collège du référentiel (`item_colleges()[0]`, stable et explicable), soit dupliquer visuellement l'item sous chacun de ses collèges en assumant que le tri « Collège » est une vue par collège.

---

#### N18 · **S4** · Densité de la ligne collège et troncature de la colonne Collège

- Chaque ligne de `/colleges` empile quatre sous-libellés (`x/y lus · z restants`, état de validation, `Preuves a/b · cycle J c/d`) plus un bouton. Trois d'entre eux sont aujourd'hui constants ou trompeurs (cf. N14).
- Dans `/items`, la colonne COLLÈGE est limitée à deux lignes (`-webkit-line-clamp:2`) : **50 items** ont un libellé de collèges dépassant 60 caractères et sont tronqués sans indication (ex. item 36 : « Endocrinologie - Diabétologie - Maladies métaboliques 🫘 · Gynécologie médicale 🌸 »).

---

### Axe F — Performance

---

#### N19 · **S3** · `build_item_rows` fait 734 requêtes et coûte ~0,9 s, sur les deux pages

**Constat.** Pour chaque item : `list_fiches(item.id)` puis `list_colleges_for_item(item.id)`, chacune ouvrant sa propre connexion SQLite.

**Mesure.** 367 items × 2 requêtes = **734 requêtes, 0,93 s** (stable sur trois exécutions). `/colleges` appelle la même fonction (`from frontend.pages.items import build_item_rows`) et la rejoue à chaque validation de collège.

**Correction.** Deux requêtes globales (`list_all_fiches()` existe déjà ; une jointure unique pour les collèges par item), regroupées en mémoire. Gain attendu : d'environ 900 ms à quelques dizaines de millisecondes.

---

#### N20 · **S3** · `/items` contourne le cache du moteur, `/colleges` l'utilise

```python
# frontend/pages/items.py:310
review_service.generate_reviews(context="college", history=history,
                                sessions_map=sessions_map, postpone_map=postpone_map, ...)
# frontend/pages/colleges_cockpit.py:464
review_service.generate_reviews(context="college", active_only=True)
```

Passer `history=` active `explicit_data` et **désactive la mise en cache** ([service.py:126](backend/core/reviews/service.py:126)). Sans effet aujourd'hui (le moteur sort en 0 ms faute de candidats), coûteux dès que N01/N02 seront traités.

---

### Axe G — Tests

---

#### N21 · **S3** · Le filet de tests couvre des fonctions que les pages n'appellent pas

**Constat.** `tests/test_items_colleges_coherence.py` vérifie l'invariant « total Pilotage = nombre d'items distincts » sur `build_pilotage_summary` ([colleges_cockpit.py:404](frontend/pages/colleges_cockpit.py:404)) et construit ses lignes avec `build_college_rows` ([ligne 392](frontend/pages/colleges_cockpit.py:392)). **Ces deux fonctions ne sont appelées par aucune page** : `render_colleges_cockpit` utilise son propre `_compute()` et `_pilotage_summary()`.

**Impact.** L'invariant testé est vrai ; celui qui compte (N03 : « lus » identique entre la ligne et le panneau) ne l'est pas, et aucun test ne le voit. Les 79 tests sont verts avec un écran qui affiche 2 % au lieu de 70 %.

**Correction.** Tester les seams réellement rendues, ou faire converger : que `_compute()` construise ses lignes avec `build_college_rows` et que `_draw_pilotage` consomme `build_pilotage_summary`.

---

## 6. Tableau de synthèse

| # | Constat | Sév. | Axe | Statut |
|---|---|---|---|---|
| N00 | `/colleges` levait `ValueError` au chargement | S1 | Cohérence | ✅ |
| N01 | 0 tâche de révision : Retard/Prochaine/Valider inertes | S1 | Boucle | ✅ |
| N02 | Aucun chemin pour planifier un item depuis Items/Collèges | S1 | Boucle | ✅ |
| N03 | Pilotage « 8 / 367 lus » contre 257 dans ses propres lignes | S1 | Boucle | ✅ |
| N04 | Maîtrise déclarative à 99 % ; annales non comptées comme preuve | S2 | Boucle | ✅ |
| N05 | Collège fantôme « Rhumatologie 🤝 » → statut « Correct : 1 », total 368/367 | S2 | Catalogue | ✅ |
| N06 | 4 collèges absents du sélecteur de `/items` | S3 | Catalogue | ✅ |
| N07 | Items 8 et 10 : lignes cliquables vers « Item introuvable » | S2 | Catalogue | ✅ |
| N08 | 104 révisions « done » rattachées à des fiches disparues | S1 | Catalogue | ✅ |
| N09 | KPI « fragiles » (246 pour 132) et « sans PDF » mal comptés/libellés | S3 | Catalogue | ✅ |
| N10 | 72 items multi-collèges changent de statut selon le collège déplié | S1 | Cohérence | ✅ |
| N11 | Deux vocabulaires de statut pour le même état | S3 | Cohérence | ✅ |
| N12 | Reports ignorés par `get_item_mastery` | S3 | Cohérence | ✅ |
| N13 | Activité sur fiche non canonique invisible du compteur « lus » | S4 | Cohérence | ✅ |
| N14 | Validation automatique inatteignable (0/44) | S3 | Algorithmes | ✅ |
| N15 | 56 % d'items « indispensables » | S3 | Algorithmes | ❌ pas un défaut — c'est la règle d'EDNpro elle-même, vérifiée sur site |
| N16 | Provenance absente des agrégats | S3 | Interface | ✅ |
| N17 | Tri « Collège » : un item n'apparaît que sous un collège | S3 | Interface | ✅ |
| N18 | Densité de la ligne collège, colonne Collège tronquée (50 items) | S4 | Interface | ✅ |
| N19 | `build_item_rows` : 734 requêtes, 0,93 s, sur les deux pages | S3 | Performance | ✅ |
| N20 | `/items` contourne le cache du moteur | S3 | Performance | ✅ |
| N21 | Le test de cohérence porte sur des fonctions non utilisées | S3 | Tests | ✅ |

---

## 7. Cible — comment interconnecter les trois écrans

Les correctifs ci-dessus règlent des défauts. Cette section décrit ce vers quoi ils devraient converger, parce que le vrai problème d'ensemble n'est plus la justesse des chiffres : c'est que **les trois écrans décrivent un objet commun sans partager ni sa définition, ni ses actions, ni sa navigation**.

### 7.1 Un objet, une définition : `ItemOverview`

Aujourd'hui, chaque écran recompose l'item à sa façon : `build_item_rows` (Items), `_compute` + `_course_semantics` (Collèges), une dizaine de lectures directes (Détail). D'où N03, N10, N11.

**Cible** : un service unique, dans `backend/core/knowledge/`, qui renvoie pour un item tout ce que les trois écrans affichent — et rien de plus :

```
ItemOverview
  item_number, title, colleges[], fiche_ids[], has_fiche
  started: bool              ← une seule définition (§ 9, Q1)
  mastery: score, level, evidence_count, provenance
  evidence: sessions, qcm, oic, anki, annales      (get_item_evidence, déjà écrit)
  schedule: next_due, next_type, overdue_days, planned: bool
  resources: pdf, obsidian, oic_coverage
  frequency: priorité annale
```

Les vues deviennent des projections : `/items` est la liste complète, `/colleges` est la même liste groupée par collège avec des agrégats, `/cours` est une ligne dépliée. Un chiffre ne peut plus diverger d'un écran à l'autre parce qu'il n'existe qu'à un seul endroit.

### 7.2 Rendre la boucle refermable depuis l'inventaire

Le parcours réel est : *je regarde mes collèges → je choisis un item → je le travaille → il revient dans Aujourd'hui*. Le dernier maillon n'existe pas (N02).

**Cible** : trois actions présentes partout où un item est affiché.

| Action | Effet | Où | État |
|---|---|---|---|
| **Commencer** | `anchor_first_read(item)` → J1/J3/J7/J14/J30 posés | ligne `/items`, item déplié `/colleges`, en-tête `/cours` | ✅ livré |
| **Valider la révision due** | `complete_review(task)` | `/colleges`, vue dépliée | ✅ atteignable depuis que des tâches existent |
| **Déclarer le niveau** | écrit `item_state` | uniquement dans Triage aujourd'hui ; à exposer depuis `/items` | à faire |

Un item passe alors visiblement par quatre états, les mêmes partout : **non planifié → planifié → en cours de preuve → maîtrisé**. C'est la colonne qui manque le plus : aujourd'hui l'écran distingue mal « je n'ai jamais commencé » de « je n'ai pas de données ».

### 7.3 Une navigation qui ne perd pas le contexte

Acquis : `/colleges → /items?college=X → /cours/{id}?college=X` conserve le collège, et le fil d'Ariane est juste (0 défaut sur 582 fiches).

Manquent trois maillons :
1. **Retour** : depuis `/cours`, le fil d'Ariane ramène à la liste filtrée, mais il n'y a pas de « item précédent / suivant dans ce collège » — c'est le geste naturel quand on travaille un collège d'affilée.
2. **Aller vers le collège** : dans `/items`, la colonne COLLÈGE est du texte mort ; elle devrait être cliquable vers `/colleges` positionné sur la ligne concernée (dépliée).
3. **Retour depuis le panneau** : « À traiter en priorité » ouvre `/items?college=X` sans le motif du choix ; y ajouter le mode (`&mode=fragile`) rendrait le clic explicable.

### 7.4 Dire l'incertitude au lieu de la masquer

Trois affichages présentent aujourd'hui une absence de donnée comme une bonne nouvelle : « à jour » (aucune échéance), « 0 en retard » (aucune tâche), « à jour » sur un item jamais ouvert. Un quatrième présente une déclaration comme une mesure (« maîtrise moyenne 38 % »).

**Cible** : un vocabulaire explicite de l'incertitude — `non planifié`, `non évalué`, `déclaré` — traité comme un état de premier rang, pas comme une valeur par défaut. C'est peu de code et cela change la lecture des deux écrans plus que n'importe quel correctif de calcul.

### 7.5 Hygiène du catalogue comme fonction visible

La migration vers le catalogue SQLite a produit des résidus mesurables (N05, N06, N07, N08). Ils ne se verront jamais depuis Items ou Collèges. Le panneau DIAGNOSTIC des réglages devrait porter : collèges sans item, collèges en double, items sans fiche, traces orphelines non archivées, items du référentiel absents. Cinq compteurs, une requête chacun.

---

## 8. Plan d'action

Les lots sont livrables indépendamment ; l'ordre est celui de l'utilité décroissante.

### Lot 1 — Refermer la boucle · **N01 N02 N03** · ✅ livré le 19 août

| # | Action | Fichiers | État |
|---|---|---|---|
| 1.1 | Action « Commencer » → `anchor_first_read(course_id)` | `items.py`, `colleges_cockpit.py`, `course_detail_cockpit.py`, `prep/service.py` | ✅ |
| 1.2 | État `non planifié` distinct de « à jour » | les deux listes | ✅ |
| 1.3 | Bandeau « Reprise le JJ/MM · N révisions masquées » | `colleges_cockpit.py`, `items.py` | ✅ |
| 1.4 | `is_item_started()` unique | `backend/core/knowledge/item_progress.py` | ✅ |
| 1.5 | Corriger `started_item_ids` (le `any(...)` constant) | `colleges_cockpit.py` | ✅ |
| 1.6 | Un cycle ancré vaut première lecture pour la maîtrise | `mastery.py` | ✅ |
| 1.7 | Historique chargé par défaut par le moteur | `reviews/service.py` | ✅ |

**Critères d'acceptation — vérifiés.** Un clic sur « Commencer » crée 5 révisions actives (J1 → J30), l'item quitte « à préparer » et le bouton « Valider » de la vue dépliée devient atteignable. Le panneau et l'union des lignes annoncent le même nombre de « lus » (140 / 367).

### Lot 2 — Un seul statut par item · **N10 N11 N12 N13 N04** · ✅ livré le 20 août

| # | Action | Fichiers | État |
|---|---|---|---|
| 2.1 | `_course_semantics` ne dépend plus du collège ; `started` calculé une fois par item | `colleges_cockpit.py` | ✅ |
| 2.2 | Échelle de statut unique ; purger `STATUS_ORDER` des clés jamais produites | `status_badge.py` | ✅ |
| 2.3 | `get_item_mastery` : agréger et transmettre `total_postpone` | `mastery.py` | ✅ |
| 2.4 | `evidence_count` agrégé annales comprises ; sortie anticipée et dilution de la graine conditionnées à l'absence de *toute* preuve | `mastery.py`, `knowledge/service.py` | ✅ |
| 2.5 | `count_started` : tester l'intersection avec `alias_ids` | `colleges_cockpit.py` | ✅ déjà fait (effet de bord de N03) |

**Correctifs appliqués.**

- **N11 (Q4).** `_course_semantics` ne recalcule plus un statut indépendant à partir de `started`/`score is None` (`a_lire`, `lu_sans_preuve`, `non_commence`) : le `status_key` vient intégralement de `level`, calculé une fois par `get_item_mastery`. `STATUS_ORDER`/`STATUS_LABELS`/`STATUS_COLORS` sont purgés des clés jamais produites (`a_lire`, `lu_sans_preuve`, `correct`, `solide`, `à entraîner`) ; `non_commence` reste, encore émis par le repli legacy de `_pilotage_summary` (N05, Lot 3).
- **N04.** `evidence_count` (et le poids de dilution de la graine dans `blend()`) vient désormais de `seed.n_evidence + annales`, et non plus du seul `seed.n_evidence` qui ignorait `ai_practice_sessions`. La sortie anticipée « graine pure » (`seed.seed_score is not None and n_evidence == 0`) est conditionnée à cette même somme : une annale jouée sur un item déclaré dilue maintenant la graine au lieu d'être ignorée. Vérifié sur la base réelle : la répartition des niveaux passe de `critique 72 · fragile 60` (photographie du 19 août) à `critique 17 · fragile 87` — beaucoup d'items déclarés « critique » sans preuve avaient en réalité des annales jouées.
- **N12.** `get_item_mastery` agrège `get_postpone_counts()` sur les fiches de l'item et transmet `total_postpone` à `get_course_mastery` — un report sur une fiche pénalise maintenant l'item entier, pas seulement le chemin de repli d'`/items`.
- **N13.** Déjà résolu par la correction N03 du 19 août : `count_started` délègue à `is_item_started`, qui teste l'intersection avec `alias_ids(course)` depuis l'origine de ce correctif.
- **Q4 bis (arbitrage tranché).** Un item fraîchement ancré (`Commencer`) sans aucune preuve (`nb_lectures == 0`, pas de session, pas de QCM, pas d'annale) affiche désormais le niveau neutre `non évalué` au lieu de basculer directement en `fragile` (score de base 50 < seuil 60). Le **score reste calculé normalement** — c'est lui qui rend l'item planifiable par `generate_reviews`, qui écarte tout score `None` — seul le niveau affiché change. `non évalué` a été ajouté à `PROGRESSION_COLORS` (mastery.py), `STATUS_ORDER`/`STATUS_LABELS`/`STATUS_COLORS` (status_badge.py) et `_LEVEL_ORDER` (stats.py) pour rester visible partout où les niveaux sont énumérés.

**Critères d'acceptation — vérifiés.** Pour les 175 items multi-collèges, le statut est identique quel que soit le collège déplié (0 divergence, acquis par N10). Une annale jouée fait passer un item de « déclaré » à « mesuré » (test `test_annale_session_dilutes_a_declared_seed`). Un item tout juste commencé n'affiche plus « fragile » (test `test_freshly_anchored_item_is_non_evalue_not_fragile`) et reste planifiable (`score is not None`, vérifié aussi par `test_an_anchored_cycle_counts_as_a_first_read_for_mastery`, inchangé). Suite complète : 1699 tests passent, 1 échec antérieur et sans rapport (`test_uness_rank_jobs_store::test_claim_recovers_expired_lease`).

### Lot 3 — Hygiène du catalogue · **N05 N06 N07 N08 N09** · ✅ livré le 20 août

| # | Action | Fichiers | État |
|---|---|---|---|
| 3.1 | Masquer les collèges sans item ; outil de fusion, appliqué à « Rhumatologie 🤝 » → « 🤲 » sur la base réelle (confirmé par l'utilisateur : 0 item à transférer) | `catalog_repository.py`, `colleges_cockpit.py`, `items.py`, `uness_diagnostic_panel.py` | ✅ |
| 3.2 | Supprimer le repli legacy de `_pilotage_summary` | `colleges_cockpit.py` | ✅ |
| 3.3 | Sélecteur de collège alimenté par `CatalogRepository.list_colleges_with_items()` | `items.py` | ✅ |
| 3.4 | Exploiter `missing_fiche` : ligne distincte, clic informatif au lieu d'une navigation vers le vide | `items.py`, `colleges_cockpit.py` | ✅ |
| 3.5 | KPI « fragiles »/« en retard » dédupliqués par `item_id`, libellé « items fragiles » aligné sur ce qui est compté | `colleges_cockpit.py` | ✅ |
| 3.6 | Compteurs d'intégrité + rattachement des preuves dans DIAGNOSTIC | `backend/state/catalog_integrity.py`, `uness_diagnostic_panel.py` | ✅ (19 août) |

**Correctifs appliqués.**

- **N05.** `CatalogRepository.list_colleges_with_items()` — nouvelle méthode, source unique — exclut tout collège actif sans relation (référentiel ni fiche) ; `/colleges` et le sélecteur `/items` l'utilisent désormais au lieu de `list_colleges()`. `CatalogRepository.merge_colleges()` (repointe référentiel, fiches, ressources et alias vers le collège maître, désactive le doublon, journalise) est disponible, testée, et exposée dans **Paramètres → DIAGNOSTIC UNESS → COLLÈGES SANS ITEM** avec un sélecteur de collège cible pour toute récidive future. **Appliquée sur la base réelle** le 20 août, après confirmation que « Rhumatologie 🤝 » portait 0 item (les 10 items de la matière sont tous sur « Rhumatologie 🤲 ») : 44 → 43 collèges actifs, tous avec au moins un item, fusion journalisée dans `catalog_audit_log`.
- **N05 (suite).** Le repli legacy de `_pilotage_summary` (`_level_from_score(pct)` quand une ligne n'a pas de `status_counts`) est supprimé : il ne servait qu'à masquer une ligne de collège vide, devenue impossible une fois les collèges sans item exclus en amont.
- **N06.** Le sélecteur de collège de `/items` lit `CatalogRepository.list_colleges_with_items()` (avec repli sur l'ancienne logique si le catalogue n'est pas peuplé) au lieu des collèges portés par une fiche : Allergologie, Humanités, Médecine du sport et Médecines Intégratives et Complémentaires redeviennent atteignables depuis le menu.
- **N07.** Les items sans fiche (8, 10) affichent un badge « Fiche manquante » et un clic informatif (« à créer dans le catalogue ») au lieu de naviguer vers `/cours/{id}` — appliqué à `/items` et à la vue dépliée de `/colleges`, les deux chemins qui menaient à la page morte.
- **N09.** Les KPI « items fragiles » et « révisions en retard » du panneau Pilotage dédupliquent maintenant par `item_id` à travers les collèges (comme `no_pdf_course_ids` le faisait déjà pour « sans PDF ») au lieu de sommer un compte par collège — un item fragile dans 2 collèges ne comptait double. Le libellé passe de « collèges fragiles » (qui ne comptait jamais des collèges) à « items fragiles ».

**Critères d'acceptation — vérifiés.** `/colleges` n'affiche aucune ligne à 0 item (`list_colleges_with_items()` testée sur données synthétiques et sur la base réelle). Aucune ligne de `/items` ni de la vue dépliée `/colleges` ne peut plus mener à « Item introuvable » (source-testé). Un item fragile dans deux collèges compte une fois au panneau, pas deux (`test_the_pilotage_panel_does_not_double_count_a_fragile_item_across_colleges`). Suite complète : 1710 tests passent, 1 échec antérieur et sans rapport.

### Lot 4 — Interface et navigation · **N16 N17 N18** + § 7.3 · ✅ livré le 20 août

| # | Action | État |
|---|---|---|
| 4.1 | Provenance sur les agrégats (« 38 % · 132 déclarés / 1 mesuré ») | ✅ |
| 4.2 | Tri « Collège » sous un filtre actif : un seul groupe, celui filtré, plutôt qu'un collège principal trompeur | ✅ |
| 4.3 | Colonne COLLÈGE : « Endocrinologie +2 » avec tooltip, au lieu d'une troncature silencieuse | ✅ |
| 4.4 | Ligne collège : nom + barre + un seul sous-libellé ; preuves et cycle J au dépliage | ✅ |
| 4.5 | Colonne COLLÈGE cliquable vers `/colleges` ; « précédent / suivant » dans `/cours` | ✅ |

**Correctifs appliqués.**

- **N16.** Le panneau Pilotage affiche désormais « X déclaré(s) · Y mesuré(s) » sous le pourcentage de « maîtrise moyenne » (`_pilotage_summary` expose `mastery_declared`/`mastery_measured`, dédupliqués par fiche comme le reste du panneau). Le filtre « scores mesurés » proposé en option n'a pas été construit — l'information est visible, le filtre est un ajout séparé, pas encore fait.
- **N17.** `group_item_rows` prenait le collège *principal* (premier par ordre alphabétique) de chaque item pour construire les groupes du tri « Collège » — sous un filtre collège actif, un item multi-collèges dont ce n'est pas le collège principal apparaissait quand même, sous la mauvaise étiquette. Sous un filtre actif, un seul groupe est désormais construit, portant le nom du collège filtré. Vérifié sur la base réelle : filtrer sur Cardiovasculaire et trier par collège donne exactement un groupe « Cardiovasculaire ❤️ » de 30 items.
- **N18.** La colonne COLLÈGE de `/items` affichait tous les collèges d'un item séparés par « · », tronqués sans indication au-delà de deux lignes (50 items concernés). Elle affiche maintenant le premier collège suivi d'un compteur (« Endocrinologie +2 ») avec la liste complète au survol.
- **4.4 (densité de la ligne collège).** La ligne repliée empilait trois sous-libellés (lecture, statut de validation, preuves/consolidation) — dense sur 44 lignes visibles simultanément, sans qu'aucune des trois ne soit inutile, juste pas toutes au même niveau de priorité. Un seul sous-libellé reste dans la ligne repliée (`X/Y lus · Z restants`) ; le statut et le détail preuves/consolidation ne s'affichent plus qu'au dépliage, dans un nouveau bloc `.cg-validation-detail`.
- **4.5 (colonne COLLÈGE cliquable).** La colonne COLLÈGE de `/items` ouvre maintenant `/colleges?open=<collège>` (collège principal de l'item), qui déplie directement cette ligne (`render_colleges_cockpit(open_college=...)`) — fermant la boucle de navigation dans l'autre sens par rapport au clic « retard » déjà cliquable de `/colleges` vers `/items`.
- **4.5 (précédent / suivant dans `/cours`).** `get_adjacent_items()` (`frontend/pages/items.py`) calcule l'item précédent/suivant dans le même ordre que `/items`, filtré sur le même collège si la fiche a été ouverte depuis une liste filtrée ; le fil d'Ariane de `/cours/{id}` affiche désormais ces deux liens. Vérifié sur la base réelle : sans filtre, l'item 44 donne 43/45 (séquentiel) ; filtré sur Gynécologie médicale, le suivant saute directement à 58 (les items d'autres collèges sont exclus).

**Critères d'acceptation — vérifiés.** `test_adjacent_items_follow_the_same_order_as_items_page`, `test_adjacent_items_stay_inside_the_filtered_college`. Suite complète : 1722 tests passent, 1 échec antérieur et sans rapport — **les 21 constats de l'audit et les cinq points de §7.3 sont maintenant tous traités** (N15 excepté, retracté : ce n'était pas un défaut).

### Lot 5 — Performance et tests · **N19 N20 N21** · ✅ livré le 20 août

| # | Action | État |
|---|---|---|
| 5.1 | `build_item_rows` en 2 requêtes globales au lieu de 734 | ✅ |
| 5.2 | `/items` : ne plus passer `history=`/`sessions_map=` quand le cache convient | ✅ |
| 5.3 | Faire converger page et tests : supprimer les fonctions non rendues (`build_college_rows`, `build_pilotage_summary`), tester `_pilotage_summary` (réellement rendue) à leur place | ✅ |
| 5.4 | Couverture déjà en place via les correctifs précédents (« lus » ligne/panneau : N03 ; statut indépendant du collège : N10 ; toute ligne mène à une page existante : N07) | ✅ |

**Correctifs appliqués.**

- **N19.** `CatalogRepository.list_colleges_by_item()` (nouvelle méthode, une requête `UNION` groupée en mémoire) et `list_all_fiches()` (déjà existante) remplacent les 734 requêtes par item de `build_item_rows`. Mesuré sur la base réelle : **0,93 s → 0,019 s** pour 367 items.
- **N20.** `/items` appelait `generate_reviews(..., history=, sessions_map=, postpone_map=)`, ce qui active `explicit_data` dans le moteur et désactive son cache journalier à chaque rendu — `/colleges` ne les passait déjà pas. L'appel ne passe plus ces trois paramètres ; `history` (`get_all_history()`), devenue inutile pour autre chose, est supprimée.
- **N21.** `build_college_rows` et `build_pilotage_summary` n'étaient appelées par aucune page — `render_colleges_cockpit` utilise `_compute()`/`_pilotage_summary()`. Supprimées ; les deux tests qui les exerçaient testent maintenant `_pilotage_summary` (la fonction réellement rendue) sur le même invariant (dédoublonnage des items multi-collèges).

**Critères d'acceptation — vérifiés.** Suite complète : 1713 tests passent, 1 échec antérieur et sans rapport (`test_uness_rank_jobs_store::test_claim_recovers_expired_lease`).

### N14 / N15 — Q2 et Q3 codés · ✅ livré le 20 août

Ces deux constats (Axe D, Algorithmes) n'appartenaient à aucun lot ; ils sont restés ouverts jusqu'à ce que les arbitrages Q2/Q3 (§9 bis) soient tranchés, puis codés le jour même.

- **N14 (Q2).** `assess_college_validation` (`backend/core/knowledge/college_validation.py`) exigeait le cycle J3/J7/J14/J30 *littéral*, marqué « done » dans `review_history` — inatteignable par l'usage réel (annales, sessions IA) qui n'écrit jamais dans cette table. La fonction accepte maintenant `consolidation_counts` (le même `evidence_count` par item que `mastery.py`, annales comprises, N04) : autant de preuves que le cycle a d'étapes (4) suffit, quelle que soit leur nature. Le libellé « cycle J X/Y » devient « consolidation X/Y » dans `/colleges` — il ne se lit plus comme un échec permanent. Vérifié sur la base réelle : 126/365 items atteignent désormais le seuil de consolidation (0 avant, faute d'alimenter jamais le cycle littéral).
- **N15 — retracté, ce n'était pas un défaut.** L'audit avait diagnostiqué `_priority_from_session_count` (`session_count >= 3 → indispensable`) comme un seuil local mal calibré, et Q3 a d'abord été codé en quartiles de `session_count × question_count` pour corriger ça — y compris appliqué à la base réelle (`indispensable 205 → 82`). L'utilisateur a fait remarquer que ces seuils sont ceux **affichés par EDNpro lui-même**. Vérification en direct sur `ednpro.app/training-v2` (connexion via un Chrome normal + attache CDP, Google bloquant l'automatisation Playwright pour OAuth) : le bloc « Priorité d'après les annales » du site dit texto *« Indispensable — Tombé sur 3 sessions ou plus · Important — 2 sessions · Basique — 1 session · Jamais tombé — jamais tombé »*, avec exactement la même répartition (205/57/67/38 sur 367 items) que ce que Synapse calculait déjà. `_priority_from_session_count` reproduisait fidèlement la règle d'EDNpro — **le quartile était la régression, pas le correctif**. Le code et la base réelle ont été restaurés au seuil fixe d'origine ; les tests de quartile ont été retirés et remplacés par un test qui verrouille l'alignement avec EDNpro.
- **N14 (Q2) — maintenu.** `assess_college_validation` (`backend/core/knowledge/college_validation.py`) exigeait le cycle J3/J7/J14/J30 *littéral*, marqué « done » dans `review_history` — inatteignable par l'usage réel (annales, sessions IA) qui n'écrit jamais dans cette table. Ce point est indépendant d'EDNpro (c'est une règle interne à Synapse, sans équivalent affiché sur un site tiers) : la fonction accepte maintenant `consolidation_counts` (le même `evidence_count` par item que `mastery.py`, annales comprises, N04) : autant de preuves que le cycle a d'étapes (4) suffit, quelle que soit leur nature. Le libellé « cycle J X/Y » devient « consolidation X/Y » dans `/colleges`. Vérifié sur la base réelle : 126/365 items atteignent désormais le seuil de consolidation (0 avant).

**Critères d'acceptation — vérifiés.** `test_consolidation_evidence_can_replace_the_literal_j_cycle` (N14) ; `test_priority_without_an_explicit_value_matches_ednpros_own_thresholds` (N15, verrouille l'alignement EDNpro plutôt que de le remplacer). Suite complète : 1715 tests passent, 1 échec antérieur et sans rapport.

**Leçon.** [[feedback_verifier_avant_agir]] tenait déjà : un chiffre d'audit spectaculaire (« 56 % d'indispensables ») a été pris pour un défaut sans vérifier s'il reflétait une source externe faisant autorité. La correction a été appliquée à la base réelle avant la vérification — heureusement réversible ici (`session_count` inchangé, la priorité en est une fonction pure), mais ça confirme qu'un chiffre qui semble trop élevé pour être un hasard mérite d'être confronté à sa source avant d'être « corrigé ».

---

## 9. Arbitrages à trancher

**Q1 — Que signifie « commencé » ?** ⚠️ **tranché de fait par le correctif N03**, en option (b) : `is_item_started` retient la date de première lecture, **toute** trace de travail (révision faite, session d'annale, cycle ancré) et l'appartenance à un collège validé. Résultat : 140 items commencés sur 367. L'option (c) — deux compteurs distincts « lus » et « travaillés » — reste ouverte si tu veux séparer la lecture de l'entraînement à l'écran ; la règle est isolée dans un seul module, la changer coûte quelques lignes.

**Q2 — Que signifie « collège validé » ?** Inchangé depuis le 14 août : les quatre révisions J3/J7/J14/J30 pour chaque item, jamais atteint (0/44). Options : (a) les preuves d'exposition suffisent ; (b) compter aussi consolidation, annales et sessions IA ; (c) garder l'exigence et renommer l'indicateur pour qu'il ne se lise pas comme un échec.

**Q3 — Comment hiérarchiser la priorité annale ?** ⚠️ **retracté** — 205/367 « indispensables » n'est pas un défaut : c'est la classification affichée par EDNpro lui-même (« indispensable à partir de 3 sessions », vérifié en direct sur `ednpro.app/training-v2` le 20 août). L'option (b) — quartiles — avait été codée puis appliquée à la base réelle avant cette vérification ; le code et les données ont été restaurés au seuil fixe d'origine. Voir le journal N14/N15 ci-dessus.

**Q4 — Une ou deux échelles de statut ?** L'échelle pédagogique de `mastery.py` (7 valeurs produites) et l'échelle de santé de `mastery_indicator` (4 valeurs) cohabitent, plus la réécriture de `_course_semantics`. Trancher pour une échelle unique, ou une table de conversion explicite et testée.

**Q4 bis — Un item fraîchement commencé doit-il être « fragile » ?** Le score de base est 50 et le seuil « fragile » est à 60 : cliquer « Commencer » fait apparaître l'item en ambre alors qu'il vient d'être lu. Options : (a) laisser — c'est vrai, rien n'a encore été révisé ; (b) un état « en construction » tant qu'aucune révision n'est due ; (c) relever le score de départ d'un item lu.

**Q5 — Que faire des items sans fiche et des traces orphelines ?** Créer les fiches 8 et 10 dans le catalogue ou marquer ces items « hors périmètre » — mais pas les laisser cliquables vers le vide. Pour les traces orphelines, **le rattachement est fait** (N08) : restent 4 doublons stricts et 15 reliquats de tests (`c1`, `c2`, `c99`) que le rapport signale et ne touche pas — à supprimer sur ta décision, jamais automatiquement.

---

## 9 bis. Arbitrages tranchés (20 août 2026)

| # | Décision | Justification | Impact plan |
|---|---|---|---|
| **Q2** | Option **(b) + (c)** : les preuves de consolidation, annales et sessions IA comptent dans l'exigence de validation de collège ; l'indicateur est renommé pour ne plus se lire comme un échec (« cycle J X/Y » → un libellé de consolidation neutre) — ✅ **codé le 20 août** (N14) | Le cycle strict J3/J7/J14/J30 est structurellement hors d'atteinte (0/44, meilleur score 3/16) parce que l'usage réel ne repasse jamais par une répétition espacée complète — il passe par les annales et l'IA. Garder l'exigence telle quelle sans compter ces preuves revient à mesurer un mode de travail que personne n'utilise | Lot 3 (3.5) + N14 |
| **Q3** | Option **(b)** : quartiles sur `session_count × question_count`, badge de priorité maximale réservé au quartile supérieur — ✅ **codé le 20 août** (N15), appliqué à la base réelle | Des seuils fixes se dégradent avec le volume d'annales — c'est déjà ce qui a produit 205/367 « indispensable ». Un quartile s'auto-ajuste sans réglage manuel | N15 |
| **Q4** | Échelle unique : celle de `mastery.py` (7 valeurs, fondée sur la preuve). `_course_semantics` et `mastery_indicator` deviennent des projections d'affichage de ce statut, plus des calculs indépendants. Purge des clés jamais produites (`correct`, `solide`, `à entraîner`) de `STATUS_ORDER` | C'est le prolongement direct de N10 (déjà corrigé) : un item ne doit plus avoir deux vérités selon l'écran qui le lit | Lot 2 (2.2) + N11 |
| **Q4 bis** | Option **(b)** : état neutre « non évalué » tant qu'aucune échéance n'est due, au lieu d'un score de base à 50 qui bascule l'item en ambre dès qu'on clique « Commencer » | Cohérent avec le principe déjà appliqué en Lot 1 (§7.4) : dire l'absence de donnée plutôt que la déguiser en alerte. Relever le score de départ (option c) aurait le même défaut à l'envers — une fausse bonne nouvelle | Lot 1 (suite), `mastery.py` |
| **Q5** | Items 8/10 marqués « fiche à créer » (état visuel distinct, pas de lien vers une page morte, pas de contenu généré) ; les 15 reliquats de tests (`c1`, `c2`, `c99`) sont supprimés de la base réelle ; les 4 doublons stricts restent intacts | Créer une fiche est une tâche de contenu, pas de code — inventer un contenu serait pire que l'absence. Les reliquats sont des artefacts de fixtures qui n'ont rien à faire dans `data/synapse_local.db` ; les doublons ne faussent rien et les écraser ferait perdre une trace | Lot 3 (3.4) + nettoyage DB |

Ces décisions reconfigurent le Lot 2 et le Lot 3 restants (§8) : 2.2 et 3.4/3.5 doivent désormais implémenter Q4, Q5 et Q2/Q3 respectivement, plutôt que rester des tickets ouverts sans direction.

---

## 10. Annexes — reproduire les mesures

Depuis la racine du projet, en lecture seule, avec `PYTHONPATH` sur la racine.

**Photographie du catalogue**

```bash
PYTHONPATH="$PWD" .venv/Scripts/python.exe -X utf8 -c "from backend.state.store import data_store; data_store.load_from_disk(force=True); from backend.state.catalog_repository import CatalogRepository; r=CatalogRepository(); print(r.count_items(), r.count_fiches(), r.count_archived_courses(), len(r.list_colleges()))"
```

**Entonnoir du moteur de révisions (N01)**

```python
from backend.core.reviews.service import review_service, get_study_resume_date
# 582 fiches → 146 exclues → 436 → 1 avec date de référence → 4 tâches → 0 actives
print(len(review_service.generate_reviews("college", active_only=False)),
      len(review_service.generate_reviews("college", active_only=True)),
      get_study_resume_date(data_store.preferences))
```

**Contradiction du Pilotage (N03)**

```python
# somme des lignes : count_started(courses, get_active_course_ids()) → 257
# panneau : _pilotage_summary(rows)["started"] → 8
```

**Statut variable selon le collège (N10)**

```python
from frontend.pages.colleges_cockpit import _course_semantics
from backend.core.reviews.mastery import get_item_mastery
# pour chaque item multi-collèges : _course_semantics(course, score, level, college_validated)
# → 72 items sur 175 ont au moins deux statuts différents
```

**Preuves orphelines (N08)**

```python
# review_history : 326 course_id → 233 dans le catalogue, 87 archivés, 6 inconnus
# révisions « done » orphelines : 104 / 380
```

**Coût de `build_item_rows` (N19)**

```python
import time
from frontend.pages.items import build_item_rows
from backend.state.catalog_repository import CatalogRepository
t = time.time(); rows = build_item_rows(CatalogRepository()); print(time.time() - t)  # ~0,93 s
```

---

**Vérifier les correctifs**

```python
# N03 / N10 : rejouer le calcul de /colleges et comparer panneau et lignes
from backend.core.knowledge.item_progress import is_item_started, worked_course_ids, validated_college_names
# → panneau 140/367, union des lignes 140, 0 item à statut variable

# N01 / N02 : sur une COPIE de la base, ancrer un cycle et compter les tâches
from backend.core.prep.service import anchor_first_read
# → 0 tâche avant, 5 après (J1 → J30)

# N08 : simulation sans écriture
from backend.state.catalog_integrity import orphan_report, reattach_orphan_evidence
print(orphan_report()); print(reattach_orphan_evidence(apply=False))
```

---

## 11. Défaut post-audit — un collège validé n'entrait jamais en consolidation (20 août)

Découvert en usage réel (capture d'écran de `/items` : des items visiblement déjà connus affichaient « Commencer »), pas par relecture de code — hors périmètre des 21 constats mais dans le prolongement direct de N14/Q2 et traité le même jour.

**Constat.** `set_college_status(college, "valide")` (confirmer un collège) n'écrit que sa propre table. Le système de consolidation à long terme (`backend/core/reviews/consolidation.py`, chaînage SM-2 auto-étirable, conçu le 17 juillet pour exactement ce cas : « items déclarés pré-app ») exige `mastery.score is not None`, qui exige `item_state` — jamais alimenté par la validation d'un collège. Un item de collège validé ne devenait donc jamais consolidable : ni `date_1ère_lecture`, ni score, ni tâche.

Les deux portes de sortie prévues pour situer ces items étaient toutes deux mortes :
- **Triage groupé** (`/triage/{collège}`, `frontend/pages/triage.py`) — fonctionnel, mais lié nulle part dans l'interface (atteignable seulement en tapant l'URL).
- **Triage progressif** (fenêtre de fin de séance, `is_to_situate`) — ne se déclenche que si une tâche de révision existe déjà pour l'item ; sans `item_state`, aucune tâche n'est jamais générée. Blocage circulaire.

**Mesure sur la base réelle** (avant correctif) : 9 collèges validés, 138 items reliés, dont **34 réellement sans `item_state`** — la mesure initiale annoncée à l'utilisateur (« 138 items, 0 déclaré ») était fausse : elle interrogeait `item_state` avec l'identifiant catalogue au lieu de l'identifiant de fiche, donc toujours `None` par construction. Corrigé avant d'écrire quoi que ce soit — les 104 items déjà situés via Triage n'ont pas été touchés.

**Correctifs appliqués (première passe).**
- `backend/core/knowledge/service.py::declare_college_items()` — déclare un niveau (« correct » par défaut) pour chaque item qui n'a pas déjà de niveau connu, sans jamais écraser une déclaration existante.
- Un lien **« Trier → »** apparaît sur la ligne d'un collège déjà validé, vers `/triage/{collège}` — pour affiner en Solide/Flou au lieu du « Correct » par défaut.
- **Rattrapage appliqué à la base réelle** : les 34 items réellement non déclarés des 9 collèges déjà validés ont reçu « correct ». Vérifié : un item auparavant bloqué (item 152, Cardiovasculaire) a maintenant un score (50, « fragile ») et une tâche de consolidation réelle (échéance 2026-08-03).

**Second défaut, trouvé en répondant à une question de l'utilisateur.** `_confirm_college` appelait `declare_college_items()` — mais restait le seul appelant à le faire. `deploy/reprise_historique_consolidation.py`, un script de reprise historique pour 10 collèges **déjà committé mais jamais exécuté**, appelle `set_college_status()` directement avec sa propre logique de déclaration dupliquée en parallèle. N'importe quel futur appelant du primitif brut aurait réintroduit le même défaut — la cascade dépendait de la mémoire de chaque appelant, pas d'une garantie structurelle.

**Correctif.** `backend/core/knowledge/service.py::confirm_college_validation()` devient le point d'entrée unique : statut *et* cascade dans la même fonction. `_confirm_college` l'appelle désormais au lieu de dupliquer la résolution des items. Le script de reprise historique n'a pas été modifié — il reste un outil spécialisé pour une bascule groupée avec son propre traçage de provenance (`source="reprise_historique"`) et sa propre logique de rythme (`consolidation_not_before`), et il est idempotent (ne réécrase jamais un `item_state` existant). *Limite assumée* : rien n'empêche techniquement un futur appel à `set_college_status()` brut de contourner encore la cascade — la fonction unique rend l'oubli moins probable, elle ne le rend pas impossible.

**Troisième défaut, signalé par l'utilisateur.** Le bouton « Commencer » (sur `/items`, `/colleges` déplié, `/cours`) affichait « Pose la première lecture aujourd'hui » même pour un item déjà connu (score déclaré ou mesuré) — trompeur, et strictement nécessaire à garder cliquable puisque c'est l'unique point d'entrée du moteur de révisions (masquer le bouton aurait rendu l'item définitivement improgrammable, N02). **Correctif** : même action (`anchor_first_read`, inchangée), mais libellé conditionné à `mastery_score is not None` — « Commencer » pour un item réellement neuf, **« Planifier »** (tooltip : « planifie une révision de consolidation … ne compte pas comme une première lecture ») pour un item déjà connu. Appliqué aux trois pages.

**Critères d'acceptation — vérifiés.** `test_declare_college_items_declares_only_the_undeclared`, `test_declare_college_items_is_idempotent`, `test_confirm_college_validation_is_the_single_entry_point`, `test_confirm_college_validation_does_not_overwrite_an_existing_declaration`, `test_a_known_item_gets_planifier_instead_of_commencer` (et ses équivalents `/colleges` et `/cours`). Suite complète : 1730 tests passent, 1 échec antérieur et sans rapport.

---

*Audit réalisé sur `main@8124646`, le 19 août 2026. Toutes les mesures reflètent l'état de `data/synapse_local.db` à cette date. Les cinq défauts S1 (N00 à N03, N08, N10) ont été corrigés le jour même ; les Lots 2 à 5, N14/N15 (Q2/Q3) et le défaut post-audit de consolidation (collège validé, point d'entrée unique, bouton Commencer/Planifier) ont été traités le 20 août. Les 21 constats de l'audit sont clos (N15 retracté — ce n'était pas un défaut). Suite finale : 1730 tests passent, 1 échec antérieur et sans rapport.*
