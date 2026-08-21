# Synapse — Contexte complet pour analyse IA

> Document de référence unique destiné à une IA qui doit comprendre le projet rapidement,
> sans redécouvrir le code. Complète (et remplace pour l'usage IA) `SYNAPSE_OVERVIEW.md`,
> plus court mais moins à jour. Source : lecture du code, de `docs/AUDIT_2026-08-03.md`
> (le plus complet et le plus vérifié empiriquement contre la base réelle), et de
> l'historique git jusqu'au 7 août 2026.
>
> **Règle de lecture** : ce document distingue explicitement ce qui *marche réellement*
> (vérifié contre `data/synapse_local.db`) de ce qui est *écrit mais non branché*. Ne pas
> supposer qu'une fonctionnalité présente dans le code est utilisée — voir §9.

---

## 1. Identité du projet

Synapse est une application web **personnelle et mono-utilisateur** de gestion des révisions
médicales, développée par un étudiant en médecine (externat) préparant l'**EDN** (Examen
Dématérialisé National, ex-ECN). Ce n'est pas un produit destiné à être distribué : entièrement
configuré pour un seul utilisateur (Hugo), tourne en local sur `127.0.0.1:8082`, pas de multi-
tenant, pas d'authentification.

**Objectif central** : ne jamais oublier un cours, savoir précisément quoi réviser chaque jour,
suivre sa progression par item du référentiel EDN, et transformer l'entraînement (QCM/DP/annales)
en signal de maîtrise exploitable — pas seulement en volume de questions faites.

**Deux moitiés historiquement déconnectées** (en cours de reconnexion, voir §9) :
- **Pilotage** : Notion (cours) + SQLite (historique révisions SM-2/FSRS) + Obsidian (notes) +
  score de maîtrise + planning.
- **Entraînement** : UNESS (annales scannées) + génération IA de QCM/DP + simulateur d'épreuves +
  import EDNpro/Hypocampus.

Le pont entre les deux est le **numéro d'item EDN** (référentiel UNESS, 367 items / 59 collèges) —
voir §6.

---

## 2. Utilisateur

- Étudiant en médecine (externat), niveau Python autonome (comprend NiceGUI, SQLite, Pydantic,
  async/await).
- Abonné à **EDNpro** et **Hypocampus** (prépas payantes) en plus du référentiel UNESS officiel.
- Préfère les explications directes, sans sur-explication.
- **Toujours répondre en français** sur ce projet — spec et vocabulaire entièrement en français.
- Préfère l'option la moins coûteuse ; demander avant tout appel API payant répété (coûts Gemini
  suivis dans `ai_usage_logs`).

---

## 3. Stack technique

| Couche | Technologie | Détail |
|---|---|---|
| Frontend | **NiceGUI 3.8.0** | Python → UI web réactive, port 8082, PWA (manifest) |
| Lecteur QCM | **React** (`qcm_app/`, build Node séparé) | Monté sur `/qcm-app`, utilisé par le simulateur d'épreuves et les sessions IA |
| Source de vérité cours | **Notion API** (`notion-client`) | Base des cours EDN, lue/écrite via payloads typés |
| Persistance locale | **SQLite** (`data/synapse_local.db`) | Historique révisions, sessions IA, QCM, lacunes, cache — ~35 tables |
| Notes de cours | **Obsidian** (vault sur Google Drive) | Sync bidirectionnel avec Notion/Synapse |
| Calendrier | **Google Calendar API** | OAuth, credentials dans `token.json`/`credentials.json` |
| IA générative | **Gemini** (`google-generativeai`) | Deux niveaux : `flash-lite` (économique) / `flash` (complexe), voir §7.5 |
| Web scraping | **Playwright** | LiSA (OIC), EDNpro (collecte via navigateur, OAuth Google manuel) |
| Logs | **Loguru** | Rotation quotidienne, rétention 30 jours, compression |
| Config | **Pydantic Settings** + `.env` | `backend/config/settings.py` |
| Fuseau horaire | `Europe/Paris` par défaut, `Indian/Reunion` en option | Préférence persistante, voir §7.7 dans l'audit |
| Python | ≥ 3.11 | `pyproject.toml`, lint via **ruff** |

Dépendances complètes : [requirements.txt](../requirements.txt) / [pyproject.toml](../pyproject.toml).

### Démarrage

