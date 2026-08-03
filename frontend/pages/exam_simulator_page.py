"""frontend/pages/exam_simulator_page.py — Vue principale du Simulateur d'Épreuves Blancs UNESS (Phase 2).

Conforme au Design System Linear / Cockpit Synapse.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from nicegui import ui
from loguru import logger

from backend.core.uness.exam_simulator import (
    compute_edn_score,
    list_available_subjects,
    load_dps_by_subject,
)
from frontend.components.import_dp_dialog import open_import_dp_dialog

_EXAM_CSS = """
.ex-wrap { width:100%; max-width:1100px; margin:0 auto; padding:8px 0 40px; }
.ex-head { margin-bottom: 20px; border-bottom:1px solid var(--border); padding-bottom: 16px; }
.ex-title { font-size:22px; font-weight:600; color:var(--text); letter-spacing:-0.015em; margin:0; }
.ex-subtitle { font-size:13px; color:var(--text-muted); margin-top:4px; }

.ex-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); padding:20px; }
.ex-card-header { font-size:14px; font-weight:600; color:var(--text); border-bottom:1px solid var(--border); padding-bottom:12px; margin-bottom:16px; }

.ex-panel-enonce { background:var(--bg-alt); border:1px solid var(--border); border-radius:var(--radius-md); padding:16px; height:580px; overflow-y:auto; font-size:13.5px; color:var(--text); line-height:1.6; }
.ex-panel-q { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-md); padding:20px; min-height:580px; display:flex; flex-direction:column; justify-between:space-between; }

.ex-prop-row { display:flex; align-items:flex-start; gap:10px; padding:10px 12px; border:1px solid var(--border); border-radius:var(--radius-sm); background:var(--bg); transition:all var(--duration-fast) ease; margin-bottom:8px; cursor:pointer; }
.ex-prop-row:hover { border-color:var(--border-strong); background:var(--surface-hover); }
.ex-prop-row.selected { background:var(--accent-wash); border-color:var(--accent); color:var(--text); }
.ex-prop-text { font-size:13px; color:var(--text); line-height:1.4; flex:1; }

