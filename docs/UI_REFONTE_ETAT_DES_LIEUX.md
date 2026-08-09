# Refonte UI Synapse — demandes, audit, feuille de route, état des lieux

> Document vivant. Mis à jour à chaque avancée pour pouvoir reprendre le travail
> sans relire toute la conversation en cas d'interruption. Ne pas confondre avec
> `docs/AUDIT_2026-08-07.md` (audit backend/algorithmes, chantier séparé).

**Dernière mise à jour** : 2026-08-09, **D terminé — feuille de route A→D entièrement close**. 1194
tests passés.

## ▶ REPRISE — lire ceci en premier

**État** : Chantiers A, B1, B2, B3, B4, C1-C5, D tous **terminés** et commités sur `main` (branche
par défaut, travail fait directement dessus avec consentement explicite de l'utilisateur). Suite de
tests : 1081 → 1194, aucune régression à aucune étape. La feuille de route des 4 chantiers (section 2)
est intégralement close.

Chantier C (fond pédagogique) **entièrement terminé** : **C1** (`6f16198`), **C2** (`1f3beb8`,
`d658b9f`), **C3** (`6abdccc`, `66d22d4`), **C4** (`05c5f50`, `980f599`, `6b13924`, `e82ecc4`,
`2b4bae5`), **C5** (`1c71ee9`, `9fe84bb`), tous commités.

**Important — action manuelle restante pour C5** : les deux scripts sont écrits, testés et commités,
mais **pas encore exécutés contre le vrai Notion/vault** (écriture sur données live, volontairement
laissée hors du plan automatisé — voir spec). Pour terminer la correction réelle, lancer dans
l'ordre :
```
python scripts/reconcile_item_numbers.py            # dry-run, relire data/item_number_reconcile_report.json
python scripts/reconcile_item_numbers.py --apply
python scripts/heal_obsidian_item_frontmatter.py         # dry-run, relire data/obsidian_item_heal_report.json
python scripts/heal_obsidian_item_frontmatter.py --apply
```

Chantier D (calendriers Google configurables) **entièrement terminé** : `662096d`, `0398e4c`,
`c49d1c1`, `89d3bf5`, tous commités (détail section 6). Aucune action manuelle restante — la
fonctionnalité est utilisable immédiatement depuis Paramètres.

**Prochaine étape** : plus de chantier ouvert sur cette feuille de route. Reste en attente : les deux
scripts C5 ci-dessus (exécution manuelle contre Notion/vault) si pas encore lancés.

**Conventions établies dans cette série de chantiers**, à reproduire :
- Un fichier spec (`docs/superpowers/specs/YYYY-MM-DD-<nom>-design.md`) et un fichier plan
  (`docs/superpowers/plans/YYYY-MM-DD-<nom>.md`) par sous-chantier, jamais commités (restent en
  `??` dans `git status` — c'est voulu, ce sont des artefacts de travail).
- Toujours vérifier les numéros de ligne contre le fichier réel juste avant d'écrire le plan (le
  code bouge d'un chantier à l'autre).
- Toujours faire tourner la suite complète (`./.venv/Scripts/python.exe -m pytest -q`) avant la
  première tâche (ligne de base) et après la dernière tâche, pas seulement les tests ciblés — à
  chaque chantier, au moins un test préexistant encodant l'ancien comportement volontairement
  changé n'a été détecté qu'à cette étape finale.
- Mettre à jour ce fichier à chaque étape (design validé, spec écrite, plan écrit, tâche commitée),
  pas seulement à la fin — c'est ce qui permet la reprise sans relire toute la conversation.

---

## 1. Demandes originales de l'utilisateur (7 août 2026)

Revue d'usage complète de Synapse (27 captures dans `ScreenTest/`), retranscrite telle quelle :

- Sprint EDN : logique incomprise.
- Flash-Zero : croix invisible au survol (cachée sous le bouton) ; pas de saut de ligne entre
  « Ta réponse » et « Réponse attendue » ; UI des questions pas au niveau de QCM/Annale (rectangle
  au survol, etc.) ; impression que ce sont les mêmes questions d'un jour à l'autre.
- Wizard de validation de séance : pas centrée, pas dans l'esprit Linear/Synapse.
- Sidebar : raccourci affiché en notation Mac (`⌘K`), à corriger/uniformiser.
- Vue Planning : les entités (item, Flash-Zero…) ne s'ouvrent pas au clic ; pas de vue semaine
  réelle (cours fac + cours Synapse), seulement plannif du jour/passé.
- Vue Collège : animation de déploiement des cours « trop brute ».
- Vue Semestres : peut être supprimée.
- Vue générale Items : `Ctrl+Alt+P` marche mais wizard pas beau ; tri par item/collège cassé ;
  espace mort à droite sur grand écran ; peu d'info par ligne ; fiches sans numéro d'item donc sans
  rétrolien.
- Vue item spécifique : espace mort à droite sur grand écran ; wizard mnémo noir même en thème
  clair, pas joli ; bouton « + Mnémo/Image » — le « + » ne sert à rien et traîne sur plein de
  boutons ; présentation « entraînement » en foutoir, boutons et bentos partout ; Tuteur DP mal
  placé dans l'onglet Historique ; pas de moyen de marquer un item déjà vu avant Synapse (semestres
  précédents) autrement que « non fait » ; clic sur le nom du collège en en-tête ne va pas vers la
  liste filtrée de ce collège.
