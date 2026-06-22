"""
bilan.py — Synapse — Bilan hebdomadaire
----------------------------------------
Affiche la progression de la semaine + objectifs personnalisables.

Philosophie : non culpabilisant, orienté progression réelle.
- Si les objectifs ne sont pas tous atteints : on met en avant ce qui a été fait.
- Le badge « semaine réussie » est basé sur la progression, pas le volume.
"""
from __future__ import annotations

import datetime
import json
from nicegui import ui
from loguru import logger

from frontend.theme import frame
from backend.core.reviews import local_store
from backend.core.reviews.mastery import get_course_mastery
from backend.state.store import data_store


# ── Couleurs ──────────────────────────────────────────────────────────────────

_TILE = (
    "text-center p-4 rounded-2xl "
    "bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 "
    "shadow-sm flex flex-col gap-1 items-center"
)
_VAL   = "text-2xl font-bold text-slate-800 dark:text-slate-100 tabular-nums"
_LBL   = "text-[11px] text-slate-400 font-medium"
_GOAL  = "text-[11px] text-slate-300 font-medium"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_min(minutes) -> str:
    if not minutes:
        return "—"
    m = int(minutes)
    if m >= 60:
        h, rem = divmod(m, 60)
        return f"{h}h{rem:02d}" if rem else f"{h}h"
    return f"{m}min"


def _week_bounds(offset: int = 0) -> tuple[datetime.date, datetime.date]:
    """Retourne (lundi, dimanche) de la semaine courante (offset=0) ou précédente (offset=-1)."""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=offset)
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def _get_week_stats(monday: datetime.date, sunday: datetime.date) -> dict:
    """Stats de la semaine bornée par monday..sunday."""
    with local_store._conn() as con:
        rows = con.execute(
            "SELECT * FROM study_sessions WHERE session_date >= ? AND session_date <= ?",
            (monday.isoformat(), sunday.isoformat()),
        ).fetchall()

        lacunes_added = con.execute(
            "SELECT COUNT(*) FROM weak_points WHERE DATE(created_at) >= ? AND DATE(created_at) <= ?",
            (monday.isoformat(), sunday.isoformat()),
        ).fetchone()[0]

        lacunes_resolved = con.execute(
            "SELECT COUNT(*) FROM weak_points WHERE status='résolue' "
            "AND resolved_at IS NOT NULL "
            "AND DATE(resolved_at) >= ? AND DATE(resolved_at) <= ?",
            (monday.isoformat(), sunday.isoformat()),
        ).fetchone()[0]

        qcm_rows = con.execute(
            "SELECT score_percent, session_date FROM qcm_sessions "
            "WHERE session_date >= ? AND session_date <= ? AND score_percent IS NOT NULL",
            (monday.isoformat(), sunday.isoformat()),
        ).fetchall()

        reviews_done = con.execute(
            "SELECT COUNT(*) FROM review_history WHERE status='done' "
            "AND DATE(completed_at) >= ? AND DATE(completed_at) <= ?",
            (monday.isoformat(), sunday.isoformat()),
        ).fetchone()[0]

    total_min = sum(r["duration_minutes"] or 0 for r in rows)
    confs = [r["confidence"] for r in rows if r["confidence"]]
    avg_conf = round(sum(confs) / len(confs), 1) if confs else None

    act_counts: dict[str, int] = {}
    for row in rows:
        try:
            types = json.loads(row["activity_types"] or "[]") or [row["session_type"] or "révision"]
        except Exception:
            types = [row["session_type"] or "révision"]
        for t in types:
            k = t.lower().strip()
            if k:
                act_counts[k] = act_counts.get(k, 0) + 1

    lecture_count = act_counts.get("lecture", 0)
    revision_count = act_counts.get("révision", 0) + reviews_done
    anki_count = act_counts.get("anki", 0)
    video_count = act_counts.get("vidéo", 0) + act_counts.get("video", 0)
    fiche_count = act_counts.get("fiche", 0)

    qcm_scores = [r["score_percent"] for r in qcm_rows]
    avg_qcm = round(sum(qcm_scores) / len(qcm_scores), 1) if qcm_scores else None

    unique_days = len({r["session_date"] for r in rows})

    return {
        "total_min":       total_min,
        "session_count":   len(rows),
        "unique_days":     unique_days,
        "avg_conf":        avg_conf,
        "lecture_count":   lecture_count,
        "revision_count":  revision_count,
        "anki_count":      anki_count,
        "video_count":     video_count,
        "fiche_count":     fiche_count,
        "qcm_count":       len(qcm_rows),
        "avg_qcm":         avg_qcm,
        "lacunes_added":   lacunes_added,
        "lacunes_resolved":lacunes_resolved,
        "reviews_done":    reviews_done,
    }


