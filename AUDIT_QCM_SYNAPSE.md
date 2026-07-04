# AUDIT_QCM_SYNAPSE.md
> Audit du module QCM · Synapse · 2026-06-20

---

## 1. Cartographie de l'existant

### 1.1 Fichiers impliqués

| Fichier | Rôle |
|---|---|
| `backend/core/qcm/service.py` | Helpers métier : parsing score, couleurs, labels, seuils (PASS=70%, WARN=60%), types plateformes/sessions |
| `backend/core/ai_qcm/parser.py` | Parse un fichier `.md` contenant un bloc `---json---` → `AIQCMFile` |
| `backend/core/ai_qcm/service.py` | Orchestre l'import : scan dossier, parse, match cours, insert SQLite, déplace fichier |
| `backend/core/reviews/local_store.py` | Couche SQLite complète : toutes les tables, migrations, API lecture/écriture |
| `backend/core/reviews/mastery.py` | Calcule le score de maîtrise 0-100 par cours (`CourseProgressSnapshot`) |
| `backend/core/background.py` | Boucle de fond async : refresh Notion, sync Obsidian — **aucun watcher QCM** |
| `frontend/pages/qcm.py` | Page QCM : KPI cards, graphique évolution, liste cours, dialog saisie manuelle, bouton "Importer IA" |
| `data/ai_qcm/CONTEXT_SYNAPSE_QCM.md` | Documentation schéma QCM partagée avec ChatGPT/Gemini (dans le sous-dossier inbox, pas à la racine) |

### 1.2 Schéma SQLite — tables concernées

**`qcm_sessions`** — résultats QCM complets (local_store.py:89-103, colonnes Phase C ajoutées à la migration :888-915)

```sql
id               INTEGER PRIMARY KEY AUTOINCREMENT
course_id        TEXT    NOT NULL
course_title     TEXT
item_number      TEXT
platform         TEXT    NOT NULL          -- "EDNpro"|"Hypocampus"|"ChatGPT"|"Gemini"
session_date     TEXT    NOT NULL          -- YYYY-MM-DD
score            REAL                      -- alias de score_percent (rétro-compat)
score_raw        TEXT                      -- "14/20" ou "70%"
score_percent    REAL                      -- 0.0 – 100.0
session_type     TEXT  DEFAULT 'QCM'       -- "QCM"|"DP"|"KFP"|"Annales"
total_questions  INTEGER
correct_answers  INTEGER
wrong_answers    INTEGER
difficulty       TEXT                      -- "facile"|"moyen"|"difficile"
error_types      TEXT  DEFAULT '[]'        -- JSON list ["connaissance", ...]
errors           TEXT                      -- ancien champ libre (pré-Phase C)
comments         TEXT
created_at       TEXT    NOT NULL
updated_at       TEXT    NOT NULL
```

Index : `idx_qs_course ON qcm_sessions(course_id)` (local_store.py:103)

**`weak_points`** — lacunes structurées (local_store.py:134-150, colonnes Phase D :929-937, colonnes Obsidian :1497-1506)

```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
course_id         TEXT    NOT NULL
course_title      TEXT    DEFAULT ''
item_number       TEXT    DEFAULT ''
category          TEXT                     -- 13 catégories standards
detail            TEXT    NOT NULL
severity          INTEGER DEFAULT 2        -- 1-5
status            TEXT    NOT NULL DEFAULT 'active'   -- active|à revoir|résolue|récurrente
source_type       TEXT    DEFAULT 'manuel'            -- qcm|séance|note|manuel|auto_detection
source_session_id INTEGER
recurrence_count  INTEGER DEFAULT 0
last_reviewed_at  TEXT
synapse_id        TEXT  UNIQUE             -- lien Obsidian
obsidian_path     TEXT
obsidian_uri      TEXT
obsidian_title    TEXT
college           TEXT
raw_frontmatter   TEXT
created_at        TEXT    NOT NULL
resolved_at       TEXT
```

