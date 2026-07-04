# Synapse — Compte Rendu de Mise en Production

> Généré le 2026-06-18 — Version 1.0  
> Stack : NiceGUI 3.8.0 · Notion API · SQLite · Python 3.13 · Windows 11  
> Périmètre : ~16 000 lignes Python · 44 modules · 299 cours Notion actifs

---

## 0. Résumé exécutif

### État actuel par catégorie

| Catégorie | État | Commentaire |
|-----------|------|-------------|
| Qualité du code | 🟡 | Architecture solide, dette technique ciblée |
| Sécurité | 🔴 | **Credentials Google OAuth exposés en clair — action immédiate** |
| Performance | 🟡 | Rate limit Notion dépassé au démarrage (prouvé par logs) |
| Architecture always-on | 🔴 | Plusieurs mécanismes cassés en usage permanent |
| Dépendances | 🟡 | `rapidfuzz` non déclaré, `fuzzywuzzy` déprécié |
| Résilience | 🔴 | Pas de service Windows, `daily_routine` non planifié |

### Estimation du travail avant mise en production

| Priorité | Tâches | Estimation |
|----------|--------|-----------|
| **P0 — Bloquant** | 4 corrections (credentials, reload, sleep, save_to_disk) | 2-4h |
| **P1 — Important** | 6 corrections (retry API, daily_routine boucle, health endpoint, NSSM) | 1-2j |
| **P2 — Nice-to-have** | 5 améliorations (push URIs, SQLite checkpoint, circuit breaker complet) | 3-5j |

---

## 1. Audit du code existant

### 1.1 Qualité & dette technique

#### [BLOQUANT] `asyncio.sleep(0.15)` skippé sur exception dans `_push_obsidian_uris`

**Fichier :** `backend/core/background.py:169-172`

```python
# ACTUEL (bugué) :
ok = await notion_service.update_course(course_id, ...)
if ok:
    # ...
    await asyncio.sleep(0.15)   # ← skippé si update_course lève une exception
```

Si `update_course()` lève une exception (Notion down, 429...), le `except` de la ligne 171 l'attrape mais **saute** le `sleep`. La prochaine itération du `for` s'exécute immédiatement, générant un burst non limité. **Les logs du 2026-06-18 confirment 6.67 req/s** (15 updates en 26s), soit au-dessus du rate limit Notion de 3/s.

```python
# CORRECT : sleep inconditionnel
try:
    ok = await notion_service.update_course(course_id, ...)
    if ok:
        logger.success(...)
        cours.obsidian_uri = uri
except Exception as exc:
    logger.warning(f"...")
finally:
    await asyncio.sleep(0.35)   # 0.35s = 2.86 req/s, sous le rate limit
```

#### [IMPORTANT] `daily_routine.py` tourne une seule fois au démarrage — non planifiée

**Fichier :** `main.py:142`, `backend/features/daily_routine.py:85`

`run_daily_routine()` ne contient pas de `while True`. Elle est lancée via `asyncio.create_task(run_daily_routine())` une seule fois au démarrage. En always-on, si l'app a été lancée hier, la routine du lendemain (archivage des tâches passées, création J+1/J+2) ne s'exécutera jamais jusqu'au prochain redémarrage.

```python
# À remplacer dans daily_routine.py :
async def run_daily_routine():
    """S'exécute au démarrage, puis quotidiennement à 07h00."""
    # Exécution immédiate au lancement
    await _do_daily_routine()
    
    while True:
        now = datetime.now(APP_TIMEZONE)
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        await _do_daily_routine()
```

#### [IMPORTANT] Race condition sur `save_to_disk()` — absence de verrou

**Fichier :** `backend/state/store.py:119-137`

`save_to_disk()` est appelée depuis 5 contextes concurrents différents (boucle background, auto_link, set_preference, _send_morning_notification, mark_review_done). La séquence `open(..., "w")` tronque le fichier avant d'écrire : si deux contextes l'appellent quasi-simultanément, le fichier peut être tronqué pendant l'écriture du premier.

```python
# Solution : écriture atomique (aucun verrou requis)
def save_to_disk(self):
    tmp = self.CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    os.replace(tmp, self.CACHE_FILE)   # atomique sur Windows NTFS
```

#### [IMPORTANT] `reload=True` actif en production

**Fichier :** `main.py:184`

