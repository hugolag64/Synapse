# Socle « état des connaissances » — Design

**Date :** 2026-07-14
**Bloc :** 1/3 de la refonte « planification longitudinale »
**Statut :** validé en brainstorming, prêt pour le plan d'implémentation

---

## 1. Problème

Synapse ne sait pas représenter un collège **validé académiquement** dont les items n'ont **jamais été évalués**. Concrètement, l'utilisateur a validé Cardiologie et Pneumologie avant d'utiliser Synapse : ces collèges sont invisibles du système.

La cause est identifiée dans le code :

- `mastery.py` renvoie `score = None` pour tout cours sans `date_1ere_lecture` ;
- `ReviewService.generate_reviews()` (backend/core/reviews/service.py) écarte tout cours dont `mastery.score is None` ;
- il n'existe aucun statut au niveau du **collège** — ce n'est qu'une étiquette portée par le cours.

Conséquence : aucune tâche ne peut être générée pour un ancien collège, et rien ne distingue « item maîtrisé » de « item jamais entré dans Synapse ».

## 2. Périmètre

**Dans le périmètre :** le modèle d'état (collège + item), le moteur de maîtrise qui l'exploite, les points de saisie dans l'UI.

**Hors périmètre**, traité par les blocs suivants :

- **Bloc 2 — moteur de planification longitudinale :** sélection automatique des anciens collèges, rotation, budget de temps quotidien, files rigides vs flexibles, boost pré-stage, audit et branchement des QCM.
- **Bloc 3 — intégration Anki :** AnkiConnect, mapping cartes → collège/item, estimation de charge, activation progressive.

Ce bloc rend les anciens items **représentables et planifiables**. Il ne décide pas *quand* ils sont planifiés.

## 3. Décisions de conception

### 3.1 Deux niveaux de validation, de coût et de valeur différents

| | Coût | Valeur probante | Obligatoire |
|---|---|---|---|
| **Déclaration** (case à cocher, niveau ressenti) | quasi nul | faible, s'efface | oui — c'est le socle |
| **Évaluation OIC** (AnythingLLM, réponse ouverte jugée) | élevé | forte, définitive | non — bonus |

La déclaration permet d'amorcer le système sans reprendre 300 items. L'évaluation OIC est la « seconde validation » visée mais jamais imposée.

### 3.2 Validation = billet d'entrée dans l'entretien, pas sortie du circuit

Cocher « item validé » ne retire pas l'item du planning : ça le fait passer de *inconnu de Synapse* à *connu, à entretenir*. Avec un horizon EDN à ~2 ans, un item déclaré solide aujourd'hui sera partiellement oublié : le système doit en tenir compte de lui-même.

La validation porte un **niveau déclaré à trois crans** : `solide` · `correct` · `flou`. Sans lui, les items d'un collège validé seraient 300 objets strictement équivalents, et l'algorithme n'aurait aucun moyen de savoir par où commencer.

### 3.3 Triage progressif par défaut, triage groupé en option

Cocher « collège validé » ne demande aucune saisie. Ses items entrent dans l'état **« à situer »**, et leur niveau est déclaré au fil du planning, comme sous-produit d'une vraie révision (voir §6.4). Un écran de triage groupé reste disponible pour les collèges où l'utilisateur sait déjà, sans réfléchir, ce qui est solide et ce qui est perdu.

Contrainte respectée : *« je ne veux pas devoir reprendre entièrement un collège avant de pouvoir l'utiliser »*.

### 3.4 Trois statuts de collège, saisis ; le reste est calculé

Tout état saisi à la main est un état qui finit désynchronisé. On ne stocke donc que le minimum.

**Saisis :** `non_etudie` (défaut) · `en_cours` (enseigné cette année) · `valide` (enseignement terminé, partiel réussi).

**Calculés, jamais stockés :** *en entretien* (≥ 1 item trié et révisé) · *% d'items situés* · *actif dans la rotation* (décidé par le bloc 2) · *délaissé* (non travaillé depuis N jours).

L'état « terminé mais non validé » a été écarté : le cas ne se présente pas chez l'utilisateur.

---

## 4. Modèle de données

Deux tables SQLite dans `data/synapse_local.db`. **Aucune écriture Notion** — ce sont des données de pilotage personnel, comme les stages.

### `college_status`

| colonne | type | contenu |
|---|---|---|
| `college` | TEXT PK | nom du collège Notion, **emoji à la fin** (`Cardiovasculaire ❤️`), conforme à `COLLEGE_MAPPING` |
| `status` | TEXT | `non_etudie` \| `en_cours` \| `valide` — défaut `non_etudie` |
| `validated_at` | TEXT | date ISO du passage à `valide`, `NULL` sinon |
| `updated_at` | TEXT | date ISO |

