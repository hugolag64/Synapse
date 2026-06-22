"""
network_capture/har.py
----------------------
Analyse un fichier HAR (export DevTools) pour découvrir les endpoints
QCM de Hypocampus et EDN Pro.

Usage :
    from backend.core.network_capture.har import HARAnalyzer
    a = HARAnalyzer("session.har")
    a.discover()          # affiche les endpoints probables, sauvegarde les dumps
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from loguru import logger

# ── Domaines cibles ────────────────────────────────────────────────────────────

TARGET_DOMAINS = [
    "hypocampus.fr",
    "ednpro.app",
    "ednpro.fr",
    "edn-pro.fr",
    "edn.fr",
    "supabase.co",   # EDN Pro utilise Supabase — l'API peut aller sur *.supabase.co
]

# Mots-clés dans l'URL qui indiquent un endpoint QCM potentiel
QCM_URL_KEYWORDS = [
    "quiz", "qcm", "question", "result", "score", "session",
    "exam", "training", "test", "exercice", "correction",
    "stat", "history", "performance",
    # EDN Pro / Supabase spécifiques
    "objective", "session_answer", "qre", "qroc",
    "objective_session", "user_session", "user_objective",
]

# Clés JSON qui suggèrent des données QCM
QCM_JSON_KEYS = {
    "high": {"score", "correct", "wrong", "total_questions", "nbcorrect",
             "nbwrong", "nb_correct", "nb_wrong", "result", "correction"},
    "medium": {"question", "questions", "answers", "answer", "session",
               "quiz", "percent", "percentage", "grade"},
    "low": {"title", "name", "course", "item", "module", "theme"},
}


def _score_entry(url: str, body: dict | list) -> int:
    """Score 0-100 : probabilité que cet endpoint contienne des données QCM."""
    score = 0

    url_lower = url.lower()
    for kw in QCM_URL_KEYWORDS:
        if kw in url_lower:
            score += 10

    if isinstance(body, list):
        body_to_check = body[0] if body else {}
    else:
        body_to_check = body

    if not isinstance(body_to_check, dict):
        return score

    keys_lower = {k.lower() for k in _flatten_keys(body_to_check)}
    for key in QCM_JSON_KEYS["high"]:
        if key in keys_lower:
            score += 15
    for key in QCM_JSON_KEYS["medium"]:
        if key in keys_lower:
            score += 5
    for key in QCM_JSON_KEYS["low"]:
        if key in keys_lower:
            score += 2

    return min(score, 100)


def _flatten_keys(d: dict, depth: int = 2) -> set[str]:
    """Retourne toutes les clés jusqu'à `depth` niveaux."""
    keys = set()
    for k, v in d.items():
        keys.add(k.lower())
        if depth > 1 and isinstance(v, dict):
            keys.update(_flatten_keys(v, depth - 1))
        elif depth > 1 and isinstance(v, list) and v and isinstance(v[0], dict):
            keys.update(_flatten_keys(v[0], depth - 1))
    return keys


class HARAnalyzer:
    def __init__(self, har_path: str | Path, dump_dir: str | Path | None = None):
        self.har_path = Path(har_path)
        _root = Path(__file__).parent.parent.parent.parent
        self.dump_dir = Path(dump_dir) if dump_dir else _root / "data" / "network_capture"

    def _load(self) -> list[dict]:
        """Charge le HAR et retourne la liste des entrées."""
        data = json.loads(self.har_path.read_text(encoding="utf-8"))
        return data.get("log", {}).get("entries", [])

    def _is_target(self, url: str) -> bool:
        return any(d in url for d in TARGET_DOMAINS)

    def _parse_body(self, entry: dict) -> dict | list | None:
        """Extrait et parse le body JSON d'une réponse."""
        try:
            content = entry["response"]["content"]
            mime = content.get("mimeType", "")
            if "json" not in mime:
                return None
            text = content.get("text", "")
            if not text:
                return None
            return json.loads(text)
        except Exception:
            return None

    def discover(self, min_score: int = 10) -> list[dict]:
        """
        Analyse le HAR, rank les endpoints par pertinence QCM.

        Retourne la liste des entrées pertinentes, sauvegarde les dumps JSON.
        """
        self.dump_dir.mkdir(parents=True, exist_ok=True)

        entries = self._load()
        logger.info(f"HAR chargé : {len(entries)} entrées")

        results = []
        for entry in entries:
            url = entry["request"]["url"]
            if not self._is_target(url):
                continue

            status = entry["response"]["status"]
            if status not in (200, 201):
                continue

            body = self._parse_body(entry)
            if body is None:
                continue

            s = _score_entry(url, body)
            if s < min_score:
                continue

            method = entry["request"]["method"]
            results.append({
                "score": s,
                "method": method,
                "url": url,
                "body": body,
            })

        results.sort(key=lambda x: x["score"], reverse=True)

        self._print_results(results)
        self._save_dumps(results)

        return results

    def _print_results(self, results: list[dict]) -> None:
        if not results:
            logger.warning("Aucun endpoint QCM trouvé dans ce HAR.")
            logger.info(
                "Vérifie que tu as bien fait un QCM complet APRÈS avoir ouvert "
                "DevTools → Network, et que le domaine est dans TARGET_DOMAINS."
            )
            return

        logger.success(f"\n{'─'*60}")
        logger.success(f"  {len(results)} endpoint(s) QCM probables trouvés")
        logger.success(f"{'─'*60}")
        for i, r in enumerate(results[:15], 1):
            logger.info(f"  #{i:02d}  [{r['score']:3d}]  {r['method']}  {r['url']}")
        logger.success(f"{'─'*60}")
        logger.info(f"Dumps JSON sauvegardés dans : {self.dump_dir}")

    def _save_dumps(self, results: list[dict]) -> None:
        index = []
        for i, r in enumerate(results, 1):
            slug = re.sub(r"[^a-zA-Z0-9_-]", "_", r["url"])[-60:]
            fname = f"{i:02d}_score{r['score']}_{slug}.json"
            fpath = self.dump_dir / fname
            fpath.write_text(
                json.dumps({"url": r["url"], "method": r["method"], "body": r["body"]},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            index.append({"rank": i, "score": r["score"], "file": fname, "url": r["url"]})

        if index:
            (self.dump_dir / "index.json").write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
            )
