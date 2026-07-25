"""
course_detail.py — Synapse — Fiche Course Intelligence
-------------------------------------------------------
Route : /cours/{course_id}

Vue 360° d'un cours :
  - Statut · Maîtrise · Action recommandée
  - Sources (PDF, Obsidian, Fiche EDN)
  - Rappels J3/J7/J14/J30
  - Historique QCM
  - Lacunes actives
  - Timeline (séances + révisions + lacunes)
"""
from __future__ import annotations

import datetime
import json
from nicegui import ui
from loguru import logger

from frontend.theme import frame
from frontend.components.fiche_viewer import render_traps_card
from backend.state.store import data_store
from backend.core.reviews import local_store
from backend.core.reviews.mastery import get_course_mastery, PROGRESSION_COLORS
from backend.core.reviews.recommendation_service import get_next_action
from backend.core.reviews.models import ReviewTask
from backend.core.obsidian.service import obsidian_service
from backend.core.obsidian.trap_detector import extract_traps
from backend.config.settings import settings as _settings
from backend.core.knowledge import store as knowledge_store
from backend.core.knowledge import service as knowledge_service
from backend.core.reviews.service import review_service


# ── Helpers visuels ───────────────────────────────────────────────────────────

_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]


def _fmt_date(d) -> str:
    if d is None:
        return "—"
    if hasattr(d, "strftime"):
        return f"{d.day} {_MONTHS_FR[d.month - 1]}"
    if isinstance(d, str) and len(d) >= 10:
        try:
            dd = datetime.date.fromisoformat(d[:10])
            return f"{dd.day} {_MONTHS_FR[dd.month - 1]}"
        except Exception:
            pass
    return str(d)


def _fmt_min(minutes) -> str:
    if not minutes:
        return ""
    m = int(minutes)
    if m >= 60:
        h, rem = divmod(m, 60)
        return f"{h}h{rem:02d}" if rem else f"{h}h"
    return f"{m}min"


def _day_ago(d_str: str) -> str:
    """'il y a N jours' ou 'aujourd'hui'."""
    try:
        d = datetime.date.fromisoformat(d_str[:10])
        delta = (datetime.date.today() - d).days
        if delta == 0:
            return "aujourd'hui"
        if delta == 1:
            return "hier"
        if delta < 7:
            return f"il y a {delta}j"
        return _fmt_date(d)
    except Exception:
        return d_str[:10] if d_str else "—"


_NA_COLORS = {
    "red":    "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800",
    "orange": "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/20 dark:text-orange-300 dark:border-orange-800",
    "blue":   "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800",
    "indigo": "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-900/20 dark:text-indigo-300 dark:border-indigo-800",
    "slate":  "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700",
}


def _render_knowledge_block(course) -> None:
    """Niveau déclaré (modifiable à tout moment) + couverture OIC."""
    container = ui.column().classes("w-full gap-2 mb-4")

    def _render():
        state = knowledge_store.get_item_state(course.id, "college")
        cov = knowledge_service.oic_coverage(course.id)
        badge = knowledge_service.has_rang_a_badge(course.id)

        container.clear()
        with container:
            with ui.row().classes("items-center gap-2"):
                ui.label("Niveau déclaré").classes(
                    "text-xs font-semibold text-slate-500 uppercase tracking-wide"
                )
                if state is None:
                    ui.badge("À situer").props("color=grey outline")

            with ui.row().classes("items-center gap-1"):
                for level, label, color in [
                    ("solide", "Solide", "positive"),
                    ("correct", "Correct", "warning"),
                    ("flou", "Flou", "negative"),
                ]:
                    selected = state is not None and state.declared_level == level

                    def _set(_level=level):
                        knowledge_store.set_item_state(
                            course.id, _level, context="college", source="triage"
                        )
                        review_service.invalidate_cache()
                        _render()

                    ui.button(label, on_click=_set).props(
                        f"unelevated rounded size=sm color={color}"
                        if selected else
                        "outline rounded size=sm color=grey"
                    )

            if cov["rang_a_total"] or cov["rang_b_total"]:
                with ui.row().classes("items-center gap-3 mt-1"):
                    ui.label(
                        f"OIC rang A : {cov['rang_a_ok']}/{cov['rang_a_total']} "
                        f"({int(cov['rang_a_pct'] * 100)} %)"
                    ).classes("text-xs text-slate-500")

                    if cov["rang_b_total"]:
                        ui.label(
                            f"rang B : {cov['rang_b_ok']}/{cov['rang_b_total']}"
                        ).classes("text-xs text-slate-400")

                    if badge:
                        ui.badge("Rang A ✓").props("color=green")

    _render()