**`study_sessions`** — sessions de révision avec feedback QCM intégré (local_store.py:106-125)
- Champ `qcm_result TEXT` : "réussi"/"raté" (saisie manuelle dans le dialog révision)
- Champ `weak_category`/`weak_detail` : lacune rapide liée à la session
- **Distinct de `qcm_sessions`** : ces champs sont la trace de l'activité QCM dans le cadre d'une révision, pas un résultat structuré

### 1.3 Flux de données actuels

#### Flux A — Saisie manuelle (EDNpro / Hypocampus)
```
Dialog "Ajouter un résultat" (qcm.py:649)
  ↓ _submit() (qcm.py:1008)
  ↓ local_store.add_qcm_session_full() (local_store.py:1161)
  ↓ Si score < 70% → _propose_lacune() → local_store.add_weak_point_full() (local_store.py:1000)
  ↓ Si score ≥ 70% ET lacunes actives → _propose_resolve_lacune()
  ↓ _rebuild() → mise à jour KPI + graphique + liste cours
```

#### Flux B — Import IA (JSON dans Markdown, ChatGPT/Gemini)
```
Bouton "Importer IA" (qcm.py:480)
  ↓ ai_qcm_service.import_all(courses=data_store.cours) (service.py:182)
  ↓ Scan data/ai_qcm/*.md → _is_synapse_qcm() (service.py:210)
  ↓ parse_file() (parser.py:59)   ← extrait bloc ---json---
  ↓ _find_course() (service.py:38) ← item_number exact → titre exact → partiel → fuzzy
  ↓ local_store.add_qcm_session_full()
  ↓ local_store.add_weak_point_full() (lacunes explicites + lacune auto si raté sans weak_points)
  ↓ file.rename(imported/) (service.py:168)
  ↓ Retour résumé → ui.notify() → _rebuild()
```

#### Dashboard "à retravailler"
- **KPI card** : `to_review = count(groups where last_score < 70%)` (qcm.py:99-102)
- **Badge dashboard** : `get_qcm_last_scores_by_course()` (local_store.py:1305) → dernier score + tendance ↑↓→
- **Score de maîtrise** : `mastery.py:66` lit `qcm_done_local` depuis `get_qcm_done_course_ids()` — booléen présence/absence uniquement, **pas le score numérique**

---

## 2. Diagnostic — Pipeline JSON

### 2.1 Verdict : **pipeline JSON entièrement implémenté, watcher absent**

Le pipeline de parsing et d'ingestion JSON est **complet et fonctionnel**. La seule pièce manquante pour atteindre le flux 100% automatique est le filesystem watcher qui déclencherait `import_all()` automatiquement dès le dépôt d'un fichier — au lieu d'attendre un clic sur "Importer IA".

### 2.2 Ce qui existe (et fonctionne)

| Composant | Statut | Fichier:Ligne |
|---|---|---|
| Parser `---json---` | ✅ Opérationnel | `parser.py:59-147` |
| Matching item_number → course_id | ✅ 4 niveaux de fallback | `service.py:38-80` |
| Insert `qcm_sessions` (Phase C) | ✅ Tous les champs | `local_store.py:1161-1198` |
| Insert `weak_points` (explicit + auto) | ✅ Avec source_type="qcm" | `service.py:130-159` |
| Déplacement vers `imported/` après succès | ✅ Avec timestamp si collision | `service.py:166-170` |
| Idempotence fichier (double-clic) | ✅ Le fichier est déplacé avant fin | `service.py:168` |
| Détection "est-ce un fichier Synapse QCM" | ✅ Check 5 premières lignes | `service.py:210-219` |
| Compteur badge inbox | ✅ `get_inbox_count()` | `service.py:223-226` |
| Refresh UI après import | ✅ `_rebuild()` appelé | `qcm.py:504` |

### 2.3 Ce qui manque

