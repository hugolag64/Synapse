"""
network_capture/hypocampus_sync.py — Synapse
---------------------------------------------
Orchestrateur de synchronisation Hypocampus -> Synapse.
Appelé depuis le bouton "Sync Hypocampus" dans l'UI QCM.

Workflow :
  1. Vérifie le token (privilegeToken dans localStorage)
  2. Si expiré -> demande renouvellement dans l'UI (30 secondes)
  3. Auto-découverte des endpoints GET (première fois uniquement)
  4. Fetch sessions + conversion + import dans SQLite
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from loguru import logger

from backend.core.network_capture.fetcher import (
    HypocampusFetcher,
    load_hypocampus_credentials,
    save_hypocampus_credentials,
    HYPOCAMPUS_CREDS_PATH,
)
from backend.core.network_capture.converters import extract_sessions
from backend.core.network_capture.writer import write_sessions
from backend.core.ai_qcm import service as ai_qcm_service

_ROOT = Path(__file__).parent.parent.parent.parent
_DUMP_DIR = _ROOT / "data" / "network_capture"


# ── Snippet JS — une seule ligne à coller dans la console Chrome ───────────────
# Récupère les deux tokens nécessaires :
#   privilegeToken     = token principal (expiry check)
#   cortexio.accessToken = token API QCM (/api/hypo3/v1/qs/...)

JS_SNIPPET = (
    "console.log('SYNAPSE:' + localStorage.getItem('privilegeToken') + "
    "'|ACCESS:' + localStorage.getItem('cortexio.accessToken'))"
)

# ── Snippet JS pour exporter les sessions depuis le dashboard ──────────────────
# À coller dans la console Chrome sur https://www.hypocampus.fr/app/dashboard
# Extrait tous les IDs de session visibles + fetch leurs données via l'API.

JS_SNIPPET_SESSIONS = (
    "(async()=>{"
    "const t=localStorage.getItem('cortexio.accessToken');"
    # Click every "Afficher plus" button to expand session lists
    "const btns=[...document.querySelectorAll('button,a')];"
    "btns.filter(el=>/afficher plus|voir plus/i.test(el.textContent)).forEach(b=>b.click());"
    "await new Promise(r=>setTimeout(r,1800));"
    # Also try opening Historique modal
    "const hBtn=btns.find(el=>/historique/i.test(el.textContent));"
    "if(hBtn){hBtn.click();await new Promise(r=>setTimeout(r,1800));}"
    # Extract unique session IDs from all /qs/ links visible in the page
    "const ids=[...new Set("
    "[...document.querySelectorAll('a[href*=\"/qs/\"]')]"
    ".map(a=>{try{const p=new URL(a.href).pathname;"
    "const m=p.match(/\\/qs\\/([^\\/\\?#]+)/);"
    "return m?m[1]:null;}catch(e){return null;}})"
    ".filter(Boolean)"
    ")];"
    "const s=[];"
    "for(const id of ids){"
    "try{"
    "const r=await fetch("
    "`https://www.hypocampus.fr/api/hypo3/v1/qs/sessions/${id}?pos=1`,"
    "{headers:{'Authorization':'Bearer '+t,'Accept':'application/json'}}"
    ");"
    "if(r.ok)s.push(await r.json());"
    "}catch(e){}}"
    "console.log('SYNAPSE_HYPO:'+JSON.stringify(s));"
    "})();"
)

# ── État du token ──────────────────────────────────────────────────────────────

def token_status() -> dict:
    """
    Retourne l'état du token Hypocampus.
    {status: "ok"|"expiring"|"expired"|"missing", days_left: int|None}
    """
    try:
        creds = load_hypocampus_credentials()
    except FileNotFoundError:
        return {"status": "missing", "days_left": None}

    bearer = creds.get("bearer_token", "")
    if not bearer:
        return {"status": "missing", "days_left": None}

    try:
        payload = bearer.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = json.loads(base64.b64decode(payload))
        exp = decoded.get("exp", 0)
        seconds_left = exp - time.time()
        days_left = max(0, int(seconds_left / 86400))

        if seconds_left <= 0:
            return {"status": "expired", "days_left": 0}
        elif seconds_left < 86400 * 2:
            return {"status": "expiring", "days_left": days_left}
        else:
            return {"status": "ok", "days_left": days_left}
    except Exception:
        return {"status": "expired", "days_left": None}


def save_new_token(raw: str) -> bool:
    """
    Sauvegarde les tokens collés par l'utilisateur depuis le dialog.

    Formats acceptés :
      - Format dual (nouveau snippet) :
          SYNAPSE:eyJ…privilegeToken…|ACCESS:eyJ…cortexio.accessToken…
      - Token brut unique (ancien format) : eyJ… (privilegeToken seul)

    Retourne True si au moins un token valide a été trouvé.
    """
    raw = raw.strip()
    if raw.startswith("SYNAPSE:"):
        raw = raw[len("SYNAPSE:"):]

    privilege_token: str = ""
    access_token: str = ""

    if "|ACCESS:" in raw:
        parts = raw.split("|ACCESS:", 1)
        privilege_token = parts[0].strip().strip('"\'')
        access_token    = parts[1].strip().strip('"\'')
    else:
        privilege_token = raw.strip('"\'')

    if not privilege_token.startswith("ey") or privilege_token.count(".") < 2:
        return False

    from backend.core.network_capture.fetcher import _extract_user_id_from_jwt
    user_id = _extract_user_id_from_jwt(privilege_token)

    api_token = (
        access_token
        if access_token and access_token.startswith("ey") and access_token.count(".") >= 2
        else privilege_token
    )

    save_hypocampus_credentials(
        bearer_token=privilege_token,
        access_token=api_token,
        user_id=user_id,
    )
    return True


# ── Import depuis JSON collé (snippet dashboard) ───────────────────────────────

def sync_from_json(raw: str, courses=None) -> dict:
    """
    Importe des sessions Hypocampus depuis le JSON copié-collé par l'utilisateur.

    raw : sortie du JS_SNIPPET_SESSIONS (commence par "SYNAPSE_HYPO:" ou JSON brut).

    Retourne le même format que sync().
    """
    result: dict = {
        "success":           False,
        "sessions_fetched":  0,
        "sessions_imported": 0,
        "skipped":           0,
        "raw_sessions":      [],
        "errors":            [],
    }

    raw = raw.strip()
    if raw.startswith("SYNAPSE_HYPO:"):
        raw = raw[len("SYNAPSE_HYPO:"):]
    raw = raw.strip()

    try:
        sessions_data = json.loads(raw)
    except Exception:
        result["errors"].append("JSON invalide — colle la ligne complète depuis la console.")
        return result

    if not isinstance(sessions_data, list):
        sessions_data = [sessions_data]

    if not sessions_data:
        result["errors"].append("Aucune session dans le JSON collé.")
        return result

    from backend.core.network_capture.converters import extract_sessions_hypocampus
    sessions = extract_sessions_hypocampus(sessions_data)
    result["sessions_fetched"] = len(sessions)

    if not sessions:
        result["errors"].append("Aucune session convertie (format inattendu).")
        return result

    try:
        fpath = write_sessions("Hypocampus", sessions)
        logger.success(f"Fichier créé : {fpath}")
    except Exception as exc:
        result["errors"].append(f"Écriture fichier : {exc}")
        return result

    import_res = ai_qcm_service.import_all(courses=courses)
    result["sessions_imported"] = import_res.get("total_sessions", 0)
    result["skipped"]           = import_res.get("total_skipped", 0)
    result["raw_sessions"]      = import_res.get("raw_sessions", [])
    result["errors"].extend(import_res.get("errors", []))
    result["success"] = result["sessions_imported"] > 0 or result["skipped"] > 0

    return result


# ── Synchronisation principale ─────────────────────────────────────────────────

def sync(courses=None) -> dict:
    """
    Synchronise l'historique QCM Hypocampus dans Synapse.

    Retourne {
        success, sessions_fetched, sessions_imported, skipped,
        endpoint_found, needs_token_renewal, raw_sessions, errors
    }.
    """
    result: dict = {
        "success":              False,
        "sessions_fetched":     0,
        "sessions_imported":    0,
        "skipped":              0,
        "endpoint_found":       False,
        "needs_token_renewal":  False,
        "raw_sessions":         [],
        "errors":               [],
    }

    # ── Vérification du token ──────────────────────────────────────────────────
    status = token_status()
    if status["status"] in ("missing", "expired"):
        result["needs_token_renewal"] = True
        result["errors"].append(
            "Token Hypocampus expiré ou absent (renouvellement requis)."
        )
        return result

    try:
        fetcher = HypocampusFetcher()
    except Exception as exc:
        result["needs_token_renewal"] = True
        result["errors"].append(str(exc))
        return result

    dump_dir = _DUMP_DIR / "hypocampus_fetch"

    # ── Fetch via endpoint paginé /qs/sessions/latest/all ─────────────────────
    logger.info("Récupération de toutes les sessions via /qs/sessions/latest/all...")
    raw_list = fetcher.fetch_all_sessions_list(dump_dir=dump_dir)

    if not raw_list:
        result["errors"].append(
            "Aucune session récupérée. Token peut-être expiré — renouvelle-le."
        )
        result["needs_token_renewal"] = True
        return result

    result["endpoint_found"] = True

    # ── Conversion ────────────────────────────────────────────────────────────
    all_sessions: list[dict] = []
    try:
        all_sessions = extract_sessions("Hypocampus", raw_list)
        logger.info(f"  {len(raw_list)} sessions brutes → {len(all_sessions)} sessions converties")
    except Exception as exc:
        result["errors"].append(f"Conversion : {exc}")
        return result

    result["sessions_fetched"] = len(all_sessions)

    if not all_sessions:
        result["errors"].append(
            "Données récupérées mais format API non reconnu.\n"
            f"Dumps bruts disponibles dans {dump_dir.resolve()}\n"
            "Transmets un dump à Claude pour adapter le converter."
        )
        return result

    # ── Écriture markdown + import ────────────────────────────────────────────
    try:
        fpath = write_sessions("Hypocampus", all_sessions)
        logger.success(f"Fichier créé : {fpath}")
    except Exception as exc:
        result["errors"].append(f"Écriture fichier : {exc}")
        return result

    import_res = ai_qcm_service.import_all(courses=courses)
    result["sessions_imported"] = import_res.get("total_sessions", 0)
    result["skipped"]           = import_res.get("total_skipped", 0)
    result["raw_sessions"]      = import_res.get("raw_sessions", [])
    result["errors"].extend(import_res.get("errors", []))
    result["success"] = result["sessions_imported"] > 0 or result["skipped"] > 0

    return result