```bash
python main.py
```
Lance NiceGUI sur `http://127.0.0.1:8082`. Splash screen pendant `DataStore.preload_all_views()`
(chargement async des cours Notion), puis tâches de fond (sync Obsidian, routine quotidienne),
puis redirection Dashboard.

---

## 4. Architecture des dossiers

```
Synapse/
├── main.py                        # Point d'entrée NiceGUI, routes, splash screen, /pdf/{id}
├── backend/
│   ├── config/settings.py         # Pydantic Settings, NOTION_PROPS (alias P), fuseau, chemins
│   ├── state/store.py             # DataStore — chargement async des cours + préférences
│   ├── features/daily_routine.py  # Routine quotidienne automatique
│   ├── api/qcm.py                 # API REST consommée par le lecteur React (/api/qcm/...)
│   └── core/
│       ├── notion/                # Client + modèles + service Notion (CRUD cours), payloads.py
│       ├── reviews/                # Cœur du moteur de révisions
│       │   ├── models.py              # ReviewTask (Pydantic)
│       │   ├── service.py             # Génère les tâches virtuelles du jour
│       │   ├── local_store.py         # SQLite — ~35 tables, tout le schéma (3000+ lignes)
│       │   ├── mastery.py             # Score de maîtrise 0-100 par cours/item
│       │   ├── sm2.py                 # Algorithme SM-2 (répétition espacée)
│       │   ├── consolidation.py       # Agrégation des preuves de rétention
│       │   ├── anchors.py             # Ancrages pédagogiques
│       │   └── recommendation_service.py
│       ├── obsidian/               # Sync bidirectionnel vault ↔ Notion/Synapse, weak_points_sync.py
│       ├── planning/               # Planning, focus mode, cockpit_schedule, calendar_actions
│       ├── uness/                  # Pipeline annales UNESS (voir §7.2)
│       ├── network_capture/        # Fetchers EDNpro (Supabase) / Hypocampus, HAR, converters
│       ├── ai/                     # Client Gemini, routage par tâche, logs d'usage
│       │   ├── gemini_client.py
│       │   ├── routing.py             # Sélection du modèle par type de tâche
│       │   ├── tasks.py               # generate_qcm(), generate_dp(), etc.
│       │   └── logger.py              # ai_usage_logs
│       ├── ai_qcm/                 # Import QCM depuis discussions ChatGPT/Gemini, lacunes, gap_dp_generator
│       ├── practice/                # Sessions d'entraînement (modèles, importer)
│       ├── lisa/                   # Scraping OIC (LiSA), AnythingLLM, item_service, evaluator
│       ├── anki/                   # Intégration Anki (client, service, mapping) — codé, non branché
│       ├── evaluation/             # Modèles/service d'évaluation OIC
│       ├── externat/               # Gestion des stages cliniques
│       ├── graph/                  # Graphe de connaissances (builder + modèles) — bruité, voir §9
│       ├── knowledge/               # Store de connaissances, rétention
│       ├── search/                 # Recherche full-text
│       ├── analytics/weekly_report.py
│       ├── tracking/               # Démarrage du suivi d'un cours
│       ├── google/                 # calendar_service.py
│       ├── prep/                   # Ressources et catalogue de préparation
│       ├── podcast/                # podcast_service.py
│       └── background.py          # Tâches de fond au démarrage (syncs Obsidian, EDNpro)
├── frontend/
│   ├── theme.py, cockpit_shell.py # Frame NiceGUI, shell "cockpit" (nav latérale, sidebar)
│   ├── design_tokens.py           # Tokens de design (couleurs, espacements)
│   ├── keybindings.py             # Raccourcis clavier
│   ├── pages/                     # ~35 pages ; suffixe `_cockpit.py` = version actuelle post-refonte
│   │   ├── dashboard/                 # Dashboard (sous-module : _hero, _agenda, _reviews, _monday…)
│   │   ├── colleges_cockpit.py, semestres_cockpit.py, items.py
│   │   ├── course_detail_cockpit.py, weak_points_cockpit.py
│   │   ├── stats_cockpit.py, planning_cockpit.py, todo_cockpit.py, settings_cockpit.py
│   │   ├── qcm.py, qcm_cockpit.py, annales.py, annale_detail.py
│   │   ├── exam_simulator_page.py     # Simulateur d'épreuves → redirige vers /qcm-app (React)
│   │   ├── externat_cockpit.py, prepa.py, triage.py, health.py, revue.py
│   └── components/                # ~40 composants
│       ├── course_card.py             # Carte cours UNIFIÉE — à réutiliser pour toute nouvelle vue liste
│       ├── mastery_indicator.py, sparkline.py, forgetting_curve.py
│       ├── command_palette.py         # Ctrl+K
│       ├── ai_practice_panel.py       # Génération IA de QCM/DP depuis une fiche ITEM
│       ├── dp_coverage_panel.py       # Paramètres → couverture DP par item
│       ├── uness_diagnostic_panel.py  # Paramètres → diagnostic pipeline UNESS
│       ├── flash_zero_dialog.py, flash_zero_cockpit.py, sprint_countdown_widget.py
│       ├── practice_import_panel.py, practice_session_card.py, qcm_replay.py
│       ├── weak_point_card.py, weak_point_row.py
│       ├── oic_panel.py, oic_eval_dialog.py, lisa_dialog.py
│       └── edn_insights_panel.py
├── qcm_app/                        # App React séparée (build Node → dist/), lecteur QCM/DP interactif
├── data/
│   ├── synapse_local.db               # SQLite principal
│   ├── backups/                       # Sauvegardes quotidiennes auto (7 dernières, depuis le 3 août)
│   ├── uness/verified/                # JSON canoniques UNESS/EDNpro post-correction
│   └── ednpro/artifacts/              # manifest.json + artefacts de collecte EDNpro
├── scripts/                        # Scripts ponctuels (backfill, migration, collecteurs EDNpro)
├── UNESS/                          # Données/outils liés au pipeline UNESS
├── data_cache.json                 # Cache local des cours Notion (préchargement)
├── docs/                           # Documentation technique (audits, guides) — voir §11
└── tests/                          # pytest (Python) + tests React dans qcm_app/
```

