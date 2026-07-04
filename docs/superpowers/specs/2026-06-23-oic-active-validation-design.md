# Spec — Validation active des OIC LiSA par IA locale

**Date :** 2026-06-23  
**Statut :** remplacé par `2026-07-04-oic-anythingllm-validation-design.md` (jamais implémenté — remplacé par une approche AnythingLLM/RAG avec support QCM)  
**Scope v1 :** évaluation IA seule (répétition espacée en v2)

---

## Contexte

Les OIC (Objectifs Intermédiaires de Connaissance) LiSA sont actuellement validés par une case à cocher binaire (`mastered 0/1`). Cette validation passive repose sur l'auto-évaluation et ne garantit pas la maîtrise réelle.

L'objectif est de transformer chaque OIC en une mini-évaluation : l'étudiant répond en texte libre, un LLM local corrige la réponse contre des critères de connaissance générés automatiquement, et un niveau de maîtrise progressif (0→5) est maintenu.

---

## Architecture globale

```
Approche C — pipeline 2 appels Ollama + cache critères SQLite

Clic "Évaluer" sur un OIC
  └─ Critères en cache SQLite ?
       oui → Appel 2 seulement (évaluation)
       non → Appel 1 : génération critères + Appel 2 : évaluation
```

Quatre fichiers touchés : un nouveau module backend, une nouvelle table SQLite, un nouveau dialog frontend, deux ajouts dans le dialog existant.

---

## Modèle Ollama

**Recommandé : `mistral:7b`** (4.1 GB, excellent français, bon médical)  
Fallback : `llama3.2:3b` (2.0 GB) si mémoire limitée.

**Setup :** `ollama pull mistral:7b`  
**API :** REST locale sur `http://localhost:11434` — pas de SDK, `requests` suffit.

Le modèle est configurable via une constante dans `evaluator.py`. Si Ollama ne répond pas, `OllamaUnavailableError` est levée et l'UI affiche un message avec la commande de setup.

---

## Backend — `backend/core/lisa/evaluator.py` (nouveau)

### Génération de la question affichée à l'étudiant

La question est une transformation locale de l'intitulé OIC — pas d'appel LLM. Règle : si l'intitulé commence par "Connaître", on le remplace par "Quels sont les / Quelle est la…" via une correspondance simple. Sinon, on préfixe par "Expliquez : ". Les critères restent **cachés** jusqu'à la correction — l'étudiant ne voit que la question, pas les attendus.

### Interface publique

```python
class OllamaUnavailableError(Exception): ...

def generate_criteria(intitule: str, rang: str) -> list[str]:
    """
    Appel 1 : génère 4-7 critères de connaissance pour un OIC.
    Timeout 30s. Retry une fois si JSON invalide.
    Dégradé : retourne [f"Connaître {intitule}"] si 2 échecs.
    """

def evaluate_response(
    intitule: str,
    rang: str,
    criteria: list[str],
    student_response: str,
) -> EvalResult:
    """
    Appel 2 : évalue la réponse étudiant contre les critères.
    Timeout 45s.
    """

@dataclass
class EvalResult:
    verdict: Literal["correct", "partial", "incorrect"]
    score: int                    # 0-100
    elements_corrects: list[str]
    elements_manquants: list[str]
    explication: str
    rappel_cours: str
```

### Prompt 1 — Génération des critères

```
Tu es un enseignant en médecine française (EDN/ECN).

OIC (Objectif Intermédiaire de Connaissance) :
"{intitule}"
Rang : {rang}

Génère une liste de 4 à 7 critères de connaissance précis et concis
que doit maîtriser un étudiant en médecine pour valider cet objectif.
Réponds UNIQUEMENT avec un tableau JSON de strings.
Exemple : ["critère 1", "critère 2", "critère 3"]
```

### Prompt 2 — Évaluation