def _get_default_goals() -> dict:
    return {
        "sessions_per_week":     5,
        "qcm_per_week":          3,
        "lacunes_resolved_week": 2,
        "total_minutes_week":    120,
    }


# ── Page ──────────────────────────────────────────────────────────────────────

def bilan_page() -> None:
    with frame("Bilan semaine"):

        # Période affichée (0 = semaine courante, -1 = semaine précédente)
        state = {"offset": 0}
        goals = {**_get_default_goals(), **data_store.preferences.get("weekly_goals", {})}

        monday, sunday = _week_bounds(0)

        with ui.column().classes("w-full gap-6 max-w-4xl mx-auto"):

            # ── Header ─────────────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between flex-wrap gap-3"):
                with ui.column().classes("gap-0"):
                    ui.label("Bilan semaine").classes(
                        "text-3xl font-extrabold text-slate-900 dark:text-slate-50 tracking-tight"
                    )
                    period_label = ui.label("").classes(
                        "text-sm text-slate-400 font-medium"
                    )

                with ui.row().classes("items-center gap-2"):
                    btn_prev = ui.button(icon="chevron_left").props(
                        "flat round dense color=slate"
                    ).tooltip("Semaine précédente")
                    btn_cur = ui.button("Cette semaine").props(
                        "outline rounded size=sm color=indigo"
                    )
                    week_label_nav = ui.label("").classes("text-xs text-slate-400 min-w-[80px] text-center")

            # ── Contenu ────────────────────────────────────────────────────────
            content = ui.column().classes("w-full gap-6")

            # ── Dialog Objectifs ──────────────────────────────────────────────

            def _open_goals_dialog():
                with ui.dialog().props("persistent") as dlg_goals:
                    with ui.card().classes(
                        "w-[440px] max-w-[92vw] rounded-2xl p-0 overflow-hidden"
                    ):
                        with ui.element("div").classes(
                            "px-5 py-4 border-b border-slate-100 dark:border-slate-800"
                        ):
                            with ui.row().classes("items-center justify-between"):
                                ui.label("Objectifs hebdomadaires").classes(
                                    "font-bold text-slate-800 dark:text-slate-100"
                                )
                                ui.button(icon="close", on_click=dlg_goals.close).props(
                                    "flat round dense size=sm color=grey"
                                )

                        with ui.element("div").classes("px-5 py-4 flex flex-col gap-4"):
                            inp_sessions = ui.number(
                                label="Séances de travail",
                                value=goals["sessions_per_week"],
                                min=1, max=50,
                            ).props("outlined dense").classes("w-full")
                            inp_qcm = ui.number(
                                label="QCM faits",
                                value=goals["qcm_per_week"],
                                min=0, max=50,
                            ).props("outlined dense").classes("w-full")
                            inp_lacunes = ui.number(
                                label="Lacunes résolues",
                                value=goals["lacunes_resolved_week"],
                                min=0, max=50,
                            ).props("outlined dense").classes("w-full")
                            inp_minutes = ui.number(
                                label="Temps d'étude (min)",
                                value=goals["total_minutes_week"],
                                min=10, max=600, step=10,
                            ).props("outlined dense").classes("w-full")

                        with ui.element("div").classes(
                            "px-5 py-4 bg-slate-50 dark:bg-slate-800/50 "
                            "border-t border-slate-100 dark:border-slate-800 "
                            "flex justify-end gap-2"
                        ):
                            ui.button("Annuler", on_click=dlg_goals.close).props("flat color=grey-8")

                            def _save_goals():
                                goals["sessions_per_week"]     = int(inp_sessions.value or 5)
                                goals["qcm_per_week"]          = int(inp_qcm.value or 3)
                                goals["lacunes_resolved_week"] = int(inp_lacunes.value or 2)
                                goals["total_minutes_week"]    = int(inp_minutes.value or 120)
                                data_store.preferences["weekly_goals"] = dict(goals)
                                data_store.save_to_disk()
                                dlg_goals.close()
                                _render(state["offset"])
                                ui.notify("Objectifs sauvegardés ✓", type="positive")

                            ui.button("Sauvegarder", on_click=_save_goals).props(
                                "unelevated color=indigo rounded"
                            ).classes("font-semibold")

                dlg_goals.open()

            # ── Render ────────────────────────────────────────────────────────

            def _render(offset: int):
                state["offset"] = offset
                mon, sun = _week_bounds(offset)
                stats = _get_week_stats(mon, sun)

                # Labels de navigation
                months_fr = ["jan", "fév", "mar", "avr", "mai", "juin",
                             "juil", "août", "sep", "oct", "nov", "déc"]
                mon_str = f"{mon.day} {months_fr[mon.month - 1]}"
                sun_str = f"{sun.day} {months_fr[sun.month - 1]}"
                if offset == 0:
                    period_label.set_text("Semaine en cours")
                    week_label_nav.set_text(f"{mon_str} – {sun_str}")
                else:
                    week_label_nav.set_text(f"{mon_str} – {sun_str}")
                    period_label.set_text(
                        f"Semaine du {mon_str} au {sun_str}"
                    )

                # Calcul "semaine réussie"
                g = goals
                achieved = 0
                total_goals = 4
                if stats["session_count"] >= g["sessions_per_week"]:
                    achieved += 1
                if stats["qcm_count"] >= g["qcm_per_week"]:
                    achieved += 1
                if stats["lacunes_resolved"] >= g["lacunes_resolved_week"]:
                    achieved += 1
                if stats["total_min"] >= g["total_minutes_week"]:
                    achieved += 1

                pct_goals = int(achieved / total_goals * 100)
                is_success = pct_goals >= 50

                content.clear()
                with content:

                    # ── Badge progression ─────────────────────────────────────
                    if offset == 0 and not stats["session_count"]:
                        with ui.element("div").classes(
                            "w-full p-4 rounded-2xl border border-blue-100 dark:border-blue-800 "
                            "bg-blue-50 dark:bg-blue-900/10 flex items-center gap-3"
                        ):
                            ui.icon("lightbulb", color="blue").classes("text-xl shrink-0")
                            ui.label(
                                "Aucune séance enregistrée cette semaine. "
                                "Valide une révision dans le Dashboard pour commencer !"
                            ).classes("text-sm text-blue-700 dark:text-blue-300")
                    else:
                        _bilan_icon = "emoji_events" if is_success else "trending_up"
                        _bilan_color = "green" if is_success else "blue"
                        _bilan_txt = (
                            f"Belle semaine ! {achieved}/{total_goals} objectifs atteints."
                            if is_success else
                            f"{achieved}/{total_goals} objectifs atteints — {stats['unique_days']} jour(s) travaillé(s). Continue comme ça !"
                        )
                        with ui.element("div").classes(
                            f"w-full p-4 rounded-2xl border border-{_bilan_color}-100 dark:border-{_bilan_color}-800 "
                            f"bg-{_bilan_color}-50 dark:bg-{_bilan_color}-900/10 flex items-center gap-4"
                        ):
                            ui.icon(_bilan_icon, color=_bilan_color).classes("text-3xl shrink-0")
                            with ui.column().classes("gap-0.5 flex-1"):
                                ui.label(_bilan_txt).classes(
                                    f"text-sm font-semibold text-{_bilan_color}-800 dark:text-{_bilan_color}-200"
                                )
                                if stats["total_min"]:
                                    ui.label(
                                        f"{_fmt_min(stats['total_min'])} de travail · {stats['unique_days']} jour(s)"
                                    ).classes(f"text-xs text-{_bilan_color}-600 dark:text-{_bilan_color}-400")

                            ui.button(
                                "Objectifs", icon="tune",
                                on_click=_open_goals_dialog,
                            ).props(f"outline rounded size=sm color={_bilan_color}").classes("text-xs shrink-0")

                    # ── Tuiles métriques ──────────────────────────────────────
                    with ui.element("div").classes(
                        "grid grid-cols-2 sm:grid-cols-4 gap-3 w-full"
                    ):
                        def _tile(val, lbl, goal_val=None, goal_lbl=""):
                            with ui.element("div").classes(_TILE):
                                ui.label(val).classes(_VAL)
                                ui.label(lbl).classes(_LBL)
                                if goal_val is not None:
                                    ui.label(f"Objectif : {goal_val}{goal_lbl}").classes(_GOAL)

                        _tile(
                            _fmt_min(stats["total_min"]),
                            "Temps d'étude",
                            _fmt_min(g["total_minutes_week"]),
                        )
                        _tile(
                            str(stats["session_count"]),
                            "Séances",
                            str(g["sessions_per_week"]),
                        )
                        _tile(
                            str(stats["qcm_count"]),
                            "QCM",
                            str(g["qcm_per_week"]),
                        )
                        _tile(
                            str(stats["lacunes_resolved"]),
                            "Lacunes résolues",
                            str(g["lacunes_resolved_week"]),
                        )

                    # ── Barres de progression objectifs ───────────────────────
                    with ui.card().classes(
                        "w-full p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800"
                    ):
                        ui.label("Progression des objectifs").classes(
                            "text-xs font-bold uppercase tracking-widest text-slate-400 mb-3"
                        )
                        for label, actual, goal, color in [
                            ("Séances",          stats["session_count"],     g["sessions_per_week"],     "indigo"),
                            ("Temps (min)",       stats["total_min"],         g["total_minutes_week"],    "blue"),
                            ("QCM",              stats["qcm_count"],         g["qcm_per_week"],          "purple"),
                            ("Lacunes résolues", stats["lacunes_resolved"],  g["lacunes_resolved_week"], "green"),
                        ]:
                            pct = min(1.0, actual / goal) if goal else 0.0
                            with ui.row().classes("items-center gap-3 w-full mb-2"):
                                ui.label(label).classes(
                                    "text-xs text-slate-500 dark:text-slate-400 w-32 shrink-0"
                                )
                                ui.linear_progress(value=pct).props(
                                    f"color={color} size=8px"
                                ).classes("flex-1")
                                ui.label(f"{actual}/{goal}").classes(
                                    "text-[11px] text-slate-400 w-12 text-right shrink-0 tabular-nums"
                                )

                    # ── Détails activités ─────────────────────────────────────
                    act_items = [
                        ("menu_book",   "Lectures",         stats["lecture_count"],   "blue"),
                        ("auto_stories","Révisions",        stats["revision_count"],  "indigo"),
                        ("quiz",        "QCM",              stats["qcm_count"],       "purple"),
                        ("style",       "Anki",             stats["anki_count"],      "teal"),
                        ("video_library","Vidéos",          stats["video_count"],     "orange"),
                        ("report_problem","Lacunes ajoutées",stats["lacunes_added"],  "red"),
                        ("check_circle","Lacunes résolues", stats["lacunes_resolved"],"green"),
                    ]
                    with ui.element("div").classes("grid grid-cols-2 sm:grid-cols-4 gap-3 w-full"):
                        for icon_n, lbl, val, color in act_items:
                            with ui.element("div").classes(
                                f"flex items-center gap-2 p-3 rounded-xl "
                                f"bg-{color}-50 dark:bg-{color}-900/10 "
                                f"border border-{color}-100 dark:border-{color}-800"
                            ):
                                ui.icon(icon_n, size="sm").classes(f"text-{color}-500 shrink-0")
                                with ui.column().classes("gap-0"):
                                    ui.label(str(val)).classes(
                                        f"text-lg font-bold text-{color}-700 dark:text-{color}-300 tabular-nums"
                                    )
                                    ui.label(lbl).classes(
                                        f"text-[11px] text-{color}-500 dark:text-{color}-400"
                                    )

                    # ── QCM score moyen ───────────────────────────────────────
                    if stats["avg_qcm"] is not None:
                        from backend.core.qcm.service import score_bg_classes
                        _qcm_cls = score_bg_classes(stats["avg_qcm"])
                        with ui.element("div").classes(
                            f"w-full p-4 rounded-2xl {_qcm_cls} border border-current border-opacity-20"
                        ):
                            with ui.row().classes("items-center gap-3"):
                                ui.icon("quiz").classes("text-xl shrink-0")
                                ui.label(
                                    f"Score QCM moyen cette semaine : {stats['avg_qcm']}%"
                                ).classes("text-sm font-semibold")

                    # ── Confiance moyenne ─────────────────────────────────────
                    if stats["avg_conf"] is not None:
                        conf_txt = (
                            "Très à l'aise" if stats["avg_conf"] >= 4.5 else
                            "À l'aise" if stats["avg_conf"] >= 3.5 else
                            "En progression" if stats["avg_conf"] >= 2.5 else
                            "À consolider"
                        )
                        with ui.element("div").classes(
                            "w-full p-3 rounded-2xl bg-slate-50 dark:bg-slate-800 "
                            "border border-slate-100 dark:border-slate-700 flex items-center gap-3"
                        ):
                            ui.icon("sentiment_satisfied", size="sm").classes("text-indigo-400 shrink-0")
                            ui.label(
                                f"Confiance moyenne : {stats['avg_conf']}/5 — {conf_txt}"
                            ).classes("text-sm text-slate-600 dark:text-slate-300")

            # ── Callbacks navigation ──────────────────────────────────────────

            def _go_prev():
                _render(state["offset"] - 1)
                btn_cur.props("outline rounded size=sm color=indigo")

            def _go_cur():
                _render(0)
                btn_cur.props("unelevated rounded size=sm color=indigo")

            btn_prev.on_click(_go_prev)
            btn_cur.on_click(_go_cur)

            # Rendu initial
            _render(0)
