"""Read-only reporting over the UNESS collect → correct → import pipeline:
for each known annale, which of its quizzes are imported, retrying after a
correction failure, permanently blocked, or were collected but never even
submitted to Gemini. Kept separate from import_service.py (which mutates
state) so this module can be called freely from a Settings page without side
effects beyond the one explicit, already-idempotent import pass described
below."""

from __future__ import annotations

import json
from typing import Any

from backend.core.reviews import local_store
from backend.core.uness import gemini_autocorrect, import_service


def _iter_bridge_files():
    """Every raw bridge JSON (has a "contents" key) under à_vérifier/ and
    archives/ — successfully imported bridges are moved, not deleted, into
    archives/session-<stamp>/, so a fully-imported annale's history stays
    scannable here too."""
    for directory in (import_service.TO_REVIEW_DIR, import_service.ARCHIVE_DIR):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.json"):
            if path.name.startswith("."):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and "contents" in payload:
                yield payload


def _latest_quiz_titles_by_source_url() -> dict[str, list[str]]:
    """For each source_url, the quiz titles (first line only — matches how
    `gemini_conversion.convert_with_bridge` builds `exam.title`) of its most
    recent collection. Re-scraping the same URL produces a fresh batch of
    quiz titles each time; only the latest batch is the reference — an older,
    superseded collection must not make the reference list look bigger (or
    different) than what actually exists today."""
    best_collected_at: dict[str, str] = {}
    titles: dict[str, list[str]] = {}
    for bridge in _iter_bridge_files():
        source = bridge.get("source", {})
        source_url = str(source.get("source_url", "")).strip()
        collected_at = str(source.get("collected_at", ""))
        if not source_url or not collected_at:
            continue
        contents = bridge.get("contents", [])
        quiz_titles = [
            str(item.get("title", "")).splitlines()[0]
            for item in contents
            if isinstance(item, dict) and item.get("title")
        ]
        if not quiz_titles:
            continue
        current_best = best_collected_at.get(source_url)
        if current_best is None or collected_at > current_best:
            # A strictly newer collection supersedes everything seen so far.
            best_collected_at[source_url] = collected_at
            titles[source_url] = list(quiz_titles)
        elif collected_at == current_best:
            # Same collection run, a different quiz's bridge file — every
            # quiz collected together shares the exact same collected_at
            # (collector.py builds one manifest after the whole loop and
            # reuses it verbatim in each quiz's own bridge file), so this
            # must union in rather than overwrite, or whichever file the
            # filesystem walk visits last would "win" and every sibling
            # quiz collected in the same run would silently vanish from
            # the reference list.
            for title in quiz_titles:
                if title not in titles[source_url]:
                    titles[source_url].append(title)
    return titles


def _quiz_label(course_title: str) -> str:
    """`course_title` on an imported session is "{exam meta title} — {quiz}"
    (see import_service._to_practice_question / exam.title construction in
    gemini_conversion.convert_with_bridge) — this pulls out just the quiz
    label ("DP1") for matching against the reference list."""
    return course_title.rsplit(" — ", 1)[-1].strip()


def _blocked_titles(errors: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    """Map (source_url, quiz label) -> error message for every file that just
    failed import validation (assert_verified_exam, missing bridge, etc.) —
    these files stay in VERIFIED_DIR untouched on failure, so they're always
    still readable here. Keyed by the (source_url, label) pair rather than
    label alone — UNESS quiz labels ("DP1", "QI1"...) are reused across
    unrelated annales, so a label-only key lets one annale's blocked entry
    silently clobber another's, hiding a real failure behind
    "never_attempted"."""
    blocked: dict[tuple[str, str], str] = {}
    for error in errors:
        matches = list(import_service.VERIFIED_DIR.rglob(error["file"]))
        if not matches:
            continue
        try:
            payload = json.loads(matches[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            # Legacy/malformed exports (e.g. an old bundled multi-quiz export
            # whose top level is a list of exam dicts, not one canonical
            # UnessExam dict) already show up in `errors` for their own
            # unrelated reason — this function only needs to not choke while
            # trying to attribute them to an annale.
            continue
        source_url = str(payload.get("provenance", {}).get("source_url", "")).strip()
        title = str(payload.get("title", ""))
        if not source_url or not title:
            continue
        blocked[(source_url, _quiz_label(title))] = error["error"]
    return blocked


def _retry_pending_by_source_url() -> dict[str, list[dict[str, Any]]]:
    """Group pending correction-failure rows by the source_url they belong
    to — the table itself only stores (quiz_title, collected_at), so each
    row's bridge is relocated the same way retry_failed_quiz already does."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for failure in local_store.list_pending_uness_correction_failures():
        try:
            bridge_path = gemini_autocorrect.locate_bridge(failure["quiz_title"], failure["collected_at"])
            bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            continue
        source_url = str(bridge.get("source", {}).get("source_url", "")).strip()
        if not source_url:
            continue
        label = str(failure["quiz_title"]).splitlines()[0]
        grouped.setdefault(source_url, []).append({**failure, "title": label})
    return grouped


def build_report() -> dict[str, Any]:
    """Imports everything currently importable (safe to call repeatedly —
    see import_service's dedup guards), then reports the state of every quiz
    known to have been collected at least once."""
    import_result = import_service.import_verified_directory()
    reference = _latest_quiz_titles_by_source_url()
    blocked = _blocked_titles(import_result["errors"])
    retry_pending = _retry_pending_by_source_url()

    annale_reports = []
    for annale in local_store.list_uness_annales():
        source_url = annale["source_url"]
        imported_labels = {
            _quiz_label(session["course_title"])
            for session in local_store.list_annale_sessions(annale["id"])
        }
        ref_titles = reference.get(source_url) or sorted(imported_labels)
        retry_for_url = {entry["title"]: entry for entry in retry_pending.get(source_url, [])}

        quizzes = []
        for title in ref_titles:
            if title in imported_labels:
                quizzes.append({"title": title, "status": "imported", "detail": {}})
            elif title in retry_for_url:
                failure = retry_for_url[title]
                quizzes.append({
                    "title": title,
                    "status": "retry_pending",
                    "detail": {
                        "error": failure["error_message"],
                        "attempts": failure["attempts"],
                        "next_retry_at": failure["next_retry_at"],
                        "failure_id": failure["id"],
                    },
                })
            elif (source_url, title) in blocked:
                quizzes.append({"title": title, "status": "blocked", "detail": {"error": blocked[(source_url, title)]}})
            else:
                quizzes.append({"title": title, "status": "never_attempted", "detail": {}})
        annale_reports.append({"annale": annale, "quizzes": quizzes})

    return {"annales": annale_reports, "pending": import_result["pending_tag"]}
