"""
Weekly Report — Synapse F5
---------------------------
Génère un rapport de progression hebdomadaire depuis les données SQLite.

Flux :
  1. save_mastery_snapshots()  → appeler chaque semaine après preload
  2. generate_weekly_report()  → comparer snapshot N vs N-1, calculer stats
  3. WeeklyReport              → affiché en bannière sur le dashboard
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from backend.core.qcm.service import QCM_PASS_THRESHOLD
from backend.core.reviews.local_store import _conn, _now


# ── Modèle ────────────────────────────────────────────────────────────────────

@dataclass
class WeeklyReport:
    week_start: datetime.date
    total_hours: float
    sessions_count: int
    courses_improved: list[str]                 # course_ids dont mastery_score a augmenté
    courses_regressed: list[str]                # mastery_score a baissé
    lacunes_resolved: int
    lacunes_new: int
    top_weak_categories: list[tuple[str, int]]  # [(category, count)]
    avg_confidence: Optional[float]
    qcm_pass_rate: Optional[float]
    narrative: str
    retention_improved: list[str] = field(default_factory=list)
    retention_declined: list[str] = field(default_factory=list)


# ── Table mastery_snapshots ────────────────────────────────────────────────────

def _ensure_snapshots_table() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS mastery_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id     TEXT    NOT NULL,
                week          TEXT    NOT NULL,
                mastery_score INTEGER,
                retention_score INTEGER,
                mastery_level TEXT,
                calculation_version TEXT NOT NULL DEFAULT 'legacy',
                created_at    TEXT    NOT NULL,
                UNIQUE(course_id, week)
            );
            CREATE INDEX IF NOT EXISTS idx_ms_week ON mastery_snapshots(week);
        """)
        columns = {row["name"] for row in con.execute("PRAGMA table_info(mastery_snapshots)").fetchall()}
        if "retention_score" not in columns:
            con.execute("ALTER TABLE mastery_snapshots ADD COLUMN retention_score INTEGER")
        if "calculation_version" not in columns:
            con.execute(
                "ALTER TABLE mastery_snapshots ADD COLUMN calculation_version TEXT NOT NULL DEFAULT 'legacy'"
            )


def save_mastery_snapshots(snapshots: list[dict]) -> int:
    """
    Persist les snapshots mastery de la semaine courante.

    snapshots : [{"course_id": str, "mastery_score": int|None, "retention_score": int|None, "mastery_level": str}]
    Idempotent grâce au UNIQUE(course_id, week).
    Retourne le nombre de lignes écrites.
    """
    _ensure_snapshots_table()
    week = _current_week_iso()
    now = _now()
    count = 0
    with _conn() as con:
        for s in snapshots:
            con.execute("""
                INSERT INTO mastery_snapshots
                    (course_id, week, mastery_score, retention_score, mastery_level, calculation_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(course_id, week) DO UPDATE SET
                    mastery_score = excluded.mastery_score,
                    retention_score = excluded.retention_score,
                    mastery_level = excluded.mastery_level,
                    calculation_version = excluded.calculation_version
            """, (
                s["course_id"],
                week,
                s.get("mastery_score"),
                s.get("retention_score"),
                s.get("mastery_level"),
                s.get("calculation_version", "v2"),
                now,
            ))
            count += 1
    logger.debug(f"weekly_report: {count} snapshots mastery enregistrés (semaine {week})")
    return count


def snapshot_courses(courses: list) -> int:
    """
    Prend un snapshot mastery de tous les cours fournis.
    Appeler une fois par semaine après preload_all_views().

    courses : list[Cours] depuis data_store.cours
    """
    from backend.core.reviews.mastery import get_course_mastery
    from backend.core.reviews.local_store import get_sessions_by_course, get_postpone_counts, get_qcm_done_course_ids

    sessions_map  = get_sessions_by_course()
    postpone_map  = get_postpone_counts()
    qcm_done_set  = get_qcm_done_course_ids()

    snapshots = []
    for c in courses:
        mastery = get_course_mastery(
            c,
            context="college",
            sessions=sessions_map.get(c.id, []),
            total_postpone=postpone_map.get(c.id, 0),
            qcm_done_local=(c.id in qcm_done_set),
        )
        snapshots.append({
            "course_id":    c.id,
            "mastery_score": mastery.mastery_score,
            "retention_score": mastery.retention_score,
            "mastery_level": mastery.level,
            "calculation_version": "v2",
        })

    return save_mastery_snapshots(snapshots)


# ── Helpers date ──────────────────────────────────────────────────────────────

def _current_week_iso() -> str:
    """Retourne '2026-W25'."""
    return _week_iso(datetime.date.today())


