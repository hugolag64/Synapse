"""
stats.py — Page Suivi v2 (Feed style)
--------------------------------------
Layout :
  • Bandeau cours fragiles / critiques  → slider horizontal, actionnable
  • Statistiques de la période          → accordion replié par défaut
  • Timeline d'activité                 → séances + pièges fusionnés par date
"""
from __future__ import annotations

import datetime
import json
from collections import defaultdict
from types import SimpleNamespace

from loguru import logger
from nicegui import ui

from backend.core.reviews import local_store
from backend.core.reviews.mastery import get_course_mastery, PROGRESSION_COLORS
from backend.state.store import data_store
from frontend.theme import frame
from frontend.components.course_card import _ACCENT_HEX
from frontend.components.course_quick_actions import open_quick_session_dialog
from frontend.components.sparkline import sparkline_svg


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(row, key: str, default=None):
    try:
        v = row[key]
        return v if v is not None else default
    except Exception:
        return default


def _fmt_minutes(minutes) -> str:
    if not minutes:
        return "—"
    m = int(minutes)
    if m >= 60:
        h, rem = divmod(m, 60)
        return f"{h}h{rem:02d}" if rem else f"{h}h"
    return f"{m}min"


def _fmt_activities(raw: str | None) -> str:
    if not raw:
        return "Révision"
    try:
        types = json.loads(raw)
        return " + ".join(t.capitalize() for t in types) if types else "Révision"
    except Exception:
        return str(raw).capitalize()


def _day_label(d: datetime.date) -> str:
    today = datetime.date.today()
    if d == today:
        return "Aujourd'hui"
    if d == today - datetime.timedelta(days=1):
        return "Hier"
    return d.strftime("%d %b")


def _get_all_mastery_snapshots() -> list[tuple]:
    """Snapshot de maîtrise pour tous les cours (y compris non commencés).
    Contrairement à _get_fragile_courses, ne filtre rien : sert de base
    commune au score moyen (KPI) et à la répartition par niveau."""
    if not data_store.cours:
        return []
    try:
        sessions_map = local_store.get_sessions_by_course()
        postpone_map = local_store.get_postpone_counts()
    except Exception as exc:
        logger.warning(f"mastery snapshots load: {exc}")
        return []

    results = []
    for course in data_store.cours:
        try:
            sessions = sessions_map.get(course.id, [])
            snap = get_course_mastery(
                course, context="college", sessions=sessions,
                total_postpone=postpone_map.get(course.id, 0),
            )
        except Exception:
            continue
        results.append((snap, course))
    return results


_LEVEL_HEX: dict[str, str] = {
    level: _ACCENT_HEX.get(color, "#94A3B8")
    for level, color in PROGRESSION_COLORS.items()
}
_LEVEL_ORDER = [
    "à préparer", "à lire", "en construction", "à consolider",
    "à entraîner", "fragile", "critique", "maîtrisé",
]


def _render_mastery_distribution(container, snapshots: list) -> None:
    container.clear()
    if not snapshots:
        return

    counts: dict[str, int] = defaultdict(int)
    for snap, _ in snapshots:
        counts[snap.level] += 1
    total = sum(counts.values())
    if not total:
        return

    with container:
        with ui.element("div").classes("synapse-panel w-full p-4"):
            ui.label("Répartition de la maîtrise").classes(
                "text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-3"
            )
            with ui.element("div").classes(
                "flex w-full rounded-full overflow-hidden gap-px"
            ).style("height:10px"):
                for level in _LEVEL_ORDER:
                    cnt = counts.get(level, 0)
                    if not cnt:
                        continue
                    pct = max(cnt / total * 100, 2)
                    color = _LEVEL_HEX.get(level, "#94A3B8")
                    ui.element("div").style(
                        f"width:{pct}%;background:{color};flex-shrink:0"
                    ).tooltip(f"{cnt} cours · {level.capitalize()}")

            with ui.row().classes("flex-wrap gap-x-4 gap-y-1.5 mt-3"):
                for level in _LEVEL_ORDER:
                    cnt = counts.get(level, 0)
                    if not cnt:
                        continue
                    color = _LEVEL_HEX.get(level, "#94A3B8")
                    with ui.row().classes("items-center gap-1.5 cursor-pointer").on(
                        "click", lambda: ui.navigate.to("/colleges")
                    ):
                        ui.element("div").classes("w-2 h-2 rounded-full shrink-0").style(
                            f"background:{color}"
                        )
                        ui.label(f"{level.capitalize()} ({cnt})").classes(
                            "text-[11px] text-slate-500 dark:text-slate-400"
                        )


