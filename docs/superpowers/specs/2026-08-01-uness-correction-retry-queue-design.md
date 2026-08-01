# Design — File d'attente persistante des corrections UNESS en échec

## Contexte et objectif

Deux bugs constatés sur le pipeline de correction automatique Gemini (voir
`2026-07-31-uness-gemini-autocorrect-design.md`) :

1. **Échec total silencieux** : si un quiz d'un partiel échoue (JSON tronqué par
   Gemini, image manquante...) alors que ses voisins réussissent, l'échec finit
   dans `result["errors"]` mais le pipeline automatique ("🚀 Tout faire") ne le
   signalait pas tant qu'au moins un quiz avait réussi — corrigé le 2026-08-01
   (notification systématique, cf. `_gemini_partial_failure_message` dans
   `frontend/pages/annales.py`), mais sans mémoire persistante ni retry : une fois
   la notification disparue, il faut retrouver et recorriger le fichier à la main.
2. **Échec partiel non détecté** : un quiz peut être "réussi" au sens du code
   (JSON valide, converti, importé) tout en contenant **moins de questions que le
   HTML source** — Gemini en a tronqué certaines sans faire échouer le parsing JSON.
   Exemple constaté : DP1 a 6 questions sur UNESS, Synapse n'en a importé que 5.
   Rien ne compare aujourd'hui le nombre de questions renvoyées au nombre réel.