Un collège absent de la table est réputé `non_etudie`. Aucun backfill nécessaire.

### `item_state`

| colonne | type | contenu |
|---|---|---|
| `course_id` | TEXT | PK composite |
| `context` | TEXT | PK composite — `college` \| `ue`, aligné sur le reste du projet |
| `declared_level` | TEXT | `solide` \| `correct` \| `flou`, ou `NULL` |
| `declared_at` | TEXT | date ISO de la déclaration — **origine de la dégradation** |
| `source` | TEXT | `triage` (écran groupé) \| `reprise` (au fil du planning) |
| `updated_at` | TEXT | date ISO |

**L'état « à situer » n'est pas stocké** : c'est un item d'un collège `valide` dont `declared_level IS NULL`. Un état calculé ne peut pas se désynchroniser.

---

## 5. Moteur de maîtrise

Le niveau déclaré n'est pas un score : c'est **un a priori qui s'efface**. Deux mécanismes, tous deux appelés depuis `mastery.py`.

### 5.1 La graine se dégrade

```
SEED = { solide: 70, correct: 50, flou: 30 }
DECAY_PER_30D = 2 points
SEED_FLOOR    = 25

graine(t) = max(SEED_FLOOR, SEED[niveau] - DECAY_PER_30D × (jours_écoulés / 30))
```

`jours_écoulés` est compté depuis `declared_at`. Un item déclaré `solide` atteint le plancher en ~22 mois, un `correct` en ~12 mois : l'horizon EDN est couvert sans que rien ne stagne indéfiniment en haut de l'échelle.

**La dégradation s'arrête dès qu'une preuve réelle existe** — au-delà, c'est l'évidence qui pilote, pas le temps. Précisément : `jours_écoulés` est compté jusqu'à la date de la **première preuve** si elle existe, jusqu'à aujourd'hui sinon. La graine est donc gelée à sa valeur du jour où la première vraie donnée est arrivée.

### 5.2 L'évidence prend le dessus

Une **preuve** est une session d'étude, un résultat de QCM, ou une tentative OIC.

```
n = nombre de preuves réelles
poids_graine = 1 / (1 + n)
score_final  = poids_graine × graine(t) + (1 - poids_graine) × score_calculé
```

| preuves | poids de la graine |
|---|---|
| 0 | 100 % — la graine seule |
| 1 | 50 % |
| 2 | 33 % |
| 3 | 25 % |

La graine ne disparaît jamais brutalement, elle est diluée. `score_calculé` est le score existant de `mastery.py`, inchangé.

### 5.3 Effet sur `ReviewService` — et ce qui ne change pas

Un item déclaré a désormais un score au lieu de `None` : il devient **planifiable**.

Il ne produit pour autant **aucune tâche J3/J7/J14/J30**, parce que la génération JX exige une `date_1ere_lecture` qu'il n'a pas (`service.py`, boucle `for c in cours_snapshot`). C'est **voulu** : le cycle d'entretien des anciens items est le sujet du bloc 2. Le bloc 1 ne modifie donc le comportement d'aucune tâche existante — c'est le test de non-régression central (§7).

### 5.4 Couche OIC

Deux indicateurs calculés par item, à partir de `lisa_oic` :

- **couverture rang A** = % d'OIC de rang A réussis ;
- **couverture rang B** = affichée, sans aucune conséquence sur le score ou la planification.

Un OIC est **réussi** quand `lisa_oic.mastered = 1`.

**Chaînon manquant à implémenter :** aujourd'hui `mastered` est une bascule strictement manuelle (`local_store.py:2599`), et les évaluations AnythingLLM stockent un `session_score` dans `oic_attempts` **sans jamais la mettre à jour**. Une tentative avec `session_score ≥ 70` doit désormais passer `mastered = 1` automatiquement. La bascule manuelle reste disponible.

**Badge « Rang A ✓ »** — acquis quand l'item possède au moins un OIC de rang A et que **≥ 80 %** d'entre eux sont réussis.

C'est un badge **séparé de l'échelle de maîtrise**, délibérément : l'échelle contient déjà un niveau `à consolider` (`PROGRESSION_COLORS`), et y ajouter un niveau « consolidé » rendrait les deux indiscernables dans l'UI. Le rang B ne conditionne rien — l'ériger en condition transformerait un bonus en dette infinie.

**Effets d'une évaluation OIC :** réussite → preuve forte au sens de §5.2 ; échec → création d'une lacune via le mécanisme `weak_points` existant, et baisse du score.

