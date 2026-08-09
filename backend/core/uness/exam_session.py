"""Persistent, correction-free session state for a continuous exam run."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.core.reviews import local_store


@dataclass(frozen=True)
class ExamSessionState:
    session_id: str
    annale_id: int
    subpart_ids: tuple[int, ...]
    current_index: int
    mode: str
    started_at: str
    completed_at: str | None = None

    @property
    def correction_visible(self) -> bool:
        return self.completed_at is not None


@dataclass(frozen=True)
class ExamResult:
    session_id: str
    status: str
    correction_visible: bool
    responses: dict[str, object]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value):
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    raise TypeError(f"Réponse non sérialisable : {type(value).__name__}")


def _ensure_table() -> None:
    with local_store._conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS continuous_exam_sessions (
                session_id TEXT PRIMARY KEY,
                annale_id INTEGER NOT NULL,
                subpart_ids_json TEXT NOT NULL,
                current_index INTEGER NOT NULL DEFAULT 0,
                mode TEXT NOT NULL DEFAULT 'exam',
                status TEXT NOT NULL DEFAULT 'in_progress',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                responses_json TEXT NOT NULL DEFAULT '{}'
            )"""
        )


def _parts_for_annale(annale_id: int) -> list[int]:
    return [int(row["id"]) for row in local_store.list_annale_sessions(int(annale_id))]


def _from_row(row) -> ExamSessionState:
    return ExamSessionState(
        session_id=str(row["session_id"]),
        annale_id=int(row["annale_id"]),
        subpart_ids=tuple(json.loads(row["subpart_ids_json"])),
        current_index=int(row["current_index"]),
        mode=str(row["mode"]),
        started_at=str(row["started_at"]),
        completed_at=row["completed_at"],
    )


def _get_row(session_id: str):
    _ensure_table()
    with local_store._conn() as con:
        return con.execute(
            "SELECT * FROM continuous_exam_sessions WHERE session_id = ?",
            (str(session_id),),
        ).fetchone()


def start_exam_session(annale_id: int) -> ExamSessionState:
    """Resume the active run for an annale, or create one from its subparts."""
    _ensure_table()
    with local_store._conn() as con:
        existing = con.execute(
            "SELECT * FROM continuous_exam_sessions WHERE annale_id = ? AND status = 'in_progress' ORDER BY started_at DESC LIMIT 1",
            (int(annale_id),),
        ).fetchone()
        if existing:
            return _from_row(existing)
        subpart_ids = tuple(_parts_for_annale(annale_id))
        if not subpart_ids:
            raise ValueError("Cette annale ne contient aucune sous-partie importée")
        session_id = uuid.uuid4().hex
        con.execute(
            """INSERT INTO continuous_exam_sessions
               (session_id, annale_id, subpart_ids_json, started_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, int(annale_id), json.dumps(subpart_ids), _now()),
        )
    row = _get_row(session_id)
    return _from_row(row)


def advance_exam_session(session_id: str, response: object) -> ExamSessionState:
    """Save one response and advance, without exposing intermediate correction."""
    row = _get_row(session_id)
    if row is None:
        raise ValueError("Session d’épreuve introuvable")
    state = _from_row(row)
    if state.completed_at is not None:
        return state
    responses = json.loads(row["responses_json"] or "{}")
    if state.current_index < len(state.subpart_ids):
        responses[str(state.subpart_ids[state.current_index])] = response
    next_index = min(state.current_index + 1, len(state.subpart_ids))
    completed_at = _now() if next_index >= len(state.subpart_ids) else None
    status = "completed" if completed_at else "in_progress"
    with local_store._conn() as con:
        con.execute(
            """UPDATE continuous_exam_sessions
               SET current_index = ?, status = ?, completed_at = ?, responses_json = ?
               WHERE session_id = ?""",
            (
                next_index,
                status,
                completed_at,
                json.dumps(responses, ensure_ascii=False, default=_json_default),
                str(session_id),
            ),
        )
    return _from_row(_get_row(session_id))


def complete_exam_session(session_id: str) -> ExamResult:
    row = _get_row(session_id)
    if row is None:
        raise ValueError("Session d’épreuve introuvable")
    if row["completed_at"] is None:
        with local_store._conn() as con:
            con.execute(
                "UPDATE continuous_exam_sessions SET status = 'completed', completed_at = ? WHERE session_id = ?",
                (_now(), str(session_id)),
            )
        row = _get_row(session_id)
    return ExamResult(
        session_id=str(row["session_id"]),
        status=str(row["status"]),
        correction_visible=row["completed_at"] is not None,
        responses=json.loads(row["responses_json"] or "{}"),
    )