def _compute_kpis(days: int, snapshots: list) -> dict:
    stats = local_store.get_weekly_study_stats(days=days)

    sessions = local_store.get_recent_study_sessions(limit=200)
    if days > 0:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        sessions = [s for s in sessions if (_get(s, "session_date") or "") >= cutoff]

    daily_minutes: dict[str, int] = defaultdict(int)
    daily_counts: dict[str, int] = defaultdict(int)
    for s in sessions:
        d = _get(s, "session_date")
        if not d:
            continue
        daily_minutes[d] += _get(s, "duration_minutes", 0) or 0
        daily_counts[d] += 1

    days_sorted = sorted(daily_minutes.keys())
    minutes_series = [daily_minutes[d] for d in days_sorted]
    sessions_series = [daily_counts[d] for d in days_sorted]

    scores = [snap.score for snap, _ in snapshots if snap.score is not None]
    avg_score = round(sum(scores) / len(scores)) if scores else None

    return {
        "total_minutes": stats["total_minutes"],
        "session_count": stats["session_count"],
        "minutes_series": minutes_series,
        "sessions_series": sessions_series,
        "avg_score": avg_score,
        "tracked_count": len(scores),
        "streak": local_store.get_streak_days(),
    }


def _render_kpi_row(container, kpis: dict) -> None:
    container.clear()

    def _kpi(icon_name, label, value_txt, accent_hex, sub_txt, extra=None):
        with ui.element("div").classes("synapse-kpi-card w-full").style(
            f"--card-accent:{accent_hex}"
        ):
            if extra:
                extra()
            with ui.column().classes("gap-1 min-w-0 flex-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon(icon_name, size="xs").classes("text-slate-300")
                    ui.label(label).classes("text-xs text-slate-400 font-medium")
                ui.label(value_txt).classes(
                    "text-3xl font-extrabold tabular-nums leading-none text-slate-800 dark:text-slate-100"
                )
                ui.label(sub_txt).classes("text-xs text-slate-400")

    with container:
        # Temps d'étude
        def _time_spark(_vals=kpis["minutes_series"]):
            if len(_vals) >= 2:
                ui.html(
                    sparkline_svg(_vals, "#2563EB"), sanitize=False
                ).classes("synapse-spark")

        _kpi(
            "schedule", "Temps d'étude", _fmt_minutes(kpis["total_minutes"]),
            "#2563EB", f"{kpis['session_count']} séance(s)",
            extra=_time_spark if len(kpis["minutes_series"]) >= 2 else None,
        )

        # Séances
        def _sess_spark(_vals=kpis["sessions_series"]):
            if len(_vals) >= 2:
                ui.html(
                    sparkline_svg(_vals, "#2563EB"), sanitize=False
                ).classes("synapse-spark")

        _kpi(
            "event_repeat", "Séances", str(kpis["session_count"]),
            "#2563EB", "sur la période",
            extra=_sess_spark if len(kpis["sessions_series"]) >= 2 else None,
        )

        # Score de maîtrise moyen (ring)
        avg = kpis["avg_score"]
        ring_col = (
            "#22c55e" if avg is not None and avg >= 80
            else "#3B82F6" if avg is not None and avg >= 60
            else "#f97316" if avg is not None and avg >= 40
            else "#ef4444" if avg is not None
            else "#CBD5E1"
        )

        def _ring_extra(_pct=avg or 0, _col=ring_col):
            with ui.element("div").classes("synapse-ring").style(
                f"--ring-pct:{_pct};--ring-color:{_col}"
            ):
                ui.label(f"{_pct}%").classes("synapse-ring-label").style(f"color:{_col}")

        _kpi(
            "insights", "Score de maîtrise", f"{avg}%" if avg is not None else "—",
            ring_col, f"{kpis['tracked_count']} cours suivis",
            extra=_ring_extra if avg is not None else None,
        )

        # Série en cours (streak)
        streak = kpis["streak"]
        streak_col = "#f97316" if streak >= 3 else "#94A3B8"

        def _streak_extra(_col=streak_col):
            with ui.element("div").classes(
                "flex items-center justify-center rounded-full w-11 h-11 shrink-0"
            ).style(f"background:{_col}1A"):
                ui.icon("local_fire_department", size="sm").style(f"color:{_col}")

        _kpi(
            "local_fire_department", "Série en cours", f"{streak}j",
            streak_col, "jours consécutifs",
            extra=_streak_extra,
        )


def _get_fragile_courses(limit: int = 15) -> list[tuple]:
    if not data_store.cours:
        return []
    try:
        sessions_map = local_store.get_sessions_by_course()
        postpone_map = local_store.get_postpone_counts()
    except Exception as exc:
        logger.warning(f"fragile load: {exc}")
        return []

    results = []
    for course in data_store.cours:
        try:
            sessions = sessions_map.get(course.id, [])
            nb_lec = getattr(course, "nb_lectures", 0) or 0
            if nb_lec == 0 and not sessions and not getattr(course, "qcm_done", False):
                continue
            snap = get_course_mastery(course, context="college", sessions=sessions, total_postpone=postpone_map.get(course.id, 0))
        except Exception:
            continue
        if snap.level in ("critique", "fragile"):
            results.append((snap, course))

    results.sort(key=lambda x: x[0].score)
    return results[:limit]


# ── Couleurs activités ────────────────────────────────────────────────────────

_ACT = {
    "révision":   ("bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",   "blue"),
    "lecture":    ("bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300", "indigo"),
    "qcm":        ("bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300", "purple"),
    "dp":         ("bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",   "pink"),
    "kfp":        ("bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",   "pink"),
    "anki":       ("bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300", "green"),
    "fiche":      ("bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",   "teal"),
    "correction": ("bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300", "orange"),
}


# ── Section 1 : Slider cours fragiles ────────────────────────────────────────

def _render_fragile_banner(fragile: list, render_fn) -> None:
    if not fragile:
        return

    try:
        client = ui.context.client
    except Exception:
        client = None

    n_crit  = sum(1 for s, _ in fragile if s.level == "critique")
    n_frag  = len(fragile) - n_crit
    is_crit = n_crit > 0

    parts = []
    if n_crit:
        parts.append(f"{n_crit} critique{'s' if n_crit > 1 else ''}")
    if n_frag:
        parts.append(f"{n_frag} fragile{'s' if n_frag > 1 else ''}")
    lbl = " · ".join(parts)

    border_col = "red" if is_crit else "orange"

    with ui.element("div").classes(
        f"w-full border border-{border_col}-200 dark:border-{border_col}-800 "
        f"bg-{border_col}-50 dark:bg-{border_col}-900/10 p-4"
    ).style("border-radius: var(--s-r-xl)"):
        # Titre du bandeau
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon(
                "local_fire_department" if is_crit else "warning_amber"
            ).classes(f"text-{border_col}-500")
            ui.label(lbl).classes(
                f"text-sm font-bold text-{border_col}-700 dark:text-{border_col}-400 flex-1"
            )
            ui.label("Voir Collèges →").classes(
                "text-xs text-slate-400 cursor-pointer hover:text-slate-600"
            ).on("click", lambda: ui.navigate.to("/colleges"))

        # Slider horizontal
        with ui.element("div").classes(
            "flex gap-3 w-full overflow-x-auto pb-2"
        ).style("scrollbar-width: thin; -webkit-overflow-scrolling: touch"):
            for snap, course in fragile:
                _render_fragile_card(snap, course, render_fn, client)


def _render_fragile_card(snap, course, render_fn, client) -> None:
    LEVEL = {
        "critique": (
            "border-red-200 dark:border-red-800",
            "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
        ),
        "fragile": (
            "border-orange-200 dark:border-orange-800",
            "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
        ),
    }
    border_cls, badge_cls = LEVEL.get(snap.level, LEVEL["fragile"])
    title = getattr(course, "display_title", None) or course.title

    anki_done   = getattr(course, "anki", False)
    resume_done = getattr(course, "resume_done", False)
    qcm_done    = getattr(course, "qcm_done", False)

    with ui.element("div").classes(
        f"flex-shrink-0 w-44 border {border_cls} "
        "bg-white dark:bg-slate-900 p-3 flex flex-col gap-2"
    ).style("border-radius: var(--s-r-lg); box-shadow: var(--s-shadow-sm)"):
        # Niveau + score
        with ui.row().classes("items-center gap-1"):
            ui.label(snap.level.capitalize()).classes(
                f"text-[11px] font-bold px-1.5 py-0.5 rounded-full {badge_cls}"
            )
            ui.label(f"{snap.score}%").classes(
                "text-[11px] font-semibold text-slate-400 ml-auto tabular-nums"
            )

        # Titre
        ui.label(title).classes(
            "text-xs font-semibold text-slate-800 dark:text-slate-100 leading-snug"
        ).style(
            "display:-webkit-box;-webkit-line-clamp:2;"
            "-webkit-box-orient:vertical;overflow:hidden"
        ).tooltip(title)

        # Raisons
        if snap.reasons:
            ui.label(" · ".join(snap.reasons[:2])).classes(
                "text-[11px] text-slate-400 leading-tight"
            )

        # Chips statut
        with ui.row().classes("flex-wrap gap-1 mt-auto pt-1"):
            for done, lbl, col in [
                (anki_done,   "Anki",   "teal"),
                (resume_done, "Résumé", "blue"),
                (qcm_done,    "QCM",    "indigo"),
            ]:
                ui.badge(
                    f"✓ {lbl}" if done else lbl,
                    color=col if done else "grey",
                ).classes(
                    "text-[11px] px-1 py-0.5" + ("" if done else " opacity-40")
                )

        # CTA
        ui.button(
            "Séance",
            icon="edit_note",
            on_click=lambda c=course: open_quick_session_dialog(c, render_fn, client),
        ).props("outline rounded size=xs color=grey-7").classes(
            "w-full text-[11px] mt-1"
        )


# ── Section 3 : Timeline d'activité ──────────────────────────────────────────

def _render_timeline(sessions: list, weak_points: list, render_fn) -> None:
    """Séances + pièges fusionnés, triés par date décroissante."""

    events: list[dict] = []

    for s in sessions:
        sd = _get(s, "session_date")
        if sd:
            events.append({"type": "session", "date": sd, "row": s})

    for wp in weak_points:
        sd = (_get(wp, "created_at") or "")[:10]
        if sd:
            events.append({"type": "weak", "date": sd, "row": wp})

    if not events:
        with ui.column().classes("items-center py-12 gap-3"):
            ui.icon("feed", size="xl").classes("text-slate-200 dark:text-slate-700")
            ui.label("Aucune activité enregistrée").classes(
                "text-sm text-slate-400"
            )
            ui.label(
                "Valide une révision dans le Dashboard pour commencer."
            ).classes("text-xs text-slate-300 text-center")
        return

    events.sort(key=lambda e: e["date"], reverse=True)

    groups: dict[str, list] = defaultdict(list)
    for ev in events:
        groups[ev["date"]].append(ev)

    for date_str in sorted(groups.keys(), reverse=True):
        try:
            d = datetime.date.fromisoformat(date_str)
            day_lbl = _day_label(d)
        except Exception:
            day_lbl = date_str

        # En-tête de groupe
        with ui.row().classes("items-center gap-3 mt-3 mb-1"):
            ui.label(day_lbl).classes(
                "text-[11px] font-bold uppercase tracking-widest text-slate-400"
            )
            ui.element("div").classes(
                "flex-1 h-px bg-slate-100 dark:bg-slate-800"
            )

        for ev in groups[date_str]:
            if ev["type"] == "session":
                _render_session_row(ev["row"])
            else:
                _render_weak_row(ev["row"], render_fn)


def _render_session_row(s) -> None:
    item_txt  = f"ITEM {_get(s, 'item_number')} – " if _get(s, "item_number") else ""
    title     = f"{item_txt}{_get(s, 'course_title') or _get(s, 'course_id', '—')}"
    acts_raw  = _get(s, "activity_types")
    acts      = _fmt_activities(acts_raw)
    dur       = _get(s, "duration_minutes")
    conf      = _get(s, "confidence")
    qcm       = (_get(s, "qcm_result") or "").strip().lower()
    notes     = (_get(s, "notes") or _get(s, "weak_detail") or "").strip()

    try:
        primary = json.loads(acts_raw)[0].lower() if acts_raw else "révision"
    except Exception:
        primary = "révision"

    badge_cls, _ = _ACT.get(primary, ("bg-slate-100 text-slate-600", "slate"))

    QCM_CLR = {"réussi": "text-green-600", "moyen": "text-orange-500", "raté": "text-red-500"}

    with ui.element("div").classes(
        "flex items-center gap-3 py-2 px-2 rounded-lg "
        "hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
    ):
        # Badge activité
        ui.label(acts).classes(
            f"text-[11px] font-semibold px-2 py-1 rounded-lg shrink-0 "
            f"w-24 text-center {badge_cls}"
        )

        # Titre + méta
        with ui.column().classes("flex-1 min-w-0 gap-0.5"):
            ui.label(title).classes(
                "text-sm font-semibold text-slate-800 dark:text-slate-100 truncate"
            ).tooltip(title)

            meta: list[str] = []
            if conf:
                meta.append(f"conf. {conf}/5")
            if qcm:
                meta.append(f"QCM {qcm}")
            if notes:
                meta.append(notes[:60] + ("…" if len(notes) > 60 else ""))
            if meta:
                ui.label(" · ".join(meta)).classes(
                    f"text-[11px] {QCM_CLR.get(qcm, 'text-slate-400')}"
                )

        # Durée
        if dur:
            ui.label(_fmt_minutes(dur)).classes(
                "text-xs font-bold text-slate-400 shrink-0 tabular-nums"
            )


def _render_weak_row(wp, render_fn) -> None:
    item_txt = f"ITEM {_get(wp, 'item_number')} – " if _get(wp, "item_number") else ""
    course   = f"{item_txt}{_get(wp, 'course_title') or _get(wp, 'course_id', '—')}"
    detail   = (_get(wp, "detail") or "").strip()
    cat      = (_get(wp, "category") or "").strip()
    wp_id    = _get(wp, "id")

    with ui.element("div").classes(
        "flex items-center gap-3 py-2 px-2 rounded-lg "
        "hover:bg-amber-50 dark:hover:bg-amber-900/10 transition-colors"
    ):
        # Badge piège
        ui.label("⚠ Piège").classes(
            "text-[11px] font-semibold px-2 py-1 rounded-lg shrink-0 "
            "w-24 text-center "
            "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
        )

        # Contenu
        with ui.column().classes("flex-1 min-w-0 gap-0.5"):
            ui.label(course).classes(
                "text-sm font-semibold text-slate-800 dark:text-slate-100 truncate"
            )
            row2_parts = []
            if detail:
                row2_parts.append(detail[:80] + ("…" if len(detail) > 80 else ""))
            if cat and cat.lower() not in ("autre", ""):
                row2_parts.append(cat)
            if row2_parts:
                ui.label(" · ".join(row2_parts)).classes(
                    "text-[11px] text-amber-600 dark:text-amber-400 italic"
                )

        # Bouton résolu
        if wp_id is not None:
            def _resolve(wid=wp_id):
                try:
                    local_store.resolve_weak_point(wid)
                    ui.notify("Piège résolu ✓", type="positive")
                    render_fn()
                except Exception as exc:
                    ui.notify(f"Erreur : {exc}", type="negative")
            ui.button(icon="check", on_click=_resolve).props(
                "flat round dense size=xs color=positive"
            ).tooltip("Marquer résolu")


# ── Onglet Semaine (bilan hebdomadaire) ──────────────────────────────────────

def _render_semaine_tab() -> None:
    import datetime as _dt

    _TILE = (
        "text-center p-4 rounded-2xl "
        "bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 "
        "shadow-sm flex flex-col gap-1 items-center"
    )
    _VAL  = "text-2xl font-bold text-slate-800 dark:text-slate-100 tabular-nums"
    _LBL  = "text-[11px] text-slate-400 font-medium"
    _GOAL = "text-[11px] text-slate-300 font-medium"

    def _fmt_min(m) -> str:
        if not m:
            return "—"
        m = int(m)
        return f"{m//60}h{m%60:02d}" if m >= 60 else f"{m}min"

    def _week_bounds(offset: int = 0):
        today = _dt.date.today()
        mon = today - _dt.timedelta(days=today.weekday()) + _dt.timedelta(weeks=offset)
        return mon, mon + _dt.timedelta(days=6)

    state  = {"offset": 0}
    goals  = {
        "sessions_per_week": 5,
        "qcm_per_week": 3,
        "lacunes_resolved_week": 2,
        "total_minutes_week": 120,
        **data_store.preferences.get("weekly_goals", {}),
    }

    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 mb-4"):
        period_label  = ui.label("Semaine en cours").classes("text-sm text-slate-400 font-medium")
        with ui.row().classes("items-center gap-2"):
            btn_prev = ui.button(icon="chevron_left").props("flat round dense color=slate").tooltip("Semaine précédente")
            btn_cur  = ui.button("Cette semaine").props("unelevated rounded size=sm color=indigo")
            week_nav = ui.label("").classes("text-xs text-slate-400 min-w-[80px] text-center")

    content_sem = ui.column().classes("w-full gap-5")

    def _open_goals_dialog():
        with ui.dialog().props("persistent") as dlg_goals:
            with ui.card().classes("w-[440px] max-w-[92vw] rounded-2xl p-0 overflow-hidden"):
                with ui.element("div").classes("px-5 py-4 border-b border-slate-100 dark:border-slate-800"):
                    with ui.row().classes("items-center justify-between"):
                        ui.label("Objectifs hebdomadaires").classes("font-bold text-slate-800 dark:text-slate-100")
                        ui.button(icon="close", on_click=dlg_goals.close).props("flat round dense size=sm color=grey")
                with ui.element("div").classes("px-5 py-4 flex flex-col gap-4"):
                    inp_s = ui.number(label="Séances de travail",  value=goals["sessions_per_week"],     min=1, max=50).props("outlined dense").classes("w-full")
                    inp_q = ui.number(label="QCM faits",           value=goals["qcm_per_week"],          min=0, max=50).props("outlined dense").classes("w-full")
                    inp_l = ui.number(label="Lacunes résolues",    value=goals["lacunes_resolved_week"], min=0, max=50).props("outlined dense").classes("w-full")
                    inp_m = ui.number(label="Temps d'étude (min)", value=goals["total_minutes_week"],    min=10, max=600, step=10).props("outlined dense").classes("w-full")
                with ui.element("div").classes("px-5 py-4 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2"):
                    ui.button("Annuler", on_click=dlg_goals.close).props("flat color=grey-8")
                    def _save():
                        goals["sessions_per_week"]     = int(inp_s.value or 5)
                        goals["qcm_per_week"]          = int(inp_q.value or 3)
                        goals["lacunes_resolved_week"] = int(inp_l.value or 2)
                        goals["total_minutes_week"]    = int(inp_m.value or 120)
                        data_store.preferences["weekly_goals"] = dict(goals)
                        data_store.save_to_disk()
                        dlg_goals.close()
                        _render_sem(state["offset"])
                        ui.notify("Objectifs sauvegardés ✓", type="positive")
                    ui.button("Sauvegarder", on_click=_save).props("unelevated color=indigo rounded").classes("font-semibold")
        dlg_goals.open()

    def _render_sem(offset: int):
        state["offset"] = offset
        mon, sun = _week_bounds(offset)
        stats = local_store.get_bounded_week_stats(mon, sun)
        g = goals

        months_fr = ["jan","fév","mar","avr","mai","juin","juil","août","sep","oct","nov","déc"]
        mon_s = f"{mon.day} {months_fr[mon.month-1]}"
        sun_s = f"{sun.day} {months_fr[sun.month-1]}"
        period_label.set_text("Semaine en cours" if offset == 0 else f"Semaine du {mon_s} au {sun_s}")
        week_nav.set_text(f"{mon_s} – {sun_s}")
        btn_cur.props("unelevated rounded size=sm color=indigo" if offset == 0 else "outline rounded size=sm color=indigo")

        achieved = sum([
            stats["session_count"] >= g["sessions_per_week"],
            stats["qcm_count"]     >= g["qcm_per_week"],
            stats["lacunes_resolved"] >= g["lacunes_resolved_week"],
            stats["total_min"]     >= g["total_minutes_week"],
        ])
        is_ok = achieved >= 2

        content_sem.clear()
        with content_sem:
            # Badge progression
            if offset == 0 and not stats["session_count"]:
                with ui.element("div").classes(
                    "w-full p-4 border border-blue-100 dark:border-blue-800 "
                    "bg-blue-50 dark:bg-blue-900/10 flex items-center gap-3"
                ).style("border-radius: var(--s-r-2xl)"):
                    ui.icon("lightbulb", color="blue").classes("text-xl shrink-0")
                    ui.label("Aucune séance cette semaine. Valide une révision dans le Dashboard !").classes(
                        "text-sm text-blue-700 dark:text-blue-300"
                    )
            else:
                _col = "green" if is_ok else "blue"
                _ico = "emoji_events" if is_ok else "trending_up"
                _txt = (
                    f"Belle semaine ! {achieved}/4 objectifs atteints."
                    if is_ok else
                    f"{achieved}/4 objectifs atteints — {stats['unique_days']} jour(s) travaillé(s). Continue !"
                )
                with ui.element("div").classes(
                    f"w-full p-4 border border-{_col}-100 dark:border-{_col}-800 "
                    f"bg-{_col}-50 dark:bg-{_col}-900/10 flex items-center gap-4"
                ).style("border-radius: var(--s-r-2xl)"):
                    ui.icon(_ico, color=_col).classes("text-3xl shrink-0")
                    with ui.column().classes("gap-0.5 flex-1"):
                        ui.label(_txt).classes(f"text-sm font-semibold text-{_col}-800 dark:text-{_col}-200")
                        if stats["total_min"]:
                            ui.label(f"{_fmt_min(stats['total_min'])} de travail · {stats['unique_days']} jour(s)").classes(
                                f"text-xs text-{_col}-600 dark:text-{_col}-400"
                            )
                    ui.button("Objectifs", icon="tune", on_click=_open_goals_dialog).props(
                        f"outline rounded size=sm color={_col}"
                    ).classes("text-xs shrink-0")

            # Tuiles métriques
            with ui.element("div").classes("grid grid-cols-2 sm:grid-cols-4 gap-3 w-full"):
                for val, lbl, goal_val in [
                    (_fmt_min(stats["total_min"]),      "Temps d'étude",   _fmt_min(g["total_minutes_week"])),
                    (str(stats["session_count"]),        "Séances",         str(g["sessions_per_week"])),
                    (str(stats["qcm_count"]),            "QCM",             str(g["qcm_per_week"])),
                    (str(stats["lacunes_resolved"]),     "Lacunes résolues",str(g["lacunes_resolved_week"])),
                ]:
                    with ui.element("div").classes(_TILE):
                        ui.label(val).classes(_VAL)
                        ui.label(lbl).classes(_LBL)
                        ui.label(f"Objectif : {goal_val}").classes(_GOAL)

            # Barres de progression
            with ui.card().classes("w-full p-4 border border-slate-100 dark:border-slate-800").style(
                "border-radius: var(--s-r-2xl); box-shadow: var(--s-shadow-sm)"
            ):
                ui.label("Progression des objectifs").classes(
                    "text-xs font-bold uppercase tracking-widest text-slate-400 mb-3"
                )
                for lbl, actual, goal_v, color in [
                    ("Séances",          stats["session_count"],    g["sessions_per_week"],     "indigo"),
                    ("Temps (min)",       stats["total_min"],        g["total_minutes_week"],    "blue"),
                    ("QCM",              stats["qcm_count"],        g["qcm_per_week"],          "purple"),
                    ("Lacunes résolues", stats["lacunes_resolved"], g["lacunes_resolved_week"], "green"),
                ]:
                    pct = min(1.0, actual / goal_v) if goal_v else 0.0
                    with ui.row().classes("items-center gap-3 w-full mb-2"):
                        ui.label(lbl).classes("text-xs text-slate-500 dark:text-slate-400 w-32 shrink-0")
                        ui.linear_progress(value=pct).props(f"color={color} size=8px").classes("flex-1")
                        ui.label(f"{actual}/{goal_v}").classes("text-[11px] text-slate-400 w-12 text-right shrink-0 tabular-nums")

            # Détails activités
            with ui.element("div").classes("grid grid-cols-2 sm:grid-cols-4 gap-3 w-full"):
                for icon_n, lbl, val, color in [
                    ("menu_book",      "Lectures",          stats["lecture_count"],    "blue"),
                    ("auto_stories",   "Révisions",         stats["revision_count"],   "indigo"),
                    ("quiz",           "QCM",               stats["qcm_count"],        "purple"),
                    ("style",          "Anki",              stats["anki_count"],       "teal"),
                    ("report_problem", "Lacunes ajoutées",  stats["lacunes_added"],    "red"),
                    ("check_circle",   "Lacunes résolues",  stats["lacunes_resolved"], "green"),
                ]:
                    with ui.element("div").classes(
                        f"flex items-center gap-2 p-3 rounded-xl "
                        f"bg-{color}-50 dark:bg-{color}-900/10 "
                        f"border border-{color}-100 dark:border-{color}-800"
                    ):
                        ui.icon(icon_n, size="sm").classes(f"text-{color}-500 shrink-0")
                        with ui.column().classes("gap-0"):
                            ui.label(str(val)).classes(f"text-lg font-bold text-{color}-700 dark:text-{color}-300 tabular-nums")
                            ui.label(lbl).classes(f"text-[11px] text-{color}-500 dark:text-{color}-400")

    btn_prev.on_click(lambda: _render_sem(state["offset"] - 1))
    btn_cur.on_click(lambda: _render_sem(0))
    _render_sem(0)


# ── Page principale ───────────────────────────────────────────────────────────

def stats_page() -> None:
    with frame("Ma Progression"):
        state = SimpleNamespace(days=7)

        with ui.element("div").classes("synapse-hero w-full mb-4"):
            with ui.column().classes("gap-0.5"):
                ui.label("Ma Progression").classes(
                    "text-2xl font-extrabold text-slate-900 dark:text-slate-50 tracking-tight"
                )
                ui.label("Historique d'apprentissage · tendances · objectifs").classes(
                    "text-sm text-slate-500 dark:text-slate-400 mt-0.5"
                )

        snapshots = _get_all_mastery_snapshots()
        kpi_container = ui.element("div").classes(
            "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full mb-4"
        )
        _render_kpi_row(kpi_container, _compute_kpis(state.days, snapshots))

        mastery_container = ui.element("div").classes("w-full mb-4")
        _render_mastery_distribution(mastery_container, snapshots)

        with ui.tabs().classes("w-full mb-4").props("dense") as tabs:
            tab_activite = ui.tab("Activité",   icon="feed")
            tab_fragiles = ui.tab("À retravailler", icon="warning_amber")
            tab_semaine  = ui.tab("Objectifs",      icon="calendar_today")

        with ui.tab_panels(tabs, value=tab_activite).classes("w-full"):

            # ── Onglet Activité ───────────────────────────────────────────────
            with ui.tab_panel(tab_activite):
                period_row = ui.row().classes("gap-1 items-center mb-4")
                content    = ui.column().classes("w-full gap-5")

                def render():
                    days = state.days
                    try:
                        sessions = list(local_store.get_recent_study_sessions(limit=60))
                        wps      = list(local_store.get_unresolved_weak_points(limit=60))
                    except Exception as exc:
                        logger.error(f"stats render: {exc}")
                        content.clear()
                        with content:
                            ui.label(f"Erreur : {exc}").classes("text-red-400 text-sm")
                        return

                    content.clear()
                    with content:
                        with ui.element("div").classes("synapse-panel w-full p-5"):
                            ui.label("Activité").classes(
                                "text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-1"
                            )
                            _render_timeline(sessions, wps, render)

                def set_period(d: int):
                    state.days = d
                    _rebuild_period_row()
                    _render_kpi_row(kpi_container, _compute_kpis(state.days, snapshots))
                    render()

                def _rebuild_period_row():
                    period_row.clear()
                    with period_row:
                        for lbl, dv in [("7j", 7), ("30j", 30), ("Tout", 0)]:
                            ui.button(lbl, on_click=lambda d=dv: set_period(d)).props(
                                "unelevated color=primary rounded size=sm"
                                if dv == state.days else
                                "outline color=grey rounded size=sm"
                            )

                _rebuild_period_row()
                render()

            # ── Onglet Fragiles ───────────────────────────────────────────────
            with ui.tab_panel(tab_fragiles):
                frag_content = ui.column().classes("w-full gap-4")

                def render_fragiles():
                    fragile = _get_fragile_courses()
                    frag_content.clear()
                    with frag_content:
                        if fragile:
                            _render_fragile_banner(fragile, render_fragiles)
                        else:
                            with ui.column().classes("w-full items-center py-12 gap-3"):
                                ui.icon("check_circle", size="xl").classes("text-green-300 dark:text-green-700")
                                ui.label("Aucun cours fragile — beau travail !").classes(
                                    "text-sm text-slate-400 text-center"
                                )

                ui.timer(0.05, render_fragiles, once=True)

            # ── Onglet Semaine ────────────────────────────────────────────────
            with ui.tab_panel(tab_semaine):
                _render_semaine_tab()
