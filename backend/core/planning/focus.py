"""Pure helpers for the Planning cockpit's weekly focus block."""
from __future__ import annotations


def build_focus_rows(plans: list, all_tasks: list) -> list[dict]:
    overdue = sum(1 for task in all_tasks if getattr(task, "days_overdue", 0) > 0)
    next_session = next((plan.total_min for plan in plans if getattr(plan, "total_min", 0) > 0), 0)
    free_slots = sum(1 for plan in plans if getattr(plan, "total_min", 0) <= 0)
    return [
        {"kind": "overdue", "value": overdue},
        {"kind": "next_session", "value": next_session},
        {"kind": "free_slots", "value": free_slots},
    ]


def focus_row_label(row: dict) -> str:
    kind = row.get("kind")
    value = int(row.get("value", 0) or 0)
    if kind == "overdue":
        return f"{value} révision{'s' if value != 1 else ''} en retard"
    if kind == "next_session":
        if value <= 0:
            return "Aucune session recommandée"
        hours, minutes = divmod(value, 60)
        duration = f"{hours}h{minutes:02d}" if hours else f"{minutes} min"
        return f"Prochaine session recommandée · {duration}"
    if kind == "free_slots":
        return f"{value} créneau{'x' if value != 1 else ''} libre{'s' if value != 1 else ''} à utiliser"
    return ""