---

## 6. Architecture logicielle

### 6.1 Nouveau module `backend/core/knowledge/`

`local_store.py` fait déjà 2 647 lignes et concentre tout le SQL du projet ; l'alourdir encore aggraverait un problème existant. Le nouveau domaine vit à part, avec une frontière nette :

| fichier | responsabilité | dépendances |
|---|---|---|
| `models.py` | `CollegeStatus`, `ItemState`, enums, constantes `SEED` / `DECAY_PER_30D` / `SEED_FLOOR` | aucune |
| `store.py` | SQL des deux tables : création, migration, lecture, écriture | sqlite3 |
| `service.py` | logique métier : valider un collège, déclarer un item, calculer la graine dégradée, agréger la couverture OIC | `store`, `models`, `local_store` (lecture `lisa_oic`) |

### 6.2 Modification de `mastery.py`

`get_course_mastery()` appelle `knowledge.service` pour obtenir la graine et la fusionner selon §5.2. Il **ne connaît ni le SQL ni les tables**. C'est la seule modification du moteur existant, et elle est petite.

`CourseProgressSnapshot` gagne trois champs : `declared_level`, `oic_coverage_a`, `has_rang_a_badge`.

### 6.3 Flux de données

```
UI (collèges / triage / fiche cours / modale de session)
        ↓ écrit
knowledge.service  →  knowledge.store  →  SQLite
        ↑ lit (graine, couverture OIC)
mastery.get_course_mastery()
        ↓ score fusionné
ReviewService  →  Dashboard / Planning
```

### 6.4 Points de contact UI

**Page Collèges** (`frontend/pages/colleges.py`) — sélecteur de statut par collège ; une fois `valide`, barre d'avancement du triage (« 12 items situés sur 47 ») et bouton *Trier maintenant*.

**Écran de triage groupé** (nouveau) — liste des items du collège, trois boutons par ligne (solide / correct / flou), sélection multiple pour traiter un paquet d'un coup. Quittable à tout moment : ce qui est trié est acquis, le reste reste « à situer ».

**Fiche cours** (`frontend/pages/course_detail.py`) — niveau déclaré affiché et **modifiable à tout moment** ; couverture OIC rang A / rang B ; badge « Rang A ✓ ».

**Modale de session** (`open_session_feedback_dialog`) — **c'est ici que le triage progressif se fait réellement.** Quand la session porte sur un item encore « à situer », la modale demande en plus le niveau déclaré (`source = reprise`). Un clic de plus dans un écran déjà ouvert, plutôt qu'une corvée de saisie séparée.

**CourseCard** (`frontend/components/course_card.py`) — badge « à situer » sur les items concernés.

---

## 7. Tests

Aucune de ces règles n'est visuelle : tout est testable directement, avec le pattern de fixtures pytest sur base temporaire déjà en place dans le projet.

1. La graine se dégrade avec le temps et respecte son plancher (`solide` à 0 j → 70 ; à 30 mois → 25).
2. L'évidence prend progressivement le dessus sur la graine (0, 1, 3 preuves → poids 100 %, 50 %, 25 %).
3. Un item d'un collège `valide` mais **non déclaré** n'a **pas** de score : il est « à situer », pas « correct par défaut ».
4. **Non-régression :** un item déclaré, sans `date_1ere_lecture`, ne génère **aucune** tâche J3/J7/J14/J30.
5. Une tentative OIC à `session_score ≥ 70` passe `mastered = 1` ; en dessous, non.
6. Le badge « Rang A ✓ » se déclenche à ≥ 80 % des OIC de rang A réussis, jamais avec 0 OIC de rang A.
7. Le rang B n'influence ni le score ni le badge.
8. Repasser un collège de `valide` à `non_etudie` **ne détruit pas** les `declared_level` de ses items.
9. Un collège absent de `college_status` est traité comme `non_etudie` sans erreur.

---

## 8. Critères d'acceptation

- Cocher « Cardiovasculaire ❤️ = validé » rend ses items visibles dans Synapse **sans aucune autre saisie**.
- Un item « à situer » peut recevoir son niveau soit par l'écran de triage, soit au fil d'une session — les deux chemins produisent le même état.
- Un item déclaré `solide` en 2026-07 est mécaniquement redescendu dans l'échelle en 2027-07, sans intervention.
- Une éval OIC réussie fait plus bouger le score qu'une déclaration ; trois preuves réelles rendent la déclaration initiale négligeable.
- Aucune tâche du dashboard actuel ne change de date, de priorité ou de statut du fait de ce bloc.