# ── Page principale ───────────────────────────────────────────────────────────

def course_detail_page(course_id: str) -> None:
    with frame("Fiche cours"):
        # ── Refonte : détail item cockpit (feature-flag ui_mode) ──────────────
        if data_store.preferences.get("ui_mode", "cockpit") == "cockpit":
            from frontend.pages.course_detail_cockpit import render_item_cockpit
            render_item_cockpit(course_id)
            return

        # Chercher le cours
        course = next((c for c in data_store.cours if c.id == course_id), None)
        if not course:
            with ui.column().classes("w-full items-center py-16 gap-4"):
                ui.icon("search_off", size="xl").classes("text-slate-300")
                ui.label("Cours introuvable.").classes("text-slate-400")
                ui.button("Retour", icon="arrow_back", on_click=lambda: ui.navigate.back()).props(
                    "outline rounded size=sm color=slate"
                )
            return

        # Données SQLite
        sessions_map  = local_store.get_sessions_by_course()
        postpone_map  = local_store.get_postpone_counts()
        sessions      = sessions_map.get(course_id, [])
        postpone_cnt  = postpone_map.get(course_id, 0)
        session_summary = local_store.get_course_session_summary(course_id)
        qcm_summary   = local_store.get_qcm_summary_for_course(course_id)
        qcm_sessions  = local_store.get_qcm_sessions_all(limit=20, course_id=course_id)
        lacunes       = local_store.get_weak_points_for_course(course_id)
        review_hist   = local_store.get_review_history_by_course(course_id)

        # F3 — Pièges EDN depuis Obsidian (si note disponible)
        _obs_traps: list = []
        try:
            _obs_path = obsidian_service.find_course_note(course)
            if _obs_path and _obs_path.exists():
                _obs_traps = extract_traps(_obs_path)
        except Exception:
            pass

        # Maîtrise
        try:
            mastery = get_course_mastery(course, sessions, postpone_cnt)
        except Exception:
            mastery = None

        # Next action (on construit une ReviewTask minimale)
        nb_lec = getattr(course, "nb_lectures", 0) or 0
        try:
            task_mock = ReviewTask(
                id=f"{course_id}_college_J7_mock",
                course_id=course_id,
                course_title=course.title,
                item_number=course.item_number,
                college=course.college,
                context="college",
                url_pdf=getattr(course, "url_pdf", None),
                theoretical_due_date=datetime.date.today(),
                due_date=datetime.date.today(),
                review_type="J7",
                nb_lectures=nb_lec,
                anki=getattr(course, "anki", False),
                qcm_done=getattr(course, "qcm_done", False),
                mastery_level=mastery.level if mastery else None,
                mastery_score=mastery.score if mastery else None,
                days_overdue=0,
            )
            qcm_last_score = qcm_summary.get("last_score") if qcm_summary["count"] else None
            lacune_count   = len([l for l in lacunes if (l["status"] or "") not in ("résolue",)])
            next_action    = get_next_action(task_mock, last_qcm_score=qcm_last_score, lacune_count=lacune_count)
        except Exception as exc:
            logger.warning(f"next_action mock failed: {exc}")
            next_action = None

        # Obsidian
        obs_configured = bool(_settings.obsidian_vault_path)
        obs_exists     = obsidian_service.note_exists(course) if obs_configured else False
        obs_uri        = getattr(course, "obsidian_uri", None)

        # Layout
        with ui.column().classes("w-full gap-6 max-w-5xl mx-auto"):

            # ── Header ─────────────────────────────────────────────────────────
            with ui.row().classes("items-start gap-3 flex-wrap w-full"):
                ui.button(icon="arrow_back", on_click=lambda: ui.navigate.back()).props(
                    "flat round dense size=sm color=slate"
                ).tooltip("Retour")

                with ui.column().classes("flex-1 gap-2 min-w-0"):
                    # Badges
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        if course.display_item_number:
                            ui.badge(f"ITEM {course.display_item_number}", color="slate").classes(
                                "text-[11px] font-bold px-2 py-0.5"
                            )
                        for col in (course.college or []):
                            ui.badge(col, color="indigo").classes(
                                "text-[11px] px-2 py-0.5"
                            )
                        if course.course_status:
                            ui.badge(course.course_status, color="blue").classes(
                                "text-[11px] px-2 py-0.5"
                            )
                        if mastery:
                            m_color = PROGRESSION_COLORS.get(mastery.level, "slate")
                            ui.badge(
                                f"{mastery.level.capitalize()} {mastery.score}%",
                                color=m_color,
                            ).classes("text-[11px] font-bold px-2 py-0.5")

                    # Titre
                    ui.label(course.title).classes(
                        "text-2xl font-extrabold text-slate-900 dark:text-slate-50 "
                        "leading-snug tracking-tight"
                    )

                    # Raisons de maîtrise
                    if mastery and mastery.reasons:
                        ui.label(" · ".join(mastery.reasons[:3])).classes(
                            "text-xs text-slate-400"
                        )

            # ── Next Action Banner ─────────────────────────────────────────────
            if next_action:
                na_cls = _NA_COLORS.get(next_action.color, _NA_COLORS["slate"])
                with ui.element("div").classes(
                    f"w-full p-4 rounded-2xl border {na_cls} flex items-center gap-4 flex-wrap"
                ):
                    ui.icon(next_action.icon, size="md").classes("shrink-0")
                    with ui.column().classes("flex-1 gap-0.5 min-w-0"):
                        ui.label(next_action.label).classes("text-sm font-bold")
                        if next_action.reason:
                            ui.label(next_action.reason).classes("text-[11px] opacity-70 truncate")
                    ui.label(f"{next_action.duration_min} min").classes(
                        "text-sm font-bold shrink-0 tabular-nums"
                    )

                    # Boutons d'action contextuelle
                    if course.url_pdf:
                        ui.button(
                            "PDF",
                            icon="picture_as_pdf",
                            on_click=lambda: ui.navigate.to(f"/pdf/{course.id}", new_tab=True),
                        ).props("outline rounded size=sm color=red").classes("text-xs shrink-0")
                    if obs_exists or obs_uri:
                        ui.button(
                            "Obsidian",
                            icon="edit_note",
                            on_click=lambda: obsidian_service.open_course_note(course),
                        ).props("outline rounded size=sm color=violet").classes("text-xs shrink-0")

            # ── Stats rapides ──────────────────────────────────────────────────
            with ui.row().classes("items-center gap-3 flex-wrap"):
                def _stat_chip(val, lbl, icon_n, color="slate"):
                    with ui.element("div").classes(
                        f"flex items-center gap-1.5 px-3 py-1.5 rounded-full "
                        f"bg-{color}-50 dark:bg-{color}-900/20"
                    ):
                        ui.icon(icon_n, size="xs").classes(f"text-{color}-400")
                        ui.label(f"{val} {lbl}").classes(
                            f"text-xs font-semibold text-{color}-600 dark:text-{color}-300"
                        )

                _stat_chip(nb_lec, "lecture(s)", "menu_book", "blue")
                if session_summary["session_count"]:
                    _stat_chip(
                        session_summary["session_count"], "séance(s)",
                        "school", "indigo"
                    )
                if session_summary["average_confidence"]:
                    _stat_chip(
                        f"{session_summary['average_confidence']}/5",
                        "confiance moy.",
                        "thumb_up",
                        "green",
                    )
                if qcm_summary["count"]:
                    _stat_chip(
                        f"{qcm_summary['avg_score']}%",
                        f"moy. QCM ({qcm_summary['count']})",
                        "quiz",
                        "purple",
                    )
                if lacune_count:
                    _stat_chip(
                        lacune_count, "lacune(s) active(s)",
                        "report_problem", "orange"
                    )

            # ── État des connaissances (niveau déclaré + couverture OIC) ────────
            _render_knowledge_block(course)

            # ── Grille principale ──────────────────────────────────────────────
            with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-3 gap-6 w-full"):

                # ── Colonne gauche ─────────────────────────────────────────────
                with ui.column().classes("col-span-1 lg:col-span-2 gap-6"):

                    # Sources
                    with ui.card().classes(
                        "w-full p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800"
                    ):
                        ui.label("SOURCES").classes(
                            "text-[11px] font-bold tracking-widest text-slate-400 uppercase mb-3"
                        )
                        with ui.element("div").classes("flex flex-wrap gap-2"):
                            # PDF
                            if course.url_pdf:
                                ui.button(
                                    "Ouvrir PDF",
                                    icon="picture_as_pdf",
                                    on_click=lambda: ui.navigate.to(f"/pdf/{course.id}", new_tab=True),
                                ).props("unelevated rounded size=sm color=red")
                            else:
                                ui.button(
                                    "PDF manquant",
                                    icon="picture_as_pdf",
                                ).props("outline rounded size=sm color=grey").classes("opacity-50")

                            # Obsidian
                            if obs_configured:
                                if obs_exists or obs_uri:
                                    ui.button(
                                        "Note Obsidian",
                                        icon="edit_note",
                                        on_click=lambda: obsidian_service.open_course_note(course),
                                    ).props("unelevated rounded size=sm color=violet")
                                else:
                                    async def _create_obs():
                                        ok, path = await obsidian_service.create_course_note(course)
                                        if ok:
                                            ui.notify("Note créée ✓", type="positive")
                                        else:
                                            ui.notify(f"Erreur : {path}", type="negative")
                                    import asyncio
                                    ui.button(
                                        "Créer note Obsidian",
                                        icon="add",
                                        on_click=lambda: asyncio.create_task(_create_obs()),
                                    ).props("outline rounded size=sm color=violet")

                            # Fiche EDN
                            if getattr(course, "agregation_fiche_edn", None):
                                ui.button(
                                    "Fiche EDN",
                                    icon="auto_stories",
                                    on_click=lambda url=course.agregation_fiche_edn: ui.navigate.to(url, new_tab=True),
                                ).props("outline rounded size=sm color=teal")

                    # Rappels J3/J7/J14/J30
                    with ui.card().classes(
                        "w-full p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800"
                    ):
                        ui.label("CALENDRIER DE RÉVISIONS").classes(
                            "text-[11px] font-bold tracking-widest text-slate-400 uppercase mb-3"
                        )
                        today = datetime.date.today()

                        rows_def = [
                            ("1ère lecture",      getattr(course, "date_1ere_lecture", None),    "book_open", "blue"),
                            ("J3",                getattr(course, "lecture_j3_college", None),   "looks_3",   "indigo"),
                            ("J7",                getattr(course, "lecture_j7_college", None),   "looks_7",   "violet"),
                            ("J14",               getattr(course, "lecture_j14_college", None),  "calendar_month", "purple"),
                            ("J30",               getattr(course, "lecture_j30_college", None),  "event",     "orange"),
                        ]
                        with ui.element("div").classes("flex flex-col gap-1.5"):
                            for lbl, d, icon_n, color in rows_def:
                                is_past  = d and hasattr(d, "timetuple") and d < today
                                is_today = d and hasattr(d, "timetuple") and d == today
                                is_future = d and hasattr(d, "timetuple") and d > today
                                status_icon = "check_circle" if is_past else ("today" if is_today else ("schedule" if is_future else "radio_button_unchecked"))
                                status_color = "green" if is_past else ("blue" if is_today else ("orange" if is_future else "slate"))
                                with ui.row().classes("items-center gap-3 py-1"):
                                    ui.icon(icon_n, size="xs").classes(f"text-{color}-400 shrink-0 w-4")
                                    ui.label(lbl).classes(
                                        "text-xs font-semibold text-slate-600 dark:text-slate-300 w-24 shrink-0"
                                    )
                                    ui.label(_fmt_date(d) if d else "—").classes(
                                        "text-xs text-slate-500 dark:text-slate-400 flex-1"
                                    )
                                    ui.icon(status_icon, size="xs").classes(
                                        f"text-{status_color}-400 shrink-0"
                                    )

                    # QCM Sessions
                    if qcm_sessions:
                        with ui.expansion(
                            value=True,
                        ).classes(
                            "w-full rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800"
                        ) as _qcm_exp:
                            with _qcm_exp.add_slot("header"):
                                with ui.row().classes("items-center gap-2 px-4 py-3 w-full"):
                                    ui.icon("quiz", size="sm").classes("text-purple-400")
                                    ui.label("Historique QCM").classes(
                                        "font-bold text-slate-800 dark:text-slate-100 text-sm flex-1"
                                    )
                                    if qcm_summary["avg_score"] is not None:
                                        ui.label(f"moy. {qcm_summary['avg_score']}%").classes(
                                            "text-xs text-purple-500 font-semibold"
                                        )

                            with ui.column().classes("px-4 pb-4 gap-1.5 w-full"):
                                for qs in qcm_sessions[:8]:
                                    from backend.core.qcm.service import score_bg_classes
                                    score = qs.get("score_percent") or qs.get("score")
                                    raw   = qs.get("score_raw") or (f"{score}%" if score else "—")
                                    platform = qs.get("platform", "?")
                                    s_date   = qs.get("session_date", "")
                                    cls = score_bg_classes(score)
                                    with ui.row().classes(
                                        "items-center gap-2 py-1.5 px-2 rounded-lg "
                                        "hover:bg-slate-50 dark:hover:bg-slate-800 w-full"
                                    ):
                                        ui.label(platform).classes(
                                            "text-[11px] font-bold px-2 py-0.5 rounded-full "
                                            "bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-300 shrink-0"
                                        )
                                        ui.label(raw).classes(
                                            f"text-xs font-bold px-2 py-0.5 rounded-full {cls} shrink-0"
                                        )
                                        ui.element("div").classes("flex-1")
                                        ui.label(_day_ago(s_date)).classes(
                                            "text-[11px] text-slate-400 shrink-0"
                                        )

                # ── Colonne droite ─────────────────────────────────────────────
                with ui.column().classes("col-span-1 gap-6"):

                    # F3 — Pièges EDN (Clinical Black card)
                    render_traps_card(course, _obs_traps, list(lacunes))

                    # Lacunes actives
                    active_lacunes = [l for l in lacunes if (l["status"] or "") not in ("résolue",)]
                    if active_lacunes:
                        with ui.card().classes(
                            "w-full p-4 rounded-2xl shadow-sm border border-orange-100 dark:border-orange-900/30"
                        ):
                            ui.label(f"LACUNES ({len(active_lacunes)})").classes(
                                "text-[11px] font-bold tracking-widest text-orange-400 uppercase mb-3"
                            )
                            with ui.column().classes("gap-2 w-full"):
                                for lc in active_lacunes[:6]:
                                    severity = lc.get("severity") or lc["severity"] if "severity" in lc.keys() else 2
                                    detail   = (lc["detail"] or "").strip()
                                    cat      = (lc.get("category") or "").strip()
                                    sev_color = "red" if severity >= 4 else "orange" if severity == 3 else "slate"
                                    with ui.element("div").classes(
                                        "w-full p-2 rounded-lg bg-orange-50 dark:bg-orange-900/10 "
                                        "border border-orange-100 dark:border-orange-900/30"
                                    ):
                                        with ui.row().classes("items-start gap-2 w-full"):
                                            ui.badge(str(severity), color=sev_color).classes(
                                                "text-[11px] shrink-0 mt-0.5"
                                            )
                                            with ui.column().classes("gap-0 min-w-0"):
                                                ui.label(detail[:80] + ("…" if len(detail) > 80 else "")).classes(
                                                    "text-xs font-semibold text-slate-800 dark:text-slate-100 "
                                                    "leading-snug"
                                                )
                                                if cat:
                                                    ui.label(cat).classes("text-[11px] text-orange-500")

                            ui.button(
                                "Voir toutes les lacunes",
                                icon="arrow_forward",
                                on_click=lambda: ui.navigate.to("/lacunes"),
                            ).props("flat dense size=sm color=orange").classes("text-xs mt-2 w-full")

                    # Timeline
                    with ui.card().classes(
                        "w-full p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800"
                    ):
                        ui.label("ACTIVITÉ").classes(
                            "text-[11px] font-bold tracking-widest text-slate-400 uppercase mb-3"
                        )
                        _render_course_timeline(sessions, qcm_sessions[:5], lacunes[:5], review_hist[:5])


