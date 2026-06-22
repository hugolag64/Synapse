"""
network_capture/writer.py
--------------------------
Écrit les sessions extraites dans data/ai_qcm/ au format Synapse markdown,
compatibles avec le pipeline ai_qcm/service.py existant.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent.parent
INBOX_DIR = _ROOT / "data" / "ai_qcm"


def write_sessions(platform: str, sessions: list[dict], out_dir: Path | None = None) -> Path:
    """
    Génère un fichier markdown Synapse QCM à partir d'une liste de sessions.

    Retourne le chemin du fichier créé.
    """
    if not sessions:
        raise ValueError("Aucune session à écrire")

    out_dir = out_dir or INBOX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.today().strftime("%Y-%m-%d")
    ts = int(time.time())
    fname = f"capture_{platform.lower()}_{today}_{ts}.md"
    fpath = out_dir / fname

    # Filtrage minimal : on garde les sessions avec au moins un cours identifiable
    valid = [s for s in sessions if s.get("course_title") or s.get("item_number")]
    if not valid:
        raise ValueError("Aucune session valide (course_title ou item_number manquants)")

    payload = {
        "synapse_version": 1,
        "date": today,
        "platform": platform,
        "session_type": "QCM",
        "sessions": [_clean_session(s) for s in valid],
    }

    content = f"---json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n---\n\n"
    content += f"# Import automatique {platform} — {today}\n\n"
    content += f"Capture réseau automatique : {len(valid)} session(s).\n"

    fpath.write_text(content, encoding="utf-8")
    return fpath


def _clean_session(s: dict) -> dict:
    """Garde uniquement les clés attendues par le parser Synapse."""
    out: dict = {
        "course_title":  s.get("course_title", ""),
        "item_number":   str(s.get("item_number", "") or ""),
        "score_raw":     s.get("score_raw", "") or "",
        "score_percent": s.get("score_percent"),
        "session_type":  s.get("session_type", "QCM"),
        "error_types":   s.get("error_types", []),
        "weak_points":   s.get("weak_points", []),
    }
    for opt in ("total_questions", "correct_answers", "wrong_answers", "difficulty", "comments"):
        if s.get(opt) is not None:
            out[opt] = s[opt]
    # Inclut les questions détaillées si présentes (text + propositions + résultat)
    if s.get("questions"):
        out["questions"] = s["questions"]
    return out