- Vue QCM : logique bonne, présentation à revoir (espace mort, pas uniforme) ; historique rejouable
  pas assez Linear/moderne ; difficulté de session à limiter à EDN uniquement.
- Épreuves & Annales / Examen blanc : cards grises, pas uniforme, espace mort.
- Prépa : cards grises, pas intuitif (suite de liens), veut des animations et du ludique.
- Points faibles : centré mais n'occupe pas tout l'espace ; menu ⋮ pas Linear.
- Revue hebdo : pas centrée, n'occupe pas tout l'espace.
- Statistiques : n'occupe pas tout l'espace, pas Linear.
- Récents (sidebar) : a l'air figé, toujours les mêmes items.

Questions posées :
- Comment est calculé le score de maîtrise ?
- Comment marche la programmation des cours (report qui semble non logique) ?
- Comment marche l'onglet Révisions (semble vide alors qu'il y a des cours à faire) ?

**Réponses apportées en début de session** (voir historique de conversation) : score de maîtrise
détaillé (`backend/core/reviews/mastery.py`), report corrigé en chantier A, logique de
Révisions expliquée (ne montre que la répétition espacée de cours déjà lus, jamais les premières
lectures — comportement voulu, pas un bug).

---

## 2. Découpage en 4 chantiers

| # | Chantier | Contenu | Statut |
|---|---|---|---|
| **A** | Correctifs & navigation | Bugs fonctionnels ponctuels, causes racines identifiées dans le code | ✅ **Terminé** (6 commits) |
| **B** | Design system Linear | Extension du design system existant aux écrans qui ne l'ont jamais reçu + 2 wizards + polish | ✅ **Terminé** — B1→B2→B3→B4 |
| **C** | Fond pédagogique | Flash-Zero génératif, acquis antérieurs, fiches orphelines, logique Sprint EDN | ✅ **Terminé** — C1→C5 |
| **D** | Calendriers Google configurables | Gestion des IDs de calendrier depuis Paramètres, étiquetage de la source dans la grille Planning | ✅ **Terminé** (4 commits) |

---

## 3. Chantier A — Correctifs & navigation ✅ TERMINÉ

Spec : [docs/superpowers/specs/2026-08-07-chantier-a-correctifs-navigation-design.md](superpowers/specs/2026-08-07-chantier-a-correctifs-navigation-design.md)
Plan : [docs/superpowers/plans/2026-08-07-chantier-a-correctifs-navigation.md](superpowers/plans/2026-08-07-chantier-a-correctifs-navigation.md)

| Tâche | Commit | Ce qui a été fait |
|---|---|---|
| 1. Report de révision | `716ba6f` | `next_postpone_date()` — le report part de `max(due_date, today)`, plus de la date théorique périmée |
| 2. Tri & largeur Items | `542e48e` | `visible_item_rows()` applique le tri au rendu ; `.it-wrap` en `max-width:none` |
| 3. Flash-Zero croix/correction | `ae060fc` | Croix sortie du recouvrement ; réponse donnée / attendue séparées ; `flash_zero_dialog.py` (Streamlit mort) supprimé |
| 4. Récents réels | `06c7901` | Table `recent_courses`, `record_course_visit()`/`get_recent_course_ids()`, sidebar masquée si vide |
| 5. Palette unique | `0d9db9d` | Fusion `command_palette`/`item_search_palette` → une seule sur `Ctrl+Alt+P`, navigation clavier préservée |
| 6. Navigation | `9fb69b8` | Blocs Planning cliquables ; lien collège → `/items?college=` ; Semestres retiré de la nav (route conservée) |

Suite de tests : 1081 → 1110 (aucune régression). Découverte notée pour plus tard : `mastery.py:279`
affiche « Socle Rang A critique » même sans preuve Rang A réelle — renvoyé au chantier C.

