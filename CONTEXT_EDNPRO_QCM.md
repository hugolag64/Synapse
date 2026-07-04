# Pipeline QCM EDN Pro — Synapse

## Vue d'ensemble

Synapse récupère automatiquement les sessions QCM depuis EDN Pro (Supabase) en arrière-plan, sans intervention manuelle après la configuration initiale. Les sessions sont converties en fichiers markdown, importées en SQLite, et les mauvaises réponses deviennent des lacunes automatiques.

```
EDN Pro (Supabase)
       │
       │  HTTPS / PostgREST
       ▼
  fetcher.py              ← récupère sessions + questions + propositions
       │
       ▼
  converters.py           ← transforme en sessions Synapse + génère weak_points
       │
       ▼
  writer.py               ← écrit data/ai_qcm/capture_ednpro_<date>_<ts>.md
       │
       ▼  [watchdog]
  watcher.py              ← détecte le fichier, déclenche l'import
       │
       ▼
  service.py (ai_qcm)     ← parse + mappe sur cours Notion + insère SQLite
       │
       ├── qcm_results     (sessions)
       └── weak_points     (lacunes auto depuis mauvaises réponses)
```

---

## 1. Configuration initiale (une seule fois)

```bash
python scripts/capture_qcm.py init-ednpro
```

- Ouvre EDN Pro dans Chrome
- F12 → Console → colle le snippet JS affiché
- Copie la sortie `SYNAPSE:{...}` → colle dans le terminal
- Sauvegarde `access_token` + `refresh_token` dans `data/ednpro_credentials.json`

Après ça : **aucune action manuelle nécessaire**. Le token est renouvelé automatiquement.

---

## 2. Credentials (`data/ednpro_credentials.json`)

```json
{
  "base_url":      "https://hiwarmfutyzsdlmqicvc.supabase.co",
  "apikey":        "<anon_key_publique>",
  "bearer_token":  "<access_token JWT ~1h>",
  "refresh_token": "<refresh_token rotatif>",
  "user_id":       "abc3070a-4620-4465-bb45-5ba71e84c294"
}
```

- `apikey` : clé anonyme publique (embarquée dans le JS d'EDN Pro, non secrète)
- `bearer_token` : JWT d'accès, expire ~1h — **renouvelé automatiquement**
- `refresh_token` : token rotatif (change à chaque refresh, durée plusieurs semaines)
- `user_id` : UUID Supabase de l'utilisateur (fixe)

> **Gitignore** : ce fichier ne doit pas être commité.

Renouvellement automatique dans `SupabaseFetcher._get_valid_token()` :
- Décode le JWT (base64) → lit le champ `exp`
- Si expiration dans moins de 60s → POST `/auth/v1/token?grant_type=refresh_token`
- Sauvegarde le nouveau couple `(access_token, refresh_token)`

---

## 3. Base Supabase EDN Pro — tables utilisées

| Table | Rôle | Champs clés |
|-------|------|-------------|
| `training_sessions` | Sessions de travail complétées | `id`, `user_id`, `question_ids[]`, `answer_states{}`, `score`, `total_questions`, `completed`, `completed_at`, `resume_path` |
| `objective_questions` | Texte des questions | `id`, `objective_id`, `question_text`, `explanation`, `type`, `tags` |
| `objective_question_propositions` | Choix de réponses (A/B/C/D) | `id`, `question_id`, `label`, `proposition_text`, `is_correct` |
| `courses` | Noms des cours | `id`, `name` |
| `questions` | Questions liées aux cours (autre format) | `id`, `course_id`, `item_number` |

### Structure `answer_states`

Champ JSON dans `training_sessions`. Clé = UUID de question, valeur = résultat utilisateur :

```json
{
  "037109d5-c8b6-4c34-bbbe-725dfb943566": {
    "correct":       true,
    "verified":      true,
    "selected":      ["85c1ba53-47d2-475c-8143-22db5b38d32b"],
    "qrocText":      "",
    "tcsValue":      null,
    "kfpAnswers":    {},
    "pointsFraction": 1
  }
}
```

- `selected` : liste d'UUIDs des propositions cochées par l'utilisateur
- `correct` : résultat global de la question (calculé par EDN Pro)
- `verified` : `true` si l'utilisateur a validé la réponse (question réellement traitée)

### Déduction du cours

Le `resume_path` de la session contient le cours :
```
/objective-session/multi?courses=fd34d0d2-f0b9-4cf6-b129-789b87117697&limit=5&types=qcm%2Cqre%2Cqroc
```

Extraction par regex : `r"courses=([a-f0-9\-]{36})"` → UUID du cours → requête `courses?id=eq.<uuid>` → `name`.

L'`item_number` est obtenu via `questions?course_id=eq.<uuid>&limit=1` (table `questions` différente d'`objective_questions`).

