# Spec — Validation active des OIC LiSA via AnythingLLM (QCM + ouvertes)

**Date :** 2026-07-04
**Statut :** validé
**Remplace :** `2026-06-23-oic-active-validation-design.md` (jamais implémenté — spec Ollama sans RAG, texte libre uniquement)

---

## Contexte

Les OIC (Objectifs Intermédiaires de Connaissance) LiSA sont actuellement validés par une case à cocher binaire (`mastered` 0/1). Cette validation passive repose sur l'auto-évaluation et ne garantit pas la maîtrise réelle.

L'utilisateur a installé AnythingLLM en local et y a importé l'ensemble de ses collèges/items (un workspace par collège, contenant les PDF de cours nommés `ITEM X - COURS Y`, identiques aux documents Synapse). L'objectif est de transformer chaque OIC en mini-évaluation grounded sur cette base documentaire : 3 à 5 questions (QCM et/ou ouvertes) générées par IA, réponse dans une fenêtre Synapse (sans jamais basculer vers l'interface AnythingLLM), correction immédiate, et progression d'un niveau de maîtrise (0→5) par OIC.

Ceci remplace le spec du 23/06/2026 qui prévoyait Ollama en appel direct (sans RAG) et le texte libre uniquement. Ce spec est obsolète et remplacé par le présent document.

---

## Architecture globale

```
Approche A — appels stateless "query" vers AnythingLLM + cache mémoire du mapping workspace

Clic "Évaluer" sur un OIC (lisa_dialog.py)
  └─ Résoudre le workspace AnythingLLM du collège du cours
       (cache mémoire ; sinon GET /api/v1/workspaces + fuzzy match sur le nom normalisé)
       └─ Appel "query" #1 : génère 3-5 questions (QCM + ouvertes), grounded RAG sur le workspace
            └─ Dialog quiz : une question à la fois
                 ├─ QCM   → correction locale instantanée (correct_index caché dans la réponse #1)
                 └─ Ouverte → Appel "query" #2 (par question répondue) : évalue vs les critères + documents
            └─ Feedback affiché immédiatement après chaque question
       └─ Score de session agrégé → mise à jour progressive de oic_level (0→5)
```

Appels stateless choisis plutôt qu'un thread conversationnel par tentative : chaque appel embarque tout le contexte nécessaire dans le prompt, ce qui évite la gestion d'état côté AnythingLLM (création/nettoyage de threads) pour un bénéfice marginal.

---

## API AnythingLLM

- Base URL configurable (défaut `http://localhost:3001`), API v1.
- Authentification : `Authorization: Bearer <clé API>` (clé système générée dans le dashboard admin AnythingLLM).
- Endpoints utilisés :
  - `GET /api/v1/workspaces` — liste des workspaces (résolution du mapping collège → slug).
  - `POST /api/v1/workspace/{slug}/chat` avec `{"message": "...", "mode": "query"}` — génération de questions et correction des réponses ouvertes.
- Client HTTP : `requests` (convention du projet, comme `lisa/scraper.py`), appels sync enveloppés en `asyncio.to_thread(...)` côté UI (comme `cas_login` dans `settings.py`).

---

## Résolution du workspace AnythingLLM

Les noms de collèges Synapse contiennent des emojis (ex: `"Cardiovasculaire ❤️"`), donc pas de dérivation de slug fiable par simple transformation de chaîne.

1. Au premier besoin dans la session applicative (le cache mémoire est vide au démarrage et n'est jamais invalidé automatiquement ensuite — un redémarrage de l'app suffit à le rafraîchir si des workspaces changent), appel `GET /api/v1/workspaces`.
2. Pour chaque collège, matching fuzzy (librairie `fuzzywuzzy`, déjà utilisée dans `backend/core/ai_qcm/parser.py`) entre le nom du collège normalisé (minuscule, sans emoji/accents, via `COLLEGE_MAPPING` si applicable) et le nom de chaque workspace, normalisé de la même façon.
3. Résultat mis en cache mémoire (dict `college_name → workspace_slug`) pour la durée de la session app.
4. Si aucun match au-dessus d'un seuil de confiance (ex: 80), lever `WorkspaceNotFoundError` avec le nom du collège recherché, affiché à l'utilisateur pour qu'il vérifie le nom du workspace dans AnythingLLM.