.ex-badge-rank { font-size:10px; font-weight:600; font-family:var(--font-mono); padding:2px 6px; border-radius:var(--radius-sm); }
.ex-badge-rank-a { background:var(--college-late-bg); color:var(--danger); border:1px solid rgba(229,72,77,0.2); }
.ex-badge-rank-b { background:var(--surface-hover); color:var(--text-muted); border:1px solid var(--border); }
"""

def render_exam_simulator_page() -> None:
    """Rend la page du simulateur d'épreuves blancs UNESS avec le design tokens Synapse."""
    ui.add_head_html(f"<style>{_EXAM_CSS}</style>", shared=True)

    state = {
        "active_session": False,
        "finished": False,
        "selected_subject": "Toutes les spécialités",
        "num_dps": 2,
        "dps": [],
        "current_dp_idx": 0,
        "current_q_idx": 0,
        "user_answers": {},
        "validated_questions": set(),
        "scores": {},
        "mismatches": {},
    }

    container = ui.column().classes("ex-wrap space-y-6")

    def _refresh_ui():
        container.clear()
        with container:
            if not state["active_session"]:
                _render_setup_view()
            elif state["finished"]:
                _render_debrief_view()
            else:
                _render_exam_view()

    def _render_setup_view():
        with ui.element("div").classes("ex-head"):
            ui.label("⏱️ Simulateur d'Épreuves Blancs UNESS").classes("ex-title")
            ui.label("Entraînement en conditions réelles EDN (déroulement séquentiel, anti-retour et barème officiel 1 / 0.5 / 0.2 / 0).").classes("ex-subtitle")

        available_subjects = ["Toutes les spécialités"] + list_available_subjects()

        with ui.element("div").classes("ex-card space-y-6"):
            ui.label("Configuration du Concours Blanc").classes("ex-card-header")

            with ui.row().classes("w-full gap-6 items-center"):
                ui.select(
                    label="Spécialité / Discipline",
                    options=available_subjects,
                    value=state["selected_subject"],
                    on_change=lambda e: state.update({"selected_subject": e.value})
                ).props("outlined dense").classes("w-72")

                ui.select(
                    label="Nombre de Dossiers Progressifs (DP)",
                    options={1: "1 DP (Rapide)", 2: "2 DP (Standard)", 3: "3 DP (Format SNE)", 5: "5 DP (Marathon)"},
                    value=state["num_dps"],
                    on_change=lambda e: state.update({"num_dps": e.value})
                ).props("outlined dense").classes("w-64")

            with ui.row().classes("w-full justify-between items-center pt-4 border-t border-zinc-200 dark:border-zinc-800"):
                ui.button(
                    "Importer un DP (ChatGPT / Gemini)",
                    icon="upload",
                    on_click=lambda: open_import_dp_dialog(on_success=_refresh_ui)
                ).props("outline size=sm color=primary")

                ui.button(
                    "Lancer l'Épreuve Blanc",
                    icon="play_arrow",
                    on_click=_start_exam
                ).props("unelevated color=primary size=md").classes("font-semibold px-6")

    def _start_exam():
        import json
        from backend.core.reviews.local_store import create_ai_practice_session
        from backend.core.practice.models import PracticeSessionSpec, PracticeKind, PracticeDifficulty, QuestionKind

        subj = None if state["selected_subject"] == "Toutes les spécialités" else state["selected_subject"]
        dps = load_dps_by_subject(subject=subj, max_dps=state["num_dps"])

        if not dps:
            ui.notify("Aucun DP disponible pour cette sélection.", type="warning")
            return

        all_questions = []
        dp_titles = []

        for dp in dps:
            dp_title = dp.get("title", "DP Examen")
            dp_titles.append(dp_title)
            stem = dp.get("dp_context", {}).get("enonce_general", "")

            for q in dp.get("questions", []):
                choices = [p.get("texte", "") for p in q.get("propositions", [])]
                correct_choices = [p.get("texte", "") for p in q.get("propositions", []) if p.get("reponse_uness")]
                answer_str = json.dumps(correct_choices, ensure_ascii=False) if len(correct_choices) > 1 else (correct_choices[0] if correct_choices else "")
                
                exp = q.get("propositions", [{}])[0].get("explication_ia", "Correction selon le référentiel EDN.")

                all_questions.append({
                    "prompt": q.get("enonce", ""),
                    "choices": choices,
                    "answer": answer_str,
                    "explanation": exp,
                    "kind": QuestionKind.CLOSED if choices else QuestionKind.OPEN,
                    "uness": {
                        "exam": {
                            "title": dp_title,
                            "dp_context": {"CONTEXTE DU DOSSIER": stem}
                        },
                        "question": {
                            "dp_context": {"CONTEXTE DU DOSSIER": stem}
                        }
                    }
                })

        title_summary = "Concours Blanc — " + (" & ".join(dp_titles[:2]))
        if len(dp_titles) > 2:
            title_summary += f" (+{len(dp_titles)-2} DP)"

        spec = PracticeSessionSpec(
            practice_kind=PracticeKind.DP,
            total_questions=len(all_questions),
            open_questions=0,
            closed_questions=len(all_questions),
            course_id="exam-blanc",
            course_title=title_summary,
            item_number="CONCOURS BLANC",
            difficulty=PracticeDifficulty.EDN
        )

        session_id = create_ai_practice_session(spec=spec, questions=all_questions, model="exam-simulator-node")
        ui.navigate.to(f"/qcm-app/?session={session_id}&exam=1")

    def _render_exam_view():
        dp_idx = state["current_dp_idx"]
        q_idx = state["current_q_idx"]

        current_dp = state["dps"][dp_idx]
        questions = current_dp.get("questions", [])
        current_q = questions[q_idx] if q_idx < len(questions) else None

        if not current_q:
            _next_question()
            return

        is_validated = (dp_idx, q_idx) in state["validated_questions"]
        q_key = (dp_idx, q_idx)

        if q_key not in state["user_answers"]:
            state["user_answers"][q_key] = {}

        # En-tête DP
        with ui.row().classes("w-full justify-between items-center p-4 ex-card"):
            with ui.column().classes("gap-0"):
                ui.label(f"Dossier {dp_idx + 1}/{len(state['dps'])} — Question {q_idx + 1}/{len(questions)}").classes("text-xs font-mono font-bold text-indigo-500 uppercase")
                ui.label(current_dp.get("title", "Dossier Progressif")).classes("text-base font-semibold")
            
            ui.badge("🔒 Anti-Retour Actif", color="negative").props("outline size=sm").classes("text-xs")

        # Split screen Énoncé / Question
        with ui.grid().classes("w-full grid-cols-1 lg:grid-cols-12 gap-5"):
            # Enoncé général (5 cols)
            with ui.element("div").classes("lg:col-span-5 ex-panel-enonce"):
                ui.label("ÉNONCÉ GÉNÉRAL DU DOSSIER").classes("text-xs font-bold font-mono text-zinc-400 mb-2 border-b border-zinc-200 dark:border-zinc-800 pb-1")
                enonce = current_dp.get("dp_context", {}).get("enonce_general", "Aucun contexte fourni.")
                ui.markdown(enonce)

            # Question & propositions (7 cols)
            with ui.element("div").classes("lg:col-span-7 ex-panel-q"):
                with ui.column().classes("w-full space-y-4"):
                    ui.label(f"Q{q_idx + 1}. {current_q.get('enonce', '')}").classes("text-sm font-semibold leading-snug")
                    ui.label("Cochez les propositions vraies :").classes("text-xs text-zinc-400 italic")

                    propositions = current_q.get("propositions", [])
                    for prop in propositions:
                        pid = prop.get("id", "").lower()
                        p_text = prop.get("texte", "")
                        p_rank = prop.get("rank") or prop.get("rang")
                        display_txt = str(p_text).strip()
                        display_txt = re.sub(r"^\s*[A-Z][\.\)]\s*", "", display_txt, flags=re.IGNORECASE).strip()
                        current_val = state["user_answers"][q_key].get(pid, False)

                        def _toggle_prop(checked: bool, prop_id=pid):
                            state["user_answers"][q_key][prop_id] = checked

                        with ui.card().classes("w-full p-3 border border-zinc-200 dark:border-zinc-800 rounded-md bg-zinc-50 dark:bg-zinc-900/60 hover:bg-zinc-100 dark:hover:bg-zinc-800/80 transition shadow-none mb-2"):
                            with ui.row().classes("w-full items-start justify-between gap-3"):
                                chk = ui.checkbox(
                                    text=f"{pid.upper()}. {display_txt}",
                                    value=current_val,
                                    on_change=lambda e, prop_id=pid: _toggle_prop(bool(e.value), prop_id)
                                ).classes("text-sm text-zinc-900 dark:text-zinc-100 font-medium flex-1 leading-normal")
                                chk.set_enabled(not is_validated)

                                if p_rank:
                                    rank_cls = "ex-badge-rank-a" if p_rank == "A" else "ex-badge-rank-b"
                                    ui.html(f'<span class="ex-badge-rank {rank_cls} shrink-0">Rang {p_rank}</span>', sanitize=False)

                # Navigation
                with ui.row().classes("w-full justify-end items-center pt-4 border-t border-zinc-200 dark:border-zinc-800 mt-4"):
                    if not is_validated:
                        ui.button(
                            "Valider & Question Suivante",
                            icon="lock",
                            on_click=lambda: _validate_and_advance(dp_idx, q_idx, current_q)
                        ).props("unelevated color=primary size=sm")
                    else:
                        ui.button(
                            "Passer à la suite",
                            icon="arrow_forward",
                            on_click=_next_question
                        ).props("unelevated color=positive size=sm")

    def _validate_and_advance(dp_idx: int, q_idx: int, question: Dict[str, Any]):
        q_key = (dp_idx, q_idx)
        user_choices = state["user_answers"].get(q_key, {})
        props = question.get("propositions", [])

        score, mismatches = compute_edn_score(user_choices, props)
        state["scores"][q_key] = score
        state["mismatches"][q_key] = mismatches
        state["validated_questions"].add(q_key)
        _next_question()

    def _next_question():
        dp_idx = state["current_dp_idx"]
        q_idx = state["current_q_idx"]
        current_dp_questions = state["dps"][dp_idx].get("questions", [])

        if q_idx + 1 < len(current_dp_questions):
            state["current_q_idx"] += 1
        elif dp_idx + 1 < len(state["dps"]):
            state["current_dp_idx"] += 1
            state["current_q_idx"] = 0
        else:
            state["finished"] = True

        _refresh_ui()

    def _render_debrief_view():
        with ui.element("div").classes("ex-head"):
            ui.label("Épreuve Blanche Terminée").classes("ex-title")
            ui.label("Bilan synthétique et notation selon le barème officiel UNESS.").classes("ex-subtitle")

        total_questions = len(state["scores"])
        total_score = sum(state["scores"].values())
        max_score = float(total_questions)
        percent = (total_score / max_score * 100.0) if max_score > 0 else 0.0

        with ui.element("div").classes("ex-card space-y-4"):
            with ui.row().classes("w-full justify-between items-center border-b border-zinc-200 dark:border-zinc-800 pb-4"):
                with ui.column().classes("gap-0"):
                    ui.label("SCORE GLOBAL EDN").classes("text-xs font-mono font-bold text-zinc-400")
                    ui.label(f"{total_score:.2f} / {max_score:.0f} pts ({percent:.1f}%)").classes("text-2xl font-bold text-indigo-500")

                status_txt = "Rang A Sécurisé 🛡️" if percent >= 75 else "À Consolider ⚠️"
                badge_col = "positive" if percent >= 75 else "warning"
                ui.badge(status_txt, color=badge_col).props("size=md font-bold")

            for d_idx, dp in enumerate(state["dps"]):
                with ui.expansion(f"Dossier {d_idx + 1} : {dp.get('title', 'DP')}", icon="assignment").classes("w-full border border-zinc-200 dark:border-zinc-800 rounded-md p-2"):
                    for q_idx, q in enumerate(dp.get("questions", [])):
                        q_key = (d_idx, q_idx)
                        sc = state["scores"].get(q_key, 0.0)
                        mm = state["mismatches"].get(q_key, 0)
                        score_badge_col = "positive" if sc == 1.0 else ("warning" if sc > 0 else "negative")

                        with ui.row().classes("w-full justify-between items-center p-2 border-b border-zinc-200 dark:border-zinc-800"):
                            ui.label(f"Q{q_idx + 1}. {q.get('enonce', '')[:80]}...").classes("text-xs")
                            with ui.row().classes("items-center gap-2"):
                                ui.label(f"{mm} discordance(s)").classes("text-[11px] text-zinc-400")
                                ui.badge(f"{sc} pt", color=score_badge_col).classes("text-xs font-bold")

        with ui.row().classes("w-full justify-center pt-4"):
            ui.button(
                "Nouvelle Épreuve Blanc",
                icon="refresh",
                on_click=lambda: state.update({"active_session": False, "finished": False}) or _refresh_ui()
            ).props("unelevated color=primary")

    _refresh_ui()