Objectif : détecter les deux cas, les rendre visibles (badge + liste dans
l'UI), et les retenter automatiquement un nombre borné de fois avant de
demander une action manuelle — sans construire de nouvelle infrastructure de
scheduling (réutilise la boucle de fond existante).

Décisions validées avec l'utilisateur avant ce design :
- Retry automatique **borné** (3 tentatives, délai croissant), pas illimité —
  évite de retenter indéfiniment un échec structurel qui ne se corrigera jamais
  tout seul (ex. quiz trop volumineux pour Gemini) et de gaspiller des tokens.
- Un quiz **incomplet** (question manquante) n'est **pas importé partiellement** :
  rien n'est écrit tant que le compte de questions ne correspond pas — plus
  simple que de gérer le remplacement d'une session déjà importée à 5/6.
- L'UI vit dans la page Annales existante (bandeau en haut de `/annales`), pas
  une nouvelle page dédiée — plus un badge sur l'item de nav "Annales".

## Architecture

Aucune nouvelle infrastructure : la table de suivi vit dans le même SQLite que
`uness_annales` (via `local_store`), et le retry automatique est une étape de
plus dans la boucle de fond déjà existante (`backend/core/background.py:
run_background_tasks`, cycle de 5 min).

```
correct_directory(folder)
        │  pour chaque quiz du dossier
        ▼
_correct_one_quiz(bridge_path, quiz, prompt, folder, service)   ← NOUVEAU (extrait)
        │
        ├─ succès + nb questions == nb attendu (HTML)  → écrit UNESS/vérifiés/*.json
        │
        └─ échec (exception OU mismatch de count)      → local_store.record_uness_correction_failure(...)
                                                                  │
                                                                  ▼
                                                    table uness_correction_failures
                                                                  │
                        ┌─────────────────────────────────────────┼──────────────────────────┐
                        ▼                                         ▼                          ▼
        run_background_tasks() (cycle 5 min)          page /annales (bandeau)      cockpit_shell.py (badge nav)
        retry silencieux si next_retry_at ≤ now        liste + bouton "Relancer"    compteur "pending"
        et attempts < 3
```

## Composants

### 1. `backend/core/reviews/local_store.py` (modifié)

Nouvelle table, créée dans une migration `_migrate_uness_correction_failures`
au même endroit que `_migrate_uness_annales` :

```sql
CREATE TABLE IF NOT EXISTS uness_correction_failures (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    bridge_folder  TEXT NOT NULL,   -- dossier au moment de l'échec (indicatif, peut devenir stale)
    quiz_title     TEXT NOT NULL,
    collected_at   TEXT NOT NULL,   -- clé stable pour relocaliser le bridge (cf. composant 2)
    error_message  TEXT NOT NULL,
    attempts       INTEGER NOT NULL DEFAULT 0,
    next_retry_at  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'resolved'
    created_at     TEXT NOT NULL,
    last_attempt_at TEXT
)
```

Nouvelles fonctions (même style que les fonctions `uness_annales` existantes) :
- `record_uness_correction_failure(*, bridge_folder, quiz_title, collected_at, error_message) -> int`
  — upsert par `(quiz_title, collected_at)` : si une entrée `pending` existe déjà
  pour ce couple, incrémente `attempts` et met à jour `error_message`/`next_retry_at`
  au lieu d'en créer une deuxième.
- `resolve_uness_correction_failure(quiz_title: str, collected_at: str) -> None`
  — appelée dès qu'un retry réussit (ou qu'une correction manuelle "Corriger
  dossier existant" réussit sur ce même titre/`collected_at`).
- `list_pending_uness_correction_failures(*, due_only: bool = False) -> list[dict]`
  — `due_only=True` filtre `status='pending' AND attempts < 3 AND next_retry_at <= now`
  (utilisé par le retry auto) ; `due_only=False` retourne tout ce qui est `pending`
  (utilisé par le bandeau et le badge, y compris les échecs qui ont épuisé leurs
  3 tentatives).
- `count_pending_uness_correction_failures() -> int` — pour le badge nav (évite de
  charger toute la liste juste pour un compteur).

### 2. `backend/core/uness/gemini_autocorrect.py` (modifié)

**Refactor nécessaire** : extraire le corps de la boucle `for quiz in
bridge.get("contents", [])` de `correct_directory` dans une fonction dédiée,
pour qu'un retry ciblé puisse corriger *un seul* quiz sans repasser sur ses
voisins déjà réussis (coût Gemini inutile sinon) :

```python
def _correct_one_quiz(bridge_path: Path, quiz: dict, prompt: str, folder: Path,
                       service: AIService | None) -> tuple[str | None, str | None]:
    """Retourne (nom_fichier_écrit, erreur). Un seul des deux est non-None."""
    # corps actuel de la boucle, avec en plus :
    #   - comptage des questions attendues depuis le HTML du bridge
    #     (compter les `div.que` hors `.description`, même sélecteur que
    #     `_general_context` dans gemini_conversion.py)
    #   - comparaison avec len(exams[i].questions) après conversion
    #   - si mismatch : ne PAS écrire le fichier vérifié, retourner une erreur
    #     explicite ("Réponse incomplète : 5/6 questions")
```

`correct_directory` devient une boucle fine sur `_correct_one_quiz`, qui :
- en cas d'erreur, appelle `local_store.record_uness_correction_failure(...)`
  (`collected_at` vient de `bridge["source"]["collected_at"]`, déjà présent dans
  le bridge — même champ que `convert_with_bridge` utilise aujourd'hui) — en
  plus de remplir `errors` comme aujourd'hui, pour ne rien changer au retour
  utilisé par `_gemini_partial_failure_message` ;
- en cas de succès, appelle `local_store.resolve_uness_correction_failure(quiz_title,
  collected_at)` (no-op si aucune entrée `pending` n'existait pour ce couple).
  Cette résolution est donc automatique quel que soit le chemin emprunté —
  retry auto, clic "Relancer", ou simplement l'utilisateur qui repointe
  manuellement "Corriger dossier existant" vers le dossier archivé.

Nouvelle fonction publique pour le retry ciblé :

```python
def retry_failed_quiz(failure_id: int) -> dict:
    """Relocalise le bridge : recherche par titre dans à_vérifier/ puis
    archives/ (même mécanisme que find_bridge_for_title), désambiguïsé par
    collected_at si plusieurs bridges archivés partagent le même titre —
    puis appelle _correct_one_quiz, qui gère lui-même la résolution/le
    ré-échec (cf. ci-dessus)."""
```

Utilisée à la fois par le bouton "Relancer" manuel (reset `attempts=0` avant
l'appel) et par le retry automatique de la boucle de fond.

### 3. `backend/core/background.py` (modifié)

Nouvelle étape dans `run_background_tasks`, à chaque cycle de 5 min :

```python
# ── N. Retry des corrections UNESS en échec (borné, silencieux) ──────────
from backend.core.reviews import local_store
from backend.core.uness.gemini_autocorrect import retry_failed_quiz

due = local_store.list_pending_uness_correction_failures(due_only=True)
for failure in due:
    try:
        await asyncio.to_thread(retry_failed_quiz, failure["id"])
    except Exception as exc:
        logger.warning(f"Retry correction UNESS #{failure['id']} échoué : {exc}")
```

Délai croissant porté par `next_retry_at` (posé par `record_uness_correction_failure` /
`retry_failed_quiz`) : ~30 s après le 1ᵉʳ échec, ~2 min après le 2ᵉ, ~10 min
après le 3ᵉ — arrondi à l'entier de cycles de 5 min le plus proche puisque la
boucle ne tourne que toutes les 5 min (donc en pratique : retry au cycle
suivant, puis 1 cycle plus tard, puis 2 cycles plus tard).

### 4. `frontend/pages/annales.py` (modifié)

Bandeau en haut de `annales_page()`, avant la liste des annales, visible
seulement si `local_store.list_pending_uness_correction_failures()` est
non-vide :

```
⚠️ 2 quiz en attente de correction  [▾ déplier]
  ├─ SQI1 — Psychiatrie/Pôle 5-Session 2  · 3 tentatives · "Extra data: line 42..."   [Relancer]
  └─ DP1 — Pneumologie/pôle 1-T2          · 1 tentative  · "Réponse incomplète : 5/6" [Relancer]
```

Le bouton **Relancer** appelle `retry_failed_quiz(failure_id)` via
`asyncio.to_thread` (appel réseau Gemini synchrone), affiche un spinner le
temps de l'appel, puis rafraîchit le bandeau + relance `_finalize_scan()` si
ça a réussi (le fichier vérifié fraîchement écrit doit être importé comme
n'importe quel scan manuel).

### 5. `frontend/cockpit_shell.py` (modifié)

Le dispatch de badge dans `_nav_item` ignore aujourd'hui la valeur de
`badge[1]` et appelle toujours `_revision_badge()` pour tout badge
`dynamic_count` — bug préexistant qu'il faut corriger pour brancher un
deuxième badge dynamique :

```python
_BADGE_PROVIDERS = {
    "revisions": _revision_badge,
    "uness_failures": _uness_failures_badge,   # nouveau
}
...
elif badge and badge[0] == "dynamic_count":
    ui.label(_BADGE_PROVIDERS[badge[1]]()[1]).classes("cockpit-badge-count")
```

`_uness_failures_badge()` (nouveau, même forme que `_revision_badge`) appelle
`local_store.count_pending_uness_correction_failures()`. L'entrée `"Annales"`
dans `_NAV_GROUPS` passe de badge `None` à `("dynamic_count", "uness_failures")`.

## Gestion des erreurs

- Un échec qui persiste au-delà de 3 tentatives auto reste `pending` (visible
  dans le bandeau, badge inclus) mais n'est plus retenté automatiquement — seul
  un clic manuel sur "Relancer" relance (et repart pour 3 tentatives auto si ça
  échoue encore).
- Si le bridge JSON a disparu (session archivée puis nettoyée manuellement,
  fichier renommé) au moment du retry, `retry_failed_quiz` échoue avec un
  message explicite ("bridge introuvable") plutôt qu'une exception non
  attrapée — l'entrée reste `pending` avec ce message, à traiter à la main.
- Deux `record_uness_correction_failure` sur le même `(quiz_title,
  collected_at)` ne créent jamais deux lignes (upsert) — évite un bandeau qui
  grossit indéfiniment si le même quiz échoue à chaque cycle.

## Tests

- `tests/test_uness_annales_model.py` (ou nouveau
  `tests/test_uness_correction_failures.py`) : create/upsert/resolve/list
  (`due_only` avec `next_retry_at` passé/futur), compteur.
- `tests/test_gemini_autocorrect.py` : cas mismatch de count de questions
  (bridge HTML à 6 `div.que`, réponse Gemini avec 5 questions → erreur, aucun
  fichier vérifié écrit) ; `retry_failed_quiz` relocalise un bridge archivé et
  résout l'échec en base après succès.
- `tests/test_annales_page.py` : rendu du bandeau (présence/absence selon la
  liste), formatage du message par entrée.
- Test manuel (pas d'automatisation d'`asyncio.sleep` réel) : vérifier que
  `run_background_tasks` appelle bien `retry_failed_quiz` pour une entrée due
  et pas pour une entrée dont `next_retry_at` est dans le futur.

## Hors périmètre (v1)

- Pas de suppression automatique des entrées `resolved` (historique conservé,
  filtré par `status` dans les requêtes — un nettoyage manuel via SQL suffit si
  la table grossit trop).
- Pas de configuration du nombre de tentatives (3) ni des délais — codés en dur,
  ajustables plus tard si besoin réel.
- Pas de parallélisation des retries dans la boucle de fond (séquentiel, comme
  `correct_directory` aujourd'hui).
- Le badge ne distingue pas visuellement "en attente de retry auto" vs "a
  épuisé ses 3 tentatives" — les deux comptent pareil ; le détail (nombre de
  tentatives) n'est visible que dans le bandeau déplié.