---

## 4. Chantier B — Design system Linear 🔄 EN COURS

### 4.0 Contexte découvert pendant l'audit

Il existe un design system documenté et une refonte complète déjà réalisée :
`design_handoff_synapse_refonte/README.md` (16 écrans, tokens, critères d'acceptation) +
`design_handoff_synapse_refonte/CLAUDE.md` (journal, étapes 0-18 « terminées »).

**QCM, Épreuves & Annales, Examen blanc et Prépa ne font PAS partie des 16 écrans d'origine** —
ce sont des ajouts postérieurs à la refonte (QCM était dans les 16 mais Annales/Épreuves/Examen
blanc/Prépa sont arrivés après, via d'autres plans : `2026-07-30-uness-annales-grouping`,
`2026-08-04-prepa-hub-plan`). Ils n'ont donc jamais reçu le traitement Linear — ce n'est pas une
régression, c'est une extension jamais faite.

### 4.1 Audit — cause racine par symptôme (vérifié dans le code)

| Symptôme | Fichier(s) | Cause racine |
|---|---|---|
| Espace mort QCM/Annales/Épreuves/Examen blanc/Prépa/Points faibles/Revue hebdo/Stats | 9 fichiers, liste ci-dessous | `max-width` plafonné (700–1200px), même défaut qu'Items avant chantier A |
| Revue hebdo, Stats, Prépa « pas centrées » | `revue.py:44`, `stats_cockpit.py:36`, `prepa.py:15` | `max-width` **sans** `margin:0 auto` → collé à gauche |
| Annales : cards grises | `annales.py:24` (`.ans-card`) | `background:var(--surface)` en fond permanent au lieu d'un fond `--bg`/transparent + survol seul en `--surface` |
| Annales/Épreuves : incohérent | `annales.py:227,313`, `annale_detail.py:175` | Restes Tailwind bruts (`bg-slate-50`, `border-slate-200`, `dark:bg-slate-900/40`) jamais migrés |
| Wizard mnémo noir même en clair | `obsidian_quick_edit_dialog.py:25,39` | `bg-slate-900 text-white` codé en dur + `.props("outlined dark")` ignore le thème ; emojis 💡📷⚠️ partout (interdits par le design system) |
| Bouton « + Mnémo/Image » redondant | `course_detail_cockpit.py:725` | `ui.button("💡 + Mnémo / Image", icon="add")` — emoji + texte « + » + icône, triple redondance |
| Wizard validation de séance pas centré/moche | `dashboard/_dialogs.py:210-539` (`open_session_feedback_dialog`) | `self-end mr-0` colle à droite ; **10 couleurs décoratives** (indigo/rouge/orange/bleu/sarcelle/vert/violet/rose/deep-orange/blue-grey) alors que le design system réserve rouge/ambre/vert à l'urgence/santé uniquement |
| Animation collège « brute » | `colleges_cockpit.py:396,438,529` (`_toggle_expand`) | Ajout/retrait d'un `set` Python + redessin instantané, aucune transition CSS (contrairement à `annales.py` qui a déjà un `@keyframes ansFadeIn` réutilisable) |
| Tuteur DP mal placé | `course_detail_cockpit.py:1107-1140` | Bloc rendu en dur dans `_tab_historique`, alors que c'est de l'entraînement actif → appartient à l'onglet QCM à côté de la Série QCM adaptative |
| Prépa suite de liens, pas ludique | `prepa.py:18-26` (`.prep-provider`, `.prep-shortcut`) | Blocs plats identiques sans hiérarchie ni animation ; `record_prep_access()` déjà écrit en base mais jamais réexploité pour un « récemment consulté » |
| Récents figés | déjà corrigé | Voir chantier A tâche 4 |
| Raccourci Mac `⌘K` | déjà corrigé | Voir chantier A tâche 5 (`Ctrl Alt P` partout) |

**Fichiers avec plafond de largeur à traiter en B1** :
`qcm_cockpit.py` (.qc-wrap 1200px), `annales.py` (.ans-wrap 1200px), `annale_detail.py` (.an-wrap
1200px), `exam_simulator_page.py` (.ex-wrap 1100px), `prepa.py` (.prep-wrap 980px),
`weak_points_cockpit.py` (.wp-wrap 860px, déjà centré), `revue.py` (.rh-wrap 900px, pas centré),
`stats_cockpit.py` (.st-wrap 900px, pas centré), `course_detail_cockpit.py` (.ci-center 900px,
dans un layout à 2 colonnes — traitement différent, colonne centrale doit rester flexible sans
cap dur).

Hors périmètre volontaire : `semestres_cockpit.py` (900px), `externat_cockpit.py` (900px),
`settings_cockpit.py` (700px) — non cités dans les plaintes utilisateur, ce sont des pages
courtes/formulaire où un plafond reste pertinent.

### 4.2 Sous-découpage validé par l'utilisateur

Ordre confirmé : **B1 → B2 → B3 → B4**.

- [x] **B1 — Densité & tokens (mécanique, faible risque)** — ✅ **TERMINÉ**, 7 commits.
  Spec : [docs/superpowers/specs/2026-08-07-chantier-b1-densite-tokens-design.md](superpowers/specs/2026-08-07-chantier-b1-densite-tokens-design.md).
  Plan : [docs/superpowers/plans/2026-08-07-chantier-b1-densite-tokens.md](superpowers/plans/2026-08-07-chantier-b1-densite-tokens.md).

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Largeur 8 pages | `95a2594` | `max-width:none` sur qcm_cockpit, annales, annale_detail, exam_simulator_page, prepa, weak_points_cockpit, revue, stats_cockpit |
  | 2. Plafond item détail | `2ef6344` | `.ci-center` 900px → 1100px (lecture confortable, pas plein-écran) |
  | 3. Cards grises → tokens | `8ab0219` | `.ans-card`/`.an-part-card` (hover conservé) + `.qc-history`/`.qc-selected`/`.ex-card`/`.ex-panel-q` (panneaux structurels, pas de hover ajouté) |
  | 4. Résidus Tailwind → tokens | `76ba510` | 3 emplacements dans annales.py/annale_detail.py |
  | 5. Retrait préfixe « + » | `640dfc7` | 8 boutons (Lacune, QCM, Séance, Lecture, Nouveau stage) |
  | 6. Suppression difficulté QCM | `dbb5c8f` | Toggle retiré, EDN fixé en dur dans `ai_practice_panel.py` |
  | Correctif tests obsolètes | `84c69db` | 3 tests préexistants qui encodaient l'ancien comportement (largeur QCM, largeur Points faibles, toggle difficulté) mis à jour |

  Suite de tests : 1110 → 1125 (aucune régression fonctionnelle ; 3 tests obsolètes corrigés
  parce qu'ils vérifiaient explicitement l'ancien comportement volontairement changé).
  Auto-revue notable : la spec initiale prescrivait d'ajouter un `:hover` sur tous les
  sélecteurs « carte grise » ; corrigée avant le plan car 4 des 6 sélecteurs sont des panneaux
  structurels (contiennent leurs propres lignes déjà survolables), pas des cartes cliquables.

- [x] **B2 — Les deux wizards** — plan d'implémentation écrit, prêt à exécuter.
  Spec : [docs/superpowers/specs/2026-08-07-chantier-b2-wizards-design.md](superpowers/specs/2026-08-07-chantier-b2-wizards-design.md).
  Plan : [docs/superpowers/plans/2026-08-07-chantier-b2-wizards.md](superpowers/plans/2026-08-07-chantier-b2-wizards.md).

  Règle de conversion : toute puce de sélection sans signification propre → `color=primary` ;
  seules les puces déjà sémantiquement correctes (Difficulté, Résultat QCM) restent inchangées.
  Décision utilisateur : la Confiance (1-5) reçoit aussi le traitement neutre, pas de dégradé
  rouge→vert, pour ne garder aucune exception à la règle.

  3 tâches TDD : (1) wizard mnémo/image — thème réactif, zéro emoji, `indigo`→`primary` ;
  (2) wizard validation de séance — recentré (`self-end mr-0` retiré), tokens généraux ;
  (3) wizard validation de séance — 8 couleurs décoratives (Activité/Durée/Confiance/Catégorie)
  → `primary`.

  Piège trouvé et corrigé pendant l'auto-relecture de la spec : la couleur `indigo` (et 7 autres)
  apparaît aussi dans `open_sr_help_dialog`, l'autre wizard du même fichier, explicitement hors
  périmètre — un remplacement global sur tout le fichier l'aurait touché par erreur. Le plan scope
  chaque test/remplacement au corps exact de `open_session_feedback_dialog` via
  `inspect.getsource()`, pas une lecture brute du fichier entier.

  **Statut : ✅ TERMINÉ**, 3 commits.

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Wizard mnémo/image | `290216b` | Carte/textarea/upload retokenisés, emojis retirés, `indigo`→`primary` |
  | 2. Wizard séance — centrage + tokens | `a838fd8` | `self-end mr-0` retiré, en-tête/corps/pied retokenisés |
  | 3. Wizard séance — couleurs de puces | `1823c87` | 8 occurrences décoratives (Activité/Durée/Confiance/Catégorie) → `primary` ; Difficulté/Résultat QCM inchangés |

  Suite de tests : 1125 → 1137 (aucune régression).

- [x] **B3 — Polish créatif** — ✅ **TERMINÉ**, 3 commits.
  **Contrainte technique confirmée** : `_toggle_expand` (colleges_cockpit.py:529) redessine
  **toute** la liste des collèges à chaque clic (`_render()` complet), pas seulement la ligne
  cliquée — le nœud DOM des sous-cours est détruit/recréé à chaque fermeture. Seule
  l'**ouverture** peut être animée proprement (le nœud est neuf, une animation d'entrée y joue
  une fois) ; la fermeture reste instantanée par construction. Décision utilisateur : fondu +
  glissement vertical à l'ouverture (même mécanisme que `@keyframes ansFadeIn` déjà présent dans
  `annales.py`).

  **Prépa** : `record_prep_access()` (backend/core/prep/catalog.py:85) écrit déjà un timestamp
  `last_used` en base mais aucune fonction ne le relit — une vraie section « Récemment consulté »
  est possible sans nouvelle donnée, juste une nouvelle requête `list_recent_prep_shortcuts()`.

  Visual companion utilisé (serveur local, maquettes dans `.superpowers/brainstorm/`, arrêté
  proprement en fin de chantier). 3 directions visuelles comparées pour Prépa : (A) relief au
  survol + section récents, (B) identité de couleur par plateforme, (C) mouvement seul sans
  nouvelle couleur — direction A retenue par l'utilisateur.

  Spec écrite et auto-relue →
  [docs/superpowers/specs/2026-08-07-chantier-b3-polish-creatif-design.md](superpowers/specs/2026-08-07-chantier-b3-polish-creatif-design.md).

  4 points : (1) animation d'ouverture des collèges (`@keyframes cgItemsEnter`, fermeture reste
  instantanée par contrainte architecturale assumée) ; (2) nouvelle fonction
  `list_recent_prep_shortcuts()` + section « Récemment consulté » sur Prépa (aucune migration,
  `last_used` déjà écrit par `record_prep_access`) ; (3) relief au survol des tuiles Prépa ; (4)
  apparition échelonnée des sections plateforme au chargement (CSS pur, `nth-of-type`).

  Plan d'implémentation écrit → [docs/superpowers/plans/2026-08-07-chantier-b3-polish-creatif.md](superpowers/plans/2026-08-07-chantier-b3-polish-creatif.md).
  3 tâches TDD : (1) animation collèges, (2) `list_recent_prep_shortcuts()` backend,
  (3) intégration Prépa (récents + `relative_time_label` + relief + apparition échelonnée).

  **Statut : ✅ TERMINÉ**, 3 commits.

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Animation collèges | `a599bf2` | `@keyframes cgItemsEnter` + classe sur `.cg-items` |
  | 2. `list_recent_prep_shortcuts` | `0ab276d` | Nouvelle requête backend, testée avec le fixture `prep_db` existant |
  | 3. Intégration Prépa | `52089b0` | Section « Récemment consulté », `relative_time_label()`, relief au survol, apparition échelonnée |

  Suite de tests : 1137 → 1145 (aucune régression). Serveur de maquettes arrêté proprement en fin
  de chantier.