---

## Backend — `backend/core/lisa/anythingllm_client.py` (nouveau)

Client HTTP fin, responsabilité unique : parler à l'API AnythingLLM.

```python
class AnythingLLMUnavailableError(Exception): ...
class WorkspaceNotFoundError(Exception): ...

def list_workspaces() -> list[dict]:
    """GET /api/v1/workspaces. Lève AnythingLLMUnavailableError si injoignable."""

def resolve_workspace_slug(college_name: str) -> str:
    """Résout le slug via cache mémoire + fuzzy match. Lève WorkspaceNotFoundError si aucun match."""

def query_workspace(slug: str, message: str) -> str:
    """POST /api/v1/workspace/{slug}/chat, mode='query'. Timeout 45s. Retourne le texte brut de la réponse."""
```

## Backend — `backend/core/lisa/evaluator.py` (nouveau)

Logique domaine : construction des prompts, parsing, scoring. Ne connaît pas les détails HTTP (délègue à `anythingllm_client`).

```python
@dataclass
class Question:
    type: Literal["qcm", "ouverte"]
    enonce: str
    options: list[str] | None = None       # QCM uniquement
    correct_index: int | None = None       # QCM uniquement, caché de l'UI jusqu'à réponse
    criteres: list[str] | None = None      # ouverte uniquement, caché de l'UI

@dataclass
class EvalResult:
    verdict: Literal["correct", "partial", "incorrect"]
    score: int                    # 0-100
    elements_corrects: list[str]
    elements_manquants: list[str]
    explication: str
    rappel_cours: str

def generate_questions(course_title: str, intitule: str, rang: str, workspace_slug: str) -> list[Question]:
    """
    Appel query #1. Demande 3-5 questions mixtes QCM/ouvertes en JSON strict.
    Retry une fois si JSON invalide (extraction regex de secours).
    Dégradé : une seule question ouverte générique si échec double.
    """

def evaluate_open_answer(
    question: Question, student_response: str, workspace_slug: str,
) -> EvalResult:
    """Appel query #2, un par question ouverte répondue. Timeout 45s."""

def grade_qcm(question: Question, selected_index: int) -> EvalResult:
    """Correction locale instantanée, pas d'appel réseau."""
```

### Prompt — Génération des questions (appel #1)

```
Tu es un enseignant en médecine française (EDN/ECN).
Cours : "{course_title}"
OIC (Objectif Intermédiaire de Connaissance) : "{intitule}"
Rang : {rang}

En te basant sur les documents de ce workspace concernant ce cours,
génère entre 3 et 5 questions pour tester la maîtrise de cet OIC,
en mélangeant QCM et questions ouvertes.

Réponds UNIQUEMENT avec ce JSON (pas de texte autour) :
[
  {"type": "qcm", "enonce": "...", "options": ["...", "...", "..."], "correct_index": 0, "explication": "..."},
  {"type": "ouverte", "enonce": "...", "criteres": ["critère 1", "critère 2"]}
]
```

### Prompt — Évaluation d'une réponse ouverte (appel #2)

```
Tu es un correcteur médical pour l'EDN (Examen Classant National).
Base-toi sur les documents de ce workspace pour vérifier l'exactitude.

Question : "{enonce}"
Critères attendus : {criteres_json}
Réponse de l'étudiant : "{student_response}"

Évalue si la réponse couvre les critères attendus.
Réponds UNIQUEMENT avec ce JSON (pas de texte autour) :
{
  "verdict": "correct" | "partial" | "incorrect",
  "score": <entier 0-100>,
  "elements_corrects": ["..."],
  "elements_manquants": ["..."],
  "explication": "<phrase courte>",
  "rappel_cours": "<rappel essentiel en 1-3 phrases>"
}
```

