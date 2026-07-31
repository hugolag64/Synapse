"""One-off backfill: attach pre-existing UNESS sessions (imported before annale_id existed) to uness_annales."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.core.reviews import local_store  # noqa: E402
from backend.core.uness.import_service import ANNALE_TYPE_LABELS  # noqa: E402


def _session_uness_metadata(session_id: int) -> dict | None:
    """Read the faculty/level/year/source_url buried in the session's first question metadata."""
    for question in local_store.get_ai_practice_session(session_id):
        uness = question.get("import_metadata", {}).get("uness")
        if uness:
            return uness
    return None


def backfill_annales() -> None:
    sessions_without_annale = [
        row
        for row in local_store.get_ai_practice_sessions_history(limit=10_000)
        if str(row.get("model", "")).startswith("uness-") and row.get("annale_id") is None
    ]
    groups: dict[str, list[int]] = {}
    metadata_by_source: dict[str, dict] = {}
    for row in sessions_without_annale:
        uness = _session_uness_metadata(int(row["id"]))
        if not uness:
            continue
        source_url = str(uness.get("provenance", {}).get("source_url", "")).strip()
        if not source_url:
            continue
        groups.setdefault(source_url, []).append(int(row["id"]))
        metadata_by_source.setdefault(source_url, uness)

    for source_url, session_ids in groups.items():
        annale = local_store.get_uness_annale_by_source_url(source_url)
        if annale is None:
            uness = metadata_by_source[source_url]
            exam = uness.get("exam", {})
            print(f"\nAnnale sans type : {exam.get('title', source_url)} ({source_url})")
            for key, label in ANNALE_TYPE_LABELS.items():
                print(f"  {key} : {label}")
            type_annale = input("Type d'annale (matiere/concours_blanc/vrai_concours/edn_complet) : ").strip()
            annale_id = local_store.create_uness_annale(
                source_url=source_url,
                collected_at=str(uness.get("provenance", {}).get("collected_at", "")).strip(),
                faculte=str(exam.get("faculty", "")),
                niveau=str(exam.get("level", "")),
                annee=exam.get("year"),
                matiere=str(exam.get("title", "")),
                titre=str(exam.get("title", "")),
                type_annale=type_annale,
            )
            annale = local_store.get_uness_annale(annale_id)
        for session_id in session_ids:
            local_store.set_session_annale_id(session_id, annale["id"])


if __name__ == "__main__":
    backfill_annales()