- [x] **B4 — Déplacement structurel Tuteur DP** — ✅ **TERMINÉ**, 1 commit.
  Spec : [docs/superpowers/specs/2026-08-07-chantier-b4-tuteur-dp-design.md](superpowers/specs/2026-08-07-chantier-b4-tuteur-dp-design.md).
  Plan : [docs/superpowers/plans/2026-08-07-chantier-b4-tuteur-dp.md](superpowers/plans/2026-08-07-chantier-b4-tuteur-dp.md).

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Extraction + déplacement + indigo→primary | `408cb54` | `_render_dp_tutor(course, lacunes)` extrait, appelé dans `_tab_qcm` avant la Série adaptative (évite le `return` prématuré ligne 924), conteneur migré vers `.ci-reco`/`.ci-reco-meta`, les 2 `color=indigo` → `color=primary`, bloc supprimé de `_tab_history` |

  Point trouvé pendant l'implémentation, hors spec initiale : la convention de ce fichier est 2
  lignes vides entre fonctions top-level (pas 1, comme le plan le supposait) — corrigé avant le
  commit après vérification par `grep -B2` sur toutes les définitions `_tab_*`.

  Suite de tests : 1145 → 1147 (aucune régression ; +2 nets dans `test_dp_tutor.py`, qui passe de 2
  à 4 tests — l'ancien `test_item_history_exposes_tutor_dp_action` obsolète remplacé par 3 tests
  scopés à la nouvelle structure via un petit helper `_extract_function()` texte, pas
  `inspect.getsource()` comme suggéré dans la spec — cohérent avec la convention déjà en place pour
  ce fichier précis, jamais importé en test).