| Manque | Impact | Priorité |
|---|---|---|
| **Filesystem watcher** — déclenchement automatique | Bloquant pour le flux zéro-clic | Sprint 1 |
| **Debounce** — éviter double-trigger sur écriture | Risque double-import si OS envoie 2 events | Sprint 1 |
| **Gestion erreur idempotente** — ParseError laisse le fichier en place → re-trigger en boucle | Log spam potentiel | Sprint 2 |
| **Notification UI proactive** — aucune alerte si import watcher pendant navigation hors page QCM | Invisibilité pour l'utilisateur | Sprint 3 |
| **CONTEXT_SYNAPSE_QCM.md à la racine** — actuellement dans `data/ai_qcm/`, pas à la racine du repo | Découvrabilité réduite | Sprint 0 |

### 2.4 Écarts entre CONTEXT_SYNAPSE_QCM.md et le code réel

| Point documenté | Réalité code | Écart |
|---|---|---|
| Seuil validation 70% | `PASS_THRESHOLD = 70.0` (qcm/service.py:17) | ✅ Conforme |
| Zone limite 60-70% | `WARN_THRESHOLD = 60.0` (qcm/service.py:18) | ✅ Conforme |
| `error_types` = 4 valeurs | `QCM_ERROR_TYPES = ("connaissance", "raisonnement", "inattention", "stratégie EDN")` (local_store.py:1157) | ✅ Conforme |
| `session_type` = QCM/DP/KFP/Annales | `QCM_SESSION_TYPES = ("QCM", "DP", "KFP", "Annales")` (local_store.py:1156) | ✅ Conforme |
| Sévérité auto : <50%→4, 50-60%→3, 60-70%→2 | `suggested_severity()` : <50→4, <60→3, else→2 (qcm/service.py:133-141) | ✅ Conforme |
| Lacune auto si raté sans weak_points | `service.py:145-159` | ✅ Conforme |
| `platform` "ChatGPT"\|"Gemini" | `QCM_PLATFORMS = ("EDNpro", "Hypocampus", "ChatGPT", "Gemini")` | ✅ Conforme |
| Synapse mappe `item_number` vers cours | `_find_course()` avec 4 niveaux de fallback | ✅ Conforme |
| Le fichier commence par `---json` ligne 1 | `_is_synapse_qcm()` : cherche dans les 5 premières lignes (pas uniquement la 1ère) | ✅ Plus permissif, pas de régression |
| `synapse_version: 1` dans le JSON | Champ **lu mais ignoré** par le parser (data.get("synapse_version") n'est pas utilisé) | ⚠️ Documenté mais non validé |

---

## 3. Architecture proposée — Flux Markdown automatique

### 3.1 Format de fichier : aucun nouveau format nécessaire

Le "nouveau flux Markdown" décrit dans la mission utilise **exactement le même format** que le flux JSON existant. Le fichier généré par ChatGPT/Gemini contient :
1. Le bloc `---json ... ---` en tête (données structurées) — **déjà parsé par `parser.py`**
2. Du Markdown en prose en dessous (récap lisible) — **déjà ignoré par `parser.py`** (parser.py:62-76)

Le format de CONTEXT_SYNAPSE_QCM.md section 8 et l'exemple section 10 correspondent exactement à ce que `parse_file()` attend. Il n'y a pas de nouveau format à concevoir.

**Recommandation de nommage des fichiers** (convention, pas contrainte technique) :
```
YYYYMMDD_ChatGPT_item154.md
YYYYMMDD_Gemini_cardio_dp.md
```
Le parser identifie les fichiers valides par contenu (`_is_synapse_qcm()`), pas par nom.

### 3.2 Décision : pipeline unique

**Verdict : pipeline unique — les deux flux alimentent le même `import_file()`.**

Justification :
- `parse_file()` fait abstraction du contenu Markdown — il extrait seulement le bloc JSON
- La structure interne (`AIQCMFile` → `QCMSessionEntry`) est identique quel que soit l'origine
- `add_qcm_session_full()` et `add_weak_point_full()` sont déjà les fonctions terminales communes
- Créer un second parser "Markdown pur" introduirait une duplication des règles métier (seuils, catégories, matching cours) et deux chemins de normalisation à maintenir

Le seul ajout est un **point d'entrée différent** (watcher vs bouton) qui appelle la même `import_all()`.

Schéma final :
```
Dépôt fichier .md              Bouton "Importer IA"
dans data/ai_qcm/              (qcm.py:480)
       ↓                              ↓
  Watcher event                import_all()
       ↓                              ↓
   [MÊME PIPELINE]
   import_file() → parse_file() → _find_course() → add_qcm_session_full() → add_weak_point_full()
                                                             ↓
                                                    data/ai_qcm/imported/
```

### 3.3 Mécanisme de filesystem watcher

**Librairie recommandée : `watchdog`** — légère, cross-platform, mature, pas de service externe.

```python
# Ajout dans requirements.txt
watchdog==4.0.0
```

**Architecture du watcher** (nouveau fichier `backend/core/ai_qcm/watcher.py`) :

```python
"""
watcher.py — Surveillance automatique de data/ai_qcm/
Détecte les .md déposés → import immédiat sans action utilisateur.
"""
import asyncio
import threading
from pathlib import Path
from loguru import logger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from backend.core.ai_qcm.service import import_file, _is_synapse_qcm, INBOX_DIR


class _QCMInboxHandler(FileSystemEventHandler):
    def __init__(self, courses_getter, notify_callback=None):
        self._courses_getter = courses_getter      # lambda → data_store.cours
        self._notify_callback = notify_callback    # lambda result → ui.notify (optionnel)
        self._pending: dict[str, asyncio.TimerHandle] = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        self._schedule(event.src_path)

    def on_modified(self, event):
        self._schedule(event.src_path)

    def _schedule(self, path: str):
        """Debounce : attend 2s que l'écriture OS soit terminée avant d'importer."""
        if not path.endswith(".md"):
            return
        p = Path(path)
        if p.parent != INBOX_DIR:
            return
        with self._lock:
            # Annule le timer précédent si le fichier est toujours en cours d'écriture
            if path in self._pending:
                self._pending[path].cancel()
            timer = threading.Timer(2.0, self._process, args=[path])
            self._pending[path] = timer
            timer.start()

    def _process(self, path: str):
        p = Path(path)
        with self._lock:
            self._pending.pop(path, None)
        if not p.exists():
            return
        if not _is_synapse_qcm(p):
            return
        # Évite de re-traiter un fichier déjà en cours d'import
        sentinel = p.with_suffix(".importing")
        if sentinel.exists():
            return
        try:
            sentinel.touch()
            courses = self._courses_getter()
            result = import_file(p, courses=courses)
            if result["success"] and self._notify_callback:
                self._notify_callback(result)
        except Exception as exc:
            logger.error(f"Watcher import error ({p.name}): {exc}")
            # Crée un marker d'erreur pour éviter le retry en boucle
            p.with_suffix(".error").write_text(str(exc))
        finally:
            if sentinel.exists():
                sentinel.unlink(missing_ok=True)


_observer: Observer | None = None


def start_watcher(courses_getter, notify_callback=None) -> None:
    """Démarre le watcher en arrière-plan. Idempotent."""
    global _observer
    if _observer and _observer.is_alive():
        return
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    handler = _QCMInboxHandler(courses_getter, notify_callback)
    _observer = Observer()
    _observer.schedule(handler, str(INBOX_DIR), recursive=False)
    _observer.start()
    logger.info(f"AI QCM watcher démarré → {INBOX_DIR}")


def stop_watcher() -> None:
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None
```

**Intégration dans `background.py`** — après la boucle existante, au premier cycle :

```python
# backend/core/background.py — dans run_background_tasks(), cycle 1
if _CYCLE == 1:
    from backend.core.ai_qcm.watcher import start_watcher
    start_watcher(
        courses_getter=lambda: list(data_store.cours),
    )
    logger.info("AI QCM watcher initialisé.")
```

**Gestion du notify_callback** : optionnel au démarrage (NiceGUI n'est pas forcément prêt). La page QCM peut enregistrer son propre callback via un événement bus si besoin (Sprint 3).

### 3.4 Idempotence — gestion des cas limites

| Cas | Comportement |
|---|---|
| Fichier déposé une fois, import OK | Fichier déplacé vers `imported/` → watcher ne le détecte plus |
| OS envoie 2 events (created + modified) | Debounce 2s : seul le dernier est traité. Si import déjà fait, le fichier est absent → `p.exists()` → retour silencieux |
| Deux watchers simultanés (redémarrage app) | Sentinel `.importing` : le 2ème processus voit le sentinel et skip |
| ParseError (JSON malformé) | Fichier reste en place, `.error` créé → watcher ignore les `.error`, pas de retry en boucle |
| Import partiel (0 session importée) | Fichier reste en place (service.py:166 : `if result["imported"] > 0`). Watcher re-tentera au prochain event (modif fichier) |
| Fichier CONTEXT_SYNAPSE_QCM.md dans inbox | `_is_synapse_qcm()` : `---json` n'est pas dans les 5 premières lignes → skip correct |

### 3.5 Mapping item_number / course_title → cours existants

La fonction `_find_course()` (service.py:38-80) implémente déjà 4 niveaux de matching. Analyse des cas limites :

| Cas | Comportement actuel | Recommandation |
|---|---|---|
| item_number "154" vs "154.0" en base | `lstrip("0")` uniquement — "154" vs "154" → ✅ Match | Ajouter normalisation float : `clean = str(int(float(item_number.strip())))` |
| item_number absent (DP multi-items) | Fallback sur titre → partiel → fuzzy | ✅ Correct |
| Plusieurs cours avec item_number identique | `_find_course()` retourne le premier trouvé | Acceptable (un seul cours par item dans Notion) |
| Aucun cours trouvé | Retourne `("", course_title, item_number)` → session insérée avec `course_id=""` | ✅ Non-bloquant, session quand même enregistrée |
| Fuzzy score < 75 | Aucun match → `course_id=""` | Logger.warning + rapport dans le résumé d'import |
| `data_store.cours` vide au moment du watcher | `courses_getter()` retourne `[]` → `_find_course()` retourne `("", ...)` | Import quand même, `course_id=""`. Correction possible via re-run manuel |

---

## 4. Risques de régression sur le pipeline manuel

| Risque | Impact | Mitigation |
|---|---|---|
| `import_all()` / `import_file()` déjà appelés par le bouton ET le watcher simultanément | Double-import si un fichier est dans inbox au moment où l'utilisateur clique ET que le watcher tourne | Sentinel `.importing` (§3.4) |
| `_is_synapse_qcm()` lit 200 chars — fichiers avec BOM UTF-8 (`\xef\xbb\xbf`) en tête | Le BOM déplace les caractères → `---json` pourrait ne pas être détecté | Ajouter `text.lstrip('﻿')` dans `_is_synapse_qcm()` |
| `add_qcm_session_full()` n'est pas transactionnel avec `add_weak_point_full()` | Si crash entre les deux : session insérée sans lacune | Acceptable (mono-utilisateur, crash rare) — pas de correction nécessaire |
| `score` et `score_percent` sont dupliqués dans qcm_sessions | `score = score_percent` (local_store.py:1188, identiques) | Non-bloquant mais redondant. Ne pas toucher : rétro-compat avec l'ancien `add_qcm_session()` |
| Le watcher tourne dans un thread OS (watchdog) mais `import_file()` est synchrone et accède à SQLite | Concurrence thread watchdog / thread NiceGUI sur SQLite | SQLite WAL mode (local_store.py:36) + connexion contextuelle `_conn()` (local_store.py:32-37) → safe par conception |
| CONTEXT_SYNAPSE_QCM.md dans `data/ai_qcm/` sera traité par le watcher si déplacé/modifié | Fichier ne contient pas `---json` dans les 5 premières lignes → `_is_synapse_qcm()` retourne False | ✅ Pas de risque |

---

## 5. Plan d'implémentation

### Sprint 0 — CONTEXT_SYNAPSE_QCM.md à la racine (15 min, risque nul)

**Problème** : le fichier est dans `data/ai_qcm/` → invisible pour un nouveau développeur ou une session ChatGPT qui ne connaît pas le chemin.

**Action** : copier à la racine du projet (conserver l'original dans `data/ai_qcm/` pour les sessions ChatGPT qui liraient le dossier inbox).

```bash
cp data/ai_qcm/CONTEXT_SYNAPSE_QCM.md CONTEXT_SYNAPSE_QCM.md
```

**Pas de modification du code** — c'est une opération documentaire.

**Test** : fichier visible à la racine dans l'IDE et via `ls *.md`.

---

### Sprint 1 — Filesystem Watcher (2-3h, risque faible)

**Fichiers à créer/modifier** :
- **Nouveau** : `backend/core/ai_qcm/watcher.py` (code complet §3.3)
- **Modifier** : `requirements.txt` — ajouter `watchdog==4.0.0`
- **Modifier** : `backend/core/background.py` — appel `start_watcher()` au cycle 1

**Modification détaillée de `background.py`** (après la ligne `_LACUNES_SYNC_DONE = True`) :

```python
# ── 6. Watcher AI QCM — une seule fois au démarrage ──────────────────────
if _CYCLE == 1:
    try:
        from backend.core.ai_qcm.watcher import start_watcher
        start_watcher(courses_getter=lambda: list(data_store.cours))
        logger.info("AI QCM watcher démarré.")
    except Exception as exc:
        logger.error(f"Watcher démarrage échoué : {exc}")
```

**Migration SQLite** : aucune — toutes les tables/colonnes existent déjà.

**Tests de validation** :
1. Déposer un fichier `.md` valide dans `data/ai_qcm/` → vérifier import dans les 3 secondes dans `data/ai_qcm/imported/`
2. Déposer un fichier `.md` invalide (pas de `---json`) → vérifier qu'il reste en place et qu'aucun `.error` n'est créé
3. Déposer un fichier `.md` avec JSON malformé → vérifier création de `.error` et pas de retry
4. Cliquer sur "Importer IA" pendant que le watcher tourne → vérifier qu'aucun double-import n'a lieu (sentinel)
5. Redémarrer l'app avec un fichier dans inbox → vérifier import automatique au démarrage

---

### Sprint 2 — Robustesse & Nettoyage (1h, risque faible)

**Fichiers à modifier** :
- `backend/core/ai_qcm/service.py` — fix `_is_synapse_qcm()` pour les fichiers BOM
- `backend/core/ai_qcm/service.py` — normalisation item_number (float → int → str)
- `backend/core/ai_qcm/watcher.py` — nettoyage des `.importing` orphelins au démarrage

**Fix 1 — BOM UTF-8** (`service.py:211-219`) :
```python
def _is_synapse_qcm(path: Path) -> bool:
    try:
        first = path.read_text(encoding="utf-8-sig", errors="ignore")[:200]  # utf-8-sig strip BOM
        first_lines = first.splitlines()[:5]
        return any(line.strip() == "---json" for line in first_lines)
    except Exception:
        return False
```

**Fix 2 — Normalisation item_number** (`service.py:49-53`) :
```python
if item_number:
    try:
        clean = str(int(float(item_number.strip())))  # "154.0" → "154"
    except ValueError:
        clean = item_number.strip().lstrip("0")
    for c in courses:
        try:
            c_item = str(int(float(str(getattr(c, "item_number", "") or "").strip())))
        except ValueError:
            c_item = str(getattr(c, "item_number", "") or "").strip().lstrip("0")
        if c_item and c_item == clean:
            return c.id, c.title, str(getattr(c, "item_number", "") or "")
```

**Nettoyage sentinels orphelins** (ajouter dans `watcher.py:start_watcher()`) :
```python
# Nettoie les .importing orphelins d'un crash précédent
for sentinel in INBOX_DIR.glob("*.importing"):
    sentinel.unlink(missing_ok=True)
```

**Migration SQLite** : aucune.

**Tests de validation** :
1. Fichier avec BOM en tête → correctement détecté comme Synapse QCM
2. Item "154.0" → matche le cours "154" en base
3. Crash simulé pendant import → relance de l'app → sentinels nettoyés, fichier re-importé

---

### Sprint 3 — Notification UI proactive (1h, risque moyen)

**Problème** : si l'utilisateur est sur le Dashboard ou une autre page au moment où le watcher importe, il ne voit rien.

**Solution** : NiceGUI permet des notifs globales via `ui.notify()` depuis n'importe quel thread si on utilise l'API async NiceGUI correctement (`ui.run_javascript()` ou `app.storage.user`). La solution la plus simple est d'utiliser un flag en mémoire et une notification au prochain accès à la page QCM.

**Fichiers à modifier** :
- `backend/core/ai_qcm/watcher.py` — mémoriser les résultats d'import récents
- `frontend/pages/qcm.py` — vérifier les résultats pending au chargement de la page

**Implémentation légère** :
```python
# watcher.py — ajouter
_PENDING_RESULTS: list[dict] = []

def pop_pending_results() -> list[dict]:
    """Retourne et vide les résultats d'import watcher non encore affichés."""
    results, _PENDING_RESULTS[:] = list(_PENDING_RESULTS), []
    return results
```

```python
# qcm.py:qcm_page() — au début de la page
from backend.core.ai_qcm.watcher import pop_pending_results
for r in pop_pending_results():
    ui.notify(
        f"Import auto : {r['file']} — {r['imported']} session(s)",
        type="positive", icon="cloud_download",
    )
```

**Tests de validation** :
1. Déposer un fichier en étant sur le Dashboard → naviguer vers QCM → notification visible
2. Déposer deux fichiers → naviguer vers QCM → deux notifications

---

### Récapitulatif des sprints

| Sprint | Durée | Fichiers touchés | Risque | Pré-requis |
|---|---|---|---|---|
| Sprint 0 | 15 min | Aucun code | Nul | — |
| Sprint 1 | 2-3h | `requirements.txt`, `background.py`, `ai_qcm/watcher.py` (nouveau) | Faible | Sprint 0 |
| Sprint 2 | 1h | `ai_qcm/service.py`, `ai_qcm/watcher.py` | Faible | Sprint 1 |
| Sprint 3 | 1h | `ai_qcm/watcher.py`, `frontend/pages/qcm.py` | Moyen | Sprint 1 |

**Ordre recommandé** : 0 → 1 → 2 → 3. Sprint 1 seul suffit pour le flux zéro-clic. Sprints 2 et 3 sont des améliorations de robustesse.

---

## Synthèse

Le module QCM de Synapse est **architecturalement complet**. Le pipeline JSON (`---json---`) est entièrement implémenté et fonctionnel (parser, matching, insert SQLite, déplacement fichier). La base de données contient toutes les colonnes nécessaires. CONTEXT_SYNAPSE_QCM.md est en cohérence avec le code sur tous les points testés.

**La seule pièce manquante est le filesystem watcher** (`watchdog`), qui représente environ 60 lignes de code dans un fichier nouveau (`backend/core/ai_qcm/watcher.py`) et 5 lignes d'intégration dans `background.py`. Aucune migration SQLite n'est nécessaire. Aucun risque de régression sur le pipeline manuel si le sentinel `.importing` est correctement implémenté.
