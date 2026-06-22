"""
network_capture/ednpro_sync.py — Synapse
-----------------------------------------
Version synchrone du fetch EDN Pro pour le bouton "Importer QCM".
Réutilise la même logique que _fetch_ednpro_background() dans background.py,
mais appelle _do_fetch() directement (pas de asyncio.to_thread).
"""
from __future__ import annotations

import json
from pathlib import Path
from loguru import logger


def sync() -> dict:
    """
    Récupère les nouvelles sessions EDN Pro et écrit un fichier .md dans data/ai_qcm/.

    Retourne {
        success       : bool,
        new_sessions  : int,   # nombre de sessions nouvelles trouvées
        file          : Path|None,
        needs_setup   : bool,  # True si credentials manquants/incomplets
        errors        : list[str],
    }
    """
    result: dict = {
        "success":      False,
        "new_sessions": 0,
        "file":         None,
        "needs_setup":  False,
        "errors":       [],
    }

    try:
        from backend.core.network_capture.fetcher import SupabaseFetcher, EDNPRO_CREDS_PATH
        from backend.core.network_capture.converters import extract_sessions_ednpro
        from backend.core.network_capture.writer import write_sessions

        if not EDNPRO_CREDS_PATH.exists():
            result["needs_setup"] = True
            return result

        creds = json.loads(EDNPRO_CREDS_PATH.read_text(encoding="utf-8"))
        if not creds.get("refresh_token") or not creds.get("bearer_token"):
            result["needs_setup"] = True
            return result

        _SYNC_STATE = EDNPRO_CREDS_PATH.parent / "ednpro_sync_state.json"

        # Charge les IDs déjà exportés
        known_ids: set[str] = set()
        if _SYNC_STATE.exists():
            try:
                state = json.loads(_SYNC_STATE.read_text(encoding="utf-8"))
                known_ids = set(state.get("session_ids", []))
            except Exception:
                pass

        fetcher = SupabaseFetcher()
        rows    = fetcher.fetch_training_sessions(limit=500)
        if not rows:
            result["success"] = True  # credentials ok mais aucune session
            return result

        current_ids = {r["id"] for r in rows if r.get("id")}
        new_ids     = current_ids - known_ids

        if not new_ids:
            result["success"] = True  # tout déjà exporté
            return result

        new_rows = [r for r in rows if r.get("id") in new_ids]
        sessions = extract_sessions_ednpro(new_rows)
        if not sessions:
            result["success"] = True
            return result

        fpath = write_sessions("EDNpro", sessions)

        # Met à jour l'état — écriture atomique
        all_ids = sorted(known_ids | current_ids)
        _tmp = _SYNC_STATE.with_suffix(".json.tmp")
        _tmp.write_text(
            json.dumps({"session_ids": all_ids}, ensure_ascii=False),
            encoding="utf-8",
        )
        _tmp.replace(_SYNC_STATE)

        result["success"]      = True
        result["new_sessions"] = len(sessions)
        result["file"]         = fpath
        logger.success(f"EDN Pro sync : {len(sessions)} session(s) → {fpath.name}")

    except Exception as exc:
        msg = str(exc)
        result["errors"].append(msg)
        logger.warning(f"EDN Pro sync erreur : {msg}")

    return result