---

## 4. Fetch (fetcher.py — `SupabaseFetcher`)

### `fetch_training_sessions(limit=500)`

1. `GET training_sessions` filtré `completed=true&user_id=eq.<uid>&order=completed_at.desc`
2. Batch fetch `courses` pour les UUIDs extraits des `resume_path`
3. Batch fetch `questions` pour récupérer les `item_number` par cours
4. Collecte tous les `question_ids` + clés de `answer_states` de toutes les sessions
5. Appelle `fetch_questions_and_propositions()` avec la liste dédupliquée
6. Enrichit chaque session : `_course_name`, `_item_number`, `_questions`

### `fetch_questions_and_propositions(question_ids)`

- Traitement par lots de 200 UUIDs (limite URL PostgREST)
- `GET objective_questions?id=in.(uuid1,uuid2,...)` → texte + explication + type
- `GET objective_question_propositions?question_id=in.(uuid1,...)` → choix A/B/C/D

Construit un dict `{question_uuid: {question_text, explanation, type, tags, propositions: [...]}}`.

Croise avec `answer_states.selected` → marque `was_selected: true/false` sur chaque proposition.

---

## 5. Conversion (converters.py)

### `extract_sessions_ednpro(rows)`

Pour chaque session :

| Champ Synapse | Source |
|---------------|--------|
| `course_title` | `_course_name` (enrichi) ou `label` de la session |
| `item_number` | `_item_number` (enrichi) |
| `score_raw` | `"3/5"` reconstruit depuis `answer_states` ou champ `score` |
| `score_percent` | calculé `correct/total × 100` |
| `session_type` | extrait de `resume_path` (`types=qcm%2Cqre`) → `"QCM"`, `"QRE"`, etc. |
| `questions` | liste des questions avec propositions + résultat utilisateur |
| `weak_points` | **généré automatiquement** depuis les mauvaises réponses |

### Génération automatique des `weak_points`

`_build_weak_points_from_questions()` : pour chaque question où `user_verified=true` et `user_correct=false` :

```json
{
  "category": "Item 339",
  "detail":   "Concernant la CORONAROGRAPHIE... | Correct: A, B, D, E — Choisi: B, C, D, E",
  "severity": 2
}
```

- `category` : `"Item {item_number}"` ou titre du cours
- `detail` : début du texte de question (150 chars) + labels corrects + labels choisis
- `severity` : `2` (valeur int attendue par le parser)

---

## 6. Format de fichier (`data/ai_qcm/capture_ednpro_<date>_<ts>.md`)

```markdown
---json
{
  "synapse_version": 1,
  "date": "2026-06-21",
  "platform": "EDNpro",
  "session_type": "QCM",
  "sessions": [
    {
      "course_title":    "Syndrome coronarien aigu (339)",
      "item_number":     "339",
      "score_raw":       "3/5",
      "score_percent":   60.0,
      "total_questions": 5,
      "correct_answers": 3,
      "wrong_answers":   2,
      "session_type":    "QCM",
      "error_types":     [],
      "weak_points": [
        {
          "category": "Item 339",
          "detail":   "Concernant la CORONAROGRAPHIE... | Correct: A, B, D, E — Choisi: B, C, D, E",
          "severity": 2
        }
      ],
      "questions": [
        {
          "question_text": "Quels sont les TRAITEMENTS AU LONG COURS après un SCA ?",
          "explanation":   "BASIC après SCA : Bêtabloquant, Aspirine...",
          "type":          "qcm",
          "tags":          ["BASIC"],
          "user_correct":  true,
          "user_verified": true,
          "propositions": [
            { "label": "A", "text": "IEC", "is_correct": true,  "was_selected": true  },
            { "label": "B", "text": "Statine", "is_correct": true,  "was_selected": true  },
            { "label": "C", "text": "...",     "is_correct": false, "was_selected": false }
          ]
        }
      ]
    }
  ]
}
---

# Import automatique EDNpro — 2026-06-21
```

> Le champ `questions` est stocké dans le fichier mais **ignoré par le parser actuel** (`parser.py` ne le lit pas). Il est disponible pour un futur module de révision.

