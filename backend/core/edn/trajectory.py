"""Progression, potentiel de gain et projection de trajectoire EDN."""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressSnapshot:
    covered_items: int
    total_items: int
    average_mastery: float | None
    overdue_reviews: int
    remaining_reviews: int
    new_items_per_week: float
    recent_minutes_per_day: float


@dataclass(frozen=True)
class ProjectionScenario:
    name: str
    projected_coverage: float
    projected_mastery: float | None
    remaining_items: int
    confidence: str


def _row_value(row, key: str, default=None):
    """Lit une valeur sur un dict, une `sqlite3.Row` ou un objet.

    `get_all_history()` renvoie des `sqlite3.Row` : elles s'indexent par clé
    mais n'exposent pas leurs colonnes en attributs, si bien qu'un `getattr`
    y renvoyait silencieusement le défaut pour chaque ligne.
    """
    if isinstance(row, dict):
        return row.get(key, default)
    keys = getattr(row, "keys", None)
    if callable(keys):
        try:
            return row[key] if key in keys() else default
        except (TypeError, IndexError, KeyError):
            pass
    return getattr(row, key, default)


def _completed_date(row) -> datetime.date | None:
    raw = str(_row_value(row, "completed_at", "") or "").strip()
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _item_key(row) -> str:
    """Numéro d'item normalisé : « ITEM 147 », « 147 » et « 147 » ne font qu'un."""
    raw = str(_row_value(row, "item_number", "") or "").strip()
    return raw.removeprefix("ITEM").removeprefix("item").strip()


def _session_date(row) -> datetime.date | None:
    raw = str(_row_value(row, "session_date", "") or "").strip()
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _total_edn_items() -> int:
    from backend.core.qcm.items_mapping import all_items

    return len(all_items())


def build_progress_snapshot(
    *,
    tasks: list,
    history: dict,
    as_of: datetime.date,
    study_sessions: list | None = None,
    total_edn_items: int | None = None,
) -> ProgressSnapshot:
    """Photographie de la progression EDN, en items du programme.

    La couverture compte les items EDN dont au moins une révision a été
    validée. Elle se lisait auparavant sur `date_1ere_lecture`, renseigné sur
    8 fiches quand l'historique local en comptait 163 travaillés : la
    progression paraissait nulle et la projection à l'examen sans valeur.

    La cadence récente est comptée dans la même unité — des items, pas des
    fiches — pour que la projection reste homogène. Les durées viennent de
    `study_sessions` : `review_history` n'a pas de colonne `duration_minutes`.
    """
    done_rows = [row for row in history.values() if _row_value(row, "status") == "done"]
    covered_items = len({_item_key(row) for row in done_rows if _item_key(row)})
    total_items = total_edn_items if total_edn_items is not None else _total_edn_items()

    scores = [_row_value(task, "mastery_score") for task in tasks if _row_value(task, "mastery_score") is not None]
    average_mastery = round(sum(scores) / len(scores), 1) if scores else None
    overdue = sum(1 for task in tasks if (_row_value(task, "days_overdue", 0) or 0) > 0)

    # Cadence de découverte : un item compte le jour de sa PREMIÈRE validation.
    # Le compter à chaque révision revenait à projeter la couverture avec un
    # taux qui inclut le réexamen de l'acquis — 25 items/semaine au lieu de 7,
    # et une projection saturée à 100 % pour quiconque révise régulièrement.
    cutoff = as_of - datetime.timedelta(days=27)
    first_done: dict[str, datetime.date] = {}
    for row in done_rows:
        item = _item_key(row)
        completed = _completed_date(row)
        if not item or completed is None:
            continue
        if item not in first_done or completed < first_done[item]:
            first_done[item] = completed
    new_items = sum(1 for day in first_done.values() if day >= cutoff)
    recent_minutes = sum(
        float(_row_value(row, "duration_minutes", 0) or 0)
        for row in (study_sessions or [])
        if (session_day := _session_date(row)) is not None and session_day >= cutoff
    )
    return ProgressSnapshot(
        covered_items=covered_items,
        total_items=total_items,
        average_mastery=average_mastery,
        overdue_reviews=overdue,
        remaining_reviews=len(tasks),
        new_items_per_week=round(new_items / 4, 2),
        recent_minutes_per_day=round(recent_minutes / 28, 2),
    )


