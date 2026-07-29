"""Panneau Cockpit des sessions IA, questions immuables et tentatives."""

from __future__ import annotations

import asyncio

from nicegui import ui

from backend.core.practice.models import (
    PracticeDifficulty,
    PracticeKind,
    PracticeSessionSpec,
    QuestionKind,
)
from backend.core.practice.service import PracticeService
from backend.core.reviews import local_store
from frontend.components.practice_import_panel import open_practice_import_dialog
from frontend.components.qcm_replay import (
    open_chained_dialog,
    open_qcm_correction,
    open_qcm_session,
    session_action_keys,
)


def _item_number(course) -> str:
    return str(
        getattr(course, "display_item_number", "")
        or getattr(course, "item_number", "")
        or ""
    )


def _open_generation_dialog(course, refresh) -> None:
    page_slot = ui.context.slot
    ui.add_head_html("""
    <style>
      .ai-practice-generation-card { border:1px solid var(--border); box-shadow:var(--shadow-popover); }
      .ai-practice-kind-toggle { border:1px solid var(--border); border-radius:6px; overflow:hidden; }
      .ai-practice-kind-toggle .q-btn { min-height:40px; border-radius:0 !important; }
    </style>
    """, shared=True)
    with ui.dialog() as dialog, ui.card().classes("ai-practice-generation-card p-5").style(
        "width: 620px; max-width: calc(100vw - 32px); border-radius: 8px;"
    ):
        ui.label("Nouvelle session IA").classes("text-lg font-semibold")
        ui.label("Les questions seront conservées et rejouables à l’identique.").classes(
            "text-xs text-slate-500 mb-4"
        )
        kind = ui.toggle(
            {"OIC": "OIC", "QCM": "QCM", "DP": "DP", "KFP": "KFP"},
            value="QCM",
        ).props("spread no-caps unelevated").classes("w-full ai-practice-kind-toggle")
        difficulty = ui.toggle(
            {
                PracticeDifficulty.STANDARD.value: "Standard",
                PracticeDifficulty.EDN.value: "EDN",
                PracticeDifficulty.DIFFICULT.value: "Difficile",
                PracticeDifficulty.CONCOURS.value: "Concours",
            },
            value=PracticeDifficulty.EDN.value,
        ).props("spread no-caps unelevated").classes("w-full ai-practice-kind-toggle mt-2")

        with ui.row().classes("w-full items-center justify-between mt-5"):
            total_label = ui.label().classes("text-sm font-medium")
            total_value_chip = ui.label().classes(
                "text-xs font-mono font-semibold px-2 py-1 rounded-md bg-slate-100 text-slate-700"
            )
        total = ui.slider(min=1, max=50, step=1, value=10).props("color=primary").classes("w-full")
        total.props("aria-label='Nombre total de questions'")

        with ui.row().classes("w-full items-center justify-between mt-4"):
            open_label = ui.label().classes("text-sm font-medium")
            open_value_chip = ui.label().classes(
                "text-xs font-mono font-semibold px-2 py-1 rounded-md bg-violet-50 text-violet-700"
            )
        opened = ui.slider(min=0, max=10, step=1, value=0).props("color=deep-purple").classes("w-full")
        opened.props("aria-label='Nombre de questions ouvertes'")

        distribution = ui.label().classes("text-xs text-slate-500 mt-2")
        status = ui.label().classes("text-xs text-red-500 mt-2")
        open_after_generation = ui.checkbox(
            "Ouvrir directement la session pour répondre",
            value=True,
        ).props("dense").classes("mt-4")

        def _sync_sliders(_event=None) -> None:
            total_value = int(total.value or 1)
            opened.props(f"max={total_value}")
            opened.value = min(int(opened.value or 0), total_value)
            total_label.set_text(f"Nombre total · {total_value} question{'s' if total_value != 1 else ''}")
            total_value_chip.set_text(str(total_value))
            open_value = int(opened.value or 0)
            open_label.set_text(f"Questions ouvertes · {open_value}")
            open_value_chip.set_text(str(open_value))
            closed_value = total_value - open_value
            distribution.set_text(
                f"{open_value} ouverte{'s' if open_value != 1 else ''} · "
                f"{closed_value} fermée{'s' if closed_value != 1 else ''}"
            )

        total.on_value_change(_sync_sliders)
        opened.on_value_change(_sync_sliders)
        _sync_sliders()

        async def _generate() -> None:
            try:
                spec = PracticeSessionSpec(
                    practice_kind=PracticeKind(str(kind.value).upper()),
                    total_questions=int(total.value or 0),
                    open_questions=int(opened.value or 0),
                    closed_questions=int(total.value or 0) - int(opened.value or 0),
                    item_number=_item_number(course),
                    course_id=str(getattr(course, "id", "") or ""),
                    course_title=str(getattr(course, "title", "") or ""),
                    difficulty=PracticeDifficulty(str(difficulty.value)),
                )
            except (TypeError, ValueError) as exc:
                status.set_text(str(exc))
                return
            status.set_text("Génération en cours…")
            try:
                session_id = await asyncio.to_thread(
                    PracticeService().create_new_session, spec, str(getattr(course, "title", "") or "")
                )
            except Exception as exc:
                status.set_text(f"Échec de génération : {exc}")
                return
            dialog.close()
            if open_after_generation.value:
                open_chained_dialog(
                    page_slot,
                    lambda: _open_answer_dialog(session_id, refresh),
                )
            ui.notify(f"Session IA #{session_id} enregistrée", type="positive")

        with ui.row().classes("justify-end gap-2 mt-5"):
            ui.button("Annuler", on_click=dialog.close).props("flat")
            ui.button("Générer et conserver", on_click=_generate).props("color=primary unelevated")
    dialog.open()