---

## 5. Base de données SQLite — schéma (`data/synapse_local.db`)

Toutes les tables sont créées/migrées dans `backend/core/reviews/local_store.py` (fichier
volumineux, ~3000+ lignes, source unique du schéma). Regroupées par domaine :

### Pilotage / révisions (le socle qui fonctionne)
| Table | Rôle |
|---|---|
| `review_history` | Historique de chaque révision (date, type, résultat) — SM-2/FSRS |
| `study_sessions` | Sessions enrichies (activités, confiance, temps, QCM, lacune) |
| `mastery_snapshots` | Historique hebdomadaire du score de maîtrise par cours |
| `weak_points` | Lacunes / points faibles (statuts : active → à revoir → résolue/récurrente) |
| `pending_gap_proposals` | Propositions automatiques de lacunes (F6) en attente de validation |
| `manual_planning_entries` | Programmation manuelle dans le planning |
| `routine_items`, `routine_checks` | Routine quotidienne automatique |
| `course_edges` | Graphe sémantique entre cours (`same_college`, `same_item`, `shared_lacune`, `qcm_confound`) |

### Entraînement / IA
| Table | Rôle |
|---|---|
| `ai_practice_sessions` | Sessions de QCM/DP/KFP générées par IA ou importées d'annales |
| `ai_practice_questions` | Questions individuelles (prompt, propositions, correction) |
| `ai_practice_session_questions` | Liaison session ↔ questions |
| `ai_practice_session_items` | **Pont F1** : items EDN couverts par une session (un DP peut couvrir plusieurs items) |
| `ai_practice_question_items` | **Pont F1 affiné (§7.4)** : liaison au niveau *question*, avec provenance/confiance/version de classifieur — la maîtrise se calcule sur ce niveau, pas sur la session entière |
| `ai_practice_attempts` | Tentatives de réponse (score, durée, hints_used) |
| `ai_practice_attempt_propositions` | Détail par proposition (sélection, vérité, rang, points, discordance) — barème EDN propositionnel |
| `ai_practice_anchors` | Ancrages pédagogiques sur des questions |
| `imported_practice_cases`, `imported_practice_questions` | Banques QCM/DP/KFP importées en JSON (ChatGPT/Gemini) |
| `ai_usage_logs` | Coût/usage réel des appels Gemini (base pour arbitrer les coûts) |

### UNESS (annales officielles)
| Table | Rôle |
|---|---|
| `uness_scanned_catalog` | Catalogue scanné des annales disponibles sur entrainement.uness.fr |
| `uness_annales` | Annales effectivement importées dans Synapse |
| `uness_correction_failures` | File d'échecs de correction IA à retraiter |

