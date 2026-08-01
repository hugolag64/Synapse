"""Diagnostic UNESS panel for Paramètres — one card per annale, one row per
quiz, showing exactly why a quiz isn't imported yet and a button to fix it.
Kept out of settings_cockpit.py to keep that file to layout/wiring only."""

from __future__ import annotations

import asyncio

from loguru import logger
from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness import diagnostics, gemini_autocorrect, import_service

_STATUS_ICONS = {
    "imported": "✅",
    "retry_pending": "🔄",
    "blocked": "❌",
    "never_attempted": "⬜",
}


def render(container: ui.element) -> None:
    # Every element below must be constructed while `container`'s slot is
    # active — NiceGUI parents a new element to whatever slot is on top of
    # the stack AT CONSTRUCTION TIME (see nicegui/element.py), not to
    # whatever `container` object a function happens to receive as an
    # argument. Building `body`/labels/etc. before entering `with
    # container:` (as an earlier draft of this function did) parents them
    # to the CALLER's currently-active slot instead — `container` itself
    # ends up permanently empty, and the panel "works" only by accident,
    # landing as a stray sibling wherever the caller happened to be.
    with container:
        ui.label("DIAGNOSTIC UNESS").classes("se-label")
        body = ui.column().classes("w-full gap-0")

        def _refresh() -> None:
            body.clear()
            with body:
                with ui.row().classes("w-full justify-end mb-2"):
                    ui.button("Rafraîchir", icon="refresh", on_click=_refresh).props(
                        "flat dense size=sm color=primary"
                    )
                try:
                    report = diagnostics.build_report()
                except Exception as exc:  # noqa: BLE001 - an optional read-only
                    # diagnostics widget must never take down the rest of
                    # Paramètres (connexions, apparence, IA...) on the same page
                    # just because build_report() hit a bad file on disk, a
                    # SQLite hiccup, or any other future failure mode — this
                    # already happened once during this feature's own
                    # development (a real crash from a malformed file).
                    logger.exception(
                        "uness_diagnostic_panel: build_report() a levé une exception"
                    )
                    ui.label(f"Erreur lors du diagnostic UNESS : {exc}").classes(
                        "se-diag-quiz-detail"
                    )
                    return
                if not report["annales"] and not report["pending"]:
                    ui.label("Aucune annale UNESS collectée pour le moment.").classes(
                        "text-sm text-slate-500"
                    )
                for entry in report["annales"]:
                    _render_annale(entry)
                _render_unattributed_errors(report.get("unattributed_errors") or [])
                for pending in report["pending"]:
                    _render_pending(pending)

        async def _retry(failure_id: int) -> None:
            local_store.reset_uness_correction_failure_attempts(failure_id)
            result = await asyncio.to_thread(gemini_autocorrect.retry_failed_quiz, failure_id)
            if result["success"]:
                ui.notify("✅ Quiz corrigé et importé.", type="positive")
                await asyncio.to_thread(import_service.import_verified_directory)
            else:
                ui.notify(f"❌ Toujours en échec : {result['error']}", type="negative")
            _refresh()

        def _render_annale(entry: dict) -> None:
            annale = entry["annale"]
            quizzes = entry["quizzes"]
            imported_count = sum(1 for q in quizzes if q["status"] == "imported")
            total = len(quizzes)
            ratio_class = "full" if imported_count == total else "partial"
            with ui.element("div").classes("se-diag-annale"):
                with ui.element("div").classes("se-diag-head"):
                    ui.label(annale["titre"]).classes("se-diag-title")
                    ui.label(f"{imported_count}/{total}").classes(f"se-diag-ratio {ratio_class}")
                for quiz in quizzes:
                    if quiz["status"] == "imported":
                        continue
                    with ui.element("div").classes("se-diag-quiz-row"):
                        ui.label(f"{_STATUS_ICONS[quiz['status']]} {quiz['title']}")
                        if quiz["status"] == "retry_pending":
                            ui.label(
                                f"tentative {quiz['detail']['attempts']}/3 — {quiz['detail']['error']}"
                            ).classes("se-diag-quiz-detail")

                            # NiceGUI runs an async on_click handler as its OWN
                            # properly-slotted task when the handler is passed
                            # directly (not wrapped in asyncio.create_task, which
                            # would spawn a task with an empty slot stack — see
                            # the identical pattern already used for this same
                            # button on /annales, frontend/pages/annales.py). The
                            # default-arg trick captures this row's failure_id
                            # since the loop variable itself would be stale by
                            # the time the button is actually clicked.
                            async def _on_retry_click(failure_id: int = quiz["detail"]["failure_id"]) -> None:
                                await _retry(failure_id)

                            ui.button("Relancer", on_click=_on_retry_click).props(
                                "flat dense size=sm color=primary"
                            )
                        elif quiz["status"] == "blocked":
                            ui.label(quiz["detail"]["error"]).classes("se-diag-quiz-detail")
                        elif quiz["status"] == "never_attempted":
                            ui.label(
                                "Jamais soumis à Gemini — utilise « Corriger dossier "
                                "existant » sur /annales pour ce dossier de collecte."
                            ).classes("se-diag-quiz-detail")

        def _render_unattributed_errors(errors: list[dict]) -> None:
            # These are import failures diagnostics.build_report() could not
            # match to any (source_url, quiz label) — typically a raw AI
            # response whose conversion to a canonical exam failed before it
            # ever carried a provenance/title to key off. Without this
            # section they'd silently vanish from the report instead of
            # showing up (wrongly) as "never_attempted" or not at all.
            if not errors:
                return
            with ui.element("div").classes("se-diag-annale"):
                ui.label(
                    f"⚠️ {len(errors)} fichier(s) en erreur non rattaché(s) à une annale"
                ).classes("se-diag-title")
                for error in errors:
                    with ui.element("div").classes("se-diag-quiz-row"):
                        ui.label(error["file"])
                        ui.label(error["error"]).classes("se-diag-quiz-detail")

        def _render_pending(pending: dict) -> None:
            with ui.element("div").classes("se-diag-annale"):
                with ui.element("div").classes("se-diag-head"):
                    ui.label(pending["titre"]).classes("se-diag-title")
                    ui.label("en attente de matière").classes("se-diag-ratio partial")
                ui.label(f"{len(pending['files'])} quiz corrigés, matière à qualifier sur /annales.").classes(
                    "se-diag-quiz-detail"
                )

        _refresh()