def _render_course_timeline(sessions, qcm_sessions, lacunes, review_hist):
    """Timeline fusionnée des activités d'un cours."""
    events: list[dict] = []

    for s in sessions:
        d = s.get("session_date") or ""
        if d:
            acts = "?"
            try:
                types = json.loads(s.get("activity_types") or "[]") or [s.get("session_type") or "révision"]
                acts = " + ".join(t.capitalize() for t in types[:2])
            except Exception:
                acts = str(s.get("session_type") or "Révision").capitalize()
            dur = s.get("duration_minutes")
            events.append({
                "date": d, "type": "session",
                "label": acts,
                "sub":   _fmt_min(dur) if dur else "",
                "icon": "school", "color": "indigo",
            })

    for qs in qcm_sessions:
        d = qs.get("session_date") or ""
        if d:
            score = qs.get("score_percent") or qs.get("score")
            raw   = qs.get("score_raw") or (f"{score}%" if score else "—")
            events.append({
                "date": d, "type": "qcm",
                "label": f"QCM — {raw}",
                "sub":   qs.get("platform", ""),
                "icon": "quiz", "color": "purple",
            })

    for lc in lacunes[:3]:
        d = (lc.get("created_at") or "")[:10]
        if d:
            events.append({
                "date": d, "type": "lacune",
                "label": (lc.get("detail") or "Lacune")[:50],
                "sub":   lc.get("category") or "",
                "icon": "report_problem", "color": "orange",
            })

    for rh in review_hist[:5]:
        d = (rh.get("completed_at") or rh.get("effective_due_date") or "")[:10]
        if d and rh.get("status") == "done":
            rtype = rh.get("review_type") or ""
            events.append({
                "date": d, "type": "revision",
                "label": f"Révision {rtype}",
                "sub":   "",
                "icon": "check_circle", "color": "green",
            })

    if not events:
        with ui.column().classes("items-center py-6 gap-2 text-slate-400"):
            ui.icon("history", size="lg").classes("opacity-30")
            ui.label("Aucune activité enregistrée.").classes("text-xs")
        return

    events.sort(key=lambda e: e["date"], reverse=True)
    shown = events[:10]

    with ui.column().classes("gap-1.5 w-full"):
        for ev in shown:
            with ui.row().classes("items-start gap-2 py-1"):
                ui.icon(ev["icon"], size="xs").classes(
                    f"text-{ev['color']}-400 shrink-0 mt-0.5"
                )
                with ui.column().classes("gap-0 min-w-0 flex-1"):
                    ui.label(ev["label"]).classes(
                        "text-xs font-semibold text-slate-700 dark:text-slate-200 truncate"
                    )
                    row2_parts = []
                    if ev["sub"]:
                        row2_parts.append(ev["sub"])
                    row2_parts.append(_day_ago(ev["date"]))
                    ui.label(" · ".join(row2_parts)).classes(
                        "text-[11px] text-slate-400"
                    )