### EDNpro / Hypocampus (sources externes — F2, actif depuis début août)
| Table | Rôle |
|---|---|
| `external_results` | Résultats importés (CSV/JSON manuel ou collecteur EDNpro), normalisés, dédupliqués par `(source, external_id)` |
| `ednpro_item_frequency` | Fréquence d'apparition d'un item aux sessions EDNpro (signal pour la priorisation) |
| `ednpro_frequency_history` | Historique/snapshots comparables de ces fréquences dans le temps |
| `annales_sessions`, `annales_dossiers`, `annales_questions`, `annales_propositions`, `annales_question_oic` | Structure détaillée des sessions EDNpro collectées (dossiers/sous-parties/propositions) |

### QCM / rétention / diagnostic
| Table | Rôle |
|---|---|
| `qcm_results`, `qcm_sessions` | Résultats QCM saisis/importés |
| `error_signals` | Profil d'erreur (F4) : oubli, raisonnement, piège EDN, rang A/B, inattention, temps |
| `edn_recommendations` | Priorisation calculée (F3 — potentiel de gain relatif) |
| `anki_review_evidence` | Prévu pour intégration Anki — **table vide, service codé mais jamais câblé** |

### Autres
| Table | Rôle |
|---|---|
| `lisa_oic`, `lisa_oic_cache` | OIC (objectifs de connaissance officiels) scrapés depuis LiSA |
| `pdf_local_cache`, `pdf_item_scan` | Cache/scan des PDF locaux |
| `stages` (externat) | Stages cliniques — quasi jamais utilisée |

> **Note fiabilité** : `init_db()` crée désormais une sauvegarde quotidienne dans `data/backups/`
> (7 dernières conservées) avant migrations/écritures — corrigé début août après un audit ayant
> signalé l'absence de backup comme risque critique.

---

## 6. Vocabulaire métier (source : `CONTEXT.md`)

- **Item** : unité de connaissance EDN canonique. Existe une seule fois au niveau du programme
  (référentiel UNESS, 367 items / 59 collèges), même s'il est rattaché à plusieurs collèges dans
  Synapse.
- **Collège** : contexte de classement/affichage/révision d'un item dans Synapse. La présence d'un
  item dans plusieurs collèges ne crée pas plusieurs connaissances indépendantes.
- **Cours Synapse** : représentation contextuelle d'un item dans un collège. Plusieurs cours Synapse
  peuvent donc pointer vers le même item canonique.
- **Note Obsidian canonique** : une seule note par item, partageable depuis tous les collèges
  auxquels il est rattaché — la liaison doit résoudre l'item canonique **avant** son collège
  d'affichage.
- **Conséquence** : les identifiants et relations doivent distinguer item canonique, cours Synapse
  contextuel, et note Obsidian canonique. Aucune opération de sync ne doit créer une note par
  collège ni choisir silencieusement un alias quand un item a plusieurs cours.
- Le **référentiel UNESS** (367 items/59 collèges) est la **source de vérité** pour la correspondance
  collège ↔ item ; Notion est réconcilié dessus, pas l'inverse.

---

## 7. Intégrations externes

### 7.1 Notion — source de vérité des cours
- Toute la base des 707 cours EDN vit dans Notion, lue/écrite via `notion-client`.
- **Règles impératives** (voir §8) : payloads typés, jamais de valeurs Python brutes ; propriétés
  toujours référencées via `NOTION_PROPS` (`P.NOM_CONSTANTE`).
- `update_course_action()` (`frontend/utils.py`) : mise à jour optimiste — local d'abord, puis
  Notion, avec retry/backoff sur erreurs transitoires (timeouts, réseau, HTTP 408/409/425/429/5xx)
  depuis début août.

### 7.2 Pipeline UNESS (annales officielles)
Collecte depuis `entrainement.uness.fr` → correction/normalisation IA (Gemini) → vérification IA →
classification automatique de l'item (voir F1 §9) → import dans `uness_annales` +
`ai_practice_sessions`. Modules : `backend/core/uness/{collector,normalizer,gemini_conversion,
gemini_autocorrect,ai_verifier,item_classifier,diagnostics,exam_simulator}.py`. Un panneau de
diagnostic existe dans Paramètres (`uness_diagnostic_panel.py`) pour suivre l'état du pipeline.