En mode always-on, `reload=True` active watchfiles qui surveille les fichiers Python. Sur certaines versions de watchfiles/NiceGUI, les écritures du répertoire `logs/` peuvent déclencher des redémarrages. La rotation loguru à minuit (création d'un nouveau `.log`) est un déclencheur potentiel.

```python
# main.py — détection automatique du mode
import os
_PROD = os.getenv("SYNAPSE_ENV", "dev") == "prod"

ui.run(
    title='Synapse',
    favicon='🧠',
    dark=False,
    reload=not _PROD,
    port=8082,
    show=not _PROD,          # ne pas ouvrir de navigateur au démarrage du service
    host='127.0.0.1',        # explicite (bonne pratique)
)
# Lancement : SYNAPSE_ENV=prod python main.py
```

#### [IMPORTANT] Log de debug en production

**Fichier :** `backend/core/notion/service.py:90`

```python
# À SUPPRIMER :
logger.info(f"DEBUG PROPERTIES: {list(results[0]['properties'].keys())}")
```

Exécuté à chaque appel de `get_all_daily_tasks_for_check()`, soit à chaque démarrage. Expose le schéma de la base Notion dans les logs de production.

Aussi dans `backend/core/reviews/recommendation_service.py` : deux `print()` qui écrivent sur stdout en dehors de loguru.

#### [IMPORTANT] Variables globales module-level non encapsulées

**Fichier :** `backend/core/background.py:9-19`

`_PROCESSED_COURSES`, `_VAULT_SYNC_DONE`, `_LACUNES_SYNC_DONE`, `_CYCLE` sont des variables module-level. Avec `reload=True`, elles sont réinitialisées dans le nouveau worker, forçant un vault sync complet à chaque rechargement. Elles ne peuvent pas être testées unitairement sans monkey-patching du module.

**Recommandation :** encapsuler dans une dataclass `BackgroundState` passée en paramètre.

#### [MINEUR] Duplication de logique `get_all_items_map` / `get_updated_items_map`

**Fichier :** `backend/core/notion/service.py:367-484`

90% du code est identique entre les deux méthodes (3 stratégies d'extraction de `item_val`). Commenter ligne 446 : *"Copy logic from get_all_items_map (reusing logic would be better but keeping it simple for now)"*.

```python
def _parse_item_value(props: dict) -> float | None:
    """Extrait le numéro d'item depuis les propriétés Notion."""
    # 1. "ITEMS" (Number property)
    if "ITEMS" in props and "number" in props["ITEMS"]:
        return props["ITEMS"]["number"]
    # 2. "Numéro de l'ITEM" (Title)
    if "Numéro de l'ITEM" in props:
        p = props["Numéro de l'ITEM"]
        if "title" in p and p["title"]:
            try: return float(p["title"][0].get("plain_text", "").replace(',', '.'))
            except ValueError: pass
    # 3. "ITEM" fallback (Number / rich_text / title)
    item_prop = props.get("ITEM", {})
    for key in ("number", "rich_text", "title"):
        if key in item_prop:
            val = item_prop[key] if key == "number" else item_prop[key][0].get("plain_text","") if item_prop[key] else None
            if val is not None:
                try: return float(str(val).replace(',', '.')) if key != "number" else val
                except (ValueError, TypeError): pass
    return None
```

#### [MINEUR] Méthode DEPRECATED sans date de suppression

**Fichier :** `backend/state/store.py:139`

`mark_review_done()` annoté `DEPRECATED`, non appelé dans le code. À supprimer.

---

### 1.2 Sécurité

#### [CRITIQUE — ACTION IMMÉDIATE] Credentials Google OAuth exposés en clair

**Fichiers :** `credentials.json` (racine), `token.json` (racine)

Ces deux fichiers contiennent des secrets OAuth Google actifs :
- `credentials.json` : client_id, client_secret, project_id
- `token.json` : access token actif + **refresh token permanent** (non expirant)

Le `.gitignore` exclut correctement ces fichiers, mais ils existent sur le disque à la racine du projet git. Un `git add .` accidentel, une sauvegarde cloud automatique (OneDrive, iCloud), ou tout outil de backup les expose.

**Actions immédiates (dans cet ordre) :**
1. **Révoquer le refresh token** : Google Cloud Console → Credentials → OAuth 2.0 Client IDs → supprimer ou régénérer
2. **Révoquer le client secret** et en générer un nouveau
3. **Vérifier l'historique git** : `git log --all --full-history -- credentials.json token.json`
   - Si jamais commités : purger avec `git filter-repo --invert-paths --path credentials.json --path token.json`
4. **Déplacer les fichiers** hors du workspace git :
   ```python
   # Dans backend/config/settings.py :
   google_credentials_path: str = Field(
       default=str(Path.home() / ".config" / "synapse" / "credentials.json"),
       alias='GOOGLE_CREDENTIALS_PATH'
   )
   ```
5. Ajouter explicitement dans `.gitignore` : `credentials.json`, `token.json`, `*.json` (si approprié)

#### [IMPORTANT] Path traversal dans `serve_pdf()` si répertoires non configurés

**Fichier :** `main.py:54-58`

```python
allowed_roots = [r for r in (_cfg.medicine_dir, _cfg.fac_dir) if r]
if allowed_roots:           # ← si la liste est VIDE, tout ce bloc est ignoré
    if not any(...):
        return None
```

Si `MEDICINE_DIR` et `FAC_DIR` sont vides (cas par défaut selon `.env.example`), n'importe quel chemin `.pdf` du système est servi sans restriction.

```python
# CORRECTION : bloquer par défaut si aucun répertoire configuré
if not allowed_roots:
    logger.warning("serve_pdf: MEDICINE_DIR/FAC_DIR non configurés — endpoint désactivé.")
    return None
```

#### [IMPORTANT] IDs Notion hardcodés dans le code source

**Fichier :** `backend/config/settings.py:66-67`

```python
item_db_id: str = Field(default="1c9b9fc3-1e69-81dd-a626-e622d9ac878c", ...)
daily_db_id: str = Field(default="1c9b9fc31e69816fb29fdc0006d36308", ...)
```

Des IDs réels de bases Notion sont commités dans le code source. Bien qu'ils ne permettent pas l'accès sans token, ils constituent une fuite d'information.

**Recommandation :** Supprimer les valeurs par défaut, forcer la déclaration dans `.env`. Documenter dans `.env.example`.

#### [MINEUR] Absence de `host='127.0.0.1'` explicite dans `ui.run()`

NiceGUI 3.8.0 écoute sur `127.0.0.1` par défaut, mais cela n'est pas explicite dans le code. Une mise à jour de NiceGUI pourrait changer ce défaut.

```python
ui.run(..., host='127.0.0.1', ...)
```

---

### 1.3 Performance

#### [IMPORTANT] Pas de retry/backoff sur les appels Notion API

**Fichier :** `backend/core/notion/client.py`

Zéro logique de retry sur `query_database()`, `update_page()`, `create_page()`. Une erreur 429 (rate limit) ou 503 (Notion down) échoue immédiatement. Voir §2.2 pour l'implémentation du retry wrapper.

#### [IMPORTANT] Pagination Notion sans throttle inter-pages

**Fichier :** `backend/core/notion/client.py:23`

Le `while has_more` envoie les pages successives sans délai. Pour 300 cours (3 pages Notion), 3 requêtes en rafale — dans les limites, mais fragile si la DB grossit.

```python
# Ajouter dans la boucle while has_more :
if next_cursor:   # pas sur la première requête
    await asyncio.sleep(0.4)   # 2.5 req/s max
```

#### [IMPORTANT] `save_to_disk()` bloque l'event loop

**Fichier :** `backend/state/store.py:119`

Sérialisation JSON de 314 KB + écriture disque synchrone dans l'event loop asyncio. Micro-freeze UI de ~50ms à chaque cycle.

```python
async def save_to_disk_async(self):
    data = self._build_cache_dict()   # rapide, en mémoire
    await asyncio.to_thread(self._write_to_disk, data)   # I/O hors event loop
```

#### [IMPORTANT] Cache invalidé après 12h → cold start systématique

**Fichier :** `backend/state/store.py:205-209`

Si l'app est lancée >12h après la dernière utilisation, le cache est ignoré et un refresh Notion complet est déclenché. Si Notion est down, l'app démarre avec 0 cours.

**Recommandation :** Charger le cache même si >12h ("stale-while-revalidate"), puis rafraîchir en fond.

```python
def load_from_disk(self) -> bool:
    # ... chargement ...
    if age_hours > 12:
        self._needs_refresh = True   # flag, pas un return False
    return True   # toujours charger les données disponibles
```

#### [MINEUR] `ui.timer(0.1)` splash — 10 polls/seconde

**Fichier :** `main.py:114`

10 Hz pendant 2-15 secondes au démarrage. Remplacer par `ui.timer(0.5, ...)`.

---

### 1.4 Dépendances

#### [IMPORTANT] `rapidfuzz` utilisé mais non déclaré

**Fichier :** `backend/core/search/service.py`

`rapidfuzz` est importé et utilisé dans le module de recherche mais absent de `requirements.txt` et `pyproject.toml`. Installation dans un nouvel environnement → `ImportError` au runtime.

```
# À ajouter dans requirements.txt et pyproject.toml :
rapidfuzz>=3.0
```

#### [IMPORTANT] `fuzzywuzzy` déprécié — coexiste avec `rapidfuzz`

**Fichier :** `backend/core/files.py:11`

`fuzzywuzzy` (dernière release : 2021) est encore utilisé dans `files.py` alors que `search/service.py` utilise déjà `rapidfuzz`. Deux librairies de fuzzy matching coexistent, `fuzzywuzzy` ne reçoit plus de mises à jour de sécurité.

**Migration :** API `fuzzywuzzy` → `rapidfuzz` est compatible, remplacer l'import suffit dans la plupart des cas.

#### [IMPORTANT] Absence de lockfile pour les dépendances transitoires

`requirements.txt` et `pyproject.toml` pinent les dépendances directes avec `==` (bien), mais les dépendances transitoires (starlette, httpx, anyio utilisés par NiceGUI) ne sont pas pinees. Un `pip install` dans un nouvel environnement peut installer des versions différentes.

```bash
# Générer un lockfile complet :
uv pip compile pyproject.toml -o requirements.lock
# Commiter requirements.lock
```

---

## 2. Architecture cible (always-on)

### 2.1 Background tasks & scheduler

**Décision architecturale : asyncio natif avec superviseur explicite** (pas APScheduler).

Justification : 3 jobs distincts ne justifient pas une dépendance externe. La couche de supervision ci-dessous apporte les garanties essentielles (restart automatique, backoff, isolation des jobs) sans complexité supplémentaire.

**Problème actuel :** si un job crash, `asyncio.create_task` ne le relance pas.

**Structure révisée de `background.py` :**

```python
async def _supervised_loop(name: str, coro_factory, interval_seconds: int):
    """Relance la coroutine si elle crashe. Backoff exponentiel plafonné à 5 min."""
    consecutive_errors = 0
    _notified_down = False
    while True:
        try:
            await coro_factory()
            consecutive_errors = 0
            if _notified_down:
                _send_windows_notification("Synapse", f"{name} rétabli.")
                _notified_down = False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            consecutive_errors += 1
            backoff = min(60 * (2 ** (consecutive_errors - 1)), 300)
            logger.error(f"[{name}] Erreur #{consecutive_errors}: {e}. Reprise dans {backoff}s.")
            if consecutive_errors == 3 and not _notified_down:
                _send_windows_notification("Synapse — Alerte sync", f"'{name}' en échec 3x: {e}")
                _notified_down = True
            await asyncio.sleep(backoff)
            continue
        await asyncio.sleep(interval_seconds)


async def run_background_tasks():
    logger.info("Démarrage des background tasks supervisées.")
    asyncio.create_task(
        _supervised_loop("sync-notion", _sync_notion_job, interval_seconds=300)
    )
    # daily_routine géré dans son propre module avec boucle interne
```

---

### 2.2 Sync Notion (stratégie + fréquence)

#### Budget de requêtes en régime permanent

| Opération | Fréquence | Req/appel | Req/heure |
|-----------|-----------|-----------|-----------|
| Full refresh cours (300 pages → 3 pages Notion) | 60 min | 4 | 4 |
| Sync diff items (`last_edited_time`) | 5 min | 1 | 12 |
| `auto_link_process` (régime établi) | 5 min | 0 | 0 |
| **Total régime permanent** | | | **~16/h** |
| Rate limit Notion | | | 10 800/h |

Le budget est très confortable. La fréquence actuelle est correcte.

#### Retry wrapper avec backoff exponentiel (nouveau fichier)

**`backend/core/notion/retry.py` (à créer) :**

```python
import asyncio, random, time
from notion_client.errors import APIResponseError
from loguru import logger

_CB_FAILURES = 0
_CB_OPEN_UNTIL: float = 0.0
_CB_THRESHOLD = 5
_CB_RESET_SECONDS = 600   # 10 min de pause circuit ouvert


async def notion_request_with_retry(coro, max_retries: int = 3, base_delay: float = 1.0):
    """Retry avec backoff exponentiel + circuit breaker pour les appels Notion."""
    global _CB_FAILURES, _CB_OPEN_UNTIL

    if _CB_OPEN_UNTIL and time.monotonic() < _CB_OPEN_UNTIL:
        raise RuntimeError("Circuit breaker ouvert — Notion API en pause 10 min.")

    last_exc = None
    for attempt in range(max_retries):
        try:
            result = await coro
            _CB_FAILURES = 0
            _CB_OPEN_UNTIL = 0.0
            return result
        except APIResponseError as e:
            status = getattr(e, 'status', 0)
            if status == 429:
                wait = float(getattr(e, 'headers', {}).get('Retry-After', base_delay))
                wait += random.uniform(0, 1)
                logger.warning(f"Notion 429 (essai {attempt+1}/{max_retries}). Attente {wait:.1f}s.")
                await asyncio.sleep(wait)
            elif status >= 500:
                wait = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(f"Notion {status} (essai {attempt+1}/{max_retries}). Attente {wait:.1f}s.")
                await asyncio.sleep(wait)
            else:
                _CB_FAILURES += 1
                if _CB_FAILURES >= _CB_THRESHOLD:
                    _CB_OPEN_UNTIL = time.monotonic() + _CB_RESET_SECONDS
                    logger.warning(f"Circuit breaker OUVERT après {_CB_FAILURES} échecs Notion.")
                raise
            last_exc = e
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            wait = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(f"Erreur réseau Notion (essai {attempt+1}/{max_retries}): {e}. Attente {wait:.1f}s.")
            await asyncio.sleep(wait)
            last_exc = e

    _CB_FAILURES += 1
    if _CB_FAILURES >= _CB_THRESHOLD:
        _CB_OPEN_UNTIL = time.monotonic() + _CB_RESET_SECONDS
    raise last_exc or RuntimeError("notion_request_with_retry: max retries atteints")
```

Intégration dans `NotionClient.query_database()` : envelopper l'appel `self.client.request(...)` avec `notion_request_with_retry(...)`.

---

### 2.3 Real-time UI (NiceGUI)

#### Mécanismes disponibles

| Mécanisme | Contexte | Usage approprié |
|-----------|----------|-----------------|
| `ui.timer` | Par client WebSocket | Poll UI-side, splash progress, indicateurs sync |
| `app.on_startup` | Serveur global | Lancement des background tasks — déjà utilisé |
| `asyncio.create_task` dans `on_startup` | Loop globale | Background tasks sans lien client |

#### Push de mise à jour depuis background task vers l'UI

NiceGUI n'a pas de mécanisme direct de push depuis une background task vers tous les clients. Pattern recommandé : **état partagé + polling léger côté client**.

```python
# backend/core/ui_notifier.py (à créer)
from datetime import datetime, timezone

_SYNC_STATE: dict = {
    "last_sync_ok": None,
    "last_sync_error": None,
    "cours_count": 0,
    "error_count": 0,
}

def record_sync_success(cours_count: int):
    _SYNC_STATE["last_sync_ok"] = datetime.now(timezone.utc).isoformat()
    _SYNC_STATE["cours_count"] = cours_count
    _SYNC_STATE["error_count"] = 0

def record_sync_error(error: str):
    _SYNC_STATE["last_sync_error"] = datetime.now(timezone.utc).isoformat()
    _SYNC_STATE["error_count"] += 1

def get_sync_state() -> dict:
    return _SYNC_STATE.copy()
```

```python
# Dans une page NiceGUI (ex: dashboard) :
from backend.core.ui_notifier import get_sync_state

def setup_sync_indicator(status_label):
    last_seen = {"ts": None}
    async def _check():
        state = get_sync_state()
        if state["last_sync_ok"] != last_seen["ts"]:
            last_seen["ts"] = state["last_sync_ok"]
            status_label.set_text(f"Sync OK — {state['cours_count']} cours")
    ui.timer(30, _check)   # poll toutes les 30s
```

#### Reconnexion WebSocket

NiceGUI gère la reconnexion automatiquement côté client. Au reconnect, la fonction de page est réexécutée. Si `is_preloaded = True`, le dashboard s'affiche directement avec les données en mémoire (fraîches selon le dernier cycle de sync). Aucun code supplémentaire requis.

---

### 2.4 Résilience & auto-restart (Windows)

#### Option recommandée : NSSM (Non-Sucking Service Manager)

NSSM gère les processus Windows comme des services natifs, avec restart automatique sans limite, redirection des logs, et contrôle via `services.msc`.

**`install_service.bat` (à créer à la racine du projet) :**

```batch
@echo off
:: À exécuter en tant qu'Administrateur une seule fois
set NSSM=C:\nssm\nssm.exe
set APP_DIR=%~dp0
set VENV_PYTHON=%APP_DIR%.venv\Scripts\python.exe

%NSSM% install Synapse "%VENV_PYTHON%"
%NSSM% set Synapse AppDirectory "%APP_DIR%"
%NSSM% set Synapse AppParameters "main.py"
%NSSM% set Synapse AppEnvironmentExtra "SYNAPSE_ENV=prod" "PYTHONUNBUFFERED=1"

:: Restart automatique sur crash (délai 5s)
%NSSM% set Synapse AppExit Default Restart
%NSSM% set Synapse AppRestartDelay 5000

:: Logs du service (en plus de loguru)
%NSSM% set Synapse AppStdout "%APP_DIR%logs\service_stdout.log"
%NSSM% set Synapse AppStderr "%APP_DIR%logs\service_stderr.log"
%NSSM% set Synapse AppRotateFiles 1
%NSSM% set Synapse AppRotateSeconds 86400
%NSSM% set Synapse AppRotateBytes 10485760

:: Démarrage automatique avec Windows
%NSSM% set Synapse Start SERVICE_AUTO_START
%NSSM% start Synapse

echo Service Synapse installe et demarre.
echo Acceder a : http://127.0.0.1:8082
pause
```

**Commandes quotidiennes :**
```batch
nssm start Synapse
nssm stop Synapse
nssm restart Synapse
nssm status Synapse
```

#### Option 2 : Script watchdog .bat (sans droits admin)

```batch
:: watchdog.bat
@echo off
:loop
cd /d "%~dp0"
set SYNAPSE_ENV=prod
.venv\Scripts\python.exe main.py
echo Processus arrete (code %ERRORLEVEL%). Redemarrage dans 5s...
timeout /t 5 /nobreak >nul
goto loop
```

---

### 2.5 Logging & monitoring

#### Endpoint `/health` (nouveau fichier)

```python
# backend/core/health_endpoint.py (à créer)
import time
from datetime import datetime, timezone
from fastapi.responses import JSONResponse

_metrics = {
    "start_time": time.monotonic(),
    "start_dt": datetime.now(timezone.utc).isoformat(),
    "last_sync_ok": None,
    "last_sync_error": None,
    "consecutive_errors": 0,
    "cours_count": 0,
}

def record_sync_success(cours_count: int, items_count: int):
    _metrics["last_sync_ok"] = datetime.now(timezone.utc).isoformat()
    _metrics["consecutive_errors"] = 0
    _metrics["cours_count"] = cours_count

def record_sync_error(error: str):
    _metrics["last_sync_error"] = datetime.now(timezone.utc).isoformat()
    _metrics["consecutive_errors"] += 1

def register_health_endpoint(fastapi_app):
    @fastapi_app.get("/health")
    async def health():
        from backend.state.store import data_store
        uptime = int(time.monotonic() - _metrics["start_time"])
        stale_min = None
        if _metrics["last_sync_ok"]:
            last = datetime.fromisoformat(_metrics["last_sync_ok"])
            stale_min = int((datetime.now(timezone.utc) - last).total_seconds() / 60)

        status = "ok"
        if _metrics["consecutive_errors"] >= 5: status = "degraded"
        elif stale_min and stale_min > 120: status = "degraded"
        elif not data_store.is_preloaded: status = "starting"

        return JSONResponse({
            "status": status,
            "uptime_seconds": uptime,
            "started_at": _metrics["start_dt"],
            "sync": {
                "last_ok": _metrics["last_sync_ok"],
                "last_error": _metrics["last_sync_error"],
                "stale_minutes": stale_min,
                "consecutive_errors": _metrics["consecutive_errors"],
            },
            "data": {
                "cours_count": _metrics["cours_count"] or len(data_store.cours),
                "is_preloaded": data_store.is_preloaded,
            }
        })

    @fastapi_app.get("/health/ping")
    async def ping():
        return {"pong": True}
```

Vérification rapide depuis le navigateur : `http://127.0.0.1:8082/health`

#### Loguru — configuration actuelle

La configuration loguru dans `main.py` est **correcte** pour un always-on :
- ✅ Rotation quotidienne à minuit
- ✅ Rétention 30 jours
- ✅ Compression ZIP des anciens logs
- ✅ Niveau DEBUG sur fichier, INFO sur console

Volumétrie mesurée : ~1-2 MB/jour non compressé → ~50-100 KB compressé → ~1.5-3 MB/mois. Acceptable.

---

## 3. Problèmes anticipés & solutions

| # | Problème | Proba | Impact | Délai | Solution recommandée |
|---|----------|-------|--------|-------|----------------------|
| 1 | **Notion rate limit 429** sur `_push_missing_obsidian_uris` au redémarrage post-12h | **CONFIRMÉ** | Burst 6.67 req/s → 429 en cascade | Immédiat (déjà actif) | Sleep inconditionnel `finally: await asyncio.sleep(0.35)` |
| 2 | **JSON corrompu** `data_cache.json` — double save concurrent | Haute | Perte totale du cache → cold start | 1-4 semaines | Écriture atomique via `os.replace()` |
| 3 | **Restart loop** `reload=True` + watchfiles surveille les `.log` | Haute | App inutilisable | 1-7 jours | `reload=False` en prod (`SYNAPSE_ENV=prod`) |
| 4 | **`daily_routine` non planifié** — tourne une seule fois | **CONFIRMÉ** | Tâches Notion J+1/J+2 non créées | Immédiat | Transformer en boucle avec calcul heure cible |
| 5 | **Cold start vide** : cache >12h + Notion down | Moyenne | App ouvre avec 0 cours | Premiers jours | Stale-while-revalidate : charger le cache même si >12h |
| 6 | **SQLite WAL non checkpoint** en always-on | Moyenne | `.db-wal` grossit indéfiniment | 30-90 jours | Ajouter `PRAGMA wal_checkpoint(TRUNCATE)` hebdomadaire |
| 7 | **Pas de service Windows** → pas de restart sur crash | **CONFIRMÉ** | Downtime si crash ou reboot Windows | Immédiat | Installer NSSM |
| 8 | **`_push_obsidian_uris` sleep skippé** sur exception inner | Haute | Burst Notion non limité sur erreur | Aléatoire | `finally: await asyncio.sleep(0.35)` (même fix que #1) |
| 9 | **Connexion httpx idle** trop longtemps → reset TCP | Moyenne | Exception au prochain appel | Jours | Géré par retry wrapper (§2.2) |
| 10 | **data_cache.json** croissance linéaire | Faible | 314 KB/299 cours → ~1 MB/1000 cours | Mois | Non bloquant, monitoring suffisant |
| 11 | **`synapse_local.db` WAL** croissance non bornée (mastery_snapshots) | Faible | Croissance lente, ~1 MB/an | Mois | Purge des snapshots >2 ans |
| 12 | **`build_semantic_graph` O(n²)** règle same_college | Faible | Rebuild lent si >500 cours | Mois | Acceptable à l'échelle actuelle |
| 13 | **Deux `preload_all_views()` concurrents** si reconnexion pendant splash + CancelledError | Faible | États `loading_progress` corrompus | Rare | Ajouter guard avec lock asyncio |
| 14 | **Antivirus Windows Defender** scanne les `.py` → déclenche watchfiles | Variable | Restart intempestif (avec `reload=True`) | Dès le début | Fix #3 (reload=False) élimine ce risque |
| 15 | **Windows Update** / reboot → downtime | **CONFIRMÉ** | App ne redémarre pas seule | Aléatoire | Fix #7 (NSSM) |

---

## 4. Plan d'action priorisé

### Bloquant — À faire avant tout lancement always-on

- [ ] **[SEC]** Révoquer le refresh token Google OAuth et le client secret dans Google Cloud Console
- [ ] **[SEC]** Déplacer `credentials.json` et `token.json` hors du répertoire git (ex: `~/.config/synapse/`)
- [ ] **[BUG]** `main.py` — passer `reload=False` en prod via `SYNAPSE_ENV=prod`
- [ ] **[BUG]** `background.py` — rendre `await asyncio.sleep(0.35)` inconditionnel dans `_push_obsidian_uris` et `_push_missing_obsidian_uris` (déplacer dans `finally:`)

### Important — Semaine 1

- [ ] **[ARCH]** Transformer `run_daily_routine()` en boucle avec déclenchement quotidien à 07h00
- [ ] **[BUG]** `store.py` — écriture atomique `save_to_disk()` via `os.replace(tmp, cache_file)`
- [ ] **[PERF]** `store.py` — stale-while-revalidate : supprimer l'invalidation à 12h (charger + flag refresh)
- [ ] **[ARCH]** Créer `backend/core/notion/retry.py` et intégrer dans `NotionClient.query_database()`
- [ ] **[OPS]** Créer `install_service.bat` et installer NSSM
- [ ] **[ARCH]** Créer `backend/core/health_endpoint.py` + enregistrer dans `startup_handler`
- [ ] **[DEP]** Ajouter `rapidfuzz>=3.0` dans `requirements.txt` + `pyproject.toml`, supprimer `fuzzywuzzy` + `python-Levenshtein`
- [ ] **[CODE]** Supprimer le `logger.info("DEBUG PROPERTIES:...")` dans `service.py:90`
- [ ] **[CODE]** Remplacer les deux `print()` dans `recommendation_service.py` par `logger.debug()`
- [ ] **[SEC]** Corriger `serve_pdf()` : bloquer si `allowed_roots` est vide
- [ ] **[SEC]** Supprimer les IDs Notion hardcodés dans `settings.py` (forcer via `.env`)

### Nice-to-have — Semaine 2

- [ ] **[PERF]** Ajouter `asyncio.sleep(0.4)` entre pages de pagination dans `NotionClient.query_database()`
- [ ] **[ARCH]** Ajouter superviseur `_supervised_loop` dans `background.py` pour relance auto sur crash
- [ ] **[ARCH]** Créer `backend/core/ui_notifier.py` pour indicateur de sync dans l'UI
- [ ] **[OPS]** Ajouter `PRAGMA wal_checkpoint(TRUNCATE)` hebdomadaire dans `local_store.py`
- [ ] **[DEP]** Générer `requirements.lock` avec `uv pip compile`
- [ ] **[CODE]** Extraire `_parse_item_value()` pour dédupliquer `get_all_items_map` / `get_updated_items_map`
- [ ] **[CODE]** Supprimer la méthode `mark_review_done()` DEPRECATED
- [ ] **[PERF]** Rendre `save_to_disk()` async via `asyncio.to_thread()`
- [ ] **[PERF]** `ui.timer(0.5, ...)` au lieu de `0.1` pour le splash screen
- [ ] **[SEC]** `host='127.0.0.1'` explicite dans `ui.run()`

---

## 5. Checklist finale avant mise en prod

### Sécurité
- [ ] Credentials Google révoqués et régénérés
- [ ] `credentials.json` et `token.json` déplacés hors du projet git
- [ ] `git log --all --full-history -- credentials.json token.json` → aucun commit
- [ ] `.gitignore` vérifié : `credentials.json`, `token.json`, `.env` présents
- [ ] `serve_pdf()` corrigé (blocage si allowed_roots vide)
- [ ] IDs Notion supprimés du code source

### Configuration
- [ ] `SYNAPSE_ENV=prod` défini dans l'environnement ou dans NSSM
- [ ] `reload=False` vérifié au démarrage (check via logs : pas de message "Reloading...")
- [ ] `.env` complet : `NOTION_TOKEN`, `DATABASE_COURS_ID`, `MEDICINE_DIR`, `FAC_DIR`
- [ ] `OBSIDIAN_VAULT_PATH` et `OBSIDIAN_VAULT_NAME` configurés si vault utilisé
- [ ] `GOOGLE_CREDENTIALS_PATH` pointant vers le nouvel emplacement des credentials

### Background tasks
- [ ] `run_daily_routine()` transformée en boucle — vérifier dans les logs qu'elle se lance à 07h00
- [ ] `_push_obsidian_uris` : sleep inconditionnel dans `finally` — vérifier dans les logs qu'aucun burst >3 req/s
- [ ] Retry wrapper Notion installé — vérifier un log de type "Notion 429 → retry" dans les tests

### Service Windows
- [ ] NSSM installé : `nssm status Synapse` → `SERVICE_RUNNING`
- [ ] Démarrage automatique activé : `nssm get Synapse Start` → `SERVICE_AUTO_START`
- [ ] Test de crash : tuer le processus python.exe → vérifier redémarrage en <10s
- [ ] Test reboot Windows → Synapse redémarre automatiquement

### Monitoring
- [ ] `/health/ping` répond `{"pong": true}` à `http://127.0.0.1:8082/health/ping`
- [ ] `/health` répond `"status": "ok"` après le preload complet
- [ ] Logs dans `logs/synapse_YYYY-MM-DD.log` : rotation confirmée à minuit
- [ ] Espace disque disponible suffisant (>1 GB recommandé)

### Dépendances
- [ ] `pip install rapidfuzz` (ou via requirements.txt mis à jour)
- [ ] `fuzzywuzzy` et `python-Levenshtein` désinstallés
- [ ] `pip check` → aucun conflit de dépendances

### Validation fonctionnelle
- [ ] Ouvrir `http://127.0.0.1:8082` → splash screen puis dashboard en <15s
- [ ] Vérifier les logs du Cycle 1 : refresh cours + sync items sans erreur 429
- [ ] Attendre 5 min → Cycle 2 dans les logs, pas de restart de l'app
- [ ] Attendre jusqu'à 07h00 → `daily_routine` créé les tâches J+1/J+2 dans Notion
- [ ] Attendre 60 min → Cycle 12, refresh complet des cours visible dans les logs

---

## Annexe — Fichiers à créer / modifier

| Fichier | Action | Priorité |
|---------|--------|----------|
| `backend/core/notion/retry.py` | Créer | P1 |
| `backend/core/health_endpoint.py` | Créer | P1 |
| `backend/core/ui_notifier.py` | Créer | P2 |
| `install_service.bat` | Créer | P1 |
| `main.py` | Modifier (reload, host, health endpoint, SYNAPSE_ENV) | P0 |
| `backend/core/background.py` | Modifier (sleep finally, supervised_loop) | P0/P1 |
| `backend/features/daily_routine.py` | Modifier (boucle planifiée) | P1 |
| `backend/state/store.py` | Modifier (save atomique, stale-while-revalidate) | P1 |
| `backend/core/notion/client.py` | Modifier (intégrer retry wrapper) | P1 |
| `backend/config/settings.py` | Modifier (supprimer IDs hardcodés) | P1 |
| `backend/core/notion/service.py` | Modifier (supprimer DEBUG log, extraire _parse_item_value) | P1 |
| `requirements.txt` + `pyproject.toml` | Modifier (rapidfuzz, supprimer fuzzywuzzy) | P1 |
| `.gitignore` | Vérifier / compléter | P0 |

---

*Document généré le 2026-06-18 par analyse automatique du codebase (3 agents en parallèle + analyse manuelle).*  
*Prochaine révision recommandée : après implémentation des corrections P0/P1.*