### Parsing robuste

Identique à l'ancien spec : `json.loads()` en priorité, sinon extraction `re.search(r'[\[{].*[\]}]', response, re.DOTALL)`. Si le second essai échoue aussi, dégradé (question générique unique en génération ; `EvalResult(verdict="incorrect", score=0, explication="Erreur de parsing IA")` en évaluation).

---

## SQLite — migrations et CRUD

### Migration `lisa_oic`

```sql
ALTER TABLE lisa_oic ADD COLUMN oic_level INTEGER NOT NULL DEFAULT 0;
```

- `oic_level` : 0=non vu, 1=échec, 2=fragile, 3=en acquisition, 4=acquis, 5=maîtrisé

### Nouvelle table `oic_attempts`

```sql
CREATE TABLE IF NOT EXISTS oic_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    oic_id          INTEGER NOT NULL REFERENCES lisa_oic(id),
    session_score   INTEGER NOT NULL,        -- 0-100, moyenne des scores par question de la session
    questions_json  TEXT    NOT NULL,        -- questions posées + réponses données + corrections (historique complet)
    attempted_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oic_attempts_oic ON oic_attempts(oic_id);
```

La migration est ajoutée dans `init_db()` via `_migrate_oic_anythingllm_validation()`, comme les migrations existantes.

### Fonctions CRUD (`local_store.py`)

```python
def save_oic_attempt(oic_id: int, session_score: int, questions_json: str) -> int   # retourne l'id
def get_oic_attempts(oic_id: int, limit: int = 10) -> list[sqlite3.Row]
def update_oic_level(oic_id: int, new_level: int) -> None
```

Le champ `mastered` (binaire) dans `lisa_oic` reste contrôlé exclusivement par la case à cocher manuelle dans `lisa_dialog.py` — les deux systèmes coexistent sans interférence.

---

## Logique de scoring — session et progression de `oic_level`

**Score de session** : moyenne des scores par question (QCM = 100 si correct sinon 0 ; question ouverte = `score` retourné par `evaluate_open_answer`).

| Score session | Règle niveau |
|-------|--------------|
| ≥ 80 % | `level = min(5, level + 1)` |
| 50–79 % | inchangé si `level ≥ 3`, sinon `level = max(0, level - 1)` |
| < 50 % | `level = max(0, level - 1)` |

**Maîtrisé (niveau 5)** : atteint automatiquement quand la règle ci-dessus y mène après 3 tentatives consécutives ≥ 80 % (vérifié en lisant les 3 derniers `oic_attempts` du même `oic_id`).

---

## Frontend — `frontend/components/oic_eval_dialog.py` (nouveau)

### Point d'entrée

```python
def open_oic_eval_dialog(oic: sqlite3.Row, course_id: str, course_title: str) -> None
```

### Layout (état "question en cours")

```
┌────────────────────────────────────────────────────────────┐
│  OIC-223-04-A · Rang A                    Question 2/4  [×] │
├────────────────────────────────────────────────────────────┤
│  Quels sont les critères diagnostiques de l'endocardite    │
│  infectieuse ?                                              │
│                                                               │
│  ○ Critères de Duke                                         │
│  ○ Score de Wells                                            │
│  ○ Critères de Light                                         │
│                                    [Valider →]               │
├────────────────────────────────────────────────────────────┤
│  ✓ Correct !  Les critères de Duke sont la référence...     │
│                                    [Question suivante →]     │
└────────────────────────────────────────────────────────────┘
```

Pour une question ouverte, la zone d'options est remplacée par un textarea libre (min 4 lignes).

### États de la dialog