**Point structurel important** : entrainement.uness.fr n'expose lui-même **aucun numéro d'item** —
seulement matière/faculté/année. Ce n'est pas un défaut de collecte Synapse ; la classification par
item doit obligatoirement passer par une déduction (titre + collège + IA bornée aux candidats).

### 7.3 EDNpro / Hypocampus (prépas payantes — F2, actif)
- `backend/core/network_capture/fetcher.py` : `SupabaseFetcher` (EDNpro, PostgREST) et
  `HypocampusFetcher`.
- Collecte via Playwright avec **connexion Google manuelle** de l'utilisateur (Google refuse les
  navigateurs automatisés — contournement interdit par principe ; solution retenue : attacher le
  collecteur à un Chrome normal déjà connecté via CDP `--remote-debugging-port`).
- Flux : session EDNpro/Hypocampus → JSON canonique dans `data/uness/verified/` → import annales +
  QCM Synapse ; dossiers convertis en sous-parties ; explications déjà présentes réutilisées en
  priorité (IA seulement en repli).
- Fréquences d'items (`ednpro_item_frequency`/`ednpro_frequency_history`) synchronisées et
  comparables dans le temps (snapshots) — alimente la priorisation F3.
- Accessible depuis la page **Prépa** (`frontend/pages/prepa.py`) : raccourcis + bouton "Importer
  les EDN".
- Étiqueté explicitement comme source **non officielle** (`official: false`) dans le JSON et en
  base — distinct du référentiel UNESS.
- Cadrage légal retenu : usage personnel, propre compte, pas de redistribution, pas d'automatisation
  masquée du login (OAuth fait à la main par l'utilisateur) → risque jugé faible ; risque résiduel :
  Conditions d'Utilisation (endpoints non officiels), pas de risque pénal identifié.

### 7.4 Obsidian
- Vault Google Drive (`OBSIDIAN_VAULT_PATH`), sync bidirectionnel au démarrage
  (`backend/core/background.py`) : matching par titre → écrit `notion_id`/`synapse_id` en
  frontmatter, revalide les URIs Obsidian dans Notion.
- Lacunes : changer de statut dans Synapse déplace physiquement le fichier `.md` dans le bon
  sous-dossier Obsidian (`08 - Lacunes/Actives|À revoir|Corrigées/`).
- `trap_detector.py` extrait déjà les pièges pédagogiques des notes.

### 7.5 IA générative (Gemini)
Deux modèles routés par type de tâche (`backend/core/ai/routing.py`, voir `docs/AI_MODEL_ROUTING.md`) :

| Tâche | Modèle |
|---|---|
| OIC, QCM, ECOS simple | `gemini-3.1-flash-lite` (économique) |
| DP, KFP, ECOS complexe | `gemini-2.5-flash` |
| Extraction complexe de grille | `gemini-2.5-flash` + **validation humaine obligatoire** |
| QCM/OIC difficulté Difficile/Concours | modèle Flash configuré |
| Score, seuil, niveau, progression | **jamais l'IA** — calculé par code Synapse |

Point de discipline important : **le score n'est jamais demandé au modèle** ; le code métier valide
les réponses et calcule la progression. Sessions IA immuables une fois générées (rejouabilité :
même énoncé, mêmes choix, même correction à chaque tentative).

### 7.6 LiSA (OIC officiels) + AnythingLLM
Scraping Playwright des OIC officiels par item (`backend/core/lisa/scraper.py`). Bouton
"Rafraîchir tous les OIC" dans Paramètres — groupe par `item_number` pour éviter les scrapes
redondants. Dialogue OIC connecté à un workspace AnythingLLM (RAG sur les documents du collège),
modèle réglé sur Flash-Lite.

### 7.7 Anki
Client/service/mapping codés (`backend/core/anki/`) mais **jamais branchés** — table
`anki_review_evidence` vide. Ne pas présumer que l'intégration est active.

### 7.8 Google Calendar
Sync des séances de révision, OAuth (`credentials.json`/`token.json`).

---

## 8. Conventions de code obligatoires

1. **Payloads Notion** : toujours `checkbox(val)`, `notion_date("YYYY-MM-DD")`, `url_prop(url)`,
   `number_prop(n)` (importés de `backend/core/notion/payloads.py`) — **jamais** de `True`/dict brut.
2. **NOTION_PROPS** : toujours `P.NOM_CONSTANTE`, jamais de string en dur pour une propriété Notion.
3. **`task_id`** : format `{course_id}_{context}_{review_type}_{theoretical_due_date_iso}` — la date
   est **toujours théorique**, jamais la date reportée.
4. **Postpone** : offset calculé depuis `task.due_date` (date effective), jamais depuis aujourd'hui.
5. **Fuseau horaire** : passer par `backend.config.settings.now_local()` / `business_today()` —
   préférence utilisateur `Europe/Paris` (défaut) ou `Indian/Reunion`. Ne pas coder un fuseau en dur.
6. **`CourseCard`** (`frontend/components/course_card.py`) : composant unifié obligatoire pour toute
   nouvelle vue liste de cours.
7. **`COLLEGE_MAPPING`** : les collèges Notion ont l'emoji à la **fin** (`Cardiovasculaire ❤️`), pas
   au début.
8. **Suffixe `_cockpit.py`** : les pages `frontend/pages/*_cockpit.py` sont les versions actuelles
   post-refonte (juillet-août 2026) ; les modules sans suffixe sont parfois legacy/relais — vérifier
   ce qui est réellement importé par `main.py` avant de modifier une page.
9. **Item d'abord, collège ensuite** : toute résolution de note/lien doit passer par l'item canonique
   avant le collège d'affichage (voir §6).

---

## 9. État réel des fonctionnalités (ne pas se fier au code seul)

> Basé sur `docs/AUDIT_2026-08-03.md` (vérifié empiriquement contre la base) + commits jusqu'au
> 7 août 2026. Beaucoup de fonctionnalités **existent en code** sans être **branchées** dans
> l'application — toujours vérifier l'import réel depuis `main.py` / les pages cockpit avant de
> supposer qu'un module est actif.

### ✅ Fonctionne et vérifié
- Moteur SM-2/FSRS de révisions espacées + Dashboard quotidien.
- Score de maîtrise (bug de verrou Rang A corrigé le 3 août — s'appliquait à l'aveugle aux 99 % de
  cours sans mesure Rang A réelle).
- Sync Notion ↔ Obsidian ↔ SQLite au démarrage.
- **F1 — pont d'item** : classification IA (Gemini flash-lite, bornée aux candidats du collège)
  des annales UNESS sans numéro d'item natif. 150/151 sessions historiques classées. Affinée au
  niveau *question* (pas seulement session) le 3 août soir — voir `ai_practice_question_items`.
- **F2 — ingestion EDNpro/Hypocampus** : collecteur Playwright + OAuth manuel Google, import
  annales/QCM/fréquences d'items. Actif et étendu début août (snapshots de fréquence comparables).
- **F3 — priorisation par potentiel de gain** (`edn_recommendations`) : calculée avec poids EDN,
  déficit de maîtrise, récurrence des erreurs, disponibilité des questions.
- **F4 — profil d'erreurs** : regroupement des signaux (oubli/raisonnement/piège/rang/inattention/
  temps) sur 30 jours.