### 4.3 Prochaine étape

Chantier B **entièrement terminé** (A + B1 + B2 + B3 + B4). Chantier C démarré — voir section 5.

---

## 5. Chantier C — Fond pédagogique 🔄 EN COURS (sous-découpé C1→C5)

Périmètre initial (voir section 1), décomposé le 2026-08-08 en 5 sous-chantiers indépendants (même
logique que B1-B4 — fichiers/domaines backend distincts) :

- [x] **C1 — Correction message trompeur `mastery.py:279`** — ✅ **TERMINÉ**, 1 commit.
  Spec : [docs/superpowers/specs/2026-08-08-chantier-c1-mastery-message-critique-design.md](superpowers/specs/2026-08-08-chantier-c1-mastery-message-critique-design.md).
  Plan : [docs/superpowers/plans/2026-08-08-chantier-c1-mastery-message-critique.md](superpowers/plans/2026-08-08-chantier-c1-mastery-message-critique.md).

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Message conditionnel + 2 tests | `6f16198` | `reasons.append("Socle Rang A critique (<40%)")` rendu conditionnel à `_has_rang_a_evidence and score_rang_a < 40` (miroir du bloc `fragile`) ; 2 tests ajoutés dans `test_knowledge_mastery.py` |

  Piège trouvé pendant l'exécution : le premier jet du test « score général bas » omettait de
  passer `sessions=` à `get_course_mastery()` — sans ce paramètre explicite, la déduction
  « confiance basse » ne s'applique jamais (les sessions ne sont pas relues automatiquement depuis
  la DB), donc le score restait à 45 au lieu de 30 et le niveau à `fragile` au lieu de `critique`.
  Corrigé en réutilisant le pattern exact d'un test voisin déjà existant
  (`ls.get_sessions_by_course().get("course-1", [])` passé explicitement).

  Suite de tests : 1147 → 1149 (aucune régression ; aucun test existant n'affirmait la chaîne
  « Socle Rang A critique », confirmé par grep avant modification — donc rien à mettre à jour côté
  tests préexistants).