1. **Génération** — spinner "Génération des questions…" (appel #1)
2. **Question X/N prête** — QCM = radio buttons, ouverte = textarea + bouton "Valider" actif
3. **Correction en cours** (ouverte uniquement) — bouton désactivé + spinner inline le temps de l'appel #2 ; QCM = correction instantanée sans spinner
4. **Feedback immédiat** — verdict coloré + explication (+ éléments corrects/manquants et rappel pour les ouvertes) + bouton "Question suivante"
5. **Récapitulatif final** — score global de session, évolution du niveau ("Niveau 2 → 3"), badge mis à jour, boutons **Recommencer** (régénère un nouveau jeu de questions) / **Fermer**
6. **Erreur AnythingLLM injoignable** — message "AnythingLLM inaccessible sur `{url}` — vérifiez qu'il est lancé"
7. **Erreur workspace introuvable** — message "Aucun workspace AnythingLLM ne correspond au collège « {collège} » — vérifiez son nom"

### Verdict couleur

| Verdict | Score | Badge | Couleur |
|---------|-------|-------|---------|
| correct | ≥ 80 % | ACQUIS | `green-600` |
| partial | 50–79 % | PARTIEL | `orange-500` |
| incorrect | < 50 % | ÉCHEC | `red-600` |

---

## Frontend — modifications `lisa_dialog.py` (existant)

Deux ajouts par OIC dans `_render_oics()` :

1. **Bouton "Évaluer"** (icône `school`, dense, flat) à droite de la checkbox — ouvre `oic_eval_dialog`
2. **Badge de niveau** (petit, coloré) après l'intitulé :
   - Niveau 0 : rien (ne pas polluer la vue)
   - Niveaux 1–2 : badge rouge/orange (ex: "Lvl 1")
   - Niveaux 3–4 : badge cyan
   - Niveau 5 : badge vert "★ Maîtrisé"

Le badge se met à jour après la fermeture de `oic_eval_dialog` via un callback ou un refresh de la liste.

---

## Settings — nouvelle section "AnythingLLM"

Dans `frontend/pages/settings.py`, nouvelle `ui.expansion("AnythingLLM")` suivant le pattern existant (ex: section "LiSA / UNESS") :

- Champ URL (`ui.input`, défaut `http://localhost:3001`)
- Champ clé API (`ui.input` masqué, type password)
- Bouton "Tester la connexion" → appelle `list_workspaces()` en arrière-plan (`asyncio.to_thread`), affiche le nombre de workspaces trouvés ou l'erreur via `ui.notify(...)`

Nouveaux champs dans `Settings` (`backend/config/settings.py`) :

```python
anythingllm_url: str = Field("http://localhost:3001", alias='ANYTHINGLLM_URL')
anythingllm_api_key: str = Field("", alias='ANYTHINGLLM_API_KEY')
```

Persistés via `_write_env_var(key, value)`, comme les autres settings.

---

## Hors scope v1

- Répétition espacée / dates de réévaluation calculées automatiquement
- Dashboard statistiques OIC (par collège, par rang)
- Fiches d'erreur exportées vers Obsidian
- Cas cliniques générés
- Mapping manuel collège → workspace en settings (le matching automatique doit suffire ; à revisiter si le fuzzy matching échoue trop souvent en pratique)
- Cache des questions générées entre tentatives (chaque tentative regénère un jeu frais, intentionnellement, pour éviter l'apprentissage par cœur du format)

---

## Fichiers modifiés

| Fichier | Type |
|---|---|
| `backend/core/lisa/anythingllm_client.py` | Nouveau |
| `backend/core/lisa/evaluator.py` | Nouveau |
| `backend/core/reviews/local_store.py` | +1 colonne (`oic_level`), +1 table (`oic_attempts`), +3 fonctions, +1 migration |
| `backend/config/settings.py` | +2 champs (`anythingllm_url`, `anythingllm_api_key`) |
| `frontend/components/oic_eval_dialog.py` | Nouveau |
| `frontend/components/lisa_dialog.py` | +bouton Évaluer, +badge niveau par OIC |
| `frontend/pages/settings.py` | +section "AnythingLLM" |