def _week_iso(d: datetime.date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _qcm_pass_rate(scores: list[object]) -> float | None:
    """Calcule le taux de sessions QCM atteignant le seuil de réussite."""
    valid_scores: list[float] = []
    for raw in scores:
        try:
            score = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(score) and 0.0 <= score <= 100.0:
            valid_scores.append(score)
    if not valid_scores:
        return None
    passed = sum(score >= QCM_PASS_THRESHOLD for score in valid_scores)
    return round(passed / len(valid_scores) * 100.0, 1)


# ── Génération du rapport ─────────────────────────────────────────────────────

def generate_weekly_report(week_start: Optional[datetime.date] = None) -> WeeklyReport:
    """
    Génère le rapport de la semaine passée (ou de la semaine spécifiée).

    week_start : lundi de la semaine cible (défaut = lundi de la semaine dernière).
    """
    _ensure_snapshots_table()

    today = datetime.date.today()
    if week_start is None:
        week_start = today - datetime.timedelta(days=today.weekday() + 7)
    week_end = week_start + datetime.timedelta(days=6)

    week_str      = _week_iso(week_start)
    prev_week_str = _week_iso(week_start - datetime.timedelta(weeks=1))

    with _conn() as con:
        # Sessions de la semaine
        sessions = con.execute("""
            SELECT * FROM study_sessions
            WHERE session_date BETWEEN ? AND ?
        """, (week_start.isoformat(), week_end.isoformat())).fetchall()

        # Lacunes créées / résolues
        lacunes_new = con.execute("""
            SELECT COUNT(*) FROM weak_points
            WHERE DATE(created_at) BETWEEN ? AND ?
        """, (week_start.isoformat(), week_end.isoformat())).fetchone()[0]

        lacunes_resolved = con.execute("""
            SELECT COUNT(*) FROM weak_points
            WHERE DATE(resolved_at) BETWEEN ? AND ?
        """, (week_start.isoformat(), week_end.isoformat())).fetchone()[0]

        # Top 5 catégories lacunes actives
        cat_rows = con.execute("""
            SELECT category, COUNT(*) AS cnt
            FROM weak_points
            WHERE status IN ('active','à revoir','récurrente') AND category IS NOT NULL
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 5
        """).fetchall()

        # QCM pass rate de la semaine
        qcm_rows = con.execute("""
            SELECT score_percent FROM qcm_sessions
            WHERE DATE(session_date) BETWEEN ? AND ?
              AND score_percent IS NOT NULL
        """, (week_start.isoformat(), week_end.isoformat())).fetchall()

        # Snapshots mastery : semaine cible vs précédente
        snap_cur = {
            r["course_id"]: r["mastery_score"]
            for r in con.execute(
                "SELECT course_id, mastery_score FROM mastery_snapshots WHERE week = ?",
                (week_str,)
            ).fetchall()
        }
        snap_prev = {
            r["course_id"]: r["mastery_score"]
            for r in con.execute(
                "SELECT course_id, mastery_score FROM mastery_snapshots WHERE week = ?",
                (prev_week_str,)
            ).fetchall()
        }
        retention_cur = {
            r["course_id"]: r["retention_score"]
            for r in con.execute(
                "SELECT course_id, retention_score FROM mastery_snapshots WHERE week = ?",
                (week_str,)
            ).fetchall()
        }
        retention_prev = {
            r["course_id"]: r["retention_score"]
            for r in con.execute(
                "SELECT course_id, retention_score FROM mastery_snapshots WHERE week = ?",
                (prev_week_str,)
            ).fetchall()
        }

    # Calculs
    total_minutes = sum(s["duration_minutes"] or 0 for s in sessions)
    total_hours   = round(total_minutes / 60, 1)
    sessions_count = len(sessions)

    confidences = [s["confidence"] for s in sessions if s["confidence"]]
    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else None

    qcm_scores = [r["score_percent"] for r in qcm_rows]
    qcm_pass_rate = _qcm_pass_rate(qcm_scores)

    courses_improved: list[str] = []
    courses_regressed: list[str] = []
    retention_improved: list[str] = []
    retention_declined: list[str] = []
    for cid, cur_score in snap_cur.items():
        prev_score = snap_prev.get(cid)
        if prev_score is None or cur_score is None:
            continue
        if cur_score > prev_score:
            courses_improved.append(cid)
        elif cur_score < prev_score:
            courses_regressed.append(cid)

    for cid, cur_score in retention_cur.items():
        prev_score = retention_prev.get(cid)
        if prev_score is None or cur_score is None:
            continue
        if cur_score > prev_score:
            retention_improved.append(cid)
        elif cur_score < prev_score:
            retention_declined.append(cid)

    top_weak_categories = [(r["category"], r["cnt"]) for r in cat_rows]

    narrative = _build_narrative(
        total_hours, sessions_count,
        len(courses_improved), len(courses_regressed),
        lacunes_resolved, lacunes_new, avg_confidence,
    )

    return WeeklyReport(
        week_start=week_start,
        total_hours=total_hours,
        sessions_count=sessions_count,
        courses_improved=courses_improved,
        courses_regressed=courses_regressed,
        lacunes_resolved=lacunes_resolved,
        lacunes_new=lacunes_new,
        top_weak_categories=top_weak_categories,
        avg_confidence=avg_confidence,
        qcm_pass_rate=qcm_pass_rate,
        narrative=narrative,
        retention_improved=retention_improved,
        retention_declined=retention_declined,
    )


def _build_narrative(
    hours: float,
    sessions: int,
    improved: int,
    regressed: int,
    resolved: int,
    new_lacunes: int,
    avg_conf: Optional[float],
) -> str:
    lines: list[str] = []
    if sessions == 0:
        lines.append("Aucune session enregistrée cette semaine.")
    else:
        lines.append(
            f"{sessions} session{'s' if sessions > 1 else ''} — {hours}h de travail."
        )
    if improved:
        suffix = f", {regressed} en régression" if regressed else ""
        lines.append(f"{improved} cours progressés{suffix}.")
    elif regressed:
        lines.append(f"⚠ {regressed} cours en régression cette semaine.")
    if new_lacunes:
        s = "s" if new_lacunes > 1 else ""
        r_str = f", {resolved} résolue(s)" if resolved else ""
        lines.append(f"{new_lacunes} nouvelle{s} lacune{s}{r_str}.")
    return " ".join(lines)