def _open_answer_dialog(session_id: int, refresh) -> None:
    """Open the resumable, step-based stored-session reader."""
    page_slot = ui.context.slot
    # set_ai_practice_anchor remains available from the reader for stored questions.
    open_qcm_session(
        session_id,
        on_complete=lambda completed_id: open_chained_dialog(
            page_slot,
            lambda: _open_correction_dialog(completed_id, refresh),
        ),
        on_back=lambda: None,
    )


def _open_correction_dialog(session_id: int, refresh) -> None:
    """Open correction and route replayed sessions back into the step reader."""
    page_slot = ui.context.slot
    open_qcm_correction(
        session_id,
        on_back=lambda: open_chained_dialog(page_slot, refresh),
        on_replay=lambda new_id: open_chained_dialog(
            page_slot,
            lambda: _open_answer_dialog(new_id, refresh),
        ),
    )


def _render_history(item_number: str, refresh) -> None:
    history = local_store.get_ai_practice_history(item_number=item_number, limit=30)
    if not history:
        ui.label("Aucune question IA enregistrée pour cet ITEM.").classes("ci-empty")
        return
    for entry in history:
        session = entry["session"]
        questions = entry["questions"]
        attempted = sum(bool(q["attempts"]) for q in questions)
        difficulty_labels = {
            PracticeDifficulty.STANDARD.value: "Standard",
            PracticeDifficulty.EDN.value: "EDN",
            PracticeDifficulty.DIFFICULT.value: "Difficile",
            PracticeDifficulty.CONCOURS.value: "Concours",
        }
        difficulty_label = difficulty_labels.get(session.get("difficulty", PracticeDifficulty.STANDARD.value), "Standard")
        score = session.get("score_percent")
        score_label = f" · Score {float(score):g} %" if score is not None else ""
        with ui.expansion(
            f"Session #{session['id']} · {session['practice_kind'].upper()} · "
            f"{difficulty_label} · {len(questions)} questions · "
            f"{attempted}/{len(questions)} répondues{score_label}",
            icon="history",
        ).classes("w-full border-b border-slate-200 dark:border-slate-700"):
            with ui.row().classes("items-center gap-2 mb-2"):
                ui.label(str(session["created_at"])[:16]).classes("text-xs text-slate-400")
                ui.label(session["model"] or "modèle inconnu").classes("text-xs font-mono text-slate-400")
                actions = session_action_keys(session)
                if "resume" in actions:
                    ui.button(
                        "Reprendre",
                        on_click=lambda sid=session["id"]: _open_answer_dialog(sid, refresh),
                    ).props("flat dense color=primary")
                if "correction" in actions:
                    ui.button("Voir la correction", on_click=lambda sid=session["id"]: _open_correction_dialog(sid, refresh)).props(
                        "flat dense color=primary"
                    )
                if "replay" in actions:
                    ui.button("Rejouer exactement", on_click=lambda sid=session["id"]: _replay(sid, refresh)).props(
                        "flat dense"
                    )
            for question in questions:
                with ui.card().classes("w-full p-3 mb-2 bg-slate-50 dark:bg-slate-900/40"):
                    ui.label(question["prompt"]).classes("text-sm font-medium whitespace-pre-wrap")
                    ui.label(f"Correction : {question['answer']}").classes("text-xs text-green-700 dark:text-green-400 mt-1")
                    ui.label(f"Explication : {question['explanation']}").classes("text-xs text-slate-500 whitespace-pre-wrap")
                    for attempt in question["attempts"]:
                        duration = attempt.get("duration_seconds")
                        duration_label = f" · {duration} s" if duration is not None else ""
                        ui.label(
                            f"Réponse du {str(attempt['answered_at'])[:16]}{duration_label} : "
                            f"{attempt['response'] or '—'}"
                        ).classes("text-xs text-blue-700 dark:text-blue-300 mt-2")


