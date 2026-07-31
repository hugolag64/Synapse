# Synapse — Vue d'ensemble du projet

## Qu'est-ce que Synapse ?

Synapse est une application web personnelle de **gestion des révisions médicales**, développée par un étudiant en médecine (externat) qui prépare l'EDN (Examen Dématérialisé National). C'est un outil de productivité intime : pas destiné à être distribué, entièrement configuré pour un seul utilisateur, tournant en local.

L'objectif central : **ne jamais oublier un cours**, savoir exactement quoi réviser chaque jour, et suivre sa progression par matière au fil du temps.

---

## Stack technique

| Couche | Technologie |
|---|---|
| Frontend | **NiceGUI** (Python → UI web, tourne sur port 8082) |
| Source de vérité cours | **Notion API** (base de données des cours EDN) |
| Persistence locale | **SQLite** (`data/synapse_local.db`) |
| Notes de cours | **Obsidian** (vault sur Google Drive) |
| Calendrier | **Google Calendar API** |
| Logs | **Loguru** (rotation quotidienne, rétention 30 jours) |
| Config | **Pydantic Settings** + `.env` |
| Timezone | `Indian/Reunion` |

L'app démarre avec `main.py` via `ui.run(port=8082)` et se présente comme une PWA (manifest JSON inclus).

---

## Architecture des dossiers

```
Synapse/
├── main.py                        # Point d'entrée, routes NiceGUI, route /pdf/{course_id}
├── backend/
│   ├── config/settings.py         # Constantes globales, NOTION_PROPS (alias P), chemins
│   ├── state/store.py             # DataStore — chargement async des cours au démarrage
│   ├── core/
│   │   ├── notion/                # Client + modèles + service Notion (CRUD cours)
│   │   ├── reviews/               # Moteur de révisions espacées
│   │   │   ├── models.py          # ReviewTask (Pydantic)
│   │   │   ├── service.py         # Génération des tâches virtuelles du jour
│   │   │   ├── local_store.py     # SQLite : review_history, study_sessions, qcm_results
│   │   │   ├── mastery.py         # Score de maîtrise 0-100 par cours
│   │   │   ├── sm2.py             # Algorithme SM-2 (répétition espacée)
│   │   │   └── recommendation_service.py
│   │   ├── obsidian/              # Sync bidirectionnel vault Obsidian ↔ Notion/Synapse
│   │   ├── tracking/              # Démarrage du suivi d'un cours
│   │   ├── google/calendar_service.py  # Intégration Google Calendar
│   │   ├── planning/              # Système de planning
│   │   ├── qcm/                   # Gestion des résultats QCM
│   │   ├── search/                # Recherche full-text dans les cours
│   │   ├── graph/                 # Graphe de connaissances (builder + modèles)
│   │   ├── analytics/weekly_report.py  # Rapport hebdomadaire
│   │   ├── externat/              # Gestion des stages (externat)
│   │   ├── files.py               # Accès aux PDFs locaux
│   │   └── background.py         # Tâches de fond au démarrage (syncs Obsidian)
│   └── features/daily_routine.py  # Routine quotidienne automatique
├── frontend/
│   ├── theme.py                   # Frame NiceGUI vers le shell cockpit
│   ├── pages/
│   │   ├── dashboard.py           # Dashboard principal (révisions du jour)
│   │   ├── colleges.py            # Vue par collège médical
│   │   ├── semestres.py           # Vue par semestre/UE
│   │   ├── course_detail.py       # Détail d'un cours
│   │   ├── stats.py               # Statistiques de révision
│   │   ├── weak_points.py         # Gestion des lacunes
│   │   ├── qcm.py                 # Interface QCM
│   │   ├── planning.py            # Vue planning
│   │   ├── todo.py                # Liste de tâches
│   │   ├── externat.py            # Gestion des stages
│   │   ├── health.py              # État de santé de l'app (Notion API, etc.)
│   │   └── settings.py            # Paramètres utilisateur
│   └── components/
│       ├── course_card.py         # Carte cours unifiée (badges + actions)
│       ├── course_quick_actions.py # Actions rapides (compact + full mode)
│       ├── dashboard_card.py      # Carte révision du dashboard
│       ├── pomodoro.py            # Timer Pomodoro
│       ├── qcm_result_card.py     # Carte résultat QCM
│       ├── weak_point_card.py     # Carte lacune
│       ├── command_palette.py     # Palette de commandes (Ctrl+K)
│       ├── fiche_viewer.py        # Viewer de fiche EDN
│       ├── search_bar.py          # Barre de recherche
│       └── ui_kit.py              # Composants réutilisables
└── tests/                         # Tests unitaires (pytest)
```

---

## Fonctionnalités principales

