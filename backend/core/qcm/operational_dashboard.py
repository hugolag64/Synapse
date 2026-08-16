"""Indicateurs opérationnels du cockpit QCM.

Ces lectures sont volontairement déterministes : elles ne déclenchent aucun
appel IA et signalent explicitement l'absence de données au lieu de fabriquer
un verdict.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from backend.core.reviews import local_store

OFFICIAL_RANK_SOURCES = frozenset({"html", "ednpro", "official"})
RHYTHM_TARGET_SECONDS = {
    "qcm": 90,
    "series": 90,
    "mixed": 120,
    "dp": 180,
}


def _item(value: object) -> str:
    return str(value or "").strip().removeprefix("ITEM ")


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return [str(entry).strip().upper() for entry in parsed if str(entry).strip()]


def get_rank_a_security(*, limit: int = 10) -> dict[str, Any]:
    """Calcule le taux de propositions A attendues effectivement cochées.

    ``ednpro`` est la source historique du collecteur HTML. Les sources Gemini
    et OIC restent exclues du verdict de sécurité, conformément à l'audit.
    """
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT q.item_number, q.correct_answers_json, a.selected_answers_json,
                      a.rank, a.rank_source, q.rank_source AS question_rank_source
               FROM ednpro_qcm_attempts a
               JOIN ednpro_qcm_questions q ON q.id = a.question_id
               WHERE UPPER(COALESCE(a.rank, q.rank, '')) = 'A'
                 AND LOWER(COALESCE(a.rank_source, q.rank_source, '')) IN ('html', 'ednpro', 'official')
                 AND a.is_correct IS NOT NULL"""
        ).fetchall()

    by_item: dict[str, dict[str, int]] = defaultdict(lambda: {"expected": 0, "checked": 0, "questions": 0})
    for row in rows:
        item = _item(row["item_number"])
        expected = set(_json_list(row["correct_answers_json"]))
        selected = set(_json_list(row["selected_answers_json"]))
        if not item or not expected:
            continue
        by_item[item]["expected"] += len(expected)
        by_item[item]["checked"] += len(expected & selected)
        by_item[item]["questions"] += 1

    items = []
    for item_number, counts in by_item.items():
        ratio = counts["checked"] / counts["expected"] if counts["expected"] else 0.0
        items.append({
            "item_number": item_number,
            **counts,
            "percent": round(ratio * 100, 1),
            "status": "sécurisé" if ratio >= 0.8 else "à renforcer",
        })
    items.sort(key=lambda row: (row["percent"], row["item_number"]))
    total_expected = sum(row["expected"] for row in items)
    total_checked = sum(row["checked"] for row in items)
    return {
        "available": bool(items),
        "total_expected": total_expected,
        "total_checked": total_checked,
        "percent": round(total_checked / total_expected * 100, 1) if total_expected else None,
        "items": items[: max(1, int(limit))],
        "source_policy": "Rangs officiels uniquement (html/ednpro/official)",
    }


def get_discordance_profile(*, limit: int = 10) -> dict[str, Any]:
    """Retourne les omissions et excès issus des corrections propositionnelles."""
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT COALESCE(NULLIF(si.item_number, ''), s.item_number) AS item_number,
                      p.discordance, COUNT(*) AS count
               FROM ai_practice_attempt_propositions p
               JOIN ai_practice_attempts a ON a.id = p.attempt_id
               JOIN ai_practice_sessions s ON s.id = a.session_id
               LEFT JOIN ai_practice_session_items si ON si.session_id = s.id
               WHERE p.discordance IN ('omission', 'exces')
               GROUP BY COALESCE(NULLIF(si.item_number, ''), s.item_number), p.discordance"""
        ).fetchall()

    by_item: dict[str, dict[str, int]] = defaultdict(lambda: {"omission": 0, "exces": 0})
    for row in rows:
        item = _item(row["item_number"])
        if item:
            by_item[item][str(row["discordance"])] = int(row["count"])
    items = []
    for item_number, counts in by_item.items():
        total = counts["omission"] + counts["exces"]
        items.append({
            "item_number": item_number,
            **counts,
            "total": total,
            "dominant": "omission" if counts["omission"] >= counts["exces"] else "exces",
        })
    items.sort(key=lambda row: (-row["total"], row["item_number"]))
    omission = sum(row["omission"] for row in items)
    exces = sum(row["exces"] for row in items)
    total = omission + exces
    return {
        "available": bool(total),
        "omission": omission,
        "exces": exces,
        "total": total,
        "omission_percent": round(omission / total * 100, 1) if total else None,
        "exces_percent": round(exces / total * 100, 1) if total else None,
        "dominant": "omission" if omission >= exces else "exces" if exces else None,
        "items": items[: max(1, int(limit))],
    }


def get_rhythm_profile() -> dict[str, Any]:
    """Compare la durée moyenne par question à une cible explicite par format."""
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT COALESCE(NULLIF(s.exam_format, ''), LOWER(s.practice_kind), 'qcm') AS format,
                      a.duration_seconds
               FROM ai_practice_attempts a
               JOIN ai_practice_sessions s ON s.id = a.session_id
               WHERE a.duration_seconds IS NOT NULL AND a.duration_seconds > 0"""
        ).fetchall()
    by_format: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_format[str(row["format"] or "qcm").lower()].append(float(row["duration_seconds"]))
    formats = []
    for format_name, values in sorted(by_format.items()):
        average = round(sum(values) / len(values), 1)
        target = RHYTHM_TARGET_SECONDS.get(format_name, 120)
        formats.append({
            "format": format_name,
            "questions": len(values),
            "average_seconds": average,
            "target_seconds": target,
            "delta_seconds": round(average - target, 1),
            "status": "dans la cible" if average <= target else "trop lent",
        })
    return {"available": bool(formats), "formats": formats}