def _replay(session_id: int, refresh) -> None:
    try:
        new_id = local_store.replay_ai_practice_session(session_id)
        ui.notify(f"Session #{new_id} créée avec les mêmes questions", type="positive")
        refresh()
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _start_imported_case(case_id: int, course, refresh) -> None:
    cases = [case for case in local_store.get_imported_practice_cases(limit=500) if case["id"] == case_id]
    if not cases:
        ui.notify("Cas importé introuvable", type="warning")
        return
    case = cases[0]
    questions = []
    for question in case.get("questions", []):
        is_closed = bool(question.get("choices"))
        questions.append({
            "prompt": question["prompt"],
            "kind": QuestionKind.CLOSED.value if is_closed else QuestionKind.OPEN.value,
            "choices": question.get("choices", []),
            "answer": question["answer"],
            "explanation": question["explanation"],
        })
    open_count = sum(q["kind"] == QuestionKind.OPEN.value for q in questions)
    spec = PracticeSessionSpec(
        practice_kind=PracticeKind(str(case["kind"]).upper()),
        total_questions=len(questions),
        open_questions=open_count,
        closed_questions=len(questions) - open_count,
        item_number=_item_number(course),
        course_id=str(getattr(course, "id", "") or ""),
        course_title=str(getattr(course, "title", "") or case["title"]),
    )
    session_id = local_store.create_ai_practice_session(spec=spec, questions=questions, model="local-import")
    _open_answer_dialog(session_id, refresh)


def _start_random_imported_case(course, refresh) -> None:
    rows = local_store.get_random_imported_practice_cases(item_number=_item_number(course), limit=1)
    if not rows:
        ui.notify("Aucun cas local disponible pour cet ITEM", type="warning")
        return
    _start_imported_case(rows[0]["id"], course, refresh)


def render_ai_practice_panel(course) -> None:
    """Ajoute la génération, le rejeu et l'historique au Cockpit ITEM."""
    item_number = _item_number(course)
    container = ui.element("div").classes("w-full")

    def refresh() -> None:
        container.clear()
        with container:
            _render_content()

    def _render_content() -> None:
        with ui.row().classes("items-center justify-between w-full mb-3"):
            with ui.column().classes("gap-0"):
                ui.label("Questions IA").classes("ci-section-title")
                ui.label("Questions conservées, rejouables et comparables dans le temps.").classes(
                    "text-xs text-slate-400"
                )
            with ui.row().classes("gap-2"):
                ui.button("Importer QCM / DP / KFP", icon="upload_file", on_click=lambda: open_practice_import_dialog(
                    refresh, item_number
                )).props("flat color=primary")
                ui.button("Nouvelle session", icon="add", on_click=lambda: _open_generation_dialog(course, refresh)).props(
                    "color=primary unelevated"
                )
        _render_history(item_number, refresh)
        imported = local_store.get_imported_practice_cases(item_number=item_number, limit=20)
        if imported:
            with ui.row().classes("items-center gap-2 mt-4"):
                ui.label("Banque locale DP/KFP").classes("ci-section-title")
                ui.button("Tirer au hasard", on_click=lambda: _start_random_imported_case(course, refresh)).props(
                    "flat dense color=primary"
                )
            for case in imported:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(
                        f"{case['kind'].upper()} · {case['title']} · {len(case.get('questions', []))} questions"
                    ).classes("text-sm")
                    ui.button("S'entraîner", on_click=lambda cid=case["id"]: _start_imported_case(cid, course, refresh)).props(
                        "flat dense color=primary"
                    )
                if case["status"] == "needs_review":
                    ui.label(f"À vérifier : {case['review_reason']}").classes("text-xs text-amber-600")

    with container:
        _render_content()
