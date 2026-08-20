from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from backend.core.conferences.matcher import match_college
from backend.core.conferences.xlsx_parser import parse_calendar_xlsx
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import local_store

_DFASM1_WEEKDAY = "Ma"
_UNESS_SLOT_HOUR = 17
_UNESS_SLOT_MINUTE = 30
_UNESS_SLOT_DURATION_MINUTES = 90


@dataclass
class ImportSummary:
    imported: int = 0
    updated: int = 0
    unchanged: int = 0
    needs_validation: int = 0


async def import_conferences_from_xlsx(path: Path) -> ImportSummary:
    parsed = [c for c in parse_calendar_xlsx(path) if c.weekday_abbr == _DFASM1_WEEKDAY]
    summary = ImportSummary()
    for conf in parsed:
        match = match_college(conf.theme_raw)
        outcome, row = local_store.upsert_conference(
            date=conf.date,
            theme_raw=conf.theme_raw,
            speaker_initials=conf.speaker_initials,
            speaker_name=conf.speaker_name,
            match_status=match.status,
            college_name=match.college_name,
            source_file=path.name,
        )
        if outcome == "created":
            summary.imported += 1
        elif outcome == "updated":
            summary.updated += 1
        else:
            summary.unchanged += 1
        if row["match_status"] == "matched":
            await _sync_calendar_events(row)
        elif row["match_status"] == "needs_validation":
            summary.needs_validation += 1
    return summary


async def validate_conference(
    conference_id: int, *, college_name: str | None, skip: bool = False
) -> dict:
    if skip:
        return local_store.set_conference_match(
            conference_id, match_status="skipped", college_name=None
        )
    if not college_name:
        raise ValueError("college_name requis sauf si skip=True")
    row = local_store.set_conference_match(
        conference_id, match_status="matched", college_name=college_name
    )
    await _sync_calendar_events(row)
    return row


async def _sync_calendar_events(conference_row: dict) -> None:
    conf_date = datetime.date.fromisoformat(conference_row["date"])
    theme = conference_row["theme_raw"]
    college = conference_row["college_id"] or ""
    summary = f"Conférence — {theme}" + (f" ({college})" if college else "")

    if not conference_row["google_event_id"]:
        event = await calendar_service.create_event(
            summary=summary,
            start_time_iso=datetime.datetime.combine(conf_date, datetime.time.min).isoformat(),
            all_day=True,
            description=f"Importé depuis {conference_row['source_file']}",
        )
        if event:
            conference_row = local_store.set_conference_google_event_ids(
                conference_row["id"], google_event_id=event["id"]
            )

    if not conference_row["uness_slot_google_event_id"]:
        slot_start = datetime.datetime.combine(
            conf_date, datetime.time(_UNESS_SLOT_HOUR, _UNESS_SLOT_MINUTE)
        )
        event = await calendar_service.create_event(
            summary=f"Dossier UNESS — {theme}",
            start_time_iso=slot_start.isoformat(),
            duration_minutes=_UNESS_SLOT_DURATION_MINUTES,
            description=f"Créneau dossier UNESS pour la conférence du {conf_date.isoformat()}.",
        )
        if event:
            local_store.set_conference_google_event_ids(
                conference_row["id"], uness_slot_google_event_id=event["id"]
            )


def list_pending_uness_links() -> list[dict]:
    """Conférences validées sans dossier UNESS lié, avec leurs candidats du jour."""
    pending = []
    for conf in local_store.list_conferences(match_status="matched"):
        if conf["uness_session_id"] is not None:
            continue
        candidates = local_store.list_uness_annales_by_date(conf["date"])
        if candidates:
            pending.append({"conference": conf, "candidates": candidates})
    return pending


def link_conference_to_uness_session(conference_id: int, annale_id: int) -> dict:
    """Confirme le rapprochement entre une conférence et le dossier UNESS choisi."""
    if local_store.get_uness_annale(annale_id) is None:
        raise ValueError(f"Dossier UNESS introuvable: {annale_id}")
    return local_store.set_conference_uness_session(conference_id, annale_id)