- [x] **C2 — Acquis antérieurs à Synapse** — ✅ **TERMINÉ**, 2 commits.
  Spec : [docs/superpowers/specs/2026-08-08-chantier-c2-acquis-anterieurs-design.md](superpowers/specs/2026-08-08-chantier-c2-acquis-anterieurs-design.md).
  Plan : [docs/superpowers/plans/2026-08-08-chantier-c2-acquis-anterieurs.md](superpowers/plans/2026-08-08-chantier-c2-acquis-anterieurs.md).

  Découverte : le mécanisme (graine `declared_level` solide/correct/flou, dégradation, dilution)
  existait déjà en entier dans `backend/core/knowledge/`, avec une UI déjà écrite
  (`_render_knowledge_block`, `course_detail.py:91-145`) — mais **morte** :
  `course_detail_page()` faisait un `return` inconditionnel ligne 155 vers le cockpit, rendant le
  reste de la fonction (± 450 lignes) inatteignable. Page `/triage/{college}` (triage en masse)
  laissée hors périmètre par décision utilisateur.

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Contrôle dans le cockpit | `1f3beb8` | `_render_declared_level(course, mastery)` ajoutée, appelée dans `_tab_overview` entre la grille 2 colonnes et « Pourquoi ce score » ; couleurs positive/warning/negative conservées (sémantique, pas décorative) |
  | 2. Suppression code mort | `d658b9f` | `course_detail.py` réduit de 606 à 16 lignes (plus que `_render_knowledge_block`, `_render_course_timeline`, `_fmt_date`/`_fmt_min`/`_day_ago`/`_NA_COLORS` et tous les imports devenus inutiles) ; docstring de `test_knowledge_course_detail_data.py` corrigé pour ne plus référencer la fonction déplacée |

  Bug attrapé en auto-relecture du plan (avant toute exécution) : le premier jet plaçait les 3
  niveaux dans une constante module-level `_DECLARED_LEVELS` *avant* la fonction — la technique de
  scoping des tests (`_extract_function`, qui capture à partir de `def nom(`) ne l'aurait jamais vue,
  faisant échouer les tests même après une implémentation correcte. Corrigé en rendant le tuple
  local à la fonction avant même d'exécuter le plan.

  Suite de tests : 1149 → 1152 (aucune régression).