---

## 7. Import (watcher.py + service.py)

### Watcher (`watchdog`)

Démarre au 1er cycle de `background.py`. Surveille `data/ai_qcm/` en temps réel.

Dès qu'un `.md` valide est déposé :
1. Attente 2s (debounce)
2. Crée `<fichier>.importing` (sentinel anti-doublon)
3. Appelle `import_file(path, courses)`
4. Succès → déplace vers `data/ai_qcm/imported/`
5. Échec → écrit `<fichier>.error` avec le message d'erreur
6. Supprime le sentinel

### Service (`import_file`)

Pour chaque session du fichier :

1. **Matching cours** (`_find_course`) :
   - `item_number` exact → titre exact → titre partiel → fuzzy (fuzzywuzzy ≥75%)
   - Retourne `course_id` Notion si trouvé

2. **Insertion SQLite** (`local_store.add_qcm_session_full`) :
   - Table `qcm_results` : résultat de la session (score, date, plateforme)

3. **Lacunes** :
   - Si `weak_points` présents dans le fichier → insérés tels quels dans `weak_points` (table SQLite)
   - Si session ratée ET aucun `weak_point` → lacune automatique générique `"QCM raté — 3/5"`

---

## 8. Déduplication (`data/ednpro_sync_state.json`)

Évite de recréer un fichier à chaque lancement si aucune nouvelle session.

```json
{
  "session_ids": [
    "uuid-session-1",
    "uuid-session-2"
  ]
}
```

Logique dans `_fetch_ednpro_background()` :

```
known_ids  = session_ids du fichier state
current_ids = IDs remontés par Supabase

new_ids = current_ids - known_ids

si new_ids == vide  → log "aucune nouvelle session", pas de fichier
si new_ids non vide → filtre rows sur new_ids → écrit fichier → met à jour state
```

---

## 9. Cycle background (`background.py`)

```
Démarrage (cycle 1) :
  └── _fetch_ednpro_background()     ← fetch EDN Pro si configuré

Toutes les 60 min (cycle % 12 == 0) :
  └── _fetch_ednpro_background()     ← vérifie les nouvelles sessions

Toujours (cycle 1) :
  └── start_watcher()                ← démarre la surveillance de data/ai_qcm/
```

---

## 10. Fichiers impliqués

| Fichier | Rôle |
|---------|------|
| `backend/core/network_capture/fetcher.py` | Authentification Supabase, fetch sessions/questions/propositions |
| `backend/core/network_capture/converters.py` | Transformation données EDN Pro → format Synapse, génération weak_points |
| `backend/core/network_capture/writer.py` | Écriture du fichier markdown dans `data/ai_qcm/` |
| `backend/core/ai_qcm/watcher.py` | Watchdog sur `data/ai_qcm/`, déclenche l'import automatiquement |
| `backend/core/ai_qcm/parser.py` | Parse le bloc `---json` du fichier markdown |
| `backend/core/ai_qcm/service.py` | Mappe cours Notion, insère en SQLite, gère les lacunes |
| `backend/core/reviews/local_store.py` | Couche SQLite (`qcm_results`, `weak_points`) |
| `backend/core/background.py` | Boucle async, appelle `_fetch_ednpro_background()` |
| `scripts/capture_qcm.py` | CLI : `init-ednpro`, `fetch-ednpro`, `discover-tables` |
| `data/ednpro_credentials.json` | Tokens Supabase (gitignored) |
| `data/ednpro_sync_state.json` | IDs des sessions déjà exportées (déduplication) |
| `data/ai_qcm/` | Inbox : fichiers en attente d'import |
| `data/ai_qcm/imported/` | Fichiers traités |
| `data/synapse_local.db` | Base SQLite (`qcm_results`, `weak_points`) |

---

## 11. Limites actuelles

- **`questions` ignoré par le parser** : le champ `questions` (détail de chaque Q+R) est dans le fichier mais non exploité côté Synapse UI. Disponible pour un futur module de révision question par question.
- **2 sessions seulement** (test) : limite actuelle du compte EDN Pro utilisé. En production avec plus de sessions, le batch fetch par lots de 200 prend en charge le volume.
- **`item_number` absent de `objective_questions`** : récupéré indirectement via `questions?course_id=eq.<uuid>` (table différente).
- **Types QRE/QROC** : `answer_states` peut contenir `qrocText` (réponse texte libre) — non exploité dans les `weak_points` actuellement.