```
Tu es un correcteur médical pour l'EDN (Examen Classant National).

OIC : "{intitule}" — Rang {rang}
Critères attendus : {criteria_json}
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

Les deux prompts demandent du JSON pur. Si `json.loads()` échoue (modèle ayant ajouté du texte), on tente `re.search(r'\{.*\}', response, re.DOTALL)` pour extraire le JSON. Si toujours invalide, retry une fois. Si le 2e essai échoue aussi : `EvalResult(verdict="incorrect", score=0, explication="Erreur de parsing IA")`.

---

## SQLite — migrations et CRUD

### Migration `lisa_oic`

```sql
ALTER TABLE lisa_oic ADD COLUMN oic_level    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lisa_oic ADD COLUMN criteria_json TEXT;
```

- `oic_level` : 0=non vu, 1=échec, 2=fragile, 3=en acquisition, 4=acquis, 5=maîtrisé
- `criteria_json` : liste de critères sérialisée en JSON, générée au premier appel Ollama

### Nouvelle table `oic_attempts`

```sql
CREATE TABLE IF NOT EXISTS oic_attempts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    oic_id            INTEGER NOT NULL REFERENCES lisa_oic(id),
    question          TEXT    NOT NULL,
    reponse           TEXT    NOT NULL,
    verdict           TEXT    NOT NULL,
    score             INTEGER NOT NULL,
    elements_corrects TEXT    NOT NULL DEFAULT '[]',
    elements_manquants TEXT   NOT NULL DEFAULT '[]',
    explication       TEXT,
    rappel_cours      TEXT,
    attempted_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oic_attempts_oic ON oic_attempts(oic_id);
```

### Fonctions CRUD (`local_store.py`)

```python
def get_oic_criteria(oic_id: int) -> list[str] | None
def save_oic_criteria(oic_id: int, criteria: list[str]) -> None
def save_oic_attempt(oic_id: int, attempt: dict) -> int      # retourne l'id
def get_oic_attempts(oic_id: int) -> list[sqlite3.Row]
def update_oic_level(oic_id: int, new_level: int) -> None
```

La migration est ajoutée dans `init_db()` via la fonction `_migrate_oic_active_validation()` comme les migrations existantes.

---

## Logique de scoring — évolution de `oic_level`

| Score | Verdict | Règle niveau |
|-------|---------|--------------|
| ≥ 80 % | correct | `level = min(5, level + 1)` |
| 50–79 % | partial | `level = max(0, level - 1)` si level < 3, sinon inchangé |
| < 50 % | incorrect | `level = max(0, level - 1)` |

**Maîtrisé (niveau 5) :** 3 tentatives consécutives avec score ≥ 80 %. Vérifié en regardant les 3 derniers `oic_attempts` du même `oic_id`.

Le champ `mastered` (binaire) dans `lisa_oic` reste contrôlé exclusivement par la case à cocher manuelle dans `lisa_dialog.py` — les deux systèmes coexistent sans interférence.

---

## Frontend — `frontend/components/oic_eval_dialog.py` (nouveau)

### Point d'entrée

```python
def open_oic_eval_dialog(oic: sqlite3.Row, course_id: str) -> None
```

### Layout

```
┌────────────────────────────────────────────────────────────┐
│  OIC-223-04-A  ·  Rang A                              [×]  │
│  Critères diagnostiques de l'endocardite infectieuse       │
├────────────────────────────────────────────────────────────┤
│  QUESTION                                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Quels sont les critères diagnostiques de             │  │
│  │ l'endocardite infectieuse ?                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  VOTRE RÉPONSE                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ (textarea libre, min 4 lignes)                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                    [Corriger →]             │
├────────────────────────────────────────────────────────────┤
│  Score : 80 %  ·  PARTIELLEMENT ACQUIS (orange)            │
│  ✓ hémocultures positives  ✓ critères de Duke              │
│  ✗ échocardiographie TTE/ETO                               │
│  Explication : L'écho est indispensable pour visualiser…   │
│  Rappel : Les critères de Duke sont…                       │
│                                                             │
│  [Réessayer]   [Fermer]   Historique : 3 tentatives ▾      │
└────────────────────────────────────────────────────────────┘
```

### États de la dialog

1. **Chargement critères** — spinner "Génération de la question…" (premier appel, mis en cache ensuite)
2. **Question prête** — textarea + bouton Corriger actif
3. **Correction en cours** — bouton désactivé + spinner inline
4. **Résultat** — verdict coloré + détails + bouton Réessayer + historique dépliable
5. **Erreur Ollama** — message "Ollama inaccessible — lancez : `ollama serve` puis `ollama pull mistral:7b`"

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

## Hors scope v1

- Répétition espacée / dates de réévaluation calculées automatiquement
- Dashboard statistiques OIC (par collège, par rang)
- Fiches d'erreur exportées vers Obsidian
- Multi-formulations de question
- Cas cliniques générés
- Génération des critères depuis le texte du corps de la fiche LiSA

---

## Fichiers modifiés

| Fichier | Type |
|---|---|
| `backend/core/lisa/evaluator.py` | Nouveau |
| `backend/core/reviews/local_store.py` | +2 colonnes, +1 table, +5 fonctions, +1 migration |
| `frontend/components/oic_eval_dialog.py` | Nouveau |
| `frontend/components/lisa_dialog.py` | +bouton Évaluer, +badge niveau par OIC |