### 1. Révisions espacées (cœur du système)
- Algorithme **SM-2** adapté + intervalles fixes J3/J7/J14/J30
- Chaque cours a un historique de révisions dans SQLite
- Les `ReviewTask` sont des **tâches virtuelles** (pas stockées en DB) générées à la volée par `ReviewService` à partir de l'historique
- `task_id` format : `{course_id}_{context}_{review_type}_{theoretical_due_date_iso}` — la date est **toujours la date théorique**, jamais reportée
- Possibilité de reporter une tâche (postpone depuis `task.due_date`, pas depuis aujourd'hui)

### 2. Dashboard quotidien
- Vue des révisions du jour, triées par priorité
- Validation avec feedback : Rapide / Normal / Difficile / Détailler
- Modale de session (`open_session_feedback_dialog`) : activités réalisées, résultat QCM, catégorie faible, niveau de confiance perçu
- Badge de maîtrise sur chaque carte cours

### 3. Score de maîtrise
- Calcul par `mastery.py` : score 0-100 par cours
- Niveaux : **solide** / **correct** / **fragile** / **critique**
- Basé sur les sessions de révision + compteur de reports
- Influence la priorité dans le dashboard (critique +25, fragile +15, correct +5, solide -10)
- Tables SQLite : `review_history`, `study_sessions`, `qcm_results`

### 4. Intégration Notion (source de vérité)
- Tous les cours EDN sont dans une base Notion
- Synapse lit et écrit via l'API Notion
- **Règles critiques sur les payloads** : toujours utiliser `checkbox(val)`, `notion_date("YYYY-MM-DD")`, `url_prop(url)`, `number_prop(n)` — jamais de valeurs raw Python
- Les propriétés Notion sont toutes référencées via `P.NOM_CONSTANTE` (jamais de strings en dur)
- `update_course_action()` dans `frontend/utils.py` : mise à jour optimiste (local d'abord, puis Notion)

### 5. Intégration Obsidian (bidirectionnel)
- Vault path : `G:\Mon Drive\Médecine\Médecine` (configurable via `OBSIDIAN_VAULT_PATH`)
- Structure vault :
  - Cours EDN : `01 - Cours EDN/{Collège} {emoji}/Cours/{Titre}.md`
  - Lacunes : `08 - Lacunes/Actives|À revoir|Corrigées/{Titre}.md`
- **Au démarrage** (background.py) :
  - `_sync_vault_strict_once()` : nouvelles notes → matching par titre → écrit `notion_id` + `synapse_id` dans frontmatter
  - `_push_missing_obsidian_uris()` : revalide **toutes** les URIs Obsidian dans Notion à chaque démarrage
- **Lacunes** : sync bidirectionnel complet — créer/changer statut dans Synapse déplace physiquement le fichier dans le bon sous-dossier Obsidian

### 6. Gestion des lacunes (Weak Points)
- Créées depuis Synapse, stockées dans SQLite + fichier Obsidian
- Statuts : active → à revoir → résolue / récurrente
- Chaque changement de statut déplace le fichier `.md` dans le bon dossier Obsidian

### 7. Autres features
- **QCM** : saisie de résultats, stockage dans SQLite, stats par cours
- **Planning** : vue calendrier des révisions à venir
- **Externat** : gestion des stages cliniques (table SQLite dédiée)
- **Pomodoro** : timer intégré
- **Google Calendar** : synchronisation des séances de révision
- **Rapport hebdomadaire** : analytics automatiques
- **Graphe de connaissances** : liens entre concepts (builder + modèles)
- **Command palette** : Ctrl+K pour naviguer rapidement
- **PWA** : installable comme app desktop

---

## Flux de démarrage

1. `main.py` démarre NiceGUI sur le port 8082
2. Splash screen avec barre de progression pendant que `DataStore.preload_all_views()` charge les cours depuis Notion
3. Tâches de fond lancées en parallèle :
   - `run_background_tasks()` : sync Obsidian (vault + lacunes)
   - `run_daily_routine()` : calculs quotidiens automatiques
4. Redirect vers le Dashboard une fois le chargement terminé

---

## Base de données SQLite

Fichier : `data/synapse_local.db`

| Table | Contenu |
|---|---|
| `review_history` | Historique de chaque révision (date, type, résultat) |
| `study_sessions` | Sessions enrichies (activités, confiance, temps, QCM, lacune) |
| `qcm_results` | Résultats de QCM par cours |
| `stages` (externat) | Stages cliniques |
| `lacunes` | Lacunes / points faibles |

---

## Configuration (.env)

Variables clés :
- `NOTION_TOKEN` — token d'intégration Notion
- `NOTION_DATABASE_ID` — ID de la base de données des cours
- `MEDICINE_DIR` — répertoire local des PDFs (collège)
- `FAC_DIR` — répertoire local des PDFs (fac/UE)
- `OBSIDIAN_VAULT_PATH` — chemin du vault Obsidian
- `OBSIDIAN_VAULT_NAME` — nom du vault (pour les URIs)
- `GOOGLE_CALENDAR_*` — credentials Google Calendar

---

## Conventions importantes à respecter

1. **Payloads Notion** : toujours `checkbox(val)`, `notion_date("YYYY-MM-DD")`, `url_prop(url)`, `number_prop(n)` — importés depuis `backend/core/notion/payloads.py`
2. **NOTION_PROPS** : toujours `P.NOM_CONSTANTE`, jamais de string en dur
3. **task_id** : `{course_id}_{context}_{review_type}_{theoretical_due_date_iso}` — date **théorique** (jamais la date reportée)
4. **Postpone** : offset calculé depuis `task.due_date` (date effective), pas depuis aujourd'hui
5. **Timezone** : `Indian/Reunion` (défini dans `backend/config/settings.py` comme `APP_TIMEZONE`)
6. **CourseCard** : utiliser le composant unifié `frontend/components/course_card.py` pour toute nouvelle vue liste de cours
7. **COLLEGE_MAPPING** : les collèges Notion ont l'emoji à la **fin** (`Cardiovasculaire ❤️`), pas au début

---

## Ce que Synapse N'est PAS

- Pas une application multi-utilisateur
- Pas connecté à EDNpro ou Hypocampus (pas d'API disponible) — tout est saisi manuellement
- Pas déployé en production — tourne en local uniquement
- Pas un LMS ou un générateur de contenu — c'est un orchestrateur de révisions personnelles
