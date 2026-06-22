"""
ai_qcm/parser.py — Synapse
---------------------------
Parse les fichiers markdown générés par ChatGPT/Gemini.

Format attendu :
  ---json
  { ... }
  ---

  # Corps en prose (optionnel, ignoré)
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class WeakPointEntry:
    detail: str
    category: Optional[str] = None
    severity: int = 2


@dataclass
class QCMSessionEntry:
    course_title: str
    item_number: str
    score_raw: Optional[str]
    score_percent: Optional[float]
    total_questions: Optional[int]
    correct_answers: Optional[int]
    wrong_answers: Optional[int]
    difficulty: Optional[str]
    error_types: list[str]
    weak_points: list[WeakPointEntry]
    comments: Optional[str]


@dataclass
class AIQCMFile:
    path: Path
    date: str
    platform: str        # "ChatGPT" | "Gemini"
    session_type: str    # "QCM" | "DP" | "KFP" | "Annales"
    sessions: list[QCMSessionEntry]
    notes: Optional[str]
    raw: dict


class ParseError(Exception):
    pass


def parse_file(path: Path) -> AIQCMFile:
    """Parse un fichier markdown Synapse AI-QCM. Lève ParseError si invalide."""
    text = path.read_text(encoding="utf-8")

    # Extraire le bloc JSON entre ---json et ---
    marker = "---json"
    if marker not in text:
        raise ParseError(f"Pas de bloc ---json trouvé dans {path.name}")

    start = text.index(marker) + len(marker)
    end = text.index("---", start)
    json_str = text[start:end].strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON invalide dans {path.name}: {e}")

    if not isinstance(data, dict):
        raise ParseError(f"JSON doit être un objet dans {path.name}")

    # Date
    date_str = str(data.get("date", datetime.date.today().isoformat()))
    try:
        datetime.date.fromisoformat(date_str)
    except ValueError:
        date_str = datetime.date.today().isoformat()

    platform = str(data.get("platform", "ChatGPT"))
    session_type = str(data.get("session_type", "QCM"))

    raw_sessions = data.get("sessions", [])
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise ParseError(f"'sessions' vide ou absent dans {path.name}")

    sessions: list[QCMSessionEntry] = []
    for i, s in enumerate(raw_sessions):
        if not isinstance(s, dict):
            raise ParseError(f"Session {i} invalide dans {path.name}")

        score_raw = s.get("score_raw")
        score_percent = s.get("score_percent")

        # Auto-calcul depuis score_raw si score_percent absent
        if score_percent is None and score_raw:
            try:
                from backend.core.qcm.service import parse_score
                pct, _ = parse_score(str(score_raw))
                score_percent = pct
            except Exception:
                pass

        # Weak points
        weak_points: list[WeakPointEntry] = []
        for wp in (s.get("weak_points") or []):
            if isinstance(wp, dict) and wp.get("detail"):
                weak_points.append(WeakPointEntry(
                    detail=str(wp["detail"]),
                    category=wp.get("category") or None,
                    severity=int(wp.get("severity", 2)),
                ))

        # Error types
        raw_et = s.get("error_types") or []
        error_types = [str(e) for e in raw_et] if isinstance(raw_et, list) else []

        sessions.append(QCMSessionEntry(
            course_title=str(s.get("course_title", "")),
            item_number=str(s.get("item_number", "")),
            score_raw=str(score_raw) if score_raw else None,
            score_percent=float(score_percent) if score_percent is not None else None,
            total_questions=int(s["total_questions"]) if s.get("total_questions") is not None else None,
            correct_answers=int(s["correct_answers"]) if s.get("correct_answers") is not None else None,
            wrong_answers=int(s["wrong_answers"]) if s.get("wrong_answers") is not None else None,
            difficulty=s.get("difficulty") or None,
            error_types=error_types,
            weak_points=weak_points,
            comments=s.get("comments") or None,
        ))

    return AIQCMFile(
        path=path,
        date=date_str,
        platform=platform,
        session_type=session_type,
        sessions=sessions,
        notes=data.get("notes") or None,
        raw=data,
    )