- **F5 — Sprint Countdown** : branché au Dashboard (J-X, objectif, phase, couverture, projections),
  date EDN configurable (n'est plus codée en dur).
- **F6 — lacunes automatiques** : suggestion explicable dans le cockpit Lacunes après ≥2 erreurs
  comparables, actions Créer/Ignorer.
- Barème EDN propositionnel unique (`score_mode="edn"`, grille 1/0,5/0,2/0) — remplace l'ancien
  tout-ou-rien ; visible dans le lecteur React et le replay NiceGUI.
- Finalisation de session robuste : états explicites, refus si réponses manquantes (HTTP 409),
  plus de colonne SQLite fantôme (`statement_html` → `prompt`).
- Sauvegarde quotidienne SQLite + retry/backoff Notion (corrigés début août).
- Fuseau horaire configurable et cohérent (Europe/Paris par défaut).
- Panneau "Couverture DP par item" dans Paramètres (comptage réel par item, tri, filtre).
- Bulk refresh OIC LiSA (groupé par item, pas par cours).

### ⚠️ Partiellement fiable / à vérifier avant usage
- **Graphe sémantique** (`course_edges`) : ~96 % des arêtes sont `same_college` (O(n²), bruit) ;
  `shared_lacune`/`qcm_confound` produisent peu/pas d'arêtes faute de données sources suffisantes.
  Ne pas s'y fier comme signal pédagogique fort en l'état.
- **Flash-Zero** : rebranché dans le planning du matin (tâche quotidienne idempotente), mais à
  l'origine reposait sur une banque codée en dur non adaptative — vérifier l'état actuel du service
  avant de présenter ses questions comme personnalisées.
- **Classifications UNESS historiques très larges** (annales à 15-28 items) : partiellement
  resserrées via `scripts/refine_uness_overbroad_items.py` (6/7 cas extrêmes resserrés début août),
  mais des cas résiduels subsistent — traiter comme signal faible, pas preuve forte, sauf question
  par question.
- **Tests** : suite historiquement bloquée à la collecte (modules `_cockpit.py` vs anciens relais) ;
  état au 3 août soir : 972 tests passants après corrections — revérifier l'état courant avec
  `pytest -q` avant de se fier à "tout est vert".

### ❌ Codé mais non branché / mort
- **Intégration Anki** : service complet, jamais câblé (`anki_review_evidence` vide).
- **Mode Externat / stages** : quasi jamais utilisé (table `stages` proche de 0 lignes).
- **`_fetch_ednpro_background()`** (ancien mécanisme) : mort depuis la désactivation de
  l'auto-capture — remplacé par le collecteur explicite EDNpro décrit en §7.3.
- Ancien simulateur d'épreuves Python (barème historique) : chemin mort, remplacé par le lecteur
  React actif (`/exam` → `/qcm-app/?exam=1`) — éviter de retravailler l'ancien moteur Python isolé.

**Règle pratique pour toute analyse IA** : avant d'affirmer qu'une fonctionnalité "marche", vérifier
son usage réel (import depuis `main.py`/pages cockpit actives, lignes dans la table SQLite
correspondante) plutôt que la seule présence du code.

---

## 10. Points d'entrée HTTP (`main.py`)

| Route | Rôle |
|---|---|
| `/` | Dashboard (avec splash screen de préchargement) |
| `/stats`, `/todo`, `/planning`, `/colleges`, `/semestres`, `/settings`, `/externat` | Pages principales |
| `/cours/{course_id}` | Détail d'un cours |
| `/lacunes?item=...` | Gestion des lacunes (filtrable par item) |
| `/qcm` | Interface QCM |
| `/exam` | Simulateur d'épreuves → redirige vers `/qcm-app/?exam=1` (React) |
| `/pdf/{course_id}` | Sert un PDF local (chemin validé : extension `.pdf` + répertoire autorisé) |
| `POST /api/lacune/move` | Drag & drop kanban lacunes |
| `/api/qcm/...` | API REST consommée par le lecteur React (`backend/api/qcm.py`) |
| `/qcm-app` | App React statique montée (si build présent dans `qcm_app/dist/`) |

---

## 11. Documentation existante (`docs/`)

Le dossier `docs/` contient l'historique des audits et sessions — utile pour comprendre *pourquoi*
une décision a été prise, mais **daté** : toujours croiser avec le code actuel.

- `AUDIT_2026-08-03.md` — l'audit le plus complet et le plus vérifié (base de ce document).
- `AI_MODEL_ROUTING.md` — routage des modèles Gemini (résumé en §7.5 ici).
- `EDNPRO_IMPORT.md` — procédure de collecte EDNpro (résumé en §7.3 ici).
- `IMPORT_DP_KFP.md`, `ETAT_DES_LIEUX_2026-07-29.md`,
  `AUDIT_TECHNIQUE_PERFORMANCE_2026-08-02.md`,
  `AUDIT_ET_FEUILLE_DE_ROUTE_EDN_2026-08-02.md` — audits/notes antérieurs, partiellement absorbés
  par `AUDIT_2026-08-03.md`.
- `PROGRESSION_SESSION_*.md` — journaux de sessions de développement (fin juillet-août 2026).
- `Feuille de route.txt` (racine) — feuille de route produit, à lire pour la vision long terme.

---

## 12. Ce que Synapse N'est PAS

- Pas une application multi-utilisateur, pas de couche d'authentification.
- Pas déployé en production — tourne en local uniquement (`127.0.0.1:8082`).
- Pas un LMS ni un générateur de contenu générique — un orchestrateur de révisions personnelles
  bâti autour du référentiel EDN (367 items).
- EDNpro/Hypocampus ne sont **pas** des sources officielles — toujours étiquetées `official: false`,
  traitées comme un complément au référentiel UNESS, jamais comme s'y substituant.
- Le score affiché n'est fiable EDN (`score_mode="edn"`) que lorsque le rang des propositions est
  connu ; sinon il doit être présenté comme un score d'entraînement non calibré.
