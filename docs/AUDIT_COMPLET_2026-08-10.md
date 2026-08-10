# Audit complet — 10 août 2026

Quatre axes menés en parallèle par des agents distincts, en lecture seule, confrontés au code **et**
aux données réelles de `data/synapse_local.db`. Aucune génération IA facturée n'a été déclenchée.

**41 constats : 13 Critiques, 18 Importants, 13 Mineurs.**

| Axe | Critiques | Importants | Mineurs | Section |
|---|---:|---:|---:|---|
| Chaîne IA / API | 4 | 3 | 4 | [§1](#1-axe-chaîne-ia--api) |
| Algorithmes pédagogiques | 4 | 6 | 3 | [§2](#2-axe-algorithmes-pédagogiques) |
| Intégrité des données | 3 | 5 | 3 | [§3](#3-axe-intégrité-des-données) |
| Interface et parcours | 2 | 4 | 3 | [§4](#4-axe-interface-et-parcours) |

---

## Synthèse priorisée

Les quatre axes ont travaillé séparément. Leurs constats ne s'additionnent pas : ils se recoupent
autour de quatre problèmes de fond. Cette section les nomme, puis propose un ordre d'attaque.

### A. Le système affiche des diagnostics là où il n'a presque aucune mesure

C'est le résultat le plus lourd de cet audit, et il n'était visible qu'en confrontant le code aux
données. Le compteur d'activité réellement enregistrée est très bas :

| Signal | Volume réel en base |
|---|---:|
| Tentatives sur objectifs OIC | **3** lignes, aucune ≥ 70 |
| Tentatives de questions IA | **37** lignes, dont 7 scorées au barème EDN |
| Sessions d'étude | **34** lignes |
| Sessions QCM (ancien format) | **7** lignes |
| Cours avec une date de première lecture | **8** sur 707 (1,1 %) |
| Items avec une maîtrise mesurée | **76** sur 367 (21 %) |

Conséquence en chaîne, chaque maillon étant confirmé par une mesure distincte :

- La maîtrise réelle **plafonne à 61** sur sept semaines de snapshots. Aucun cours n'a jamais atteint
  « à consolider » ni « maîtrisé », et **96 %** des cours affichés « fragile » ou « critique » le sont
  à cause de la décroissance d'une auto-déclaration, pas d'une preuve d'apprentissage.
- Le potentiel de gain traite « maîtrise inconnue » comme « maîtrise nulle », donc lui attribue le
  facteur maximal. Le **Top 10 des items à fort potentiel est composé à 100 % d'items sans aucune
  mesure**. Pire : parmi les items mesurés, le gain moyen (176) est *inférieur* à celui des items non
  mesurés (244) — avoir une mesure fait *baisser* la priorité affichée, l'exact inverse de l'intention.
- La progression par collège compte les cours ayant une date de première lecture : elle frôle 0 % pour
  la quasi-totalité du programme, alors que 250 révisions ont réellement été effectuées — dont 80 %
  par des chemins (consolidation, bonus) que cette métrique ne capte pas.
- La couverture OIC affiche 0 % partout, non par bug (le défaut du 3 août est bien corrigé) mais faute
  de tentatives. Rien ne distingue visuellement « non mesuré » de « mesuré et faible ».

**Ce n'est pas un problème d'algorithmes faux.** Les formules font ce qu'elles annoncent. Le problème
est qu'elles sont nourries de vide et que le résultat est présenté comme un diagnostic. Un étudiant
qui suit ces indicateurs travaille en priorité les items sur lesquels l'application ne sait rien.

### B. La couche « quel item couvre quoi » est fausse à grande échelle

Quatre défauts indépendants, chacun mesuré, qui se composent :

1. **La classification IA s'applique à l'examen entier, pas au sous-dossier.** Un examen UNESS contient
   plusieurs DP/KFP/SQI indépendants couvrant des items différents ; ils reçoivent tous la même
   étiquette. Confirmé avec contenu vérifié sur trois examens — Cardiologie étiqueté item 230 pour un
   dossier de dyspnée/NYHA et un de valvulopathie, Hématologie étiqueté 212 pour un cas d'hémostase,
   Douleur/Soins palliatifs étiqueté 134 pour deux cas d'anesthésie. Douze groupes multi-sous-cas
   existent en base.
2. **Deux sources de vérité désynchronisées.** 1 749 questions sur 3 190 (**55 %**) ont un
   `item_number` qui n'apparaît dans aucune ligne de la table de classification ; 1 053 n'ont aucune
   classification du tout.
3. **Le référentiel UNESS n'est pas l'autorité en pratique.** 299 cours Notion sur 582 (**51 %**)
   portent un collège qui contredit le référentiel, alors que le principe établi du projet est
   l'inverse. Exemples : Hypercalcémie classée en Endocrinologie au lieu de Néphrologie, Contraception
   et Ménopause en Endocrinologie au lieu de Gynécologie-Obstétrique.
4. **L'erreur se recopie toute seule.** Le Tuteur DP pré-remplit son contexte pédagogique avec les cinq
   premiers énoncés de la session DP la plus récente de l'item, sans vérifier la cohérence. Comme la
   session mal étiquetée est souvent la seule disponible, chaque nouvelle génération sur cet item
   réinjecte le mauvais contexte. C'est le mécanisme exact observé sur l'item 230.

Le chantier C1 de la spec ne visait que l'ancrage du prompt — injecter titre, collège et OIC. **C'est
nécessaire mais très insuffisant** : même avec un prompt parfait, le contexte fourni en amont reste
corrompu et la statistique de maîtrise par item reste faussée.

### C. Le barème officiel R2C n'a jamais fonctionné

Les pénalités absolues — indispensable omise ou inacceptable cochée — sont ce qui fait la spécificité
du barème EDN. **Zéro question sur 3 497** ne porte ces marqueurs. Le mécanisme n'a jamais influencé
une seule note. Le second moteur, celui du mode concours, est passé d'un bug (rang forcé à « A », qui
le déclenchait à tort) à un autre état (champ jamais rempli, qui ne le déclenche jamais) sans être
passé par un état fonctionnel.

S'y ajoute que **deux moteurs distincts** implémentent ce que leurs commentaires appellent tous deux
« le barème officiel », avec des règles différentes. Ils sont inertes aujourd'hui ; le jour où les
données seront enrichies, la même réponse donnera deux notes différentes selon le mode d'entraînement.

Sur les 3 497 questions disponibles, **7 tentatives seulement** ont été scorées au barème EDN dans
toute l'histoire de l'application.

### D. Trois défauts francs, indépendants, à corriger sans arbitrage

- **« Créer une lacune » plante partout.** `frontend/pages/weak_points.py` utilise `ui` et
  `local_store` sans jamais les importer. Les deux seules entrées — palette de commandes et bouton de
  `/lacunes` — lèvent une `NameError` au premier clic. La fonctionnalité est indisponible dans toute
  l'application. Vérifié directement : le fichier n'importe que `logger` et `frame`.
- **La difficulté choisie n'atteint jamais le modèle.** Standard, EDN, Difficile, Concours : le
  réglage est injecté dans le texte du prompt mais n'est pas passé au routeur de modèle. Et le libellé
  de modèle stocké en base est calculé séparément *avec* la vraie difficulté — il annonce donc un
  modèle qui n'a pas été appelé. Aucune session Concours n'existe encore, le symptôme n'a pas encore
  été observé, mais le code est sans ambiguïté.
- **La base de production contient des données de test.** 695 lignes sur 1 358 (**51 %**) de la table
  de télémétrie, plus des fixtures dans les questions et l'historique de révision. Un critère de
  discrimination fiable a été établi : coût nul *et* tokens nuls, ce qui n'arrive jamais sur un vrai
  appel. Une fois filtré, le taux d'échec réel des appels IA tombe de 16,9 % à **1,3 %**, et le coût
  réel est de **0,97 $ sur neuf jours** — négligeable. Tant que ce bruit n'est pas purgé, toute mesure
  de coût ou de fiabilité est fausse, y compris celle affichée dans le panneau télémétrie.

### E. La dette de contraste est structurelle, pas ponctuelle

Le correctif posé le matin même sur le panneau télémétrie a traité un symptôme. La cause est dans les
tokens : `--success`, `--warning` et `--danger` sont déclarés « stables clair & sombre » et calibrés
pour un fond sombre. Tout texte qui les utilise passe sous le seuil WCAG AA en thème clair.

**131 occurrences** de `color:var(--success|danger|warning|text-dim)` dans **30 fichiers**, dont
14 sur la fiche item — l'écran le plus consulté — et 14 sur la vue Collèges, précisément sur le code
couleur de maîtrise. S'y ajoutent **547 occurrences** de couleurs Tailwind figées dans 38 fichiers,
qui échappent par construction à toute correction centralisée.

`--warning` est le pire des trois (~2,2:1) et le seul à n'avoir reçu aucune variante lisible.

### F. Ce qui va bien, et qu'il ne faut pas casser

- **La sauvegarde existe désormais** : copie SQLite native quotidienne, rétention sept jours, vérifiée
  sur disque. C'était le risque le plus brutal du projet ; il est fermé.
- **Aucune corruption** : `integrity_check` à `ok`, aucune violation de clé étrangère, aucun orphelin
  sur les jointures vérifiées, aucun `item_number` numérique hors plage. Les écritures concurrentes
  sont sérialisées par un verrou applicatif, en mode WAL.
- **Le score officiel reste interdit à l'IA**, et la clé API ne fuit jamais dans les logs.
- **Le garde-fou anti-invention de la classification est solide** : le modèle ne peut jamais retenir un
  numéro d'item qu'on ne lui a pas soumis comme candidat. C'est sa granularité qui est fautive, pas sa
  discipline.
- **Le code mort réel est limité** : trois petits composants jamais branchés et environ 600 lignes
  orphelines dans `stats.py`. La « Phase 5 » et les façades F3/F4 signalées en août sont réellement
  résolues, pas seulement dans la documentation. Ne pas rouvrir ce chantier.
- **Le lecteur React est déjà la cible de fait** pour toute session ouverte isolément, et il est
  nettement supérieur : contexte de dossier, images interactives avec zoom, mode examen, filet
  anti-échec. Deux points d'entrée seulement ne l'essaient jamais.

---

## Ordre d'attaque proposé

Trois vagues. Le critère de classement est le rapport entre l'effort et ce que le correctif débloque
en aval — pas la gravité nominale.

### Vague 1 — Rétablir la confiance dans ce qu'on mesure

Rien de ce qui suit ne demande d'arbitrage, et tout le reste en dépend.

1. **Réparer « Créer une lacune »** : deux imports manquants. Une fonctionnalité entière est à terre.
2. **Purger la pollution de test et poser un garde** qui empêche les tests d'écrire dans la base réelle.
   Sans cela, aucune mesure faite ensuite n'est défendable — y compris pour vérifier les autres
   correctifs.
3. **Faire transiter la difficulté jusqu'au modèle**, et dériver le libellé stocké du modèle
   réellement appelé plutôt que de le recalculer.

### Vague 2 — Réparer la couche item

C'est le socle de tout le reste : maîtrise par item, couverture DP, Tuteur DP, statistiques.

4. **Reclasser au niveau du sous-dossier** plutôt que de l'examen, et reprendre les douze groupes
   multi-sous-cas existants en commençant par les trois confirmés.
5. **Réconcilier les collèges Notion sur le référentiel UNESS**, conformément au principe du projet.
6. **Combler la table de classification** pour les 1 749 questions divergentes, ou trancher laquelle
   des deux sources fait foi et documenter pourquoi l'autre est ignorée.
7. **Cesser de propager un contexte non vérifié** dans le Tuteur DP : ne réutiliser une session source
   que si son item est fiable, sinon laisser le champ vide.
8. **Ancrer les prompts** sur titre, collège et objectifs OIC — le chantier C1 initial, qui n'a de sens
   qu'une fois les points 4 à 7 traités.

### Vague 3 — Décider ce que le système doit dire

Ces points demandent un arbitrage de ta part, pas seulement du code.

9. **La maîtrise** : que faire d'un score qui mesure surtout l'ancienneté d'une auto-déclaration ?
   Le calcul sait déjà distinguer la part déclarée de la part prouvée — reste à décider si on l'expose,
   si on recalibre, ou si on change ce qu'on affiche.
10. **Le potentiel de gain** : distinguer « inconnu » de « nul », et donner une échelle. En l'état
    l'indicateur trie par ignorance.
11. **Le barème R2C** : alimenter réellement les marqueurs indispensable/inacceptable à l'import, ou
    dire clairement dans l'interface que seule la partie discordances est active. Et faire converger
    les deux moteurs sur un seul.
12. **La progression par collège** : élargir le calcul aux autres signaux d'activité, ou renommer
    l'indicateur pour qu'il cesse de suggérer une inactivité qui n'existe pas.
13. **La dette de contraste** : étendre le motif `--success-text` / `--danger-text`, créer
    `--warning-text`, en commençant par la vue Collèges et la fiche item.
14. **L'unification des lecteurs QCM** : deux points d'entrée à basculer, après avoir vérifié que le
    lecteur React sait consommer un enchaînement de sous-parties piloté côté serveur.

---

## Note de méthode

Chaque constat des quatre sections qui suivent est ancré soit dans un chemin de fichier avec numéro de
ligne, soit dans une requête SQL avec son résultat. Les intuitions non vérifiées sont signalées comme
telles par leurs auteurs.

Deux réserves de transparence rapportées par les agents eux-mêmes :

- L'agent algorithmes signale qu'un import Python a déclenché en cascade les migrations idempotentes
  et la routine de sauvegarde. Vérification faite : schéma déjà à jour, aucun nouveau fichier de
  sauvegarde, compteurs de lignes identiques avant et après. Les calculs suivants ont été refaits sans
  jamais réimporter de module du paquet applicatif.
- Les mesures de coût et de fiabilité IA ont été refaites après filtrage du bruit de test. Les chiffres
  bruts et filtrés sont donnés côte à côte pour que l'écart soit visible.

---


# 1. Axe chaîne IA / API


## Synthèse

1. La difficulté choisie par l'utilisateur n'est jamais transmise à l'appel Gemini réel pour QCM/OIC/DP/KFP (`backend/core/practice/service.py:142-147`) : une session « Concours » est générée avec le même modèle qu'une session « Standard », alors que le libellé stocké en base ment sur le modèle réellement utilisé.
2. La base de production (`data/synapse_local.db`) est polluée par des données de test — 609 des 1358 lignes de `ai_usage_logs` (45 %) et au moins 6 lignes de `ai_practice_questions` sont des artefacts de fixtures pytest, pas du trafic réel. Toute mesure brute sur cette base est fausse tant qu'on ne filtre pas ce bruit.
3. Le bug item 230 « dyspnée/NYHA » signalé hier est tracé de bout en bout : une classification IA à la granularité de l'examen entier (pas du sous-dossier) a étiqueté un DP sur l'insuffisance cardiaque comme item 230 (« Douleur thoracique ») ; le Tuteur DP réinjecte ensuite automatiquement les 5 premières questions de ce DP mal classé comme contexte pédagogique pour toute nouvelle génération sur l'item 230, un mécanisme systématique et reproductible, pas un accident isolé.

Une fois le bruit de test filtré, la fiabilité réelle des appels Gemini est bonne (1,3 % d'échec, concentré sur la correction visuelle) et le coût est négligeable (~0,97 $ sur 9 jours). Le risque principal n'est pas le coût ni la robustesse réseau : c'est la justesse du contenu généré et sa traçabilité.

## Constats

### [Critique] La difficulté sélectionnée n'atteint jamais le modèle Gemini pour QCM/OIC/DP/KFP

**Ce qui se passe** : `PracticeService.generate_questions()` (`backend/core/practice/service.py:142-147`) appelle :
```python
response = self.ai_service.generate(
    task,
    _prompt_for(spec, context) + retry_hint,
    context=ctx_label,
    response_format="json",
)
```
sans le paramètre `difficulty`. Or `AIService.generate()` (`backend/core/ai/service.py:29-40`) route le modèle via `model_for_task(task, difficulty)`, avec `difficulty=None` par défaut. Résultat : quelle que soit la difficulté choisie dans l'UI (Standard/EDN/Difficile/Concours), l'appel réel à Gemini route toujours comme si `difficulty=None` — `routing.py:65-67` n'escalade vers `AIModel.FLASH` que si `difficulty_value in {"difficile", "concours"}`, condition qui n'est jamais remplie ici puisque la valeur n'arrive jamais au routeur.

Pire : `create_new_session()` (`service.py:197-201`) calcule *séparément* le libellé stocké dans `ai_practice_sessions.model` avec `model_for_task(_task_for(spec.practice_kind), spec.difficulty)` — cette fois avec la vraie difficulté. Le modèle affiché à l'utilisateur dans l'historique (`ai_practice_panel.py:317`) peut donc annoncer « flash » alors que l'appel a réellement utilisé « flash_lite ».

Vérifié en base : aucune session `QCM`/`OIC` avec `difficulty` = `difficile` ou `concours` n'existe encore (`select difficulty, practice_kind, model, count(*) from ai_practice_sessions group by 1,2,3` ne renvoie que `edn`/`standard`), donc le symptôme n'a pas encore été observé en usage réel — mais le code est sans ambiguïté et se déclenchera dès la première session Concours/Difficile.

**Pourquoi c'est un problème** : un étudiant qui sélectionne explicitement « Concours » pour se challenger reçoit en réalité des questions générées au niveau de difficulté par défaut avec le modèle le moins cher, tout en croyant (d'après le libellé affiché) avoir eu le modèle haut de gamme. C'est une divergence entre ce qui est demandé, ce qui est fait, et ce qui est affiché — silencieuse.

**Piste** : faire transiter `spec.difficulty` jusqu'à l'appel `ai_service.generate()`, et dériver le libellé stocké du modèle *effectivement* retourné par `AIResponse.model` plutôt que de le recalculer indépendamment.

---

### [Critique] La base de production contient des données de test — les métriques brutes sont fausses

**Ce qui se passe** : sur les 1358 lignes de `ai_usage_logs` (1er–9 août 2026), 609 (45 %) portent `task='gemini_generate'` — la valeur de repli codée en dur dans `backend/core/ai/gemini_client.py:69` (`t_name = task_name or "gemini_generate"`), qui ne devrait jamais apparaître en production puisque `AIService.generate()` fournit toujours un `task_name` réel. Ces lignes ont des signatures impossibles à confondre avec du vrai trafic :
- durées de 0,01 à 0,4 ms (un appel HTTP réel vers `generativelanguage.googleapis.com` prend au minimum plusieurs centaines de ms — cf. colonne `duration_ms` des autres tâches, moyenne 700 à 25000 ms) ;
- comptages de tokens strictement `11 in / 4 out` répétés à l'identique ;
- messages d'erreur `"network timeout"` et `"Réponse Gemini vide"`, qui sont mot pour mot les chaînes de `tests/test_gemini_client.py:108` (`TimeoutError("network timeout")`) et le message levé par le test `test_generate_rejects_empty_provider_response` (`gemini_client.py:143`).

Ces lignes apparaissent par salves de 6 au même timestamp à la seconde près, 111 fois entre le 1er et le 9 août — la signature exacte d'une exécution répétée de `tests/test_gemini_client.py` (6 appels `.generate()` non annotés dans ce fichier). `tests/conftest.py:14-17` redirige normalement `local_store.DB_PATH` vers un fichier temporaire via `SYNAPSE_TEST_DB_PATH`, mais cette protection ne joue que si le module est importé après que `conftest.py` a positionné la variable d'environnement — un lancement hors pytest (script isolé, session de débogage interactive) ne bénéficie pas de cette isolation, et `local_store.py:31-32` retombe alors sur `data/synapse_local.db`, la vraie base.

Le même phénomène touche `ai_practice_questions` : 6 lignes ont pour énoncé littéral `"Q ?"`, choix `["A", "B"]`, réponse `"A"`, explication `"Car A."` — un fixture minimal identique à ceux de `tests/test_annale_detail_page.py`, `tests/test_uness_annales_model.py` et `tests/test_backfill_annales.py`.

Une fois ces 609 lignes exclues, l'image change du tout au tout : 749 appels réels, dont seulement 10 en échec (1,3 %, tous sur `uness_correction_visual` — 7×429, 3×timeout), contre 229/1358 (16,9 %) si on ne filtre pas.

**Pourquoi c'est un problème** : toute lecture directe de `ai_usage_logs` ou `ai_practice_questions` — y compris cet audit avant filtrage — surestime largement le taux d'échec réel et sous-estime la part de vrai contenu généré par IA. Un futur tableau de bord de coût ou de fiabilité construit naïvement sur ces tables afficherait des chiffres trompeurs sans qu'aucun signal ne prévienne de la contamination.

**Piste** : garantir que `SYNAPSE_TEST_DB_PATH` (ou équivalent) est actif avant tout import de `backend.core.reviews.local_store`, quel que soit le mode de lancement des tests ; envisager un garde en dur dans `local_store.py` qui refuse d'écrire dans `data/synapse_local.db` si une variable d'environnement `PYTEST_CURRENT_TEST` est présente. Nettoyer rétroactivement les lignes identifiées (`task='gemini_generate'`, prompt `'Q ?'`) de la base actuelle.

---

### [Critique] Le bug item 230 est tracé : classification IA trop grossière + propagation automatique du contexte

**Ce qui se passe** : l'observation d'hier (contexte du Tuteur DP sur l'item 230 « Douleur thoracique » parlant de dyspnée et de classification NYHA) est reproduite intégralement en base et son mécanisme est identifié en deux temps.

*Étape 1 — classification à la mauvaise granularité.* `backend/core/uness/import_service.py:592-608` (`_classify_exam_items`) appelle la classification IA (`classify_exam_items`, `backend/core/uness/item_classifier.py:64-89`) **une seule fois par examen importé**, avec pour seul contexte `exam.title` et `exam.dp_context.get("enonce_general", "")[:800]`. Un même examen UNESS peut pourtant contenir plusieurs sous-parties indépendantes (DP1, DP2, KFP2) couvrant des items EDN différents. C'est exactement le cas de l'examen « DFASM1 EXAMEN Cardiologie... — DP1/DP2/KFP2 » (`annale_id=52`) : ses 5 sous-parties (sessions `id` 210, 211, 212, 213, 215 dans `ai_practice_sessions`) ont **toutes** reçu `item_number='230'`, alors que leur contenu réel couvre au moins deux sujets distincts :
  - session 211 (DP1, 8 questions, `id` 1144-1151) : diagnostics différentiels d'une dyspnée, classification NYHA (question 1145 : *« Quel est le stade de sévérité de cette dyspnée selon la classification de la New York Heart Association ? »*), NT-proBNP, échocardiographie, coronarographie — un dossier d'insuffisance cardiaque, pas de douleur thoracique aiguë ;
  - sessions 210/212/213/215 (`id` 1152-1171) : rétrécissement aortique, bioprothèse valvulaire par voie fémorale, thrombose veineuse profonde — également hors du périmètre de l'item 230.

  Le vrai item 230 (« Douleur thoracique ») n'est correctement représenté que par les sessions `id` 3, 8, 223 (`model='flash_lite'`, générées par Gemini avec le titre de cours réel « Douleur thoracique » comme `course_title`), dont les questions (`id` 14-17) portent bien sur SCA ST+, dissection aortique, embolie pulmonaire, pneumothorax.

*Étape 2 — propagation automatique.* `frontend/pages/course_detail_cockpit.py:943` et `frontend/pages/qcm_cockpit.py:535-539` construisent le `dossier_context` du Tuteur DP en concaténant les 5 premiers énoncés de la session DP la plus récente de l'item (`dp_history[:5]`, `"\n".join(str(q.get("prompt") or "") for q in questions[:5])`), sans aucune vérification de cohérence avec l'item réellement visé. Comme la session 211 est la **seule** session DP existante pour l'item 230, toute ouverture du Tuteur DP sur cet item réinjecte automatiquement son contenu dyspnée/NYHA comme « contexte pédagogique » pré-rempli (`ai_practice_panel.py:161-174`, `build_dp_tutor_context`) — ce qui correspond exactement à ce qui a été observé hier.

**Pourquoi c'est un problème** : ce n'est pas une hallucination ponctuelle du modèle de génération — c'est une erreur de classification à l'import qui devient invisible et auto-entretenue : chaque nouvelle session Tuteur DP sur l'item 230 recycle le mauvais contexte, sans jamais donner à l'utilisateur ou au système un signal pour la corriger. Le défaut connu et déjà planifié (identification par numéro d'item seul, sans titre/collège/OIC — cf. contexte de cette mission) aggrave le phénomène en aval : même si le prompt de génération recevait le bon numéro, le contexte documentaire fourni en amont serait déjà corrompu.

**Piste** : classifier chaque sous-partie (DP/QCM/KFP) individuellement avec son propre texte de vignette plutôt que l'examen entier ; ne réutiliser un `dossier_context` automatique que si la session source partage un item validé de façon fiable (score de confiance, ou validation humaine passée) ; à défaut, laisser le champ vide plutôt que de propager un contenu non vérifié.

---

### [Important] Le rattrapage partiel peut multiplier les appels IA sans plafond global

**Ce qui se passe** : `PracticeService._recover_partial_questions()` (`backend/core/practice/service.py:159-181`) est déclenché quand la génération d'un lot complet échoue sur le nombre de questions. Il boucle `spec.total_questions` fois, et pour chaque question rappelle `generate_questions(single_spec, ..., max_attempts=max_attempts)` — qui a lui-même son propre budget de `max_attempts` tentatives (1 à 3, borné ligne 129-130 de `service.py`). Pour une session Tuteur DP de 10 questions avec `max_attempts=2` (valeur passée par `ai_practice_panel.py:236`), le pire cas est 10 × 2 = 20 appels Gemini pour une seule action utilisateur « Générer », sans limite globale distincte du produit `total_questions × max_attempts`.

**Pourquoi c'est un problème** : ce n'est pas un risque financier (coût de l'ordre du millième de dollar par appel), mais un risque de latence et de quota — une session qui échoue partiellement peut silencieusement multiplier par 10-20 le nombre de requêtes et le temps d'attente perçu, sans qu'aucun message n'indique à l'utilisateur que ce mode dégradé est actif au-delà du texte générique « Génération en cours… ».

**Piste** : plafonner explicitement le nombre total d'appels IA par session (indépendamment du produit intermédiaire), et informer l'utilisateur quand le mode de rattrapage question-par-question est activé.

---

### [Important] La validation de sortie ne vérifie ni la cohérence interne ni les doublons

**Ce qui se passe** : `_parse_questions()` (`backend/core/practice/service.py:60-105`) valide le JSON, le nombre de questions, la répartition ouvert/fermé, et que chaque champ requis est non vide (`GeneratedQuestion.__post_init__`, `backend/core/practice/models.py:67-75`, qui exige seulement `prompt`, `answer`, `explanation` non vides et ≥2 choix pour une question fermée). Rien ne vérifie que :
- la réponse déclarée (`answer`) correspond effectivement à l'un des `choices` proposés pour une question fermée ;
- deux questions du même lot ne sont pas des doublons ou quasi-doublons ;
- l'énoncé respecte la limite de longueur annoncée au modèle dans le prompt (« énoncé inférieur à 280 caractères », `service.py:54`) — un cas réel en base la dépasse (question `id=3578`, 310 caractères, générée par `flash`).

**Pourquoi c'est un problème** : une contrainte demandée au modèle sans contrôle côté code n'est qu'une suggestion. Le contrat de sortie décrit dans l'audit précédent (§16.4 : « validation de schéma → contrôles métier ») s'arrête au format JSON et au comptage, pas à la cohérence sémantique minimale (réponse ∈ choix).

**Piste** : ajouter un contrôle explicite `answer in choices` pour les questions fermées avant persistance, et un contrôle de similarité basique entre les énoncés d'un même lot.

---

### [Mineur] Deux pipelines de vérification/correction UNESS utilisent des étiquettes de tâche différentes pour un travail équivalent

**Ce qui se passe** : `backend/core/uness/gemini_autocorrect.py` route via `generate_uness_correction()` (`backend/core/ai/tasks.py:54-72`), qui étiquette correctement l'appel `AITask.UNESS_CORRECTION` ou `AITask.UNESS_CORRECTION_VISUAL`. Mais `backend/core/uness/ai_verifier.py:535-541` (`verify_question`), une deuxième voie de vérification/correction UNESS utilisée par `import_service.py` et `gemini_conversion.py`, appelle `ai_service.generate(AITask.QCM, ...)` — la tâche « QCM » habituellement réservée à la génération de sessions d'entraînement. En base, le compartiment `task='qcm'` (49 appels, 0,011 $) mélange donc de vraies générations QCM (`PracticeService`) et des vérifications UNESS, sans moyen de les distinguer après coup.

**Pourquoi c'est un problème** : le découpage par tâche dans `ai_usage_logs`, censé permettre un audit de coût et de fiabilité par fonction (point 4 de cette mission), est faussé pour ces deux pipelines — impossible de savoir, a posteriori, quelle part du coût et des échecs « qcm » vient réellement de la génération de questions d'entraînement plutôt que de la vérification UNESS.

**Piste** : donner à `ai_verifier.verify_question()` sa propre valeur d'`AITask` (ou réutiliser `UNESS_CORRECTION`), distincte de la génération de sessions QCM.

---

### [Important] Le contenu réellement généré par Gemini est une part infime de la banque de questions — l'essentiel est importé, pas généré

**Ce qui se passe** : `ai_practice_questions` contient 3497 lignes. Répartition par `model` :

| model | practice_kind | lignes |
|---|---|---:|
| uness-verified-local | QCM | 3179 |
| uness-verified-local | DP | 276 |
| **flash_lite** | **QCM** | **33** |
| exam-simulator | DP | 8 |
| test | QCM | 1 |

Autrement dit, 99 % du contenu servi comme « session IA » dans le Cockpit est en réalité issu de l'import UNESS vérifié localement (pas d'appel Gemini au moment de la session), et seulement 33 questions QCM (aucune session DP/KFP/OIC réelle générée par Gemini n'existe en base à ce jour) proviennent effectivement d'une génération `flash_lite`. Sur ces 33 : aucun doublon exact d'énoncé, toutes les explications font plus de 89 caractères (pas de cas manifestement vide ou tautologique du type « car c'est la bonne réponse »), et 1 cas sur 33 (3 %) dépasse la limite de longueur d'énoncé demandée dans le prompt (cf. constat « validation de sortie » ci-dessus).

**Pourquoi c'est un problème** : ce n'est pas en soi un défaut — s'appuyer sur du contenu UNESS vérifié plutôt que sur de la génération est plus sûr. Mais cela signifie que l'essentiel de l'exposition qualité de Synapse aujourd'hui ne vient pas de la chaîne IA de génération elle-même (trop peu de volume pour juger statistiquement de sa fiabilité), et que l'audit qualité demandé au point 3 de cette mission ne peut porter, avec un échantillon significatif, que sur un flux encore marginal en usage réel. Le risque qualité mesurable aujourd'hui est concentré ailleurs : dans la classification d'item à l'import (constat ci-dessus) et dans la correction visuelle UNESS.

**Piste** : documenter explicitement, dans l'UI ou en base, la distinction entre « question importée et vérifiée » et « question générée par Gemini » au-delà du seul champ `model` technique — pour ne pas laisser croire que l'essentiel de la banque a été audité par le pipeline IA.

---

### [Mineur] Coût réel : négligeable, mais mesuré sur une base bruitée — chiffres corrigés

**Ce qui se passe** : après exclusion des 609 lignes de bruit de test identifiées plus haut, sur la période observée (1er–9 août 2026, 9 jours) :

| tâche | appels | coût total | coût moyen/appel | tokens in / out |
|---|---:|---:|---:|---:|
| uness_correction_visual | 63 | 0,676 $ | 0,0107 $ | 253 056 / 183 207 |
| uness_correction | 90 | 0,130 $ | 0,0014 $ | 458 362 / 319 197 |
| item_classification | 543 | 0,123 $ | 0,0002 $ | 1 399 330 / 17 590 |
| qcm* | 49 | 0,011 $ | 0,0002 $ | 47 476 / 25 452 |
| dp | 4 | 0,019 $ | 0,0049 $ | 1 952 / 6 174 |
| **total** | **749** | **0,966 $** | — | — |

*(qcm mélange génération réelle et vérification UNESS — cf. constat dédié.)*

Aucun appel isolé n'apparaît anormalement cher au regard des autres du même type. Le poste le plus coûteux par appel est `uness_correction_visual` (modèle `flash`, images incluses), cohérent avec le choix de routage. Le taux d'échec réel est de 1,3 % (10/749), intégralement concentré sur `uness_correction_visual` (429 rate-limit ×7, timeout réseau ×3) — aucun échec réel sur `item_classification`, `qcm`, `dp` ou `uness_correction` sur la période.

**Pourquoi c'est un problème** : ce n'est pas un problème de coût en soi — la note est proche de zéro. C'est un problème de fiabilité de la mesure : sans le travail de filtrage fait pour cet audit, quiconque interroge `ai_usage_logs` obtient une image fausse (16,9 % d'échec au lieu de 1,3 %, répartition par tâche faussée). Le panneau `settings_cockpit.py:532-542` affiche déjà un historique des appels Gemini à l'utilisateur ; si ce panneau n'exclut pas les lignes `gemini_generate`/durée quasi nulle, il expose le même bruit.

**Piste** : filtrer ou marquer distinctement, au niveau de la lecture (pas seulement de l'écriture), les lignes dont la provenance est douteuse — par exemple `duration_ms < 1` est déjà un signal fort et gratuit à vérifier. Noter aussi que `frontend/pages/settings_cockpit.py:542` utilise la même valeur de repli littérale `"gemini_generate"` pour l'affichage — si le panneau de diagnostic (`DIAGNOSTIC UNESS`, `Historique des derniers appels Gemini`) ne filtre pas ces lignes en amont, l'utilisateur voit directement ce bruit dans l'UI sans explication.

---

### [Mineur] Routage des modèles : logique cohérente et documentée, deux zones à surveiller

**Ce qui se passe** : `backend/core/ai/routing.py:57-73` (`model_for_task`) implémente une règle simple et lisible : le score officiel est interdit à l'IA (`AITask.SCORE` lève une exception, cohérent avec `backend/core/practice/scoring.py` qui reste 100 % déterministe) ; QCM/OIC/ECOS simple/UNESS_CORRECTION/classification vont vers `FLASH_LITE` ; DP/KFP/ECOS complexe/correction visuelle/extraction de grille vont vers `FLASH` ; une difficulté « difficile » ou « concours » force `FLASH` quelle que soit la tâche. La politique est pure (pas d'appel réseau, testable isolément) et documentée dans `docs/AI_MODEL_ROUTING.md`.

Deux réserves, déjà couvertes par des constats dédiés ci-dessus : (1) la difficulté n'atteint jamais ce routeur pour la génération de sessions ([Critique] ci-dessus) ; (2) `ai_verifier.py` court-circuite la logique en hardcodant `AITask.QCM` plutôt que de laisser le routeur choisir en fonction de la vraie nature de la tâche (vérification UNESS). `backend/core/ai/tasks.py:98-116` (`classify_item`) prévoit en revanche un mécanisme explicite et documenté de correction (`force_model`) pour les cas où `flash-lite` sur-classifie sur de longues listes de candidats — un bon exemple de garde-fou proportionné : modèle bon marché par défaut, escalade ciblée en cas de signal de mauvaise qualité connu.

**Pourquoi c'est un problème** : pas un problème en soi pour cette partie — signalé pour mémoire, le vrai risque de routage est déjà couvert par les deux constats critiques/importants ci-dessus.

**Piste** : aucune action nouvelle au-delà de ce qui est déjà recommandé plus haut.

---

### [Mineur] Parsing et robustesse : deux couches de retry bien séparées, mais aucune ne couvre la pertinence du contenu

**Ce qui se passe** : la robustesse est gérée à deux niveaux distincts et non redondants :
- **Transport** (`gemini_client.py:93-112`) : jusqu'à 3 tentatives avec délai fixe (0,5 s puis 1 s) uniquement pour les erreurs réseau/timeout/429/5xx (`_is_retryable_error`, lignes 20-26) — une erreur 4xx autre que 429, une réponse vide, ou un `finishReason` `MAX_TOKENS`/`SAFETY` ne sont **pas** retentées à ce niveau, elles remontent immédiatement (lignes 116-143).
- **Métier** (`PracticeService.generate_questions`, `service.py:121-157`) : jusqu'à 3 tentatives complètes (nouvel appel Gemini à chaque fois) si le JSON est invalide, mal compté ou mal réparti, avec un message de reprise explicite injecté dans le prompt (`retry_hint`, lignes 136-141) — c'est le niveau qui couvre les échecs de contrat de sortie.

Ce qui n'est couvert par aucune des deux couches : la pertinence clinique du contenu (l'item demandé est-il vraiment celui traité — cf. constat item 230), la cohérence interne d'une question isolée (réponse ∈ choix), et les doublons — cf. constats dédiés ci-dessus.

**Pourquoi c'est un problème** : signalé pour mémoire — l'architecture de retry elle-même est saine et bornée (pas de boucle infinie identifiée), le point faible n'est pas la robustesse réseau mais le contrôle de contenu, déjà couvert.

**Piste** : aucune action nouvelle au-delà de ce qui est déjà recommandé plus haut.

## Ce qui va bien

- **Le score officiel reste 100 % déterministe.** `backend/core/practice/scoring.py` et `attempt_service.py` ne font aucun appel IA pour noter une réponse fermée ; `routing.py:63-64` interdit explicitement à l'IA de calculer un score (`AITask.SCORE` lève une erreur). Ce principe, déjà relevé dans l'audit précédent, tient toujours et n'a pas régressé.
- **Les retries sont bornés partout où ils existent**, sans boucle non plafonnée identifiée : transport (3 tentatives max, backoff fixe), génération de session (1 à 3, validé par `service.py:129-130`), génération OIC/évaluation ouverte via AnythingLLM (`evaluator.py:120, 170` — 2 tentatives fixes, avec dégradation propre vers une question ouverte générique ou un verdict `incorrect`/score 0 explicitement étiqueté `"Erreur de parsing IA"`).
- **Les secrets ne fuient pas dans les logs.** `gemini_client.py:29-31` (`_redact_provider_secrets`) masque systématiquement la clé API dans les messages d'erreur avant journalisation, y compris dans le chemin d'erreur réseau — couvert par un test dédié (`test_generate_wraps_http_errors_without_exposing_key`).
- **La classification d'item a un garde-fou anti-invention solide.** `item_classifier.py:75-89` ne retient jamais un numéro d'item que le modèle n'a pas reçu explicitement comme candidat (`kept = [n for n in raw_numbers if n in candidate_numbers]`), et le prompt (lignes 54-60) instruit explicitement de répondre `confident:false` plutôt que de deviner — c'est la bonne politique, même si sa granularité d'application (par examen entier, pas par sous-partie) est le problème identifié plus haut.
- **La correction visuelle reste marquée comme non finale.** `generate_uness_correction()` (`tasks.py:60-72`) fixe `requires_human_validation=True` et `status="pending_human_validation"` dès qu'une image est impliquée — cohérent avec la règle énoncée dans l'audit précédent.
- **Le coût réel est négligeable et concentré là où on l'attend.** Une fois le bruit de test exclu, ~0,97 $ sur 9 jours, aucun appel isolé anormalement cher, le poste le plus coûteux (`uness_correction_visual`) correspond au seul usage multimodal du système — le routage modèle/coût est cohérent avec la charge réelle des tâches.

## Évolution depuis l'audit du 9 août

- **Confirmé et daté avec précision** : le défaut « item par numéro seul » (déjà connu, correction planifiée non appliquée) — `service.py:40` et `flash_zero_service.py:64-67` l'illustrent tous les deux, le second n'ayant pas été mentionné dans l'audit du 9 août.
- **Nouveau depuis le 9 août, ou non couvert par cet audit** : le bug item 230 est désormais tracé de bout en bout jusqu'à sa cause racine (classification à l'échelle de l'examen entier, pas du sous-dossier) et son mécanisme de propagation exact (réutilisation automatique du contexte DP le plus récent) — l'audit du 9 août ne faisait qu'évoquer en général « une réponse IA non corrigée par un humain peut influencer... » sans identifier ce mécanisme spécifique.
- **Nouveau** : la divergence entre la difficulté choisie et le modèle réellement appelé, explicitement laissée en suspens par l'audit du 9 août (§16.1 : « Point à vérifier ») — c'est désormais confirmé par lecture directe du code, avec les deux lignes exactes où le contrat casse.
- **Nouveau** : la contamination de la base de production par des données de test, qui n'était pas mentionnée du tout. Elle invalide rétroactivement toute lecture brute des chiffres de coût/fiabilité qu'un futur audit ferait sur cette base sans le savoir.
- **Nouveau** : la proportion réelle de contenu IA-généré vs importé (33 questions Gemini sur 3497, soit ~1 %) — l'audit précédent ne quantifiait pas ce ratio et pouvait laisser croire à une base de questions majoritairement générée.
- **Toujours valable, non dégradé** : l'architecture de retry bornés, l'interdiction du score par IA, la non-fuite de clé API, le garde-fou anti-invention de la classification d'item — rien de régressé sur ces points depuis le 9 août.
- **Non retraité ici** : le point de l'audit précédent sur l'absence de schéma JSON strict systématique (`responseSchema` n'est utilisé que si explicitement fourni, `gemini_client.py:71-74` — aucun appelant de la chaîne pratique/OIC/DP/KFP n'en fournit un aujourd'hui, la validation reste post-hoc côté `_parse_questions`) reste ouvert et n'a pas évolué.



---

# 2. Axe algorithmes pédagogiques


## Note méthodologique préalable

- Toutes les mesures ci-dessous viennent de `data/synapse_local.db` ouverte en lecture seule (`file:...?mode=ro`), et de `data/data_cache.json` (cache Notion, synchronisé le 10 août à 16:58, donc à jour au moment de l'audit — pas une base périmée).
- **Incident méthodologique à signaler** : au cours de l'exploration, un `import` Python de `backend.core.ednpro.frequency` a déclenché en cascade `backend.core.reviews.local_store.init_db()`, qui exécute des migrations idempotentes (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN` gardées par vérification préalable des colonnes existantes) et appelle `backup_database()`. Vérification faite : le schéma était déjà à jour (aucune colonne ajoutée), aucun nouveau fichier n'est apparu dans `data/backups/`, et les compteurs de lignes de toutes les tables utilisées dans cet audit sont strictement identiques avant/après. Aucune donnée n'a été modifiée, mais je le signale pour transparence : le calcul du potentiel de gain (constat Critique 3) a été obtenu via cet import ; tous les calculs suivants ont été refaits avec des connexions SQLite strictement en lecture seule et une réimplémentation locale des formules pures, sans plus jamais importer de module du package `backend`.
- **Pollution de données de test** : un audit parallèle a établi que `ai_usage_logs` (45 %) et des fixtures dans `ai_practice_questions` polluent la base. Je le confirme partiellement : `ai_usage_logs.context` contient 47 lignes `unit_test` et des dizaines de lignes portant `Test` dans des titres d'examens (ambigu — pourrait être un vrai titre d'épreuve). Je n'ai construit aucun constat sur `ai_usage_logs` (hors périmètre algorithmes). Pour `ai_practice_questions`, les chiffres utilisés ici portent spécifiquement sur le sous-ensemble `source=ednpro` (2352/3497 lignes, un canal d'import réel et distinct), ce qui limite mais n'élimine pas le risque de contamination — signalé où pertinent.

## Synthèse

1. **Le barème R2C officiel (indispensable/inacceptable) n'a jamais été appliqué en pratique** : sur 3497 questions générées et 23 questions importées, aucune ne porte les champs `indispensable_choices`/`inacceptable_choices` ou un `rank` par proposition — le mécanisme de pénalité absolue est mort-né dans les deux moteurs de scoring existants.
2. **Le potentiel de gain EDNpro est dominé par l'absence de données** : pour 291/367 items (79 %), la maîtrise est inconnue et le code la traite comme 0 — ces items truffent artificiellement le haut du classement ; le Top 10 réel est composé à 100 % d'items sans aucune mesure de maîtrise.
3. **La maîtrise réelle mesurée est plafonnée bien en dessous de ce que montre l'interface** : sur 7 semaines de snapshots (4128 lignes, 825 cours), le score va de 25 à 61 seulement, aucun cours n'a jamais atteint « à consolider » ou « maîtrisé », et 96 % des cours affichés « fragile »/« critique » le sont à cause de la graine auto-déclarée, pas d'une preuve d'apprentissage réelle.

## Constats

### [Critique] Le mécanisme indispensable/inacceptable du barème R2C est structurellement inerte

**Ce qui se passe** : `backend/core/practice/scoring.py::compute_question_score_edn` (lignes 102-186) applique correctement une pénalité absolue (score 0) si une proposition indispensable est omise ou une proposition inacceptable est cochée. Ces listes sont lues depuis `question["indispensable_choices"]` / `question["uness"]["indispensable_choices"]` par `backend/core/practice/attempt_service.py:18-24`.
Mesure sur la base : `SELECT COUNT(*) FROM ai_practice_questions WHERE import_metadata_json LIKE '%indispensable_choices%'` → **0 sur 3497**. Idem pour `inacceptable_choices` → **0**. Les 253 occurrences du mot « indispensable » trouvées dans les métadonnées sont du texte libre de correction (`dp_context.correction_globale`), pas le champ structuré attendu. Sur `imported_practice_questions` (23 lignes, table du parcours DP importé), la colonne `choices` est une simple liste de chaînes (`"A. ...", "B. ..."`), sans aucun objet `{id, rank}` : aucune proposition n'y porte de rang.
Le second moteur, `backend/core/uness/exam_simulator.py::compute_edn_score` (lignes 60-102), a une logique différente : il annule la question à 0 si une proposition de `rank == "A"` vraie est oubliée. Ce bug (rang forcé en dur à `"A"` pour toute proposition importée) avait été signalé le 3 août 2026 (`docs/AUDIT_2026-08-03.md`, §2.4) et a été corrigé depuis — mais la correction (`exam_simulator.py:162`, `choice_data.get("rank")`) lit un champ qui n'est jamais rempli côté données réelles (mêmes `choices` en chaînes plates), donc le mécanisme est passé de « déclenché à tort » à « jamais déclenché », sans jamais avoir réellement fonctionné.
**Pourquoi c'est un problème** : la partie du barème EDN qui pénalise le plus lourdement (oubli d'un item vital, choix d'un item dangereux) — celle qui a le plus de valeur pédagogique et de réalisme concours — n'a jamais influencé une seule note dans l'historique de l'application. L'étudiant s'entraîne sur un barème simplifié (discordances seules) en croyant utiliser le barème officiel R2C.
**Piste** : soit alimenter réellement `indispensable_choices`/`inacceptable_choices`/`rank` à l'import (Gemini+UNESS, EDNpro), soit documenter clairement dans l'UI que seule la partie discordances du barème est active tant que la donnée source ne porte pas cette information.

### [Critique] Le verrou « Sécurité Rang A » de mastery.py plafonne des items à « fragile » à cause d'une seule tentative OIC partielle

**Ce qui se passe** : `backend/core/knowledge/service.py::oic_coverage()` calcule `rang_a_pct = mastered / total` par cours. `backend/core/reviews/mastery.py:269-298` applique ensuite `score_rang_a = 0.5 * mastery_score + 0.5 * (rang_a_pct * 100)` dès que `rang_a_attempted > 0` (au moins une tentative enregistrée sur un OIC Rang A du cours), puis force le niveau à « critique » si `score_rang_a < 40`, « fragile » si `< 75`.
Mesure sur la base : `oic_attempts` ne contient que **3 lignes dans toute la base**, avec des scores de 50, 62 et 40 — tous **strictement inférieurs à 70**, le seuil qui bascule un OIC en `mastered=1` (`backend/core/lisa/item_service.py:128`). Résultat : `lisa_oic` a 176 lignes Rang A et **0 marquées mastered** (`SUM(mastered)=0`). Les 3 cours concernés (items 339, 225, 221 par préfixe `oic_code`) ont respectivement 9, 4 et 13 objectifs Rang A au total, donc `rang_a_pct = 0/9`, `0/4`, `0/13` = 0 % chacun. Leur `score_rang_a` est donc au mieux `0.5 × mastery_score` (≤ 50 même si `mastery_score = 100`), ce qui les verrouille en dessous du seuil 75 — donc « fragile » au mieux, quel que soit par ailleurs le score global du cours.
**Pourquoi c'est un problème** : le mécanisme punit un cours dès qu'un seul objectif Rang A sur un total pouvant dépasser dix a été *tenté* sans le réussir du premier coup — l'étudiant qui commence tout juste à travailler ses OIC Rang A d'un item voit ce cours bloqué en « fragile » de façon quasi permanente, jusqu'à ce qu'il ait réussi (≥70) au moins 80 % de la totalité de ses objectifs Rang A. C'est l'exact miroir du bug « Rang A » déjà identifié dans un audit antérieur (mentionné dans le contexte de cette mission) — ici démontré sur les 3 seuls cas réels observables.
**Piste** : ne compter au dénominateur que les objectifs réellement tentés (`mastered / attempted`, pas `mastered / total`), ou ne déclencher le verrou qu'à partir d'un nombre minimal de tentatives représentatif du total.

### [Critique] Le potentiel de gain EDNpro est dominé par l'absence de mesure de maîtrise, pas par la maîtrise elle-même

**Ce qui se passe** : `backend/core/ednpro/frequency.py::calculate_gain_priority()` (lignes 161-170) calcule `gap = 100 - mastery` en traitant `mastery=None` comme `mastery=0` (`float(mastery if mastery is not None else 0.0)`), donc `gap = 100` — le maximum — pour tout item sans donnée de maîtrise.
Mesure sur la base (jointure `data_cache.json` cours ↔ `mastery_snapshots` la plus récente ↔ `ednpro_item_frequency` (367 items) ↔ questions importées `source=ednpro`) : **291 items sur 367 (79 %) n'ont aucune valeur de maîtrise mappée** et reçoivent donc `gap=100` par défaut. La distribution du gain va de 0 à **1300**, moyenne ≈230, médiane 200 — un facteur 1300 entre le minimum et le maximum sans échelle affichée. Le **Top 10 des items par potentiel de gain est composé à 100 % d'items sans aucune mesure de maîtrise** (`mastery=None` dans les 10 premiers : items 247, 267, 135, 95, 94, 148, 279, 322, 45, 57). Parmi les 76 items qui ont une valeur de maîtrise réelle, le gain moyen (176) est inférieur au gain moyen des items sans mesure (244) — la présence même d'une mesure de maîtrise *réduit* statistiquement le score de gain affiché, l'effet inverse de ce que l'indicateur est censé faire.
Sur les 86 items à gain nul : 38 n'ont eu aucune session EDNpro recensée (fréquence 0), 48 ont des sessions recensées mais aucune question effectivement importée (`imported_question_count=0`, disponibilité nulle).
**Pourquoi c'est un problème** : présenté à l'étudiant comme un chiffre brut sans échelle (« Potentiel de gain 1300 », `frontend/components/ai_practice_panel.py:466`, `ui.label(f"Potentiel de gain {gain:g}")`), l'indicateur trie en réalité par fréquence EDNpro × disponibilité de questions importées, avec l'absence de données de maîtrise agissant comme un boost artificiel plutôt que comme un signal d'incertitude. Un étudiant qui suit ce tri travaillera en priorité les items les plus fréquents aux concours et bien pourvus en questions importées — pas nécessairement ceux où il est le plus faible.
**Piste** : distinguer explicitement « maîtrise inconnue » de « maîtrise nulle » (ne pas les faire converger vers le même `gap=100`) ; envisager un badge « lacune non mesurée » plutôt qu'un score continu quand `mastery is None`. Documenter l'échelle (min/max observés, ou normalisation 0-100) avant d'exposer un nombre brut.

### [Critique] Sur données réelles, la maîtrise ne dépasse jamais 61 et n'atteint jamais « maîtrisé » — la grande majorité des scores affichés viennent d'une auto-déclaration, pas d'une preuve

**Ce qui se passe** : `mastery_snapshots` (4128 lignes, 7 semaines S26 à S33, 825 `course_id`) enregistre l'historique persisté du score calculé par `get_course_mastery()`. Mesure : `SELECT MIN(mastery_score), MAX(mastery_score), AVG(mastery_score) FROM mastery_snapshots` → **min 25, max 61, moyenne 40.75** (NULL exclus automatiquement par SQL, donc ce ne sont que les cours réellement scorés). Sur les niveaux du dernier snapshot par cours : `à préparer` 555, `à lire` 168, `fragile` 54, `critique` 48, **et zéro `à consolider` ou `maîtrisé`** sur les 825 cours et 7 semaines d'historique.
En reliant ces `course_id` au cache Notion actuel et en regroupant par `item_number` : sur 76 items ayant une valeur de maîtrise, les valeurs se concentrent presque toutes sur exactement **28.0 (32 occurrences) ou 48.0 (34 occurrences)** — la valeur maximale observée est 58. Cette concentration confirme sur données réelles ce que l'audit du 9 août avait seulement soupçonné en lisant le code (§5.3, « paliers artificiels »).
Croisement supplémentaire : parmi les 102 cours au niveau `fragile`/`critique` (dernier snapshot), **98 (96 %) ont une entrée dans `item_state`** (niveau déclaré manuellement — ancien collège validé), contre seulement 8 cours sur 707 ayant `date_1ere_lecture` renseignée en contexte collège dans le cache Notion actuel (1,1 %), et 13/707 en contexte UE. `study_sessions` ne contient que 34 lignes et `qcm_sessions` que 7 lignes dans toute la base.
**Pourquoi c'est un problème** : la grande majorité de ce qui s'affiche comme « fragile » ou « critique » ne mesure pas un échec d'apprentissage récent — c'est la dégradation temporelle d'un niveau que l'étudiant s'est lui-même attribué au moment du triage des anciens collèges validés. Le score composite (calibré pour atteindre 70-95 avec des lectures/QCM/confiance favorables selon la formule) ne trouve presque jamais assez de preuves réelles (sessions, QCM) pour dépasser ~60, car ces preuves sont rares dans la base. Le système donne l'impression d'un diagnostic actif alors qu'il reflète surtout une auto-évaluation qui s'efface avec le temps.
**Piste** : afficher explicitement la part « graine déclarée » vs « preuve mesurée » dans le score (le calcul le sait déjà via `n_evidence` et `seed.declared_level` — il suffit de l'exposer), et ne pas laisser un score sans preuve récente ressembler visuellement à un score mesuré.

### [Important] Deux moteurs de scoring EDN divergents pour la même notion de « barème officiel »

**Ce qui se passe** : `backend/core/practice/scoring.py::compute_question_score_edn` (utilisé par le parcours d'entraînement standard via `attempt_service.py`) et `backend/core/uness/exam_simulator.py::compute_edn_score` (utilisé par le mode « Épreuves Blancs », `frontend/pages/exam_simulator_page.py:258`) appliquent des règles différentes pour ce que les deux commentaires de code appellent « le barème officiel EDN ». Le premier traite indispensable et inacceptable comme deux concepts distincts, associés à n'importe quelle proposition. Le second ne connaît que la notion de rang A « oublié » (il ignore explicitement le cas d'une proposition rang A fausse cochée à tort — le docstring dit « oubli **ou erreur** » mais le code ne teste que l'oubli, ligne 88-90). Les deux sont actuellement inertes en pratique par manque de données (constat Critique 1), mais restent deux implémentations distinctes d'une même règle métier.
**Pourquoi c'est un problème** : si les données d'entrée venaient à être enrichies (rang/indispensable renseignés), un étudiant obtiendrait un score différent pour une réponse identique selon qu'il s'entraîne en mode standard ou en mode concours — sans que rien dans l'UI ne signale que ce sont deux moteurs distincts.
**Piste** : faire converger `exam_simulator.py` sur `backend/core/practice/scoring.py::compute_question_score_edn`, seule source du barème officiel selon l'architecture IA documentée (§16.1 de l'audit du 9 août : « le score officiel est interdit à l'IA », ce qui implique aussi qu'il ne devrait exister qu'à un seul endroit).

### [Important] Le moteur de scoring R2C est très peu exercé en pratique

**Ce qui se passe** : `ai_practice_attempts` contient 37 lignes au total. `score_mode` vaut `'edn'` (le chemin `compute_question_score_edn`) sur seulement **7 d'entre elles** ; les 30 autres ont `score_mode=''`. Sur les 7 tentatives scorées en mode EDN : `score_reason` vaut `trop_de_discordances` deux fois, vide (score parfait ou discordance 1/2) le reste — jamais `indispensable_manquante` ni `inacceptable_cochee` (cohérent avec le constat Critique 1).
**Pourquoi c'est un problème** : le module dont l'audit du 9 août dit qu'il « ne doit pas être calculé par l'IA » et qui porte la responsabilité de la note officielle n'a, à ce jour, produit que 7 scores réels dans toute l'histoire de l'application, sur une banque de 3497 questions disponibles. Toute conclusion sur sa fiabilité en conditions réelles serait prématurée — il n'y a simplement pas assez d'usage pour juger.
**Piste** : aucune action corrective algorithmique ; c'est une observation sur le volume d'usage, à recouper avec l'ergonomie du parcours d'entraînement (pourquoi si peu de sessions vont au bout du scoring officiel).

### [Important] « Progression collège » ne reflète presque rien de l'activité réelle de l'étudiant

**Ce qui se passe** : `frontend/pages/colleges_cockpit.py` calcule `started` comme le nombre de cours avec `date_1ere_lecture` renseignée (ligne ~263 et ~361), sauf pour les collèges au statut `valide` où `started = total` est forcé (ligne 361). Mesure sur le cache Notion actuel (707 cours) : **8 cours ont `date_1ere_lecture` renseignée en contexte collège (1,1 %)**, 13 en contexte UE. `college_status` ne compte que **9 collèges `valide`** sur l'ensemble du référentiel — pour tous les autres, la progression affichée frôle 0 % quelle que soit l'activité réelle.
Pourtant l'activité réelle existe ailleurs dans la base : 250 révisions terminées (`review_history`, statut `done`), 3497 questions générées, 20 cours avec des OIC LiSA travaillés, 34 sessions d'étude, 7 sessions QCM. Le détail des types de révision terminées montre d'ailleurs que le flux classique J3/J7/J14/J30 (celui qui dépend de `date_1ere_lecture`) ne représente que 51/250 (20 %) des révisions réellement effectuées ; le reste (`consolidation` 112, `bonus` 87) passe par d'autres chemins qui ne renseignent pas ce champ.
**Pourquoi c'est un problème** : l'indicateur affiché en premier sur la vue Collèges donne l'impression que rien n'a été fait, alors que l'étudiant travaille manifestement — mais par des voies (annales, révisions bonus/consolidation, OIC) que cette métrique ne capture pas. C'est le même problème vocabulaire/métrique documenté conceptuellement le 9 août (§2), mais les chiffres réels montrent qu'il ne s'agit pas d'une nuance : la métrique est quasi vide pour la quasi-totalité du programme.
**Piste** : soit inclure les autres signaux d'activité (session, QCM, OIC, révision consolidation/bonus) dans le calcul de « progression », soit renommer clairement l'indicateur en « cours entrés dans le cycle classique J3-J30 » pour éviter la confusion avec l'activité globale.

### [Important] SM-2 : peu de différenciation individuelle observée, et une révision terminée sur deux n'a pas d'intervalle enregistré

**Ce qui se passe** : sur 250 lignes `review_history`, 246 sont `done`. L'`easiness_factor` vaut exactement **2.5 (la valeur initiale `SM2_INIT_EF`) sur 229 lignes (92 %)** ; seules 11 lignes sont à 2.3 et une poignée ailleurs. `next_interval_days` est **NULL sur 134/250 lignes (54 %)**, y compris parmi des lignes `done`. `repetition_count=0` sur 130/250 lignes (52 %) — majoritairement des premières occurrences, ce qui explique en partie l'EF resté au défaut, mais pas la moitié de `next_interval_days` manquants.
**Pourquoi c'est un problème** : si l'EF ne s'écarte quasiment jamais de sa valeur initiale, l'espacement adaptatif promis par SM-2 (facteur de facilité qui monte avec la réussite, descend avec l'échec) ne joue en pratique presque aucun rôle différenciateur — la plupart des cours suivent un espacement proche du cycle fixe J3/J7/J14/J30 plutôt qu'un vrai SM-2 individualisé. L'absence d'intervalle enregistré pour une révision sur deux limite aussi la capacité à auditer la cohérence du planning a posteriori.
**Piste** : vérifier pourquoi le chemin de mise à jour de l'EF n'est pas atteint pour la majorité des révisions (première occurrence vs bug de propagation), et pourquoi `next_interval_days` n'est pas systématiquement écrit à la complétion.

### [Important] Retard réel confirmé sur une portion notable des révisions, avec des cas extrêmes proches d'un an

**Ce qui se passe** : sur les 246 révisions `done` avec une date théorique et une date de complétion, l'écart (complétion − échéance théorique) va de -7 à **+298 jours**. La médiane est 0 (la plupart des révisions sont closées le jour même de leur échéance, ou rétroactivement lors d'imports groupés), mais **36 lignes (15 %) dépassent 60 jours de retard**, avec une queue à 226, 230, 251, 267, 274, 278 et 298 jours. Les dates théoriques remontent jusqu'au 18 août 2025, soit un an avant la date de cet audit.
**Pourquoi c'est un problème** : cela confirme sur données réelles la question posée dans le périmètre de mission (« accumulation de retard »). La médiane à 0 masque une queue de révisions très en retard qui, si elles pèsent dans le calcul de priorité (`_calculate_priority`, +5/jour de retard plafonné à 60, +15 si J30), peuvent avoir dominé le tri de la file d'attente pendant des mois sans que l'algorithme fasse de distinction entre « 3 jours de retard » et « 10 mois de retard » au-delà du plafond.
**Piste** : décider explicitement du traitement des révisions très en retard (les replanifier plutôt que les accumuler, ou les faire expirer) plutôt que de les laisser strictement s'empiler dans le score de priorité plafonné.

### [Important] Couverture OIC : la correction du 3 août tient au niveau du code, mais l'indicateur reste illisible faute de données

**Ce qui se passe** : le contexte de cette mission demandait de vérifier si le bug de couverture OIC forcée à 0.0 (signalé début août) tenait sur les données actuelles. Lecture du code : `backend/core/knowledge/service.py::oic_coverage()` agrège correctement `mastered/total` par cours et par rang à partir de `lisa_oic`/`oic_attempts` — pas de valeur forcée en dur trouvée. Le résultat reste néanmoins à 0 % pour la quasi-totalité des cours parce que **`oic_attempts` ne contient que 3 lignes dans toute la base**, aucune ≥70 (voir constat Critique 2).
**Pourquoi c'est un problème** : impossible de distinguer, du point de vue utilisateur, « la couverture est nulle parce que le calcul est cassé » de « la couverture est nulle parce que je n'ai presque rien tenté ». Le premier cas a été corrigé ; le second reste vrai et rend l'indicateur peu informatif en l'état.
**Piste** : afficher le nombre de tentatives (`rang_a_attempted`) à côté du pourcentage de couverture, pour distinguer visuellement « non mesuré » de « mesuré et faible ».

### [Mineur] Constante `SCORE_FLOOR = 20` toujours morte dans `forgetting_curve.py`

**Ce qui se passe** : `frontend/components/forgetting_curve.py:21` déclare `SCORE_FLOOR = 20` avec le commentaire « asymptote : on n'oublie jamais tout », mais tout le calcul de projection (`project_score`, lignes 47-63) utilise exclusivement `MASTERY_FLOOR = 25` importé de `backend/core/knowledge/retention.py`. `grep SCORE_FLOOR` sur le fichier ne retourne qu'une seule occurrence : la déclaration elle-même.
**Pourquoi c'est un problème** : incohérence déjà signalée le 9 août (§6.2) comme un risque de « courbes incohérentes » ; toujours présente inchangée un jour plus tard. Risque faible tant que la constante reste inutilisée, mais source de confusion pour quiconque modifie ce fichier en pensant que 20 est le plancher actif.
**Piste** : supprimer la constante morte.

### [Mineur] Double référentiel de seuils qualitatifs entre `forgetting_curve.py` et `mastery.py`

**Ce qui se passe** : `forgetting_curve.py::_health()` (ligne 66-73) qualifie un score en `solide/correct/fragile/critique` avec les seuils 80/55/30, alors que `mastery.py` (lignes 287-306) détermine les niveaux `maîtrisé/à consolider/fragile/critique` avec les seuils 40/60/80 (et des règles supplémentaires liées au QCM et au Rang A).
**Pourquoi c'est un problème** : deux vocabulaires proches (« critique », « fragile ») avec des bornes numériques différentes selon le composant regardé — un score de 50 est « fragile » dans la courbe d'oubli mais peut être « critique » dans le tableau de bord mastery selon le contexte QCM.
**Piste** : faire pointer `_health()` vers les mêmes seuils que `mastery.py`, ou au minimum renommer les catégories de la courbe pour éviter la collision de vocabulaire.

### [Mineur] Anomalie `item_number = 'DP'` : orpheline, mais sans impact mesurable

**Ce qui se passe** : `ai_practice_sessions` a une ligne (`id=220`, `course_id='exam-blanc'`, `completion_state='draft'`, `score_percent=NULL`) et `ai_practice_questions` a 8 lignes liées à ce même `course_id='exam-blanc'`, toutes avec `item_number='DP'` — un dossier progressif d'examen blanc jamais classifié à un vrai numéro d'item. Vérification : **aucune de ces 8 questions n'a de ligne correspondante dans `ai_practice_question_items`** (la table de classification réellement consommée par `mastery.py` et par le profil d'erreurs), et la session associée n'a jamais été complétée (`completed_at IS NULL`).
**Pourquoi c'est un problème** : concrètement aucun, cette session n'a jamais influencé de calcul (mastery, fréquence, profil d'erreurs) puisqu'elle est à la fois non classifiée et non terminée. Elle documente cependant un point d'entrée du pipeline d'import (cas DP sans énoncé clinique classifiable) qui laisse des lignes orphelines en base.
**Piste** : aucune urgence ; à surveiller si ce type de session `draft` non classifiée venait à s'accumuler.

## Ce qui va bien

- Le cœur du barème EDN (0/1/2/3+ discordances → 1 / 0,5 / 0,2 / 0 points) est implémenté à l'identique dans les deux moteurs, et correspond au barème R2C documenté.
- Aucune valeur hors bornes trouvée : `mastery_score` et `retention_score` sont strictement dans [0, 100] sur les 4128 lignes de `mastery_snapshots` (`WHERE mastery_score < 0 OR mastery_score > 100` → 0 résultat, idem retention).
- Le plancher de rétention (`MASTERY_FLOOR = 25`) est cohérent entre `backend/core/knowledge/retention.py` et `backend/core/reviews/mastery.py` — la seule incohérence relevée est la constante morte de `forgetting_curve.py` (Mineur), pas un vrai écart de calcul.
- L'agrégation OIC (`mastered/total` par rang) fonctionne correctement sur les données réelles : le bug de couverture forcée à 0.0 signalé début août ne se reproduit pas au niveau du code — le 0 % observé aujourd'hui reflète l'absence de données, pas un défaut de calcul.
- Le score de fusion graine/preuve (`blend()`, `backend/core/knowledge/models.py`) se comporte comme documenté : son poids diminue avec `n_evidence`, sans valeur aberrante observée.
- Le référentiel `ednpro_item_frequency` (367 lignes) couvre exactement l'ensemble des 367 items EDN — pas de item manquant ni de doublon détecté.
- Les scores de session QCM (`compute_session_edn_score`) et le seuil de validation Rang A (14/20) sont appliqués de façon cohérente sur les 7 sessions QCM enregistrées.

## Évolution depuis l'audit du 9 août

- Le socle de l'audit du 9 août (fondé sur la lecture du code) tenait déjà des réserves justes sur le principe : graine pondérée par `n_evidence`, Rang A « indicateur pédagogique, pas mesure empirique », potentiel de gain « heuristique de tri, pas prédiction ». Les données réelles ne contredisent aucune de ces réserves — elles les aggravent avec des chiffres : le potentiel de gain n'est pas seulement non calibré, il est *dominé* par une valeur par défaut touchant 79 % des items ; le Rang A n'est pas seulement « non empirique », il verrouille structurellement des items dès la première tentative partielle.
- Deux points signalés le 9 août restent inchangés le 10 : la constante `SCORE_FLOOR` morte et l'absence d'échelle documentée pour le potentiel de gain (§7.2 de l'audit du 9 août demandait déjà de le renommer « priorité relative de travail » plutôt que « gain prédit » — ce n'est toujours pas fait dans `ai_practice_panel.py:466`).
- Un point absent de l'audit du 9 août et de celui du 3 août sous cette forme : la divergence structurelle entre les deux moteurs de scoring EDN (`scoring.py` vs `exam_simulator.py`). L'audit du 3 août avait bien repéré un symptôme de `exam_simulator.py` (rang forcé en dur à « A », §2.4) — corrigé depuis — mais aucun des deux audits précédents n'avait relevé qu'il s'agit en réalité de deux implémentations séparées d'une même règle métier, avec des définitions différentes de ce que signifie « barème officiel ».
- Le bug de couverture OIC forcée à 0.0 (signalé début août) est vérifié corrigé au niveau du code sur les données actuelles — mais cette vérification n'était possible qu'en confrontant le code aux données : la lecture de code seule ne permet pas de voir que le 0 % réel vient désormais du manque de tentatives (3 dans toute la base), pas d'un défaut de calcul.
- Nouveau, visible uniquement par confrontation aux données (pas par lecture de code) : la maîtrise réellement mesurée plafonne à 61 sur 7 semaines de snapshots et n'atteint jamais « à consolider » ni « maîtrisé » ; 96 % des cours affichés « fragile »/« critique » proviennent de la graine déclarée et non d'une preuve d'apprentissage récente. Ce chiffre change la lecture de tout le système : il ne s'agit pas d'un score de maîtrise sous-exploité par manque de calibration, mais d'un score qui, sur l'usage réel actuel, mesure presque toujours l'auto-déclaration initiale plutôt que l'apprentissage.

---

# 3. Axe intégrité des données


Méthode : lecture seule (`file:...?mode=ro`), aucune écriture, aucun appel réseau/API. Requêtes exécutées via `./.venv/Scripts/python.exe` contre `data/synapse_local.db` (33 067 008 octets) et `data_cache.json` (cache Notion, 707 cours). Référentiel UNESS utilisé : `data/items_edn.json` (367 items).

Statut : audit terminé, rédigé au fil de l'eau.

## Synthèse

1. **Le référentiel UNESS n'est pas réellement l'autorité en pratique** : 299 des 582 cours Notion ayant un `item_number` (51 %) ont un collège qui contredit `data/items_edn.json`, alors que le principe établi dans ce projet est l'inverse.
2. **La table de classification par item (`ai_practice_question_items`) diverge massivement de la colonne historique `item_number`** : 1 749 questions sur 3 190 valides (55 %) n'ont pas de ligne de classification correspondant à leur propre `item_number`, et 1 053 questions (30 % du total) n'ont aucune classification du tout.
3. **Le bug de classification à l'échelle de l'examen entier (au lieu du sous-dossier) est confirmé sur au moins 3 examens multi-DP**, avec mismatch de contenu vérifié (Cardiologie item 230 appliqué à un DP sur la dyspnée/NYHA et un DP sur une valvulopathie ; Hématologie item 212 appliqué à un cas d'hémostase ; Douleur/Soins Palliatifs item 134 appliqué à deux cas d'anesthésie).
4. Sur `ai_usage_logs`, un critère technique fiable (coût = 0 **et** tokens = 0, ce qui n'arrive jamais sur un vrai appel Gemini réussi — coût minimum observé 0,000002 $) donne **695 lignes sur 1 358 (51 %)** de données de test, un chiffre supérieur au 45 % déjà établi par ailleurs.
5. La sauvegarde de la base, absente lors de l'audit du 2 août, **existe maintenant** (`data/backups/`, copie SQLite native quotidienne, rétention 7 jours) — mais un jour (6 août) manque dans la séquence et la copie reste sur le même disque que la source.
6. Aucune corruption détectée : `PRAGMA integrity_check` = `ok`, `PRAGMA foreign_key_check` = 0 violation, mode `WAL` actif, écritures sérialisées côté application par un verrou global.

## Inventaire

Tables non listées ci-dessous : voir requête `SELECT name FROM sqlite_master WHERE type='table'` (49 tables au total).

| Table | Lignes | Rôle | État |
|---|---:|---|---|
| `ai_practice_sessions` | 599 | Séance de pratique IA (QCM/DP), porte `item_number` principal | 19 sans item, 1 avec item non numérique (`'DP'`) |
| `ai_practice_questions` | 3 497 | Question IA, copie immuable par session (versionnage volontaire) | 299 sans item, 8 avec `item_number='DP'`, 67 % en doublon de contenu |
| `ai_practice_session_questions` | 1 758 | Lien session↔question (position) | RAS |
| `ai_practice_session_items` | 1 233 | Items multiples d'une session (DP transverses) | 25 sessions sans aucune ligne (19 item vide + 6 item non vide non reflété) |
| `ai_practice_question_items` | 2 885 | Classification item par question (source/confiance/version) | Valeurs toujours valides, mais couverture partielle et divergente de `item_number` |
| `ai_practice_attempts` | 37 | Réponse à une question | 0 orphelin (question_id toujours valide) |
| `ai_practice_attempt_propositions` | 35 | Détail des propositions cochées | RAS |
| `ai_usage_logs` | 1 358 | Journal d'appels IA (coût, tokens, tâche) | 51 % de lignes identifiables comme test |
| `uness_annales` | 86 | Annale UNESS regroupée (source_url unique) | RAS |
| `uness_scanned_catalog` | 1 128 | Catalogue des items scannés côté UNESS | statut homogène `available` |
| `uness_correction_failures` | 2 | File d'attente de correction Gemini en échec | RAS |
| `course_edges` | 15 402 | Graphe de proximité entre cours (source/target/poids) | 0 orphelin vs cache Notion actuel |
| `item_state` | 146 | Niveau déclaré par (cours, contexte) | RAS |
| `mastery_snapshots` | 4 128 | Historique de maîtrise | non audité en détail (hors items prioritaires) |
| `review_history` | 250 | Historique des tâches de révision | 7 lignes de test (`course_id` = `c1`/`c2`/`c99`), 12 lignes pointant vers 3 cours disparus du cache Notion |
| `weak_points` | 3 | Points faibles actifs | table définie deux fois dans le code (schéma identique, sans risque) |
| `pdf_item_scan` | 392 | Scan PDF par (collège, item) | RAS |
| `pdf_local_cache` | 490 | Cache de PDF locaux détectés | non audité en détail |
| `imported_practice_cases` / `imported_practice_questions` | 3 / 23 | Cas cliniques importés manuellement | pas de marqueur de test détecté |
| `study_sessions` | 34 | Sessions de travail (lecture) | non audité en détail |
| `qcm_sessions` | 7 | Ancienne table de résultats QCM (pré-`ai_practice_*`) | pas de marqueur de test détecté |
| `lisa_oic` / `lisa_oic_cache` | 290 / 26 | Cache objectifs LiSA/OIC | non audité en détail |
| `ednpro_item_frequency` | 367 | Fréquence EDNpro par item (1 par item du référentiel) | RAS, cardinalité = référentiel |
| `college_status` | 9 | Statut déclaré par collège | non audité en détail |
| `recent_courses` | 9 | Cours récents | 0 orphelin vs cache Notion |
| **Tables à 0 ligne (11 sur 49, 22 %)** | 0 | `ai_practice_anchors`, `anki_review_evidence`, `consolidation_gates`, `edn_recommendations`, `ednpro_qcm_attempts`, `ednpro_qcm_questions`, `ednpro_qcm_sessions`, `error_signals`, `external_results`, `flash_zero_ai_questions`, `notion_sync_queue`, `qcm_results`, `stages` | voir constat schéma |

## Constats

### [Critique] Le collège Notion contredit le référentiel UNESS sur 51 % des cours classés

**Ce qui se passe** : en croisant `data_cache.json` (707 cours Notion, dont 582 avec `item_number` renseigné) avec `data/items_edn.json` (367 items, colonne `college`) via la table de correspondance officielle du code (`backend/core/qcm/items_mapping.py:23-58`, `_ABBR_TO_NOTION`), **299 cours sur 582 (51 %)** ont un champ `college` Notion qui ne contient pas le nom complet attendu par le référentiel pour leur `item_number`.

Exemples vérifiés :
- « Hypercalcémie » (item 268) : Notion = `Endocrinologie - Diabétologie - Maladies métaboliques`, référentiel = `Néphrologie`.
- « FDR et Dyslipidémies » (item 222) : Notion = `Endocrinologie...`, référentiel = `Cardiovasculaire`.
- « Contraception » (item 36), « Ménopause et andropause » (item 124), « Infertilité du couple » (item 38) : tous taggés `Endocrinologie...` dans Notion, référentiel = `Gynécologie-Obstétrique`.
- « Pancréatite aiguë » (item 358) : Notion = `Médecine Intensive - Réanimation` ou `Anesthésie-Réanimation`, référentiel = `Hépato-Gastro-entérologie`.

**Pourquoi c'est un problème** : le principe établi dans ce projet (voir mémoire `project_college_item_authority`) est que le référentiel UNESS fait autorité et que Notion doit être réconcilié dessus, jamais l'inverse. Ce constat montre que la réconciliation n'a pas eu lieu, ou a régressé, sur la majorité des cours classés. Concrètement, ça fausse tout regroupement, filtre ou statistique par collège affiché dans l'application (progression par collège, répartition des lacunes par collège, etc.) — ce n'est pas une perte de données, mais une **désinformation systématique de l'utilisateur sur son propre classement des cours**.

**Piste** : réexécuter la réconciliation Notion↔référentiel décrite dans la mémoire projet (probablement `scripts/*college*` ou équivalent), en s'appuyant sur `_ABBR_TO_NOTION` comme table de vérité, et vérifier pourquoi tant de cours ont été laissés ou remis sur un collège divergent depuis.

### [Critique] La table de classification par item diverge massivement de `item_number`

**Ce qui se passe** :
```sql
SELECT COUNT(*) FROM ai_practice_questions q
WHERE q.item_number != '' AND NOT EXISTS (
    SELECT 1 FROM ai_practice_question_items qi
    WHERE qi.question_id = q.id AND qi.item_number = q.item_number
);
-- 1749

SELECT COUNT(*) FROM ai_practice_questions q
WHERE NOT EXISTS (SELECT 1 FROM ai_practice_question_items qi WHERE qi.question_id = q.id);
-- 1053
```
Sur 3 497 questions au total (3 190 avec un `item_number` valide 1-367), 1 749 ont un `item_number` qui n'apparaît dans aucune ligne de `ai_practice_question_items` les concernant, et 1 053 n'ont strictement aucune ligne de classification. La table `ai_practice_question_items` elle-même ne contient que 2 885 lignes, réparties en trois sources : `source-explicit-v1` (2 714, la classification héritée de `item_number` au moment de la question), `2026-08-03-question-v1` (167, migration UNESS ciblée du 3 août), `session-primary-v1` (4, règle de secours).

**Pourquoi c'est un problème** : ce sont deux sources de vérité pour « quel item couvre cette question » qui ne sont synchronisées qu'à 45 % environ. Toute fonctionnalité qui s'appuie sur `ai_practice_question_items` (évidence multi-item, DP transverses) pour calculer la maîtrise ou l'historique d'un item spécifique passe à côté de la majorité des questions historiques — ça **fausse les statistiques de maîtrise par item**, sans perdre la donnée brute (le `item_number` original reste lisible sur `ai_practice_questions`).

**Piste** : soit backfiller systématiquement `ai_practice_question_items` depuis `ai_practice_questions.item_number` pour les 1 749 lignes manquantes (le mécanisme existe déjà, cf. la source `source-explicit-v1`), soit clarifier laquelle des deux colonnes fait foi pour les lectures actuelles et documenter pourquoi l'autre est laissée de côté.

### [Critique] Classification IA appliquée à l'échelle de l'examen entier, confirmée sur 3 examens avec contenu vérifié

**Ce qui se passe** : en regroupant les 599 sessions par examen d'origine (titre commun avant le suffixe `DPn/KFPn/mDPn/SQIn`), 12 examens multi-sous-cas existent. Sur ces 12, plusieurs montrent un `item_number` identique appliqué à des sous-cas au contenu clairement différent :

- **« DFASM1 EXAMEN Cardiologie... 22 janvier 2026 »** (10 sessions) : 5 sessions (id 210, 211, 212, 213, 215) tagguées item **230** (Douleur thoracique). Contenu vérifié de la session 211 (DP1) : « classification de la New York Heart Association » (dyspnée/insuffisance cardiaque, pas douleur thoracique). Contenu de la session 212 (DP2) : « rétrécissement aortique », « échocardiographie » (valvulopathie, item réel ≈ 231). C'est le cas signalé en amont (DP insuffisance cardiaque mal étiqueté item 230), confirmé et élargi : au moins 2 sous-cas sur 5 ont un contenu qui ne correspond pas à l'item 230.
- **« Examen Hématologie / pôle 2 - T3 - 13/05/2025 »** (4 sessions, id 196/197/198/206) : les 4 sous-cas (DP1, DP2, KFP1, SQI1) sont **tous** tagués item **212**. Contenu de la session 198 (SQI1) : « syndrome hémorragique diffus », « Temps de Quick » (trouble de l'hémostase, pas anémie/item 212).
- **« Examen Douleur – Soins Palliatifs Accompagnement / pôle 6 - T3 - 16/05/2025 »** (4 sessions, id 134/137/140/141) : les 4 sous-cas tagués item **134** (Douleur). Contenu de la session 137 (mDP1) et 141 (SQI2) : « consultation d'anesthésie », « anesthésie loco-régionale » (anesthésie, item réel ≈ 133, pas douleur).

**Pourquoi c'est un problème** : conséquence directe sur la maîtrise affichée par item — un item peut apparaître mieux (ou moins bien) maîtrisé qu'en réalité parce que les questions qui lui sont attribuées ne le concernent pas. C'est une **distorsion de la statistique de maîtrise par item**, pas une perte de données (le contenu texte original reste correct et lisible).

**Piste** : ne pas redécouvrir au cas par cas — reclasser au niveau du sous-dossier (DP/KFP/SQI) plutôt qu'au niveau de l'examen entier pour ces 12 groupes, en commençant par les 3 confirmés ci-dessus qui représentent au minimum 13 sessions et plusieurs dizaines de questions.

### [Important] `item_number` non valide sur 20 sessions, incohérence avec la table de liaison sur 6 sessions

**Ce qui se passe** :
```sql
SELECT item_number, COUNT(*) FROM ai_practice_sessions
WHERE item_number NOT GLOB '[0-9]*' OR item_number GLOB '*[^0-9]*'
GROUP BY item_number;
-- '' : 19
-- 'DP' : 1   (session id=220, "Examen PSYCHIATRIE ... — DP4")
```
599 sessions au total, aucun `item_number` numérique n'est hors plage 1-367 (le seul problème est le vide ou la valeur littérale `'DP'`). Sur les 6 sessions avec `item_number` non vide mais absentes de `ai_practice_session_items` :
```sql
SELECT COUNT(*) FROM ai_practice_sessions s WHERE s.item_number != ''
AND NOT EXISTS (SELECT 1 FROM ai_practice_session_items si WHERE si.session_id=s.id AND si.item_number=s.item_number);
-- 6
```
Sur `ai_practice_questions` (3 497 lignes), même schéma : 299 avec `item_number=''`, 8 avec `item_number='DP'`.

**Pourquoi c'est un problème** : ces sessions/questions sont invisibles pour tout calcul de maîtrise indexé par item (elles ne cassent rien, elles disparaissent silencieusement des agrégats). Pas de perte de données brutes, mais une **sous-estimation du volume de pratique réellement associé à certains items**.

**Piste** : script de rattrapage ciblé sur les 20 sessions et 307 questions concernées (chercher le vrai item dans le titre/contenu), puis contrainte de validation à la saisie pour empêcher `'DP'` comme valeur d'`item_number` (c'est un `practice_kind`, pas un item).

### [Important] Pollution de `ai_usage_logs` par des données de test : au moins 51 %, pas 45 %

**Ce qui se passe** : un appel Gemini réel et réussi a toujours un coût strictement positif (minimum observé sur la table : `0.000002` $, tâche `gemini_generate`). Le critère « coût = 0 ET tokens entrants = 0 ET tokens sortants = 0 » est donc un signal fiable de simulation/mock, pas un artefact d'arrondi :
```sql
SELECT COUNT(*) FROM ai_usage_logs WHERE cost_usd=0 AND input_tokens=0 AND output_tokens=0;
-- 509  (dont 499 en tâche 'gemini_generate', context=NULL — clairement des appels mockés en tests)
```
En ajoutant les deux autres marqueurs de test trouvés dans la colonne `context` :
```sql
SELECT COUNT(*) FROM ai_usage_logs WHERE context = 'unit_test';
-- 47  (toutes en tâche 'qcm', datées du 1er au 7 août 2026)
SELECT COUNT(*) FROM ai_usage_logs WHERE context LIKE '%' || char(10) || 'Test';
-- 149
```
Union dédupliquée des trois critères :
```sql
SELECT COUNT(*) FROM ai_usage_logs
WHERE context = 'unit_test'
   OR (cost_usd = 0 AND input_tokens = 0 AND output_tokens = 0)
   OR context LIKE '%' || char(10) || 'Test';
-- 695 sur 1358 (51,2 %)
```
**Critère de discrimination réutilisable pour cette table** : `cost_usd = 0 AND input_tokens = 0 AND output_tokens = 0` (appel simulé, un vrai appel facturé a toujours un coût non nul) OU `context = 'unit_test'` OU `context` se terminant par le mot littéral `Test` sur sa propre ligne.

**Pourquoi c'est un problème** : ce n'est pas une perte de données — c'est une **contamination des statistiques d'usage/coût IA** affichées ou calculées à partir de cette table (tout indicateur de coût réel, de volume d'appels, de taux d'erreur par tâche est faussé tant que ces lignes restent mélangées aux vraies).

**Piste** : ajouter un flag explicite (`is_test` ou équivalent) posé par le harnais de test au moment de l'écriture plutôt que de devoir le déduire après coup, et purger les 695 lignes historiques identifiées ci-dessus.

### [Important] Un fixture de test confirmé dans `ai_practice_questions`, contamination `review_history` par 3 identifiants factices

**Ce qui se passe** :
```sql
SELECT id, course_id, item_number, practice_kind, prompt FROM ai_practice_questions WHERE model='test';
-- id=100, course_id='', item_number='', practice_kind='QCM', prompt='q'
```
Une seule ligne sur 3 497 porte un marqueur de test univoque (`model='test'`, prompt d'un seul caractère `'q'`) — les 74 lignes contenant le mot « test » dans leur `prompt` sont, à l'examen, du contenu médical légitime (« score », « test non invasif », « testing moteur », etc.), pas des fixtures.

Sur `review_history` :
```sql
SELECT course_id, COUNT(*) FROM review_history WHERE course_id IN ('c1','c2','c99') GROUP BY course_id;
-- c1: 5 lignes (22/06/2026, titre 'Cardio,')
-- c2: 1 ligne (22/06/2026, titre vide)
-- c99: 1 ligne (22/06/2026, titre vide)
```
7 lignes au total, toutes datées de la même minute le 22 juin 2026, avec des `course_id` non-UUID typiques de fixtures de test (`c1`, `c2`, `c99` au lieu d'un UUID Notion).

**Critère de discrimination pour ces deux tables** : `course_id` qui ne ressemble pas à un UUID Notion (`c1`/`c2`/`c99` vs `256b9fc3-1e69-...`), combiné à un horodatage groupé en rafale sur quelques secondes — signature typique d'une suite de tests qui écrit dans la vraie base au lieu d'une base temporaire.

**Pourquoi c'est un problème** : volume négligeable ici (8 lignes), mais démontre que le problème de fuite test→production identifié sur `ai_usage_logs` n'est pas isolé à cette table — la cause racine (tests qui n'utilisent pas systématiquement `SYNAPSE_TEST_DB_PATH` ou une base temporaire) mérite d'être vérifiée à la source plutôt que nettoyée table par table.

**Piste** : vérifier que tous les tests passent bien par `SYNAPSE_TEST_DB_PATH` (mécanisme déjà présent dans `backend/core/reviews/local_store.py:31-33`) — ces fixtures montrent que ce n'était pas encore le cas partout au moment de leur écriture.

### [Important] Duplication massive de questions par contenu identique (67 % des lignes) — vraisemblablement volontaire mais non documentée comme telle

**Ce qui se passe** :
```sql
SELECT COUNT(*) FROM (
  SELECT question_hash FROM ai_practice_questions GROUP BY question_hash HAVING COUNT(*) > 1
);
-- 1084 groupes de doublons, totalisant 2342 lignes sur 3497 (67 %)
```
`ai_practice_questions.question_hash` (empreinte SHA-256 du contenu : type, prompt, choix, réponse, explication — `backend/core/reviews/local_store.py:2142-2153`) n'est associé à **aucune contrainte d'unicité**. Le code de création de session (`create_ai_practice_session`, ligne 2156) insère explicitement une nouvelle ligne à chaque fois, avec le commentaire « conserve chaque question comme version immuable » — c'est donc un choix de conception (rejouabilité d'un examen/annale), pas une anomalie d'écriture.

**Pourquoi c'est un problème** : ce n'est pas une perte ni une corruption de données. C'est un choix de stockage qui multiplie par ~3 le volume de la table (2 342 lignes redondantes) pour un gain de fonctionnalité (replay exact d'une session passée). Le risque réel est indirect : si une future fonctionnalité utilise `question_hash` en supposant l'unicité (dédoublonnage, comptage de questions distinctes par item), elle donnera un résultat faux sans erreur visible.

**Piste** : documenter explicitement (commentaire de schéma) que `question_hash` est un fingerprint de contenu et non une clé d'unicité, pour éviter qu'un futur développeur (ou une IA) ne s'appuie dessus à tort.

### [Important] 125 cours Notion sans item (17,7 %), dont 53 récupérables depuis le nom du PDF

**Ce qui se passe** :
```python
cours = data_cache.json['cours']  # 707 au total
empty_item = [c for c in cours if not c['item_number']]  # 125
# de ceux-ci, 53 ont une URL PDF au format ".../NNN - Titre.pdf" avec NNN un numéro exploitable
```
Exemple : « Eosinophilie », `item_number=""`, mais `url_pdf` = `.../ITEMS/218 - Éosinophilie.pdf`. Les 125 cours sans item sont aussi les 125 cours sans collège (`college=[]`) — cohérent, le collège dépend de l'item.

**Pourquoi c'est un problème** : ces cours sont exclus de tout calcul de progression par item/collège. Pour 53 d'entre eux, l'information existe déjà ailleurs dans le même enregistrement (le nom de fichier PDF) et n'a simplement pas été reportée dans le champ structuré — un problème de saisie plus qu'un vrai manque de donnée.

**Piste** : script de backfill qui extrait le numéro depuis `url_pdf`/`url_pdf_ue` pour les 53 cours récupérables ; examen manuel des 72 restants (probablement des cours transverses ou hors référentiel des 367 items).

### [Mineur] Aucun index dédié sur `ai_practice_sessions.item_number`

**Ce qui se passe** : `PRAGMA index_list(ai_practice_sessions)` ne renvoie aucun index (seule la clé primaire `id` existe). Les tables liées ont en revanche des index sur `item_number` (`idx_ai_practice_session_items_item`, `idx_ai_practice_question_items_item`, `idx_ai_practice_item` sur `ai_practice_questions`).

**Pourquoi c'est un problème** : à 599 lignes, l'impact est nul aujourd'hui (un scan complet est instantané). Si la table grossit avec l'usage continu, toute requête filtrant directement `ai_practice_sessions.item_number` sans passer par la table de liaison deviendra un scan complet.

**Piste** : ajouter l'index seulement s'il existe effectivement une requête de ce type dans le code (pas vérifié dans cet audit, hors périmètre).

### [Mineur] `error_signals` reste à 0 ligne malgré un chemin de code qui devrait l'alimenter

**Ce qui se passe** : `error_signals` a 0 ligne alors que `record_error_signals_for_attempt()` (`backend/core/practice/attempt_service.py:70`) est appelé après chaque tentative enregistrée (`ai_practice_attempts`, 37 lignes). Je n'ai pas tracé la condition exacte d'insertion (hors périmètre de cet audit en lecture de données) — l'écart peut être un vrai bug silencieux ou simplement un volume de tentatives trop faible (37) pour qu'une condition d'erreur qualifiée se déclenche.

**Pourquoi c'est un problème** : si c'est un bug, l'application prive silencieusement l'utilisateur du signal d'erreur qui alimente le profil d'erreurs mentionné comme actif dans `docs/AUDIT_LOGIQUE_ALGORITHMES_IA_2026-08-09.md` (ligne 65).

**Piste** : vérifier la condition de déclenchement de `record_error_signals_for_attempt` sur un cas connu (une tentative avec réponse fausse) plutôt que de supposer.

### [Mineur] Table `weak_points` définie deux fois dans le code (sans risque immédiat)

**Ce qui se passe** : `CREATE TABLE IF NOT EXISTS weak_points` apparaît identique à `backend/core/reviews/local_store.py:506` et `:3387` (mêmes colonnes, mêmes index). Le `IF NOT EXISTS` rend la deuxième définition inoffensive tant que le schéma ne diverge pas entre les deux copies.

**Pourquoi c'est un problème** : aucun aujourd'hui. Risque latent si une des deux copies est modifiée sans répercuter sur l'autre — la migration silencieusement ignorée (`IF NOT EXISTS`) masquerait l'divergence.

**Piste** : factoriser en un seul point de définition.

## Ce qui va bien

- **Aucune corruption** : `PRAGMA integrity_check` = `ok`, `PRAGMA foreign_key_check` = 0 violation sur l'ensemble de la base.
- **Aucun orphelin détecté** sur les jointures vérifiées : `ai_practice_attempts.question_id` (0/37), `ai_practice_session_items.session_id` (0/1233), `ai_practice_question_items.question_id` (0/2885), `course_edges` vs cache Notion actuel (0/15402), `recent_courses` vs cache Notion (0/9).
- **Aucun `item_number` numérique hors plage 1-367** trouvé nulle part (sessions, questions, cours Notion) — le seul problème est le vide ou la valeur textuelle `'DP'`, jamais un numéro erroné du type 400 ou -5.
- **`ai_practice_question_items` elle-même est toujours valide** quand elle existe (aucune valeur `item_number` hors plage ou non numérique) — le problème est sa couverture, pas sa qualité.
- **La sauvegarde existe et fonctionne** : `backup_database()` (`backend/core/reviews/local_store.py:98-136`) utilise l'API SQLite native `source.backup(target)` (copie cohérente même base ouverte), déclenchée automatiquement à l'import du module (`init_db()` à la ligne 5644), une fois par jour calendaire, rétention 7 copies. Constaté sur disque : 7 fichiers dans `data/backups/`, du 4 au 10 août (avec un gap le 6 août — voir constat séparé s'il faut le creuser, non classé ici faute d'evidence de cause).
- **Écritures sérialisées côté application** : `_LockedConnection` (`local_store.py:42-93`) enveloppe la connexion SQLite unique dans un `threading.RLock`, donc même si NiceGUI/la synchronisation de fond et l'utilisateur écrivent « en même temps », les transactions sont sérialisées en Python avant même d'atteindre SQLite — pas de scénario de corruption par écriture concurrente identifié dans le code lu. Mode `WAL` actif (`PRAGMA journal_mode=WAL`), cohérent avec les fichiers `-wal`/`-shm` observés sur disque.
- **`item_number` sur les cours Notion, quand il est renseigné, est toujours valide** (0 valeur hors 1-367 sur 582 cours) — le seul problème Notion est l'absence (125 cours), pas l'invalidité.

## Évolution depuis les audits d'août

- **Sauvegarde absente (audit du 2 août, `docs/AUDIT_2026-08-03.md:175`, marquée encore ouverte le 3 août)** → **résolue**. Le même document, plus loin (ligne 742-743), confirme l'implémentation : « `init_db()` crée une copie quotidienne dans `data/backups/`... conserve les 7 dernières copies ». Cet audit confirme indépendamment, sur la base réelle actuelle, que le mécanisme tourne bien (7 fichiers datés du 4 au 10 août présents sur disque).
- **« 150 sessions sur 151 ont un `item_number` » (3 août, ligne 30)** → la situation s'est dégradée en proportion depuis : sur les 599 sessions actuelles, 580 ont un `item_number` non vide (96,8 %) contre 99,3 % le 3 août — 19 sessions vides et 1 valeur `'DP'` se sont accumulées depuis (nouvelles sessions créées sans item, pas une régression sur les anciennes).
- **« Doublons de sessions : 4 groupes (titre, kind, nb_questions) en double » (3 août, ligne 187)** → toujours 4 groupes détectés aujourd'hui avec le même critère, mais ce ne sont vraisemblablement pas les mêmes lignes (599 sessions aujourd'hui contre 151 le 3 août) : c'est un phénomène récurrent (rejeu d'annales), pas un doublon historique jamais nettoyé.
- **« Table `ai_practice_questions` : 1 141 dont 1 104 sans item — banque orpheline à 97 % » (3 août, ligne 43)** → nettement amélioré en proportion : 3 497 questions aujourd'hui, 307 sans item valide (8,8 %), mais le problème s'est déplacé vers la table de classification (`ai_practice_question_items`), qui elle-même diverge sur 55 % des questions qui ont un item (voir constat dédié).
- **Contamination test→production** (déjà établie ailleurs sur `ai_usage_logs` à 45 % et sur des fixtures dans `ai_practice_questions`) : confirmée et élargie ici avec un critère quantifié (51 % sur `ai_usage_logs`, 1 fixture confirmée sur `ai_practice_questions`, 7 lignes sur `review_history`).
- Les audits `docs/AUDIT_TECHNIQUE_PERFORMANCE_2026-08-02.md` et `docs/AUDIT_LOGIQUE_ALGORITHMES_IA_2026-08-09.md` n'ont pas été audités en détail dans cet axe (portée performance/algorithmes hors du périmètre intégrité des données), sauf pour confirmer que `error_signals` est un signal censé être actif (ligne 65 du second document) alors que la table est vide — voir constat mineur dédié.

---

# 4. Axe interface et parcours


> Rédaction au fil de l'eau, section par section (contrainte de session : ne pas perdre le travail
> en cas d'interruption).

## Synthèse

Deux bugs critiques confirmés par lecture directe du code, pas par supposition : « Créer une lacune »
plante systématiquement (imports `ui`/`local_store` manquants dans `weak_points.py`) depuis la
palette de commandes **et** depuis le bouton dédié de `/lacunes` — la fonctionnalité est
indisponible dans toute l'app. La bascule vers le lecteur React est déjà presque totale (3 des 5
points d'entrée l'essaient en premier), mais les deux qui n'essaient jamais React sont justement ceux
où l'énoncé partagé d'un dossier progressif compte le plus (mode concours continu, Tuteur DP/item).

La dette de contraste posée hier n'est pas cantonnée au panneau télémétrie déjà corrigé : 131
occurrences de `color:var(--success/danger/warning/text-dim)` dans 30 fichiers, dont 14 dans la fiche
item (l'écran le plus consulté) et 14 dans la vue Collèges — sur le code couleur de maîtrise
lui-même. Le motif de correctif posé ce matin (`--success-text`/`--danger-text`) est directement
réutilisable pour fermer l'essentiel de cette dette sans redesign.

9 constats au total (2 critiques, 4 importants, 3 mineurs). Le code mort réel se limite à trois petits
composants jamais branchés et ~600 lignes orphelines dans `stats.py` — la « Phase 5 » et les façades
F3/F4 signalées dans les audits précédents sont, côté frontend, déjà résolues.

## Comparaison des deux lecteurs de QCM

### Qui mène où — vérifié dans le code, pas supposé

Le brief suppose une coupure nette « Annales/QCM → React, sessions IA de l'item → NiceGUI ». La
réalité est plus fine : **React est bien préféré partout où un point d'entrée l'essaie**, mais deux
flux n'essaient même pas React et vont directement au lecteur NiceGUI.

| Point d'entrée | Fichier | Mécanisme | Lecteur réellement utilisé |
|---|---|---|---|
| Cockpit QCM (`/qcm`), reprendre/corriger | `frontend/pages/qcm_cockpit.py:456-472` | `open_node_qcm()` essayé d'abord, repli NiceGUI seulement si `qcm_app/dist/index.html` absent | **React** (dist présent en l'état du dépôt) |
| Annale — sous-partie isolée | `frontend/pages/annale_detail.py:339-355` | idem : `open_node_qcm()` puis repli | **React** |
| Annale — **Mode concours continu** (chaîne les sous-parties d'un partiel) | `frontend/pages/annale_detail.py:263-272` | `open_qcm_session(...)` appelé **directement**, aucun essai `open_node_qcm()` | **NiceGUI, toujours** |
| Fiche item — « Nouvelle session IA » et **Tuteur DP** | `frontend/components/ai_practice_panel.py:134-158` (docstring : « the resumable, step-based stored-session reader ») | `open_qcm_session`/`open_qcm_correction` appelés directement, aucun essai React | **NiceGUI, toujours** |
| Simulateur d'épreuve (`/exam`), cartes de session génériques | `frontend/pages/exam_simulator_page.py:171`, `frontend/components/practice_session_card.py:15-21` | `ui.navigate.to("/qcm-app/?session=…")` direct | **React** |

Donc la ligne de partage réelle n'est pas « Annales vs Item », c'est **« session simple vs session
enchaînée »** : toute ouverture d'une session isolée passe par React (si le build existe, ce qui est
le cas) ; toute séquence pilotée par NiceGUI lui-même (le mode concours continu qui enchaîne les
dossiers d'un partiel, et le Tuteur DP/génération à la volée depuis l'item) reste sur le lecteur
NiceGUI sans jamais tenter React.

### Tableau de capacités

| Capacité | Lecteur NiceGUI (`frontend/components/qcm_replay.py`) | Lecteur React (`qcm_app/src/main.tsx`) | Verdict pour la bascule |
|---|---|---|---|
| Reprise d'une session partiellement répondue | Restaure les réponses déjà saisies (`answers = latest_response_by_question(questions)`, ligne 451) mais l'index de départ est toujours `{"index": 0}` (ligne 457) — il faut recliquer « Suivant » jusqu'à la question non répondue | Même mécanique : `answers` restaurées depuis `GET /api/qcm/sessions/{id}` (`backend/api/qcm.py:85-95`, dernière réponse non vide par question) mais `useState(0)` (main.tsx:112) — même limite | **Équivalent, aucun frein à la bascule.** Les deux réhydratent les réponses mais aucun ne rouvre à la bonne position ; ce n'est pas un écart entre lecteurs, c'est un défaut partagé (voir Constats). |
| Affichage de l'énoncé commun d'un dossier progressif (`dp_context`) pendant la réponse | **Absent.** `open_qcm_session._render()` (ligne 504-533) n'affiche que `question["prompt"]` — jamais `dp_context`, jamais d'image | **Présent.** `QuestionVisualContext` (main.tsx:86-109) affiche systématiquement le contexte clinique du dossier (`exam.dp_context` + `question.dp_context` dédupliqués) et les images UNESS, dans le lecteur *et* la correction | **Bloquant pour NiceGUI si la bascule est repoussée** — c'est justement le lecteur sans React qui pilote le seul flux vraiment multi-questions-un-dossier (mode concours continu, voir ci-dessus). |
| Images médicales (support visuel) | Uniquement en correction (`qcm_replay.py:392-398`, `ui.image()` statique) — jamais pendant la réponse | Pendant réponse *et* correction, via `MedicalImageViewer` avec zoom (50-300 %), luminosité, contraste (`qcm_app/src/components/MedicalImageViewer.tsx:16-26`) | React nettement supérieur |
| Barème EDN propositionnel détaillé (rang, points, discordance) en correction | Oui (`qcm_replay.py:348-364`) | Oui (`main.tsx:286-297`) | Équivalent |
| Divergence UNESS signalée | Oui (`qcm_replay.py:365-376`) | Oui (`main.tsx:276,282`) | Équivalent |
| Ancrage d'une question (« Ancrer ») | Disponible sur **chaque question, à la demande**, pendant la réponse (`qcm_replay.py:512-518`, bouton toujours visible) | Disponible **uniquement en correction**, et seulement si `follow_up.eligible` (plusieurs échecs consécutifs sur la même question) — pas un choix libre de l'utilisateur | NiceGUI seul permet l'ancrage manuel volontaire ; capacité à porter si la bascule a lieu |
| Nudge automatique « plusieurs échecs → créer une lacune / ancrer / ignorer » | **Absent.** `_finish()` (`qcm_replay.py:551-566`) appelle `finalize_ai_practice_session` et `record_ai_practice_mastery` directement, en contournant l'API — `_follow_up()` (`backend/api/qcm.py:60-76`) n'est calculé que dans `POST /complete`, jamais atteint par ce chemin | Présent (`Correction.followUpCard`, `main.tsx:246`) | React seul ; **les sessions NiceGUI (item, Tuteur DP, concours continu) ne déclenchent jamais ce filet** |
| Mode Examen Blanc (chrono, anti-retour) | Absent du lecteur NiceGUI en tant que tel | Oui : bandeau chrono, bouton « Précédente » masqué, libellé « Anti-Retour Actif » (`main.tsx:178-196,231-233`) | React seul |
| QROC / réponse ouverte | Oui, `ui.textarea` (`qcm_replay.py:519-522`) | Oui, `textarea` avec détection élargie (`support_visuel_seul`, `type_question === 'QROC'`) (`main.tsx:139`) | Équivalent, détection légèrement plus riche côté React |
| Validation « toutes les questions répondues avant finalisation » | Oui, bloquant côté client (`qcm_replay.py:554-556`) | Oui, bloquant côté serveur (HTTP 409 sur positions manquantes, `backend/api/qcm.py:198-205`) — plus robuste car pas contournable par un second onglet | React (le serveur, donc les deux lecteurs en bénéficient, mais seul le flux React le déclenche vraiment puisque NiceGUI finalise sans passer par l'API) |

### Verdict pour la décision d'unification

React est déjà la cible de fait pour toute session ouverte isolément et il a un avantage net et
mesurable (contexte de dossier, images interactives, mode examen, filet anti-échec). Les deux trous
qui empêchent une bascule complète aujourd'hui sont précis et localisés, pas diffus :

1. `annale_detail.py:263-272` (mode concours continu) — n'essaie jamais React.
2. `ai_practice_panel.py:134-158` (sessions IA de l'item, Tuteur DP) — n'essaie jamais React, alors
   que le docstring le désigne lui-même comme « the resumable, step-based stored-session reader »,
   présenté comme une fonctionnalité delibérée et non un oubli.

Basculer ces deux points d'entrée sur `open_node_qcm()` (avec repli NiceGUI existant conservé)
suffit à unifier l'ouverture de session sans toucher au reste de l'architecture — mais uniquement
après avoir vérifié que React sait recevoir un enchaînement de sous-parties piloté côté serveur
(le mode concours continu a une logique de progression — `advance_exam_session` — que le lecteur
React n'a jamais eu à consommer) et que l'ancrage manuel volontaire (capacité NiceGUI-only) est soit
porté, soit assumé comme perdu.

## Constats

### 1 [Critique] « Créer une lacune » plante systématiquement — `frontend/pages/weak_points.py`

**Ce qui se passe** : `open_add_dialog()` (`frontend/pages/weak_points.py:9-56`) construit un dialogue
avec `ui.dialog()`, `ui.card()`, `ui.select()`, `ui.input()`, `ui.button()`… et appelle
`local_store.add_weak_point_full(...)` à la sauvegarde — mais le fichier n'importe **ni** `ui`
(`from nicegui import ui`) **ni** `local_store` (`from backend.core.reviews import local_store`) :
seuls `from loguru import logger` et `from frontend.theme import frame` sont présents en tête de
fichier (lignes 4-5), plus un import local de `data_store` (ligne 11). La fonction est bien appelée
en production, deux fois : `frontend/components/command_palette.py:240-241` (action de la palette
`Ctrl Alt P`) et `frontend/pages/weak_points_cockpit.py:183` (bouton « + » de l'écran Points faibles).

**Pourquoi c'est un problème** : au premier clic sur l'action « Créer une lacune » — que ce soit
depuis la palette de commandes ou depuis le bouton dédié de `/lacunes` — Python lève
`NameError: name 'ui' is not defined` dès la ligne `with ui.dialog() as dlg`. Aucune des deux entrées
ne peut donc jamais ouvrir le dialogue ; la création manuelle d'une lacune est indisponible dans
toute l'application, sans message d'erreur utilisateur explicite (juste rien ne s'ouvre, ou une trace
serveur).

**Piste** : ajouter les deux imports manquants en tête de `weak_points.py`. Vérifier ensuite s'il
existe un test qui instancie et invoque réellement `open_add_dialog()` dans un contexte NiceGUI (pas
seulement son import) — l'absence d'un tel test explique que la régression ait survécu à la purge
cockpit qui a réduit ce fichier à une coquille de redirection.

### 2 [Critique] Deux lecteurs QCM sans chemin d'essai commun sur les flux enchaînés — voir tableau ci-dessus

**Ce qui se passe** : `frontend/pages/annale_detail.py:263-272` (mode concours continu) et
`frontend/components/ai_practice_panel.py:134-158` (sessions IA de l'item, dont le Tuteur DP)
appellent `open_qcm_session`/`open_qcm_correction` **directement**, sans jamais tenter
`open_node_qcm()` comme le font les trois autres points d'entrée. Le lecteur NiceGUI ainsi forcé
n'affiche jamais le contexte clinique partagé d'un dossier (`dp_context`, absent de
`qcm_replay.py:504-533`) ni d'image pendant la phase de réponse, et ne déclenche jamais le filet
`follow_up` (§ tableau) parce qu'il finalise en appelant directement `local_store` au lieu de passer
par `POST /api/qcm/sessions/{id}/complete`.

**Pourquoi c'est un problème** : c'est exactement dans ces deux flux que l'énoncé partagé d'un
dossier progressif compte le plus — un concours continu enchaîne justement plusieurs sous-parties
d'un même dossier. L'utilisateur y perd le contexte clinique qui donne son sens aux questions
suivantes, sans que rien ne l'indique (aucun message « contexte non disponible ici », juste absence
silencieuse).

**Piste** : c'est un des deux verrous identifiés qui bloquent une bascule complète vers React (voir
verdict de la section précédente) — les traiter ensemble avant toute décision d'unification.

### 3 [Important] `--text-dim` en texte 10-12,5 px sur la page la plus visitée — `frontend/pages/course_detail_cockpit.py`

**Ce qui se passe** : les 14 occurrences de `color:var(--text-dim)` du fichier (lignes 93, 95, 107,
142, 156, 157, 162, 163, 186, 193, 198, 202, 208, 210) sont **toutes** posées sur du texte entre 10 et
12,5 px : fil d'Ariane (`.ci-crumb`), libellés de métadonnées, sous-titres de carte, dates/durées
d'historique, états vides. `--text-dim` vaut `#a0a0ab` en thème clair (`design_tokens.py:29`) — sur
fond `--bg`/`--surface` quasi blancs, le ratio de contraste calculé (formule WCAG, mêmes bases que la
mesure 2,57 déjà établie pour `--success` dans `RECETTE_LOT1_2026-08-10.md`) tombe autour de **2,6:1**,
très en dessous du seuil AA de 4,5:1 pour du texte de cette taille.

**Pourquoi c'est un problème** : c'est la fiche item, l'écran le plus consulté de l'application selon
les parcours principaux (réviser un item y ramène systématiquement). Le fil d'Ariane, les dates
d'historique et les sous-titres de carte y sont concrètement difficiles à lire en thème clair — pas
un cas isolé comme le panneau télémétrie corrigé ce matin, mais la texture par défaut de toute
métadonnée secondaire de la page.

**Piste** : le motif `--success-text`/`--danger-text` posé ce matin (variantes lisibles par thème,
inchangées en sombre) est directement transposable à `--text-dim` — une variable `--text-dim-text`
ou un simple resserrement de la valeur claire de `--text-dim` réglerait cette occurrence et, par
répétition du même motif CSS, la plupart des occurrences listées au constat suivant.

### 4 [Important] Le même défaut est réellement généralisé, pas cantonné à Réglages

**Ce qui se passe** : recensement de `color:var(--success)` / `color:var(--danger)` / `color:var(--warning)`
/ `color:var(--text-dim)` (recherche `color:` explicite, hors `background`/`border`) : **131
occurrences dans 30 fichiers** de `frontend/`. Le suivi du lot 1 (`RECETTE_LOT1_2026-08-10.md`,
« Observations relevées en passant ») avait déjà repéré `.se-label`, `.se-diag-ratio.full` et
« plusieurs libellés de statut » de `settings_cockpit.py` — confirmé : **13 occurrences** restent
dans ce fichier après la conversion du panneau télémétrie de ce matin, dont `.se-label`
(`settings_cockpit.py:78`, 10 px, `--text-dim`) et huit `status.style("color:var(--danger|success|warning)")`
inline sur les lignes de statut de connexion (303-464). Au-delà de Réglages, les plus concentrés sont
`course_detail_cockpit.py` (14, détail ci-dessus) et `colleges_cockpit.py` (14, dont
`.cg-item-status.solide/fragile/critique` — lignes 142-149 — qui sont précisément le code couleur de
maîtrise par item dans la vue Collèges).

**Pourquoi c'est un problème** : `colleges_cockpit.py:145-148` est le signal visuel central de la vue
Collèges — solide/fragile/critique/en retard — rendu en texte coloré à faible contraste en thème
clair. C'est l'inverse de l'intention : la couleur est censée porter l'information la plus urgente à
lire, pas la plus difficile.

**Piste** : même motif que le constat 3 — étendre `--success-text`/`--danger-text`
(et l'équivalent `--warning-text` restant à créer, `--warning` n'ayant reçu aucune variante lisible ce
matin) aux fichiers listés, en commençant par `colleges_cockpit.py` et `settings_cockpit.py` qui
concentrent le plus d'occurrences hors panneau déjà corrigé.

### 5 [Mineur] `--warning` est le pire des trois tokens sémantiques et n'a reçu aucune variante lisible

**Ce qui se passe** : `--warning: #e5a23f` (`design_tokens.py:39`) n'a pas d'équivalent
`--warning-text` contrairement à `--success`/`--danger`. Estimation par la même formule de contraste
WCAG que celle qui a mesuré 2,57 pour `--success` : `--warning` sur fond blanc tombe autour de
**2,2:1**, le plus bas des trois. Il est utilisé comme couleur de texte à plusieurs endroits déjà
cités (`colleges_cockpit.py:142,146,149`, `settings_cockpit.py:125,328`, badge « fragile » et statuts
partiels).

**Pourquoi c'est un problème** : c'est le token le moins lisible des trois, et le seul des trois à
n'avoir reçu aucun correctif ce matin — l'écart avec `--success`/`--danger` va se creuser si le motif
`--success-text`/`--danger-text` est étendu sans y penser.

**Piste** : ajouter `--warning-text` en même temps que l'extension du motif existant, plutôt qu'après
coup.

### 6 [Important] Résidus Tailwind figés : 547 occurrences de la palette `slate` dans 38 fichiers

**Ce qui se passe** : recherche de `text-slate-*`/`bg-slate-*`/`border-slate-*` (avec variantes
`dark:`) dans `frontend/` : **547 occurrences** dans **38 fichiers**. Les plus concentrées :
`course_quick_actions.py` (63 — le fichier de 1303 lignes réutilisé par 12 autres modules, donc la
plus grande surface d'exposition réelle), `stats.py` (55 — mais très majoritairement dans le code mort
identifié à l'inventaire ci-dessous, donc sans effet visuel actuel), `course_detail_cockpit.py` (41),
`dashboard/_hero.py` (36) et `dashboard/_dialogs.py` (36 — le wizard de validation de séance retravaillé
en chantier B2, qui a converti les couleurs *décoratives* des puces mais pas tout le texte informatif
autour).

**Pourquoi c'est un problème** : ces classes ignorent le thème sombre/clair et le système de tokens —
elles ne sont pas seulement un défaut esthétique isolé, elles empêchent une correction de contraste
centralisée (changer `design_tokens.py` ne les corrige jamais, contrairement aux `var(--*)`) et
perpétuent une palette parallèle à chaque nouvel écran qui copie un fichier existant.

**Piste** : traiter par ordre de surface d'exposition réelle (nombre d'appelants), pas par nombre brut
d'occurrences — `course_quick_actions.py` avant `stats.py`, dont l'essentiel du volume ne se voit
jamais.

### 7 [Mineur] Route `/exam` orpheline, doublon d'un chemin déjà accessible depuis Annales

**Ce qui se passe** : `main.py:310-314` enregistre `/exam` → `render_exam_simulator_page()` sous
`frame('Examens Blancs')` (l'ancien habillage, pas la coquille cockpit). Recherche exhaustive : aucun
lien, bouton ou `ui.navigate.to("/exam")` nulle part dans `frontend/` ne pointe vers cette route — la
seule façon d'y accéder est de taper l'URL. La même fonction `render_exam_simulator_page()` est en
réalité déjà accessible et utilisée depuis `/annales`, via l'onglet interne « ⏱️ Examens Blancs »
(`frontend/pages/annales.py:540-542,604-611`), rendue inline dans la coquille cockpit de la page.

**Pourquoi c'est un problème** : mineur en usage (la fonctionnalité reste disponible par l'autre
chemin) mais c'est une route fantôme avec un habillage visuel différent (non-cockpit) de celui
réellement utilisé — un signet ou un lien direct vers `/exam` donnerait une expérience visuellement
incohérente avec le reste de l'app.

**Piste** : supprimer la route `/exam` de `main.py` ou la faire rediriger vers `/annales` avec l'onglet
examens pré-sélectionné, plutôt que de maintenir un second habillage.

### 8 [Important] Mode concours continu : aucun score global affiché à la fin de l'épreuve

**Ce qui se passe** : `_show_continuous_result()` (`frontend/pages/annale_detail.py:242-261`) affiche,
en fin de chaînage des sous-parties d'un partiel, uniquement le texte « Les N sous-parties ont été
enregistrées sans correction intermédiaire » suivi d'un bouton « Voir la correction » **par
sous-partie**. Aucun total n'est calculé ni affiché : `start_exam_session`/`advance_exam_session`
(`backend/core/uness/exam_session.py:88-140`) ne construisent qu'un état de progression (index de
sous-partie courant), pas d'agrégat de score — il n'existe nulle part un total à afficher, pas
seulement un oubli de rendu.

**Pourquoi c'est un problème** : l'utilisateur vient de terminer ce qui se présente comme une épreuve
unique (« Mode concours continu », habillage chrono/anti-retour hérité du mode examen), mais doit
ouvrir chaque sous-partie séparément et additionner les scores lui-même pour connaître sa note
globale au partiel — l'action (terminer l'épreuve) n'a pas de résultat visible à son échelle propre.

**Piste** : soit agréger les scores des sous-parties au moment de `_show_continuous_result()` (les
scores unitaires existent déjà par session), soit renommer clairement l'écran de fin pour ne pas
laisser croire à une note unique tant que l'agrégation n'existe pas.

### 9 [Mineur] Fonctions de rendu de plusieurs centaines de lignes : la vraie ligne de fracture est la fonction, pas seulement le fichier

**Ce qui se passe** : au-delà de la taille de fichier déjà connue
(`course_detail_cockpit.py` 1342 lignes, `annales.py` 711 lignes), plusieurs écrans concentrent tout
leur rendu dans une seule fonction plutôt que de le répartir :

| Fichier | Fonction | Étendue | Part du fichier |
|---|---|---|---|
| `planning_cockpit.py` | `render_planning_cockpit` (ligne 211) | 211-743, ~530 lignes | 71 % des 743 lignes |
| `course_detail_cockpit.py` | `render_item_cockpit` (ligne 286) | 286-601, ~315 lignes | assemble données, CSS et en-tête avant de déléguer aux `_tab_*` déjà séparés (604 et suivants) |
| `colleges_cockpit.py` | `render_colleges_cockpit` (ligne 308) | 308-722, ~414 lignes | 57 % des 722 lignes |
| `qcm_cockpit.py` | `render_qcm_cockpit` (ligne 340) | 340-686, ~346 lignes | 50 % des 686 lignes |
| `annales.py` | `_open_import_dialog` (ligne 171) | 171-511, ~340 lignes | 48 % des 711 lignes, à elle seule plus grosse que `annales_page()` (512-711, ~200 lignes) qui l'appelle |
| `course_quick_actions.py` | `open_pdf_wizard` (601), `open_start_tracking_dialog` (863), `CourseQuickActions` (1039) | trois fonctions de 175 à 265 lignes dans un seul fichier de 1303 lignes, réutilisé par 12 appelants | — |

**Pourquoi c'est un problème** : `course_detail_cockpit.py` a déjà le bon réflexe (les onglets
`_tab_overview`/`_tab_note`/`_tab_qcm`/etc. sont séparés) — c'est la fonction d'orchestration
elle-même (`render_item_cockpit`) qui est restée monolithique. Les autres fichiers n'ont même pas
cette première séparation : une seule fonction porte le chargement des données, le CSS, la mise en
page et les interactions.

**Piste** : la ligne de fracture la plus rentable n'est pas « diviser le fichier », c'est « extraire
les grandes fonctions de rendu/dialogue en leurs propres modules », sur le modèle déjà appliqué au
paquet `frontend/pages/dashboard/` (`_hero.py`, `_agenda.py`, `_reviews.py`…) — un précédent interne
déjà éprouvé, pas une nouvelle convention à inventer.

## Inventaire du code non atteint

| Fichier | Taille | Atteint par une route ? | Verdict |
|---|---|---|---|
| `frontend/components/fiche_viewer.py` | 234 lignes | Aucun appelant dans `frontend/` ni `tests/` (`render_fiche_viewer` : 0 référence hors du fichier) | **Mort, mais valable.** Composant complet (PDF en iframe + sidebar pièges/lacunes), remplacé de fait par un simple lien `↗ PDF` ouvert en nouvel onglet (`course_detail_cockpit.py:477,507,1316` et 7 autres appelants de `/pdf/{id}`). Écrit, fonctionnel a priori, jamais branché — décision à prendre, pas suppression automatique. |
| `frontend/components/metric_card.py` | 13 lignes | Aucun appelant (`MetricCard` : 0 référence hors du fichier) | **Jamais terminé.** Une `@dataclass` (label/value/helper/tone) sans aucun composant de rendu ni consommateur — scaffold abandonné avant même un premier usage. |
| `frontend/components/pomodoro.py` | 65 lignes | Aucun appelant direct ; seule trace une mention obsolète dans le docstring de `dashboard/__init__.py:9` (« Focus Timer (1/3): Pomodoro compact ») | **Superseded, pas mort par accident.** `PomodoroController` a été remplacé par `frontend/components/focus_mode_cockpit.py` (branché en dialogue depuis `dashboard/_reviews.py:19-27`, qui délègue explicitement « à focus_mode_cockpit »). Le docstring du package dashboard n'a pas suivi le changement. |
| `frontend/pages/health.py` | 240 lignes | Route `/health` enregistrée (`main.py`) mais **zéro lien ou navigation** vers elle nulle part dans `frontend/` ; absente de `cockpit_shell.py::_NAV_GROUPS` | **Mort comme route, dupliqué comme logique.** `settings_cockpit.py:14-26` réimplémente les mêmes vérifications (`_check_obsidian`/`_check_google_calendar`) en synchrone plutôt que d'importer ce fichier, par un choix assumé et documenté dans son propre docstring — pas un oubli, mais la route `/health` elle-même n'a plus de porte d'entrée. |
| `frontend/pages/stats.py` | 785 lignes | Route `/stats` → `stats_page()` (ligne 780) délègue **inconditionnellement** à `render_stats_cockpit()` (ligne 783-784), sans branche de repli | **Majoritairement mort.** Sur ~750 lignes de logique, 6 fonctions seulement sont réutilisées par `stats_cockpit.py:30-33` (`_get`, `_fmt_minutes`, `_fmt_activities`, `_day_label`, `_get_all_mastery_snapshots`, `_compute_kpis`, lignes 30-188). Le reste — `_render_mastery_distribution` (107), `_render_kpi_row` (189), `_get_fragile_courses` (273), `_render_fragile_banner` (322), `_render_fragile_card` (368), `_render_timeline` (439), `_render_session_row` (494), `_render_weak_row` (548), `_render_semaine_tab` (597-776) — environ **600 lignes** ne sont atteintes par aucun chemin de production. |
| Ex-Phase 5 (`render_flash_zero_dialog`, `render_sprint_countdown_widget`, `GapDPGeneratorService` jamais appelée) | — | — | **Déjà résolu, historique seulement.** `sprint_countdown_widget.py` et le dialogue Flash-Zero Streamlit ont été supprimés (chantiers A et C3, voir `docs/UI_REFONTE_ETAT_DES_LIEUX.md`) ; `GapDPGeneratorService` (`backend/core/ai_qcm/gap_dp_generator.py`) est maintenant appelée depuis `ai_practice_panel.py`, `course_detail_cockpit.py:928-964` (Tuteur DP) et `qcm_cockpit.py`. Ne pas rouvrir ce chantier. |
| `frontend/pages/{colleges,semestres,course_detail,todo,qcm,planning,externat,settings}.py` | 11-108 lignes chacun | Toutes routées par `main.py`, délèguent immédiatement à leur `*_cockpit.py` | **Vivant, motif voulu.** Ce ne sont pas des doublons résiduels : chaque fichier est le point d'entrée réel de sa route et délègue tout le rendu au cockpit correspondant, sans code mort derrière (contrairement à `stats.py`, seule exception du lot). |
| `frontend/pages/exam_simulator_page.py` | 320 lignes | Route `/exam` orpheline (constat 7) **et** appelée inline depuis `annales.py:604-611` | **En pause côté route, vivant côté fonction.** La fonction est utilisée réellement ; c'est l'entrée `/exam` de `main.py` qui est un doublon mort. |

## Ce qui va bien

- Le motif « page mince déléguant à un `*_cockpit.py` » est appliqué de façon cohérente sur 8 des 9
  paires observées — `stats.py` est la seule anomalie, pas la norme.
- Trois éléments de dette signalés dans l'audit du 3 août (Flash-Zero et Sprint Countdown Streamlit
  jamais appelés, Tuteur DP orphelin) sont effectivement résolus dans le code actuel, pas seulement
  dans la documentation — vérifié directement par recherche d'appelants, pas par lecture des notes de
  chantier.
- Le motif de correction `--success-text`/`--danger-text` posé ce matin sur le panneau télémétrie
  (thème clair lisible, thème sombre inchangé) est directement réutilisable pour fermer les constats
  3, 4 et 5 sans redesign — c'est un gabarit prêt à l'emploi, pas un nouveau problème de conception.
- La navigation principale (`cockpit_shell.py::_NAV_GROUPS`) ne contient aucune entrée vers une page
  cassée : les deux seules routes orphelines trouvées (`/exam`, `/health`) sont des doublons de
  fonctionnalités par ailleurs correctement exposées, pas des impasses pour l'utilisateur.

---

## Addendum du 10 août — nuance sur le constat « collège Notion vs référentiel UNESS »

Le constat Critique de l'axe intégrité des données (« 51 % des cours classés contredisent le
référentiel ») a été revérifié indépendamment. **Le chiffre est exact** — 289 cours divergents sur
564 ayant à la fois un item et un collège — **mais sa qualification comme erreur ne l'est pas.**

Les couples divergents les plus fréquents :

| Cours | Collège Notion | Collège référentiel |
|---:|---|---|
| 17 | Pédiatrie | Infectiologie |
| 11 | Anesthésie-Réanimation | Médecine Intensive - Réanimation |
| 11 | Gynécologie médicale | Gynécologie-Obstétrique |
| 7 | Pédiatrie | Hépato-Gastro-entérologie |
| 6 | Pédiatrie | Hématologie |
| 6 | Médecine Interne | Hématologie |

Au moins trois phénomènes distincts sont confondus sous ce chiffre :

1. **Variantes de libellé** — « Gynécologie médicale » et « Gynécologie-Obstétrique » désignent le
   même collège ; « Anesthésie-Réanimation » et « Médecine Intensive - Réanimation » sont adjacents.
   La comparaison se fait par inclusion de chaîne, ce qui les compte à tort comme divergences.
2. **Items légitimement multi-collèges** — une pathologie infectieuse de l'enfant est couverte par le
   Collège de Pédiatrie *et* par celui d'Infectiologie. Le référentiel n'en retient qu'un ; le choix
   inverse dans Notion n'est pas une erreur.
3. **De vraies erreurs de classement** — par exemple Hypercalcémie (item 268) rangée en
   Endocrinologie alors que le référentiel dit Néphrologie.

**Conséquence sur la piste proposée.** Réécrire les 289 cours sur le référentiel serait nuisible :
cela reclasserait de force des cours de pédiatrie dans des collèges d'organes, en contradiction avec
l'organisation réelle des ouvrages et des révisions.

Le vrai sujet n'est pas un nettoyage de données mais une question de conception : **le modèle suppose
un collège unique par item alors que la réalité en admet parfois deux**, et la comparaison utilisée
pour détecter les divergences est trop naïve pour distinguer un synonyme d'un désaccord.

Ce point est donc retiré de la vague 2 et remis à l'état de question ouverte, à instruire avant toute
correction. Le principe « le référentiel UNESS fait autorité » reste valable pour arbitrer un
désaccord réel ; il ne dit rien du cas où un item relève de deux collèges.