def project_to_exam(
    snapshot: ProgressSnapshot,
    *,
    target_date: datetime.date,
    today: datetime.date | None = None,
) -> tuple[ProjectionScenario, ...]:
    """Projette la couverture EDN à `target_date` selon trois hypothèses de rythme.

    Part de `new_items_per_week`, la cadence de découverte réellement observée
    sur les 28 derniers jours — qui reflète déjà, de fait, la capacité
    quotidienne dont l'utilisateur a disposé pour l'atteindre. Un ancien
    `capacity_factor` (capacité/60 min) la multipliait une seconde fois ; comme
    `capacity_from_preferences` est borné à 180-720 min et que ce facteur sature
    à 1.5 dès 90 min, il valait 1.5 pour TOUT réglage possible — une inflation
    constante de 50 %, jamais un vrai signal.
    """
    today = today or datetime.date.today()
    weeks = max(0.0, (target_date - today).days / 7)
    baseline = snapshot.new_items_per_week or 0.0
    rates = (0.75, 1.0, 1.25)
    names = ("prudent", "central", "ambitieux")
    confidence = ("faible", "indicative", "haute")
    scenarios = []
    for name, factor, confidence_label in zip(names, rates, confidence, strict=True):
        projected_items = min(
            snapshot.total_items,
            snapshot.covered_items + baseline * factor * weeks,
        )
        coverage = round(projected_items / snapshot.total_items * 100, 1) if snapshot.total_items else 0.0
        mastery = None if snapshot.average_mastery is None else round(
            min(100.0, snapshot.average_mastery + max(0.0, coverage - snapshot.covered_items / max(snapshot.total_items, 1) * 100) * 0.15),
            1,
        )
        scenarios.append(ProjectionScenario(
            name=name,
            projected_coverage=coverage,
            projected_mastery=mastery,
            remaining_items=max(0, snapshot.total_items - round(projected_items)),
            confidence=confidence_label,
        ))
    return tuple(scenarios)


def rank_gain_potential(*, items, available_minutes: int | None = None) -> list[dict]:
    """Classe des priorités d'étude relatives avec facteurs explicables."""
    ranked = []
    for item in items:
        mastery = max(0.0, min(100.0, float(item.get("mastery", 0) or 0)))
        weight = max(0.0, min(1.0, float(item.get("edn_weight", 0.5) or 0.5)))
        error_recurrence = max(0.0, min(1.0, float(item.get("error_count", 0) or 0) / 5))
        availability = max(0.0, min(1.0, float(item.get("available_questions", 0) or 0) / 20))
        frequency_sessions = item.get("frequency_sessions")
        frequency_recurrence = (
            0.5
            if frequency_sessions is None
            else max(0.0, min(1.0, float(frequency_sessions or 0) / 10))
        )
        effort = max(1.0, float(item.get("estimated_minutes", 30) or 30) / 30)
        if available_minutes is not None and effort * 30 > available_minutes:
            effort *= 1.15
        gap = (100.0 - mastery) / 100.0
        score = 100 * (
            0.25 * weight
            + 0.30 * gap
            + 0.15 * error_recurrence
            + 0.15 * availability
            + 0.15 * frequency_recurrence
        )
        score = round(score / effort, 2)
        ranked.append({
            **item,
            "potential_score": score,
            "factors": {
                "edn_weight": round(weight, 2),
                "mastery_gap": round(gap, 2),
                "error_recurrence": round(error_recurrence, 2),
                "question_availability": round(availability, 2),
                "frequency_recurrence": round(frequency_recurrence, 2),
                "estimated_minutes": round(effort * 30, 1),
            },
        })
    return sorted(ranked, key=lambda row: (-row["potential_score"], str(row.get("item_number", ""))))