def get_frequency_coverage(*, limit: int = 10) -> dict[str, Any]:
    """Liste les items EDNpro indispensables jamais travaillés."""
    with local_store._conn() as con:
        frequency = con.execute(
            """SELECT item_number, priority, session_count, question_count
               FROM ednpro_item_frequency
               WHERE LOWER(priority) = 'indispensable'
               ORDER BY question_count DESC, session_count DESC, item_number"""
        ).fetchall()
        worked = con.execute(
            """SELECT DISTINCT item_number FROM (
                   SELECT COALESCE(NULLIF(si.item_number, ''), s.item_number) AS item_number
                   FROM ai_practice_sessions s
                   JOIN ai_practice_attempts a ON a.session_id = s.id
                   LEFT JOIN ai_practice_session_items si ON si.session_id = s.id
                   WHERE TRIM(COALESCE(a.response, '')) NOT IN ('', '[]')
                      OR a.score_mode = 'timed_out'
                   UNION
                   SELECT item_number FROM qcm_sessions
                   WHERE item_number IS NOT NULL AND TRIM(item_number) != '' AND score_percent IS NOT NULL
                   UNION
                   SELECT q.item_number
                   FROM ednpro_qcm_attempts a
                   JOIN ednpro_qcm_questions q ON q.id = a.question_id
               ) WHERE item_number IS NOT NULL AND TRIM(item_number) != ''"""
        ).fetchall()
    worked_items = {_item(row["item_number"]) for row in worked}
    uncovered = [
        {
            "item_number": _item(row["item_number"]),
            "priority": str(row["priority"]),
            "session_count": int(row["session_count"] or 0),
            "question_count": int(row["question_count"] or 0),
        }
        for row in frequency
        if _item(row["item_number"]) not in worked_items
    ]
    return {
        "available": bool(frequency),
        "indispensable_count": len(frequency),
        "worked_count": len(frequency) - len(uncovered),
        "uncovered_count": len(uncovered),
        "items": uncovered[: max(1, int(limit))],
    }


def get_replay_curve(*, limit: int = 10) -> dict[str, Any]:
    """Retourne les chaînes de rejeu et leur score à J+n."""
    with local_store._conn() as con:
        rows = con.execute(
            """SELECT id, replay_of_session_id, score_percent, created_at, item_number, course_title
               FROM ai_practice_sessions
               WHERE score_percent IS NOT NULL AND completed_at IS NOT NULL
               ORDER BY created_at, id"""
        ).fetchall()
    chains: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        root = int(row["replay_of_session_id"] or row["id"])
        chains[root].append(dict(row))

    series = []
    for root_id, chain in chains.items():
        if len(chain) < 2:
            continue
        try:
            origin = datetime.fromisoformat(str(chain[0]["created_at"]))
        except ValueError:
            origin = None
        points = []
        for index, row in enumerate(chain):
            try:
                day_offset = max(0, (datetime.fromisoformat(str(row["created_at"])) - origin).days) if origin else index
            except ValueError:
                day_offset = index
            points.append({
                "session_id": int(row["id"]),
                "day_offset": day_offset,
                "score_percent": float(row["score_percent"]),
                "is_replay": bool(row["replay_of_session_id"]),
            })
        series.append({
            "root_session_id": root_id,
            "item_number": _item(chain[0]["item_number"]),
            "course_title": str(chain[0]["course_title"] or "Session IA"),
            "points": points,
        })
    series.sort(key=lambda row: row["points"][-1]["session_id"], reverse=True)
    return {"available": bool(series), "chains": series[: max(1, int(limit))]}


def get_operational_dashboard() -> dict[str, Any]:
    """Point d'entrée unique pour le cockpit et les tests d'intégration."""
    return {
        "rank_a": get_rank_a_security(),
        "discordance": get_discordance_profile(),
        "rhythm": get_rhythm_profile(),
        "coverage": get_frequency_coverage(),
        "replay": get_replay_curve(),
    }