- [x] **C3 — Sprint EDN, rendre visible ce que la phase pilote** — ✅ **TERMINÉ**, 2 commits.
  Spec : [docs/superpowers/specs/2026-08-08-chantier-c3-sprint-edn-design.md](superpowers/specs/2026-08-08-chantier-c3-sprint-edn-design.md).
  Plan : [docs/superpowers/plans/2026-08-08-chantier-c3-sprint-edn.md](superpowers/plans/2026-08-08-chantier-c3-sprint-edn.md).

  Découverte : `sprint_countdown_widget.py` (Streamlit) était mort, zéro importeur. Le vrai panneau
  vivant (`edn_insights_panel.py`) affichait la phase (nom) mais jamais ce qu'elle pilote —
  `recommended_new_ratio`/`recommended_review_ratio`/`recommended_qcm_dp_ratio`/
  `daily_target_items`/`focus_message` étaient calculés par `SprintConfig` mais lus par aucun
  consommateur vivant.

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Modèle + rendu étendus | `6abdccc` | `edn_insights_model()` expose les 5 champs ; `focus_message` affiché sous l'en-tête, répartition recommandée sous la barre de progression |
  | 2. Suppression widget mort | `66d22d4` | `sprint_countdown_widget.py` supprimé |

  Deux pièges trouvés pendant l'exécution (aucun n'a affecté le résultat final) : (1) incohérence de
  guillemets entre le test et le style du fichier — `edn_insights_panel.py` utilise des guillemets
  simples pour les clés de dict à l'intérieur des f-strings (`model['new_ratio']`), le test
  vérifiait des guillemets doubles ; corrigé pour matcher la convention réelle du fichier. (2) le
  garde-fou `git grep` du widget mort se remontait lui-même (la chaîne recherchée apparaît comme
  argument dans le test) et une entrée d'audit historique figée
  (`docs/AUDIT_2026-08-03.md:132`) ; corrigé en restreignant la recherche aux dossiers
  `frontend`/`backend` (code vivant uniquement).

  Suite de tests : 1152 → 1154 (aucune régression ; +2 nets, pas +3 comme prédit dans le plan — un
  des deux tests de la tâche 1 modifiait un test existant plutôt que d'en ajouter un nouveau).
- [x] **C4 — Flash-Zero génératif** — ✅ **TERMINÉ**, 5 commits.
  Spec : [docs/superpowers/specs/2026-08-08-chantier-c4-flash-zero-generatif-design.md](superpowers/specs/2026-08-08-chantier-c4-flash-zero-generatif-design.md).
  Plan : [docs/superpowers/plans/2026-08-08-chantier-c4-flash-zero-generatif.md](superpowers/plans/2026-08-08-chantier-c4-flash-zero-generatif.md).

  Confirmé : `canonical_flash_bank` avait exactement 10 questions et `get_morning_quiz(count=10)` les
  renvoyait toutes, tous les jours, juste réordonnées — l'impression utilisateur était exacte.

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Routing + stockage | `05c5f50` | `AITask.FLASH_ZERO` (tier `AIModel.FLASH`) ; table `flash_zero_ai_questions` + accesseurs ; marqueurs quotidiens `routine_checks` |
  | 2. Génération ciblée | `980f599` | `generate_daily_questions()` : cible les items en tête de `build_flash_zero_priority`, valide chaque réponse IA individuellement (best-effort, pas de lot tout-ou-rien) |
  | 3. Déclenchement quotidien | `6b13924` | `ensure_daily_flash_zero_generation()` câblée dans `run_daily_routine()`, idempotente, marqueur posé avant même la tentative (jamais de réessai le même jour) |
  | 4. Fusion dans le quiz | `e82ecc4` | `FlashZeroQuestion` gagne `source`/`review_reason` (défauts rétrocompatibles) ; `get_morning_quiz()` combine banque canonique (intouchée) + pool IA |
  | 5. Badge wizard | `2b4bae5` | Signalement doux « Généré par IA » sur les questions incertaines, même esprit que le badge DP/KFP existant |

  Décisions utilisateur actées avant l'implémentation (spec, section Contexte) : hybride (l'IA
  n'ajoute que, ne remplace jamais), signalement doux (pas de gate de validation bloquant),
  déclenchement automatique 1×/jour borné à 3 questions — exception assumée à la préférence
  habituelle de limiter les appels IA automatiques.

  Suite de tests : 1154 → 1164 (aucune régression ; tous les tests préexistants du fichier —
  y compris ceux dont le fake `Store` n'implémente pas les nouvelles méthodes — continuent de
  passer grâce aux `try/except` déjà prévus dans le design).
- [x] **C5 — Fiches Obsidian orphelines** — ✅ **TERMINÉ** (code), 2 commits. **Exécution réelle des
  scripts contre Notion/vault encore à faire manuellement** — voir « ▶ REPRISE » en tête de document.
  Spec : [docs/superpowers/specs/2026-08-09-chantier-c5-fiches-obsidian-orphelines-design.md](superpowers/specs/2026-08-09-chantier-c5-fiches-obsidian-orphelines-design.md).
  Plan : [docs/superpowers/plans/2026-08-09-chantier-c5-fiches-obsidian-orphelines.md](superpowers/plans/2026-08-09-chantier-c5-fiches-obsidian-orphelines.md).

  Cause racine : `Course.display_item_number` lit uniquement `item_number`, jamais `item_lie` — des
  cours Notion ont `ITEM (number)` vide mais `ITEM lié` rempli, donc les fiches créées depuis eux
  naissent orphelines. Aucun mécanisme de sync existant ne répare les fiches déjà créées
  (`_push_missing_obsidian_uris` ne gère que l'URI ; `VaultSyncService` ignore les notes déjà liées).

  | Tâche | Commit | Ce qui a été fait |
  |---|---|---|
  | 1. Correction Notion | `1c71ee9` | `scripts/reconcile_item_numbers.py` — même pattern dry-run/`--apply` que `reconcile_colleges.py` |
  | 2. Réparation vault | `9fe84bb` | `scripts/heal_obsidian_item_frontmatter.py` — réutilise `_split_frontmatter`/`_parse_fm_lines`/`_rebuild_fm`, ne touche que la ligne `item:` |

  Suite de tests : 1164 → 1172 (aucune régression). `Course.display_item_number` n'a pas été modifié
  — les deux scripts corrigent les données à la source, le code applicatif reste inchangé.

Ordre confirmé par l'utilisateur : **C1 → (C2/C3/C4/C5 à réordonner au fil de l'eau)**.

## 6. Chantier D — Calendriers Google configurables ✅ TERMINÉ

Spec : [docs/superpowers/specs/2026-08-09-chantier-d-calendriers-configurables-design.md](superpowers/specs/2026-08-09-chantier-d-calendriers-configurables-design.md)
(non commitée, artefact de travail — voir convention).
Plan : [docs/superpowers/plans/2026-08-09-chantier-d-calendriers-configurables.md](superpowers/plans/2026-08-09-chantier-d-calendriers-configurables.md)
(non commité, idem).

Recadrage important pendant le brainstorming : le grief original du 7 août (« pas de vue semaine
réelle ») portait sur une fonctionnalité qui **existait déjà** — `planning_cockpit.py` affiche une
grille 7/3/1 jours avec tâches Synapse + événements Google Calendar depuis la refonte cockpit
initiale (`42fd8b1`), bien avant la revue. Le vrai trou, identifié en creusant le code (même pattern
que C1-C5 : mécanisme déjà là, jamais exposé) : `GoogleCalendarService.get_events_for_day` savait
déjà interroger plusieurs calendriers (`GOOGLE_CALENDAR_IDS` en `.env`, avec même un correctif +4h
déjà en dur pour un ID « Agenda FAC »), mais aucune UI ne permettait de gérer ces IDs — il fallait
éditer `.env` à la main et redémarrer l'app.

| Tâche | Commit | Ce qui a été fait |
|---|---|---|
| 1. Fonctions pures | `662096d` | `backend/core/planning/calendar_sources.py` — `list_calendar_sources`/`add_calendar_source`/`remove_calendar_source`, préférence `planning_calendar_sources` |
| 2. Fusion + étiquetage backend | `0398e4c` | `get_events_for_day` fusionne IDs `.env` + préférence (dédupliqués), chaque événement récupéré porte `_synapse_source_label` |
| 3. Panneau Paramètres | `c49d1c1` | `frontend/components/calendar_sources_panel.py` (pattern `dp_coverage_panel.py`), câblé dans `settings_cockpit.py` sous une section CALENDRIERS |
| 4. Étiquette grille Planning | `89d3bf5` | `event_display_title()` dans `planning_cockpit.py`, préfixe le titre de l'événement par le label de sa source si étiquetée |

Suite de tests : 1172 → 1194 (aucune régression). Pas d'action manuelle restante : gérable
immédiatement depuis Paramètres → CALENDRIERS, effet immédiat sur la grille sans redémarrage.
