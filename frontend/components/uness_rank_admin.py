"""Admin panel for the persistent UNESS rank-inference queue."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterable
from typing import Any

from nicegui import ui

from backend.core.reviews import local_store


def summarize_rank_jobs(jobs: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(job.get("status") or "") for job in jobs)
    return {
        "a_traiter": counts["pending"] + counts["needs_admin"],
        "en_cours": counts["running"],
        "sans_oic": counts["needs_oic"],
        "incertains": counts["needs_admin"],
        "resolus": counts["approved"],
    }


def _source_label(job: dict[str, Any]) -> str:
    metadata = job.get("import_metadata") or {}
    official = metadata.get("uness", {}).get("question", {}) if isinstance(metadata, dict) else {}
    if isinstance(official, dict) and str(official.get("rank_source") or "").lower() == "official":
        return "Officiel"
    if str(job.get("admin_rank") or "").strip().upper() in {"A", "B"}:
        return "Admin"
    if str(job.get("gemini_rank") or "").strip().upper() in {"A", "B"}:
        return "Gemini"
    return "Inconnu"


def _rank_text(job: dict[str, Any]) -> str:
    rank = str(job.get("admin_rank") or job.get("gemini_rank") or "").strip().upper()
    return rank if rank in {"A", "B"} else "—"


def render_uness_rank_admin(container=None) -> None:
    """Render the queue without exposing a Gemini result as official."""
    parent = container or ui.column().classes("w-full")
    with parent:
        ui.label("RANGS UNESS — VALIDATION").classes("se-label")
        ui.label(
            "Les rangs officiels restent prioritaires. Gemini ne classe automatiquement "
            "que les questions appuyées par les OIC ; les cas incertains restent à valider."
        ).classes("se-appearance-sub")
        controls = ui.row().classes("w-full items-end gap-2 mt-3")
        body = ui.column().classes("w-full gap-3")
        state = {"status": "", "item_number": ""}

        with controls:
            status_select = ui.select(
                {
                    "": "Tous les états",
                    "pending": "À traiter",
                    "running": "En cours",
                    "needs_oic": "Sans OIC",
                    "needs_admin": "Incertain",
                    "approved": "Résolu",
                },
                value="",
                label="État",
            ).props("outlined dense").classes("w-44")
            item_input = ui.input("Item", placeholder="233").props("outlined dense").classes("w-28")

        def _jobs() -> list[dict[str, Any]]:
            return local_store.list_uness_rank_jobs(
                status=state["status"], item_number=state["item_number"], limit=100
            )

        def _render_body() -> None:
            body.clear()
            try:
                jobs = _jobs()
            except Exception as exc:  # noqa: BLE001 - optional admin widget
                with body:
                    ui.label(f"Erreur de lecture de la file : {exc}").classes("text-red-500")
                return
            summary = summarize_rank_jobs(jobs)
            with body:
                with ui.row().classes("w-full gap-2 flex-wrap"):
                    for label, key in (
                        ("À traiter", "a_traiter"),
                        ("En cours", "en_cours"),
                        ("Sans OIC", "sans_oic"),
                        ("Incertain", "incertains"),
                        ("Résolu", "resolus"),
                    ):
                        with ui.element("div").classes("se-tele-kpi min-w-28"):
                            ui.label(str(summary[key])).classes("se-tele-value")
                            ui.label(label).classes("se-tele-muted")
                if not jobs:
                    ui.label("Aucun job de rang dans ce filtre.").classes("text-sm text-slate-500")
                for job in jobs:
                    _render_job(job)

        async def _run_action(action, job_id: int, **kwargs: Any) -> None:
            try:
                await asyncio.to_thread(action, job_id, **kwargs)
                ui.notify("File des rangs mise à jour.", type="positive")
            except (ValueError, OSError) as exc:
                ui.notify(str(exc), type="negative")
            _render_body()

        async def _scan() -> None:
            try:
                created = await asyncio.to_thread(local_store.scan_uness_rank_jobs)
                ui.notify(f"{len(created)} question(s) ajoutée(s) à la file.", type="positive")
            except Exception as exc:  # noqa: BLE001
                ui.notify(f"Scan impossible : {exc}", type="negative")
            _render_body()

        def _render_job(job: dict[str, Any]) -> None:
            source = _source_label(job)
            rank = _rank_text(job)
            status = str(job.get("status") or "unknown")
            with ui.element("div").classes("se-diag-annale"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(
                        f"{job.get('item_number') or 'Item ?'} · {job.get('question_external_id') or job.get('id')}"
                    ).classes("se-diag-title")
                    ui.label(f"{status} · {source} · Rang {rank}").classes("se-diag-ratio partial")
                ui.label(str(job.get("prompt") or "Énoncé indisponible")[:500]).classes("se-diag-quiz-detail")
                if job.get("gemini_confidence") is not None:
                    ui.label(
                        f"Gemini : {float(job['gemini_confidence']):.0%} · "
                        f"OIC : {', '.join(job.get('gemini_oic_codes') or []) or '—'}"
                    ).classes("se-diag-quiz-detail")
                if job.get("gemini_rationale"):
                    ui.label(f"Justification : {job['gemini_rationale']}").classes("se-diag-quiz-detail")
                with ui.row().classes("w-full items-end gap-2 mt-2"):
                    reason = ui.input("Raison admin", placeholder="Pourquoi cette décision ?").props(
                        "outlined dense"
                    ).classes("flex-1")
                    job_id = int(job["id"])
                    if status == "needs_admin" and job.get("gemini_rank"):
                        ui.button(
                            "Accepter Gemini",
                            on_click=lambda job_id=job_id: _run_action(local_store.accept_uness_rank_job, job_id),
                        ).props("unelevated color=positive dense")
                    if status not in {"approved", "rejected"}:
                        ui.button(
                            "Choisir A",
                            on_click=lambda job_id=job_id, reason=reason: _run_action(
                                local_store.decide_uness_rank_job, job_id, rank="A", reason=reason.value or "Validation admin"
                            ),
                        ).props("outline color=primary dense")
                        ui.button(
                            "Choisir B",
                            on_click=lambda job_id=job_id, reason=reason: _run_action(
                                local_store.decide_uness_rank_job, job_id, rank="B", reason=reason.value or "Validation admin"
                            ),
                        ).props("outline color=primary dense")
                        ui.button(
                            "Rejeter",
                            on_click=lambda job_id=job_id, reason=reason: _run_action(
                                local_store.reject_uness_rank_job, job_id, reason=reason.value
                            ),
                        ).props("flat color=negative dense")
                    if status in {"retry_wait", "failed", "needs_oic"}:
                        ui.button(
                            "Relancer",
                            on_click=lambda job_id=job_id: _run_action(local_store.retry_uness_rank_job, job_id),
                        ).props("flat color=primary dense")

        status_select.on_value_change(lambda event: (state.__setitem__("status", event.value or ""), _render_body()))
        item_input.on_value_change(lambda event: (state.__setitem__("item_number", event.value or ""), _render_body()))
        with controls:
            ui.button("Scanner", icon="search", on_click=_scan).props("unelevated color=primary dense")
            ui.button("Rafraîchir", icon="refresh", on_click=_render_body).props("flat dense")
        _render_body()
