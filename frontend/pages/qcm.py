"""
qcm.py — Page QCM v2 (Analytique)
-----------------------------------
Layout :
  • 3 KPI cards : Moyenne · Taux réussite · Cours à retravailler
  • Graphique évolution des dernières sessions
  • Liste cours (1 ligne/cours, triée ratés en premier, extension sur clic)
  • Filtres : période · plateforme · ratés seulement
"""
from __future__ import annotations

import json
import datetime
from types import SimpleNamespace
from nicegui import ui
from loguru import logger

from frontend.theme import frame
from backend.core.reviews import local_store
from backend.core.qcm.service import (
    parse_score, score_bg_classes, score_label,
    is_failed, suggested_severity,
    PLATFORM_COLORS, QCM_PASS_THRESHOLD, WARN_THRESHOLD,
)
from backend.core.qcm.items_mapping import college_full, item_college_abbr
from backend.state.store import data_store


# Sprint 1 — couleurs par type d'erreur (cohérent avec la palette Synapse)
ERROR_TYPE_COLORS: dict[str, str] = {
    "connaissance":  "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
    "raisonnement":  "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
    "inattention":   "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    "stratégie EDN": "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
}
_ET_FALLBACK = "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300"


class CollegeWrapper:
    def __init__(self, name: str):
        self.id = f"college_{name}"
        self.title = f"{name} (Matière complète)"
        self.item_number = ""


# ── Agrégation par cours ──────────────────────────────────────────────────────

def _compute_groups(rows: list) -> list[dict]:
    groups: dict[str, dict] = {}
    for r in rows:
        key = r["course_id"] or f"__nc__{r['id']}"
        if key not in groups:
            groups[key] = {
                "key":           key,
                "course_id":     r["course_id"] or "",
                "course_title":  r["course_title"] or "Cours non renseigné",
                "item_number":   r["item_number"] or "",
                "sessions":      [],
                "platforms":     set(),
            }
        groups[key]["sessions"].append(r)
        if r["platform"]:
            groups[key]["platforms"].add(r["platform"])

    result = []
    for g in groups.values():
        sessions = g["sessions"]
        scores   = [s["score_percent"] for s in sessions if s["score_percent"] is not None]

        g["avg_score"]     = round(sum(scores) / len(scores), 1) if scores else None
        g["last_score"]    = scores[0] if scores else None
        g["prev_score"]    = scores[1] if len(scores) > 1 else None
        g["session_count"] = len(sessions)
        g["failed_count"]  = sum(1 for s in scores if s < QCM_PASS_THRESHOLD)
        g["platforms"]     = sorted(g["platforms"])

        if g["last_score"] is not None and g["prev_score"] is not None:
            diff = g["last_score"] - g["prev_score"]
            if diff > 2:
                g["trend"], g["trend_color"] = "↑", "text-green-500"
            elif diff < -2:
                g["trend"], g["trend_color"] = "↓", "text-red-500"
            else:
                g["trend"], g["trend_color"] = "→", "text-slate-400"
        else:
            g["trend"], g["trend_color"] = None, ""

        result.append(g)

    # Ratés en premier, puis score croissant
    result.sort(key=lambda g: (
        0 if (g["avg_score"] is not None and g["avg_score"] < QCM_PASS_THRESHOLD) else 1,
        g["avg_score"] if g["avg_score"] is not None else 999,
    ))
    return result


# ── KPI Cards ─────────────────────────────────────────────────────────────────

def _render_kpi(container, rows: list, groups: list) -> None:
    container.clear()

    scores    = [r["score_percent"] for r in rows if r["score_percent"] is not None]
    total     = len(rows)
    avg       = round(sum(scores) / len(scores), 1) if scores else None
    passed    = sum(1 for s in scores if s >= QCM_PASS_THRESHOLD)
    pass_rate = round(passed / len(scores) * 100) if scores else None
    to_review = sum(
        1 for g in groups
        if g["last_score"] is not None and g["last_score"] < QCM_PASS_THRESHOLD
    )

    CARD = (
        "rounded-2xl border border-slate-100 dark:border-slate-800 "
        "bg-white dark:bg-slate-900 shadow-sm p-5 flex flex-col gap-1.5"
    )

    def _kpi(icon_name, label, value_txt, value_color, sub_txt):
        with ui.element("div").classes(CARD):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon_name, size="sm").classes("text-slate-300")
                ui.label(label).classes("text-xs text-slate-400 font-medium")
            ui.label(value_txt).classes(
                f"text-3xl font-extrabold tabular-nums leading-none {value_color}"
            )
            ui.label(sub_txt).classes("text-xs text-slate-400")

    with container:
        # Moyenne
        avg_color = (
            "text-green-600 dark:text-green-400" if avg and avg >= QCM_PASS_THRESHOLD
            else "text-red-500 dark:text-red-400" if avg
            else "text-slate-400"
        )
        _kpi("percent", "Moyenne QCM",
             f"{avg}%" if avg is not None else "—",
             avg_color,
             f"{total} session{'s' if total != 1 else ''} enregistrée{'s' if total != 1 else ''}")

        # Taux réussite
        pr_color = (
            "text-green-600 dark:text-green-400" if pass_rate and pass_rate >= 70
            else "text-red-500 dark:text-red-400" if pass_rate is not None
            else "text-slate-400"
        )
        _kpi("thumb_up", "Taux de réussite",
             f"{pass_rate}%" if pass_rate is not None else "—",
             pr_color,
             f"{passed} / {len(scores)} au-dessus de 70%")

        # À retravailler
        rev_color = (
            "text-red-500 dark:text-red-400" if to_review > 0
            else "text-green-500 dark:text-green-400"
        )
        _kpi("warning_amber", "Cours à retravailler",
             str(to_review) if rows else "—",
             rev_color,
             "dernier score < 70%" if to_review > 0 else "Tout est bon ✓")


# ── Graphique évolution ───────────────────────────────────────────────────────

def _render_evolution_chart(container, rows: list) -> None:
    container.clear()

    scored = [r for r in rows if r["score_percent"] is not None][:25]
    scored = list(reversed(scored))  # ordre chronologique
    if len(scored) < 2:
        return

    def _fmt_date(s: str) -> str:
        try:
            d = datetime.date.fromisoformat(s)
            return f"{d.day:02d}/{d.month:02d}"
        except Exception:
            return s[:5] if s else "?"

    dates = [_fmt_date(r["session_date"] or "") for r in scored]
    data_points = [
        {
            "value": r["score_percent"],
            "itemStyle": {
                "color": (
                    "#22c55e" if r["score_percent"] >= QCM_PASS_THRESHOLD
                    else "#f97316" if r["score_percent"] >= WARN_THRESHOLD
                    else "#ef4444"
                )
            },
        }
        for r in scored
    ]

    with container:
        with ui.element("div").classes(
            "w-full rounded-2xl border border-slate-100 dark:border-slate-800 "
            "bg-white dark:bg-slate-900 shadow-sm p-4"
        ):
            with ui.row().classes("items-center gap-2 mb-3"):
                ui.icon("show_chart", size="sm").classes("text-indigo-400")
                ui.label("Évolution des scores").classes(
                    "text-xs font-bold uppercase tracking-widest text-slate-400 flex-1"
                )
                with ui.row().classes("gap-3 text-[11px] text-slate-400"):
                    for col, lbl in [("#22c55e","≥70%"),("#f97316","60-70%"),("#ef4444","<60%")]:
                        with ui.row().classes("items-center gap-1"):
                            ui.element("div").classes("w-2 h-2 rounded-full").style(
                                f"background:{col}"
                            )
                            ui.label(lbl)

            ui.echart({
                "animation": False,
                "tooltip": {"trigger": "axis", "formatter": "{b} : {c}%"},
                "grid": {
                    "left": "3%", "right": "4%",
                    "top": "8%", "bottom": "5%",
                    "containLabel": True,
                },
                "xAxis": {
                    "type": "category",
                    "data": dates,
                    "axisLabel": {"fontSize": 10, "color": "#94a3b8"},
                    "axisLine": {"lineStyle": {"color": "#e2e8f0"}},
                    "axisTick": {"show": False},
                },
                "yAxis": {
                    "type": "value",
                    "min": 0, "max": 100,
                    "axisLabel": {"formatter": "{value}%", "fontSize": 10, "color": "#94a3b8"},
                    "splitLine": {"lineStyle": {"color": "#f1f5f9", "type": "dashed"}},
                },
                "series": [{
                    "type": "line",
                    "data": data_points,
                    "smooth": 0.3,
                    "lineStyle": {"color": "#6366f1", "width": 2},
                    "symbol": "circle",
                    "symbolSize": 8,
                    "areaStyle": {
                        "color": {
                            "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                            "colorStops": [
                                {"offset": 0, "color": "rgba(99,102,241,0.12)"},
                                {"offset": 1, "color": "rgba(99,102,241,0)"},
                            ],
                        }
                    },
                    "markLine": {
                        "symbol": "none",
                        "lineStyle": {"color": "#ef4444", "type": "dashed", "width": 1.5},
                        "label": {
                            "formatter": "70%",
                            "position": "insideEndTop",
                            "fontSize": 10,
                            "color": "#ef4444",
                        },
                        "data": [{"yAxis": QCM_PASS_THRESHOLD}],
                    },
                }],
            }).classes("w-full h-44")


# ── Sprint 1 : Distribution des types d'erreur ────────────────────────────────

def _render_error_distribution(container, rows: list) -> None:
    """Carte récapitulative des types d'erreur sur les sessions filtrées."""
    container.clear()

    counts: dict[str, int] = {}
    annotated = 0
    for r in rows:
        try:
            et_list: list = json.loads(r["error_types"] or "[]")
        except Exception:
            et_list = []
        if et_list:
            annotated += 1
            for et in et_list:
                counts[et] = counts.get(et, 0) + 1

    if not counts:
        return  # Aucune donnée (EDN Pro) → carte invisible

    total = sum(counts.values())
    with container:
        with ui.element("div").classes(
            "w-full rounded-2xl border border-slate-100 dark:border-slate-800 "
            "bg-white dark:bg-slate-900 shadow-sm px-4 py-3"
        ):
            with ui.row().classes("items-center gap-3 flex-wrap"):
                with ui.row().classes("items-center gap-1.5 shrink-0"):
                    ui.icon("analytics", size="xs").classes("text-slate-300")
                    ui.label("Types d'erreur").classes(
                        "text-xs font-bold uppercase tracking-widest text-slate-400"
                    )
                for _et, _cnt in sorted(counts.items(), key=lambda x: -x[1]):
                    _pct = round(_cnt / total * 100)
                    _col = ERROR_TYPE_COLORS.get(_et, _ET_FALLBACK)
                    with ui.element("div").classes(
                        f"flex items-center gap-1.5 px-2.5 py-1 rounded-full {_col}"
                    ).tooltip(f"{_cnt} occurrence{'s' if _cnt > 1 else ''}"):
                        ui.label(_et).classes("text-[11px] font-semibold")
                        ui.label(f"· {_pct}%").classes(
                            "text-[11px] font-bold tabular-nums opacity-80"
                        )
                ui.element("div").classes("flex-1")
                ui.label(f"{annotated}/{len(rows)} sess. analysées").classes(
                    "text-[10px] text-slate-300 shrink-0"
                )


# ── Sprint 3 : Stats par item EDN groupées par collège ───────────────────────

_COL_TEMPLATE = "80px minmax(0,1fr) 90px 80px 80px 52px 24px 36px"
_ITEM_COL_HEADERS = [
    ("ITEM",     False, None, None),
    ("COURS",    False, None, None),
    ("MOY.",     True,  "Moyenne", "Score moyen de toutes les sessions sur cet item.\n🟢 ≥ 70%  🟡 60–70%  🔴 < 60%"),
    ("SESSIONS", True,  "Sessions QCM", "Nombre total de sessions réalisées sur cet item,\ntoutes plateformes confondues."),
    ("RÉUSSITE", True,  "Taux de réussite", "Proportion de sessions avec un score ≥ 70%\n(seuil de validation EDN)."),
    ("TEND.",    True,  "Tendance", "Évolution entre les 2 dernières sessions :\n↑  progression (écart > +2%)\n→  stable (écart ≤ 2%)\n↓  régression (écart < -2%)"),
    ("",         True,  None, None),
    ("",         True,  None, None),
]


def _build_item_college_map() -> dict[str, str]:
    """item_number (normalisé) → collège, depuis le mapping statique EDN uniquement."""
    from backend.core.qcm.items_mapping import all_items, college_full
    mapping: dict[str, str] = {}
    for entry in all_items():
        key = str(entry["item"])
        col = college_full(entry.get("college", ""))
        if key and col:
            mapping[key] = col
    return mapping


def _compute_item_stats_from_rows(rows: list) -> list[dict]:
    """Agrège les stats par item EDN depuis les sessions déjà filtrées.
    Les sessions college-level (pas d'item_number, course_id='college_X') sont
    regroupées sous une entrée synthétique '__college__X'.
    """
    items_data: dict[str, dict] = {}
    for r in rows:
        itn = (r["item_number"] or "").strip()
        if r["score_percent"] is None:
            continue
        if not itn:
            # Session college-level : utilise course_id ou course_title comme clé
            cid = (r.get("course_id") or "").strip()
            col_name = ""
            if cid.startswith("college_"):
                col_name = cid[len("college_"):]
            elif (r.get("course_title") or "").strip():
                col_name = (r["course_title"] or "").strip()
            if not col_name:
                continue
            key = f"__college__{col_name}"
            if key not in items_data:
                items_data[key] = {
                    "item_number": "",
                    "course_title": col_name,
                    "_college": col_name,
                    "dated_scores": [],
                }
            items_data[key]["dated_scores"].append(
                (r["session_date"] or "", r["score_percent"])
            )
            continue
        if itn not in items_data:
            items_data[itn] = {
                "item_number": itn,
                "course_title": r["course_title"] or "—",
                "dated_scores": [],
            }
        elif not items_data[itn]["course_title"] or items_data[itn]["course_title"] == "—":
            items_data[itn]["course_title"] = r["course_title"] or "—"
        items_data[itn]["dated_scores"].append(
            (r["session_date"] or "", r["score_percent"])
        )

    # has_recurring_gap / has_pending_proposal sont indépendants des filtres — on les lit en DB
    db_stats = {s["item_number"]: s for s in local_store.get_item_stats(limit=300)}

    result: list[dict] = []
    for itn, d in items_data.items():
        dated = sorted(d["dated_scores"], key=lambda x: x[0], reverse=True)
        scores = [s for _, s in dated]

        avg = round(sum(scores) / len(scores), 1) if scores else None
        pass_count = sum(1 for s in scores if s >= QCM_PASS_THRESHOLD)
        fail_count = len(scores) - pass_count

        trend = trend_color = None
        if len(scores) >= 2:
            diff = scores[0] - scores[1]
            if diff > 2:
                trend, trend_color = "↑", "text-green-500"
            elif diff < -2:
                trend, trend_color = "↓", "text-red-500"
            else:
                trend, trend_color = "→", "text-slate-400"

        db = db_stats.get(itn, {})
        result.append({
            "item_number":          itn,
            "course_title":         d["course_title"],
            "session_count":        len(scores),
            "avg_score":            avg,
            "pass_count":           pass_count,
            "fail_count":           fail_count,
            "last_date":            dated[0][0] if dated else "",
            "trend":                trend,
            "trend_color":          trend_color or "text-slate-400",
            "has_recurring_gap":    db.get("has_recurring_gap", False),
            "has_pending_proposal": db.get("has_pending_proposal", False),
        })

    result.sort(key=lambda x: x["avg_score"] if x["avg_score"] is not None else 999)
    return result


def _open_item_wizard(item_number: str, course_title: str, course_id: str, refresh_fn) -> None:
    """Ouvre le wizard pour les sessions ratées d'un item donné."""
    all_rows = local_store.get_qcm_sessions_all(limit=500)
    failed = [
        {
            "session_id":   r["id"],
            "course_id":    r["course_id"] or course_id,
            "course_title": r["course_title"] or course_title,
            "item_number":  item_number,
            "weak_points":  [],
            "score_percent": r["score_percent"],
        }
        for r in all_rows
        if (r["item_number"] or "").strip() == item_number.strip()
        and r["score_percent"] is not None
        and r["score_percent"] < QCM_PASS_THRESHOLD
    ]
    if not failed:
        ui.notify("Aucune session ratée à documenter pour cet item.", type="info", timeout=3000)
        return
    _open_session_wizard(failed, refresh_fn)


def _render_item_stat_cells(s: dict, row_idx: int = 0, is_last: bool = False, refresh_fn=None) -> None:
    """Rend 8 cellules directes dans le grid parent (alignement garanti)."""
    avg      = s["avg_score"]
    avg_cls  = score_bg_classes(avg)
    pass_c   = s["pass_count"]
    fail_c   = s["fail_count"]
    total_c  = pass_c + fail_c
    pass_pct = round(pass_c / total_c * 100) if total_c else None

    pct_col = (
        "text-green-600 dark:text-green-400" if pass_pct is not None and pass_pct >= 70
        else "text-amber-600 dark:text-amber-400" if pass_pct is not None and pass_pct >= 60
        else "text-red-500 dark:text-red-400"
    )

    def _confirm_delete(itn: str) -> None:
        with ui.dialog() as dlg:
            with ui.card().classes(
                "rounded-2xl p-5 bg-white dark:bg-slate-900 shadow-xl flex flex-col gap-3"
            ).style("min-width:320px"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("delete_forever", size="sm").classes("text-red-500")
                    ui.label(f"Supprimer Item {itn} ?").classes(
                        "font-bold text-slate-800 dark:text-slate-100 text-sm"
                    )
                ui.label(
                    f"Toutes les sessions QCM de l'Item {itn} seront supprimées définitivement."
                ).classes("text-xs text-slate-500 leading-snug")
                with ui.row().classes("gap-2 justify-end"):
                    ui.button("Annuler", on_click=dlg.close).props("flat color=grey-8 dense")
                    def _do_delete(_itn=itn):
                        n = local_store.delete_qcm_sessions_for_item(_itn)
                        dlg.close()
                        ui.notify(
                            f"{n} session(s) supprimée(s) pour Item {_itn}",
                            type="info", icon="delete",
                        )
                        if refresh_fn:
                            refresh_fn()
                    ui.button(
                        "Supprimer", icon="delete_forever", on_click=_do_delete
                    ).props("unelevated color=red rounded dense")
        dlg.open()

    sep  = "border-b border-slate-100 dark:border-slate-700/50" if not is_last else ""
    base = f"flex items-center {sep} py-2.5"

    # Cellule 1 : ITEM
    with ui.element("div").classes(base):
        if s.get("item_number"):
            ui.label(f"ITEM {s['item_number']}").classes(
                "text-[11px] font-bold text-indigo-600 dark:text-indigo-400 tabular-nums "
                "cursor-pointer hover:underline whitespace-nowrap"
            ).on("click", lambda itn=s["item_number"]: ui.navigate.to(f"/lacunes?item={itn}"))
        else:
            ui.label("Matière").classes(
                "text-[11px] font-semibold text-violet-500 dark:text-violet-400 whitespace-nowrap"
            ).tooltip("Session matière entière (sans item spécifique)")

    # Cellule 2 : COURS — clic → wizard sessions ratées
    with ui.element("div").classes(f"{base} min-w-0 overflow-hidden"):
        if s.get("item_number"):
            def _on_course_click(
                _itn=s["item_number"], _title=s["course_title"], _cid=s.get("course_id", "")
            ):
                _open_item_wizard(_itn, _title, _cid, refresh_fn)
            ui.label(s["course_title"]).classes(
                "text-xs font-medium text-slate-700 dark:text-slate-200 truncate w-full "
                "cursor-pointer hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            ).tooltip(f"{s['course_title']} — cliquer pour documenter les sessions ratées").on(
                "click", _on_course_click
            )
        else:
            ui.label(s["course_title"]).classes(
                "text-xs font-medium text-violet-600 dark:text-violet-400 truncate w-full italic"
            ).tooltip("Session matière entière")

    # Cellule 3 : MOY.
    with ui.element("div").classes(f"{base} justify-center"):
        with ui.element("div").classes(
            f"px-2 py-0.5 rounded-lg {avg_cls} text-xs font-extrabold tabular-nums"
        ):
            ui.label(f"{avg}%" if avg is not None else "—")

    # Cellule 4 : SESSIONS
    with ui.element("div").classes(f"{base} justify-center"):
        ui.label(str(s["session_count"])).classes("text-xs text-slate-500 tabular-nums")

    # Cellule 5 : RÉUSSITE
    with ui.element("div").classes(f"{base} justify-center"):
        if pass_pct is not None:
            ui.label(f"{pass_pct}%").classes(f"text-[11px] font-bold {pct_col} tabular-nums")
        else:
            ui.label("—").classes("text-xs text-slate-300")

    # Cellule 6 : TEND.
    with ui.element("div").classes(f"{base} justify-center"):
        if s["trend"]:
            ui.label(s["trend"]).classes(f"text-sm font-bold {s['trend_color']}")
        else:
            ui.label("—").classes("text-xs text-slate-300")

    # Cellule 7 : icône lacune
    with ui.element("div").classes(f"{base} justify-center"):
        if s["has_recurring_gap"]:
            ui.icon("repeat", size="xs").classes("text-orange-500").tooltip(
                "Lacune récurrente détectée"
            )
        elif s["has_pending_proposal"]:
            ui.icon("pending", size="xs").classes("text-amber-400").tooltip(
                "Proposition de lacune en attente"
            )

    # Cellule 8 : supprimer
    with ui.element("div").classes(f"{base} justify-center"):
        if s.get("item_number"):
            ui.button(
                icon="delete_outline",
                on_click=lambda itn=s["item_number"]: _confirm_delete(itn),
            ).props("flat round dense size=xs color=grey-5").classes(
                "opacity-40 hover:opacity-100 transition-opacity"
            )
        else:
            # Entrée college-level : suppression par course_title
            def _del_college(ct=s["course_title"]):
                local_store.delete_qcm_sessions_for_college(ct)
                if refresh_fn:
                    refresh_fn()
            ui.button(
                icon="delete_outline",
                on_click=_del_college,
            ).props("flat round dense size=xs color=grey-5").classes(
                "opacity-40 hover:opacity-100 transition-opacity"
            )


def _render_college_group(college_name: str, items: list[dict], expanded: bool = False, refresh_fn=None) -> None:
    """Groupe dépliable par collège avec en-tête récapitulatif et table d'items."""
    all_pass  = sum(s["pass_count"] for s in items)
    all_total = sum(s["pass_count"] + s["fail_count"] for s in items)
    agg_pct   = round(all_pass / all_total * 100) if all_total else None
    has_gap   = any(s["has_recurring_gap"] for s in items)

    agg_col = (
        "text-green-600 dark:text-green-400" if agg_pct is not None and agg_pct >= 70
        else "text-amber-600 dark:text-amber-400" if agg_pct is not None and agg_pct >= 60
        else "text-red-500 dark:text-red-400" if agg_pct is not None
        else "text-slate-400"
    )

    with ui.expansion(value=expanded).classes(
        "w-full rounded-2xl shadow-sm overflow-hidden "
        "border border-slate-100 dark:border-slate-800 "
        "bg-white dark:bg-slate-900"
    ) as exp:
        with exp.add_slot("header"):
            with ui.row().classes(
                "items-center gap-3 px-4 py-3 w-full "
                "hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
            ):
                ui.label(college_name).classes(
                    "font-semibold text-sm text-slate-800 dark:text-slate-100 flex-1 truncate"
                )
                if has_gap:
                    ui.icon("repeat", size="xs").classes("text-orange-400 shrink-0").tooltip(
                        "Au moins un item a une lacune récurrente"
                    )
                ui.badge(
                    f"{len(items)} item{'s' if len(items) > 1 else ''}",
                    color="slate",
                ).classes("text-[11px] shrink-0")
                if agg_pct is not None:
                    ui.label(f"{agg_pct}%").classes(
                        f"text-sm font-bold tabular-nums shrink-0 {agg_col}"
                    ).tooltip("Taux de réussite agrégé du collège")

        # Grid unique : en-tête + données dans le même conteneur (alignement parfait garanti)
        with ui.element("div").style(
            f"display:grid;grid-template-columns:{_COL_TEMPLATE};column-gap:8px"
        ).classes("w-full px-4"):

            # Cellules d'en-tête
            for lbl, centered, tip_title, tip_body in _ITEM_COL_HEADERS:
                align = "justify-center" if centered else ""
                with ui.element("div").classes(
                    f"flex items-center {align} py-2 "
                    "bg-slate-50 dark:bg-slate-800/60 "
                    "border-t border-b border-slate-100 dark:border-slate-800"
                ):
                    if lbl:
                        cursor = " cursor-help" if tip_title else ""
                        lbl_el = ui.label(lbl).classes(
                            "text-[11px] font-bold uppercase tracking-wider "
                            f"text-slate-400 whitespace-nowrap{cursor}"
                        )
                        if tip_title:
                            lbl_el.tooltip(f"{tip_title} — {tip_body}")

            # Cellules de données (enfants directs du même grid → colonnes parfaitement alignées)
            for j, s in enumerate(items):
                _render_item_stat_cells(
                    s,
                    row_idx=j,
                    is_last=(j == len(items) - 1),
                    refresh_fn=refresh_fn,
                )


def _render_item_stats(container, rows: list, refresh_fn=None) -> None:
    container.clear()
    stats = _compute_item_stats_from_rows(rows)

    with container:
        if not stats:
            with ui.column().classes("w-full items-center py-12 gap-3 text-slate-300"):
                ui.icon("bar_chart", size="xl").classes("opacity-40")
                ui.label("Aucun item avec données de score pour ces filtres.").classes("text-sm")
            return

        item_college_map = _build_item_college_map()
        colleges_order   = data_store.get_colleges() if data_store.is_loaded else []

        def _norm_itn(itn: str) -> str:
            try:
                f = float(itn)
                return str(int(f)) if f.is_integer() else itn
            except (ValueError, TypeError):
                return itn

        def _group(stats_list: list[dict]) -> list[tuple[str, list[dict]]]:
            groups: dict[str, list[dict]] = {}
            for s in stats_list:
                if s.get("_college"):
                    # Entrée college-level (pas d'item_number) → groupe direct
                    college = s["_college"]
                else:
                    college = item_college_map.get(_norm_itn(s["item_number"]), "") or "Non classé"
                groups.setdefault(college, []).append(s)
            result: list[tuple[str, list[dict]]] = []
            seen: set[str] = set()
            for col in colleges_order:
                if col in groups:
                    result.append((col, groups[col]))
                    seen.add(col)
            for col in sorted(groups.keys()):
                if col not in seen:
                    result.append((col, groups[col]))
            return result

        all_groups = _group(stats)

        with ui.element("div").classes("w-full flex flex-col gap-3"):
            with ui.row().classes("items-center gap-3"):
                stats_search = ui.input(
                    placeholder="Filtrer par numéro ou titre…"
                ).props("outlined dense clearable").classes("flex-1 max-w-xs")
                ui.label(
                    f"{len(stats)} item{'s' if len(stats) > 1 else ''} · "
                    f"{len(all_groups)} collège{'s' if len(all_groups) > 1 else ''}"
                ).classes("text-xs text-slate-400")

            groups_container = ui.element("div").classes("w-full flex flex-col gap-2")

            def _render_groups(q: str = "") -> None:
                groups_container.clear()
                ql = q.lower().strip()
                with groups_container:
                    any_shown = False
                    for college_name, college_stats in all_groups:
                        if ql:
                            matched = [
                                s for s in college_stats
                                if ql in s["item_number"].lower()
                                or ql in s["course_title"].lower()
                            ]
                            if not matched:
                                continue
                            _render_college_group(college_name, matched, expanded=True, refresh_fn=refresh_fn)
                        else:
                            _render_college_group(college_name, college_stats, expanded=False, refresh_fn=refresh_fn)
                        any_shown = True
                    if not any_shown:
                        with ui.element("div").classes("px-4 py-8 text-center"):
                            ui.label("Aucun résultat.").classes("text-sm text-slate-400")

            _render_groups()
            stats_search.on_value_change(lambda e: _render_groups(e.value or ""))


# ── Page principale ───────────────────────────────────────────────────────────

def qcm_page():
    with frame("QCM"):
        try:
            with ui.column().classes("w-full gap-5 max-w-5xl mx-auto"):

                # ── Header ────────────────────────────────────────────────────
                with ui.row().classes("w-full items-end justify-between flex-wrap gap-3"):
                    with ui.column().classes("gap-0"):
                        ui.label("QCM").classes(
                            "text-2xl font-extrabold text-slate-900 dark:text-slate-50 tracking-tight"
                        )
                        ui.label("Analytique · Évolution · Cours à retravailler").classes(
                            "text-sm text-slate-400 mt-0.5"
                        )
                    with ui.row().classes("gap-2 shrink-0"):
                        ui.button(
                            "+ Ajouter",
                            icon="add",
                            on_click=lambda: _open_add_dialog(_rebuild),
                        ).props("unelevated color=indigo rounded").classes(
                            "font-semibold shrink-0"
                        )

                # ── Filtres ───────────────────────────────────────────────────
                _filter = {"platform": None, "days": 0, "failed_only": False}
                filter_row = ui.row().classes("items-center gap-2 flex-wrap")

                # ── KPI ───────────────────────────────────────────────────────
                kpi_container = ui.element("div").classes(
                    "grid grid-cols-1 md:grid-cols-3 gap-4 w-full"
                )

                # ── Distribution types d'erreur (Sprint 1) ────────────────────
                dist_container = ui.element("div").classes("w-full")

                # ── Graphique évolution ───────────────────────────────────────
                chart_container = ui.element("div").classes("w-full")

                # ── Stats par item groupées par collège ────────────────────────
                item_stats_container = ui.element("div").classes("w-full")

                # ── Rebuild ───────────────────────────────────────────────────

                def _rebuild():
                    rows = local_store.get_qcm_sessions_all(
                        limit=300, platform=_filter["platform"]
                    )
                    # Filtre période
                    if _filter["days"]:
                        cutoff = (
                            datetime.date.today()
                            - datetime.timedelta(days=_filter["days"])
                        ).isoformat()
                        rows = [r for r in rows if (r["session_date"] or "") >= cutoff]
                    # Filtre ratés
                    if _filter["failed_only"]:
                        rows = [r for r in rows if is_failed(r["score_percent"])]

                    groups = _compute_groups(rows)

                    _render_kpi(kpi_container, rows, groups)
                    _render_error_distribution(dist_container, rows)
                    _render_evolution_chart(chart_container, rows)
                    _render_item_stats(item_stats_container, rows, refresh_fn=_rebuild)

                def _rebuild_filter_row():
                    filter_row.clear()
                    with filter_row:
                        # Période
                        ui.label("Période :").classes("text-[11px] text-slate-400 font-medium")
                        for lbl, dv in [("Tout", 0), ("30j", 30), ("7j", 7)]:
                            active = _filter["days"] == dv
                            def _set_days(d=dv):
                                _filter["days"] = d
                                _rebuild_filter_row()
                                _rebuild()
                            ui.button(lbl, on_click=_set_days).props(
                                f"{'unelevated color=slate' if active else 'outline color=grey'}"
                                " dense rounded size=xs"
                            )

                        ui.element("div").classes(
                            "w-px h-4 bg-slate-200 dark:bg-slate-700 self-center mx-1"
                        )

                        # Plateforme
                        ui.label("Plateforme :").classes(
                            "text-[11px] text-slate-400 font-medium"
                        )
                        for lbl, pv in [
                            ("Tous", None), ("EDNpro", "EDNpro"),
                            ("Hypocampus", "Hypocampus"),
                            ("ChatGPT", "ChatGPT"), ("Gemini", "Gemini"),
                        ]:
                            active = _filter["platform"] == pv
                            def _set_plat(p=pv):
                                _filter["platform"] = p
                                _rebuild_filter_row()
                                _rebuild()
                            ui.button(lbl, on_click=_set_plat).props(
                                f"{'unelevated' if active else 'outline'} color=indigo"
                                " dense rounded size=xs"
                            )

                        ui.element("div").classes(
                            "w-px h-4 bg-slate-200 dark:bg-slate-700 self-center mx-1"
                        )

                        # Ratés
                        active = _filter["failed_only"]
                        def _toggle_failed():
                            _filter["failed_only"] = not _filter["failed_only"]
                            _rebuild_filter_row()
                            _rebuild()
                        ui.button(
                            "Ratés seulement",
                            icon="warning",
                            on_click=_toggle_failed,
                        ).props(
                            f"{'unelevated' if active else 'outline'} color=red "
                            "dense rounded size=xs"
                        )

                _rebuild_filter_row()
                _rebuild()

                # ── Notifications import watcher ──────────────────────────────
        except Exception as e:
            logger.exception("QCM PAGE ERROR")
            ui.label(f"Erreur : {e}").classes("text-red-500 font-bold")


# ── Dialog : Ajouter résultat QCM ─────────────────────────────────────────────

def _open_add_dialog(refresh_fn):
    today_str = datetime.date.today().isoformat()

    state = SimpleNamespace(
        platform="EDNpro",
        course_id="", course_title="", item_number="", college="",
        courses=[],
        session_type="QCM",
        score_raw="", score_percent=None,
        session_date=today_str,
        error_types=[], difficulty=None, comments="",
    )

    def _derive_college(item_number: str) -> str:
        if not item_number:
            return ""
        return college_full(item_college_abbr(item_number)) or ""

    def _open_course_picker(on_select):
        with ui.dialog() as picker:
            with ui.card().classes(
                "rounded-2xl p-0 overflow-hidden bg-white dark:bg-slate-900 shadow-xl"
            ).style("width:460px;max-width:90vw;max-height:72vh;display:flex;flex-direction:column"):

                with ui.element("div").classes(
                    "px-4 pt-4 pb-3 border-b border-slate-100 dark:border-slate-800 shrink-0"
                ):
                    search_inp = ui.input(
                        placeholder="Rechercher un cours, item ou matière…",
                    ).props("autofocus outlined dense clearable").classes("w-full")

                with ui.scroll_area().classes("w-full").style("height:300px;max-height:50vh"):
                    r_col = ui.column().classes("w-full p-2 gap-0.5")
                    with r_col:
                        ui.label("Tapez au moins 2 caractères…").classes(
                            "text-xs text-slate-400 italic px-3 py-2"
                        )

                def _do_search(q):
                    q = q or ""
                    r_col.clear()
                    try:
                        with r_col:
                            if len(q.strip()) < 2:
                                ui.label("Tapez au moins 2 caractères…").classes(
                                    "text-xs text-slate-400 italic px-3 py-2"
                                )
                                return
                            is_multi = state.session_type in ("DP", "KFP")
                            matched_colleges = []
                            if is_multi:
                                matched_colleges = [
                                    col for col in (data_store.get_colleges() or [])
                                    if col and q.lower() in str(col).lower()
                                ][:3]
                            matched_courses = []
                            for c in (data_store.cours or []):
                                t = str(getattr(c, "title", "") or "").lower()
                                i = str(getattr(c, "item_number", "") or "").lower()
                                if q.lower() in t or (i and q.lower() in i):
                                    matched_courses.append(c)
                                    if len(matched_courses) >= 10:
                                        break
                            if not matched_colleges and not matched_courses:
                                ui.label("Aucun résultat.").classes(
                                    "text-xs text-slate-400 italic px-3 py-2"
                                )
                                return
                            if matched_colleges:
                                ui.label("MATIÈRES").classes(
                                    "text-[11px] font-bold tracking-widest text-slate-400 px-3 pt-2 pb-1"
                                )
                                for col_name in matched_colleges:
                                    cw = CollegeWrapper(col_name)
                                    def _pick_c(course=cw):
                                        on_select(course)
                                        picker.close()
                                    ui.button(f"📚 {col_name}", on_click=_pick_c).props(
                                        "flat no-caps align=left"
                                    ).classes(
                                        "w-full text-left text-sm font-semibold text-indigo-600 "
                                        "dark:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800 "
                                        "rounded-lg px-3 py-1"
                                    )
                            if matched_courses:
                                if matched_colleges:
                                    ui.label("COURS").classes(
                                        "text-[11px] font-bold tracking-widest text-slate-400 px-3 pt-2 pb-1"
                                    )
                                for c in matched_courses:
                                    c_title = getattr(c, "title", None) or "Sans titre"
                                    c_item  = getattr(c, "item_number", None) or ""
                                    itxt    = f"ITEM {c_item} — " if c_item else ""
                                    def _pick_c(course=c):
                                        on_select(course)
                                        picker.close()
                                    ui.button(
                                        f"📝 {itxt}{c_title}", on_click=_pick_c
                                    ).props("flat no-caps align=left").classes(
                                        "w-full text-left text-sm text-slate-800 dark:text-slate-100 "
                                        "hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg px-3 py-1"
                                    )
                    except Exception as e:
                        logger.exception(f"Erreur recherche: {e}")

                search_inp.on_value_change(lambda e: _do_search(e.value))
        picker.open()

    with ui.dialog().props("persistent maximized=false").style("align-items:center") as dialog:
        with ui.card().classes(
            "w-full max-w-2xl rounded-3xl p-0 overflow-hidden "
            "bg-white dark:bg-slate-900 shadow-2xl"
        ).style("width:680px;max-height:92vh;display:flex;flex-direction:column;min-width:0"):

            with ui.element("div").classes(
                "px-6 pt-5 pb-4 border-b border-slate-100 dark:border-slate-800 shrink-0"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Ajouter un résultat").classes(
                        "text-base font-bold text-slate-900 dark:text-slate-50"
                    )
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense size=sm color=grey-7"
                    )

            with ui.element("div").classes(
                "px-6 py-4 flex flex-col gap-4 flex-1 overflow-y-auto"
            ).style("overflow-x:hidden"):

                def _lbl(text):
                    ui.label(text).classes(
                        "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                    )

                # Plateforme + Type
                with ui.row().classes("gap-5 w-full"):
                    with ui.column().classes("gap-1.5 min-w-0"):
                        _lbl("Plateforme")
                        plat_container = ui.row().classes("gap-1.5 flex-wrap")
                        def _rebuild_plat():
                            plat_container.clear()
                            with plat_container:
                                for p in local_store.QCM_PLATFORMS:
                                    col = PLATFORM_COLORS.get(p, "indigo")
                                    active = p == state.platform
                                    def _click_p(pv=p):
                                        state.platform = pv
                                        _rebuild_plat()
                                    ui.button(p, on_click=_click_p).props(
                                        f"{'unelevated' if active else 'outline'} rounded size=sm color={col}"
                                    )
                        _rebuild_plat()

                    ui.element("div").classes(
                        "w-px bg-slate-100 dark:bg-slate-700 self-stretch mx-1"
                    )

                    with ui.column().classes("gap-1.5 flex-1 min-w-0"):
                        _lbl("Type")
                        type_container = ui.row().classes("gap-1.5 flex-wrap")
                        def _rebuild_type():
                            type_container.clear()
                            with type_container:
                                for t in local_store.QCM_SESSION_TYPES:
                                    active = t == state.session_type
                                    def _click_t(tv=t):
                                        state.session_type = tv
                                        _rebuild_type()
                                        _rebuild_course_section()
                                    ui.button(t, on_click=_click_t).props(
                                        f"{'unelevated' if active else 'outline'} rounded size=sm color=indigo"
                                    )
                        _rebuild_type()

                # Cours
                course_section = ui.column().classes("w-full gap-2")

                def _rebuild_course_section():
                    course_section.clear()
                    is_multi = state.session_type in ("DP", "KFP")
                    with course_section:
                        if is_multi:
                            _build_multi_course()
                        else:
                            _build_single_course()

                def _build_single_course():
                    _lbl("Cours associé (optionnel)")
                    info_row = ui.row().classes("items-center gap-2 min-h-[22px]")
                    with info_row:
                        if state.course_title:
                            txt = (f"ITEM {state.item_number} — " if state.item_number else "") + state.course_title
                            ui.label(txt).classes(
                                "text-xs font-semibold text-indigo-600 dark:text-indigo-400 flex-1"
                            ).style("overflow:hidden;text-overflow:ellipsis;white-space:nowrap")
                            def _clear():
                                state.course_id = state.course_title = state.item_number = state.college = ""
                                _rebuild_course_section()
                            ui.button(icon="close", on_click=_clear).props(
                                "flat round dense size=xs color=grey-7"
                            )
                        else:
                            ui.label("Aucun cours sélectionné").classes("text-xs text-slate-400 italic")

                    # Badge collège (auto-dérivé de l'item, ou sélectionné manuellement)
                    if state.college:
                        with ui.row().classes("items-center gap-1.5 mt-0.5"):
                            ui.icon("school", size="xs").classes("text-violet-400")
                            ui.label(state.college).classes(
                                "text-[11px] font-semibold text-violet-600 dark:text-violet-400"
                            )

                    def _on_select(course):
                        state.course_id    = course.id
                        state.course_title = course.title
                        state.item_number  = getattr(course, "item_number", "") or ""
                        # College : auto-dérivé depuis item_number, ou depuis le nom du collège
                        if state.item_number:
                            state.college = _derive_college(state.item_number)
                        elif course.id.startswith("college_"):
                            state.college = course.id.removeprefix("college_")
                        else:
                            state.college = ""
                        _rebuild_course_section()

                    with ui.row().classes("items-center gap-2 flex-wrap mt-0.5"):
                        ui.button(
                            "Choisir un cours…", icon="search",
                            on_click=lambda: _open_course_picker(_on_select),
                        ).props("outline dense rounded size=sm color=indigo").classes("text-xs")

                        # Chips collège rapides (si aucun cours sélectionné)
                        if not state.course_title:
                            all_colleges = sorted({
                                college_full(item_college_abbr(str(getattr(c, "item_number", "") or "")))
                                for c in (data_store.cours or [])
                                if getattr(c, "item_number", "")
                            } - {""})
                            college_container = ui.row().classes("gap-1 flex-wrap items-center")
                            with college_container:
                                for col in all_colleges:
                                    active = col == state.college
                                    def _pick_col(cv=col):
                                        state.college      = cv
                                        state.course_id    = f"college_{cv}"
                                        state.course_title = cv
                                        state.item_number  = ""
                                        _rebuild_course_section()
                                    ui.button(col, on_click=_pick_col).props(
                                        f"{'unelevated' if active else 'outline'} "
                                        "rounded size=xs color=violet dense"
                                    ).classes("text-[10px]")

                def _build_multi_course():
                    _lbl(f"Cours du {state.session_type}")
                    chips_box = ui.column().classes("w-full gap-1")

                    def _refresh_chips():
                        chips_box.clear()
                        with chips_box:
                            if not state.courses:
                                ui.label("Aucun cours ajouté").classes("text-xs text-slate-400 italic")
                            else:
                                for i, c in enumerate(state.courses):
                                    txt = (f"ITEM {c['item_number']} — " if c.get("item_number") else "") + c["title"]
                                    with ui.row().classes(
                                        "items-center gap-2 px-3 py-1.5 rounded-lg w-full "
                                        "bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800"
                                    ):
                                        ui.label(txt).classes(
                                            "text-xs font-medium text-indigo-700 dark:text-indigo-300 flex-1"
                                        ).style("overflow:hidden;text-overflow:ellipsis;white-space:nowrap")
                                        def _rm(idx=i):
                                            state.courses.pop(idx)
                                            _refresh_chips()
                                        ui.button(icon="close", on_click=_rm).props(
                                            "flat round dense size=xs color=grey-7"
                                        )

                    _refresh_chips()

                    def _add_course(course):
                        if not any(c["id"] == course.id for c in state.courses):
                            state.courses.append({
                                "id": course.id, "title": course.title,
                                "item_number": course.item_number or "",
                            })
                        _refresh_chips()

                    ui.button(
                        "+ Ajouter cours", icon="add",
                        on_click=lambda: _open_course_picker(_add_course),
                    ).props("outline dense rounded size=sm color=indigo").classes("self-start text-xs mt-0.5")

                _rebuild_course_section()

                # Score + Date
                with ui.row().classes("gap-4 w-full items-start"):
                    with ui.column().classes("gap-1 flex-1 min-w-0"):
                        _lbl("Score")
                        def _on_score(e):
                            raw = e.value or ""
                            pct, display = parse_score(raw)
                            state.score_raw     = display
                            state.score_percent = pct
                            if pct is not None:
                                score_feedback.set_text(f"→ {pct}%  {score_label(pct)}")
                                score_feedback.classes(replace="text-[11px] font-semibold " + (
                                    "text-green-600" if pct >= QCM_PASS_THRESHOLD
                                    else "text-amber-600" if pct >= 60
                                    else "text-red-600"
                                ))
                            else:
                                score_feedback.set_text("ex : 14/20 ou 70%")
                                score_feedback.classes(replace="text-[11px] text-slate-400")
                        ui.input(
                            placeholder="14/20  ou  70%", on_change=_on_score
                        ).props("outlined dense").classes("w-full")
                        score_feedback = ui.label("ex : 14/20 ou 70%").classes(
                            "text-[11px] text-slate-400"
                        )

                    with ui.column().classes("gap-1 flex-1 min-w-0"):
                        _lbl("Date")
                        with ui.input(
                            value=datetime.date.today().strftime("%d/%m/%Y"),
                            placeholder="JJ/MM/AAAA",
                        ).props("outlined dense mask='##/##/####'").classes("w-full") as date_field:
                            with date_field.add_slot("append"):
                                ui.icon("event").classes("cursor-pointer").on(
                                    "click", lambda: cal_menu.open()
                                )
                            with ui.menu().props("no-parent-event") as cal_menu:
                                with ui.date(mask="DD/MM/YYYY").props(
                                    "today-btn first-day-of-week=1"
                                ) as cal:
                                    cal.bind_value(date_field)
                                    def _on_date(e):
                                        try:
                                            d = datetime.datetime.strptime(e.value, "%d/%m/%Y").date()
                                            state.session_date = d.isoformat()
                                        except Exception:
                                            state.session_date = datetime.date.today().isoformat()
                                        cal_menu.close()
                                    cal.on_value_change(_on_date)

                # Erreurs + Difficulté
                with ui.row().classes("gap-5 w-full"):
                    with ui.column().classes("gap-1.5 flex-1 min-w-0"):
                        _lbl("Types d'erreur")
                        err_container = ui.row().classes("gap-1.5 flex-wrap")
                        def _rebuild_err():
                            err_container.clear()
                            with err_container:
                                for et in local_store.QCM_ERROR_TYPES:
                                    active = et in state.error_types
                                    def _click_e(ev=et):
                                        if ev in state.error_types:
                                            state.error_types.remove(ev)
                                        else:
                                            state.error_types.append(ev)
                                        _rebuild_err()
                                    ui.button(et, on_click=_click_e).props(
                                        f"{'unelevated' if active else 'outline'} rounded size=xs color=red"
                                    )
                        _rebuild_err()

                    with ui.column().classes("gap-1.5 shrink-0"):
                        _lbl("Difficulté")
                        diff_container = ui.row().classes("gap-1.5")
                        def _rebuild_diff():
                            diff_container.clear()
                            with diff_container:
                                for d_id, d_lbl, d_col in [
                                    ("facile","Facile","positive"),
                                    ("moyen","Moyen","warning"),
                                    ("difficile","Difficile","negative"),
                                ]:
                                    active = d_id == state.difficulty
                                    def _click_d(dv=d_id):
                                        state.difficulty = dv
                                        _rebuild_diff()
                                    ui.button(d_lbl, on_click=_click_d).props(
                                        f"{'unelevated' if active else 'outline'} rounded size=xs color={d_col}"
                                    )
                        _rebuild_diff()

                # Commentaires
                _lbl("Commentaires (optionnel)")
                ui.textarea(
                    placeholder="Erreurs récurrentes, pièges rencontrés…"
                ).classes("w-full").props("outlined dense autogrow rows=2").on_value_change(
                    lambda e: setattr(state, "comments", e.value or "")
                )

            # Footer
            with ui.element("div").classes(
                "px-6 py-4 bg-slate-50 dark:bg-slate-800/50 "
                "border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2 shrink-0"
            ):
                ui.button("Annuler", on_click=dialog.close).props("flat color=grey-8")

                def _submit():
                    if state.score_percent is None:
                        ui.notify("Score invalide — utilisez 14/20 ou 70%", type="warning")
                        return
                    is_multi = state.session_type in ("DP", "KFP")
                    courses_to_save = (
                        state.courses if is_multi and state.courses
                        else [{"id": state.course_id, "title": state.course_title,
                               "item_number": state.item_number}]
                    )
                    last_sid = None
                    for c in courses_to_save:
                        last_sid = local_store.add_qcm_session_full(
                            platform=state.platform,
                            session_date=state.session_date,
                            course_id=c.get("id", ""),
                            course_title=c.get("title", ""),
                            item_number=c.get("item_number", ""),
                            session_type=state.session_type,
                            score_raw=state.score_raw,
                            score_percent=state.score_percent,
                            difficulty=state.difficulty,
                            error_types=state.error_types,
                            comments=state.comments or None,
                        )
                    dialog.close()
                    pct = state.score_percent
                    n   = len(courses_to_save)
                    if is_failed(pct):
                        if is_multi and n > 1:
                            sev = suggested_severity(pct)
                            for c in courses_to_save:
                                if c.get("id"):
                                    local_store.add_weak_point_full(
                                        course_id=c["id"],
                                        detail=f"{state.session_type} raté — {state.score_raw}"
                                               + (f" ({state.platform})" if state.platform else ""),
                                        course_title=c.get("title",""),
                                        item_number=c.get("item_number",""),
                                        severity=sev, source_type="qcm",
                                        source_session_id=last_sid,
                                    )
                            ui.notify(
                                f"{n} sessions + {n} lacunes créées", type="warning", icon="report_problem"
                            )
                            refresh_fn()
                        else:
                            _propose_lacune(state, last_sid, refresh_fn)
                            ui.notify(f"Score {state.score_raw} enregistré (raté)", type="warning")
                    else:
                        ui.notify(
                            f"{n} session{'s' if n>1 else ''} enregistrée{'s' if n>1 else ''} — {state.score_raw} ✓",
                            type="positive",
                        )
                        primary_cid = state.course_id or (
                            courses_to_save[0].get("id","") if courses_to_save else ""
                        )
                        if pct >= QCM_PASS_THRESHOLD and primary_cid:
                            try:
                                lacunes = local_store.get_active_lacunes_for_course(primary_cid)
                            except Exception:
                                lacunes = []
                            if lacunes:
                                _propose_resolve_lacune(state, lacunes, refresh_fn)
                                return
                        refresh_fn()

                ui.button("Enregistrer ✓", on_click=_submit).props(
                    "unelevated color=indigo rounded"
                ).classes("px-5 font-semibold")

    dialog.open()


# ── Dialogs post-enregistrement ───────────────────────────────────────────────

def _propose_resolve_lacune(state, lacunes, refresh_fn):
    n = len(lacunes)
    selected = {lc["id"]: True for lc in lacunes}

    with ui.dialog().props("persistent") as dlg:
        with ui.card().classes(
            "rounded-2xl p-0 overflow-hidden bg-white dark:bg-slate-900 shadow-2xl"
        ).style("width:440px;max-width:90vw"):
            with ui.element("div").classes(
                "px-5 py-3.5 bg-green-50 dark:bg-green-900/20 "
                "border-b border-green-100 dark:border-green-800"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check_circle", size="sm").classes("text-green-500 shrink-0")
                    ui.label("QCM réussi · Lacunes à résoudre ?").classes(
                        "font-bold text-green-800 dark:text-green-300 text-sm"
                    )

            with ui.element("div").classes("px-5 py-4 flex flex-col gap-3"):
                ui.label(
                    f"Vous avez {n} lacune{'s' if n>1 else ''} active{'s' if n>1 else ''} sur ce cours. "
                    "Souhaitez-vous les marquer comme résolues ?"
                ).classes("text-sm text-slate-600 dark:text-slate-300 leading-snug")
                sev_color = {1:"slate",2:"blue",3:"amber",4:"orange",5:"red"}
                for lc in lacunes:
                    detail = (lc["detail"] or "—")
                    sev    = lc["severity"] or 2
                    lid    = lc["id"]
                    with ui.row().classes("items-start gap-2 w-full"):
                        cb = ui.checkbox(value=True)
                        cb.on_value_change(lambda e, _lid=lid: selected.update({_lid: e.value}))
                        with ui.column().classes("gap-0.5 min-w-0 flex-1"):
                            ui.label(detail[:80] + ("…" if len(detail)>80 else "")).classes(
                                "text-xs text-slate-700 dark:text-slate-200 leading-snug"
                            )
                            ui.badge(f"Sévérité {sev}", color=sev_color.get(sev,"slate")).classes(
                                "text-[11px] px-1 py-0.5"
                            )

            with ui.element("div").classes("px-5 pb-4 flex justify-end gap-2"):
                def _skip():
                    dlg.close(); refresh_fn()
                def _resolve():
                    to_resolve = [lid for lid, checked in selected.items() if checked]
                    for lid in to_resolve:
                        local_store.update_weak_point_status(lid, "résolue")
                    dlg.close()
                    if to_resolve:
                        pl = "s" if len(to_resolve)>1 else ""
                        ui.notify(f"{len(to_resolve)} lacune{pl} résolue{pl} ✓", type="positive")
                    refresh_fn()
                ui.button("Passer", on_click=_skip).props("flat color=grey-8")
                ui.button("Résoudre", icon="check_circle", on_click=_resolve).props(
                    "unelevated color=positive rounded"
                ).classes("font-semibold")
    dlg.open()


def _propose_lacune(state, session_id, refresh_fn):
    from backend.config.settings import settings as _cfg
    from backend.core.obsidian.weak_points_sync import create_obsidian_lacune_note

    sev          = suggested_severity(state.score_percent)
    sev_labels   = {1: "mineur", 2: "modéré", 3: "important", 4: "critique", 5: "critique"}
    course_title = state.course_title or (state.courses[0]["title"] if getattr(state, "courses", []) else "")
    course_id    = state.course_id    or (state.courses[0]["id"]    if getattr(state, "courses", []) else "")
    item_number  = state.item_number  or (state.courses[0].get("item_number", "") if getattr(state, "courses", []) else "")
    college      = ""  # non disponible depuis le state QCM

    obsidian_ok  = bool(_cfg.obsidian_vault_path)

    # Titre suggéré : nom du cours si dispo, sinon formule générique
    default_title = course_title or f"QCM raté — {state.score_raw}"

    _dlg_state = {
        "title":            default_title,
        "create_obsidian":  obsidian_ok,
    }

    with ui.dialog().props("persistent") as dlg:
        with ui.card().classes(
            "rounded-2xl p-0 overflow-hidden bg-white dark:bg-slate-900 shadow-2xl"
        ).style("width:440px;max-width:90vw"):

            # ── Header amber ──────────────────────────────────────────────────
            with ui.element("div").classes(
                "px-5 py-3.5 bg-amber-50 dark:bg-amber-900/20 "
                "border-b border-amber-100 dark:border-amber-800"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("report_problem", size="sm").classes("text-amber-500 shrink-0")
                    ui.label("Score inférieur à 70% — Créer une lacune ?").classes(
                        "font-bold text-amber-800 dark:text-amber-300 text-sm"
                    )

            # ── Body ──────────────────────────────────────────────────────────
            with ui.element("div").classes("px-5 py-4 flex flex-col gap-4"):

                # Score + sévérité
                with ui.row().classes("items-center gap-3"):
                    with ui.element("div").classes(
                        "px-3 py-1.5 rounded-lg bg-red-50 dark:bg-red-900/20 "
                        "border border-red-100 dark:border-red-800"
                    ):
                        ui.label(state.score_raw or "—").classes(
                            "text-lg font-extrabold text-red-600 dark:text-red-400 tabular-nums"
                        )
                    ui.label(
                        f"Sévérité suggérée : {sev_labels.get(sev, 'modéré')} ({sev}/5)"
                    ).classes("text-xs text-slate-500")

                # Titre de la lacune (éditable)
                with ui.column().classes("w-full gap-1"):
                    ui.label("TITRE DE LA LACUNE").classes(
                        "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                    )
                    ui.input(
                        value=default_title,
                        placeholder="Ex : Oubli hémocultures avant ATB — SCA",
                        on_change=lambda e: _dlg_state.update({"title": e.value or ""}),
                    ).props("outlined dense clearable").classes("w-full")
                    ui.label(
                        "Décrivez brièvement votre erreur — ce sera le nom de la note."
                    ).classes("text-[11px] text-slate-400")

                # Switch Obsidian (uniquement si vault configuré)
                if obsidian_ok:
                    with ui.row().classes(
                        "items-start gap-3 p-3 rounded-xl "
                        "bg-violet-50 dark:bg-violet-900/10 "
                        "border border-violet-100 dark:border-violet-800"
                    ):
                        obs_sw = ui.switch(value=True).props("color=violet").classes("shrink-0 mt-0.5")
                        obs_sw.on_value_change(
                            lambda e: _dlg_state.update({"create_obsidian": e.value})
                        )
                        with ui.column().classes("gap-0.5"):
                            ui.label("Créer aussi dans Obsidian").classes(
                                "text-sm font-semibold text-violet-800 dark:text-violet-200"
                            )
                            ui.label(
                                "Une note structurée sera créée dans 08 - Lacunes / Actives/"
                            ).classes("text-[11px] text-violet-500 dark:text-violet-400")

            # ── Footer ────────────────────────────────────────────────────────
            with ui.element("div").classes("px-5 pb-4 flex justify-end gap-2"):

                def _skip():
                    dlg.close()
                    refresh_fn()

                def _create():
                    title = (_dlg_state["title"] or "").strip() or "Lacune sans titre"

                    wp_id = local_store.add_weak_point_full(
                        course_id=course_id or "—",
                        detail=title,
                        course_title=course_title,
                        item_number=item_number,
                        category=None,
                        severity=sev,
                        source_type="qcm",
                        source_session_id=session_id,
                    )

                    if _dlg_state["create_obsidian"] and obsidian_ok:
                        ok, obs_path, obs_uri = create_obsidian_lacune_note(
                            title=title,
                            college=college,
                            severity=sev,
                            course_title=course_title,
                            item_number=item_number,
                            synapse_id=str(wp_id),
                            source="qcm",
                        )
                        if ok:
                            local_store.update_weak_point_obsidian(wp_id, obs_path, obs_uri)
                            ui.notify(
                                "Lacune créée + note Obsidian ✓",
                                type="positive", icon="edit_note",
                            )
                        else:
                            ui.notify(
                                "Lacune SQLite créée — échec Obsidian",
                                type="warning", icon="warning",
                            )
                    else:
                        ui.notify("Lacune créée ✓", type="positive", icon="report_problem")

                    dlg.close()
                    refresh_fn()

                ui.button("Passer", on_click=_skip).props("flat color=grey-8")
                ui.button(
                    "Créer la lacune", icon="report_problem", on_click=_create
                ).props("unelevated color=amber rounded").classes("font-semibold")

    dlg.open()


# ── Wizard : Révision manuelle des sessions post-import ───────────────────────

def _open_session_wizard(sessions: list, refresh_fn) -> None:
    """
    Wizard pas-à-pas post-import : pour chaque session avec erreurs,
    l'utilisateur remplit type d'erreur, sévérité et détail manuellement.
    """
    from backend.core.ai_qcm.lacunes import LacuneCandidate, create_lacune as _create_lacune
    from backend.config.settings import settings as _cfg

    obsidian_ok = bool(_cfg.obsidian_vault_path)

    ERROR_TYPES = [
        ("connaissance",   "Connaissance",   "school"),
        ("comprehension",  "Compréhension",  "psychology"),
        ("inattention",    "Inattention",    "visibility_off"),
        ("methode",        "Méthode",        "rule"),
        ("hors_programme", "Hors-programme", "block"),
        ("autre",          "Autre",          "more_horiz"),
    ]
    SEV_COLORS = {1: "grey-6", 2: "blue-7", 3: "amber-7", 4: "orange-7", 5: "red-7"}
    SEV_LABELS = {1: "Mineur", 2: "Modéré", 3: "Important", 4: "Critique", 5: "Critique+"}

    n = len(sessions)
    state = {
        "idx":     0,
        "obsidian": obsidian_ok,
        "entries": [
            {"error_type": None, "severity": 3, "detail": ""}
            for _ in sessions
        ],
        "created": 0,
    }

    with ui.dialog().props("persistent") as dlg:
        with ui.card().classes(
            "rounded-2xl p-0 overflow-hidden bg-white dark:bg-slate-900 shadow-2xl"
        ).style("width:540px;max-width:95vw"):

            step_area = ui.element("div").classes("flex flex-col")

            def _do_create(idx: int) -> None:
                e    = state["entries"][idx]
                sess = sessions[idx]
                detail = (e["detail"] or "").strip() or sess.get("course_title", "Lacune QCM")
                candidate = LacuneCandidate(
                    detail=detail,
                    category=e.get("error_type") or "autre",
                    severity=e["severity"],
                    severity_original=e["severity"],
                    course_id=sess.get("course_id", ""),
                    course_title=sess.get("course_title", ""),
                    item_number=sess.get("item_number", ""),
                    session_id=sess.get("session_id", 0),
                    is_recurrence=False,
                    existing_wp_id=None,
                )
                _create_lacune(
                    candidate=candidate,
                    severity=e["severity"],
                    detail_override=detail,
                    create_obsidian=state["obsidian"],
                )
                state["created"] += 1

            def _finish():
                dlg.close()
                c = state["created"]
                if c:
                    pl = "s" if c > 1 else ""
                    ui.notify(
                        f"{c} lacune{pl} créée{pl} ✓",
                        type="positive", icon="report_problem", timeout=4000,
                    )
                refresh_fn()

            def _advance(create: bool):
                idx = state["idx"]
                if create:
                    _do_create(idx)
                if idx + 1 < n:
                    state["idx"] += 1
                    _render()
                else:
                    _finish()

            def _render():
                step_area.clear()
                idx  = state["idx"]
                sess = sessions[idx]
                e    = state["entries"][idx]

                with step_area:
                    # ── Header / progression ──────────────────────────────────
                    with ui.element("div").classes(
                        "px-5 py-3.5 bg-indigo-50 dark:bg-indigo-900/20 "
                        "border-b border-indigo-100 dark:border-indigo-800"
                    ):
                        with ui.row().classes("items-center justify-between"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("quiz", size="sm").classes(
                                    "text-indigo-500 shrink-0"
                                )
                                ui.label(
                                    f"Session {idx + 1} / {n} — Documenter la lacune"
                                ).classes(
                                    "font-bold text-indigo-800 dark:text-indigo-200 text-sm"
                                )
                            with ui.row().classes("gap-1 items-center"):
                                for i in range(min(n, 8)):
                                    color = (
                                        "bg-indigo-500"
                                        if i == idx
                                        else "bg-green-400"
                                        if i < idx
                                        else "bg-slate-200 dark:bg-slate-700"
                                    )
                                    ui.element("div").classes(
                                        f"w-2 h-2 rounded-full transition-all {color}"
                                    )
                                if n > 8:
                                    ui.label(f"+{n - 8}").classes(
                                        "text-[10px] text-slate-400 ml-1"
                                    )

                    # ── Info session ──────────────────────────────────────────
                    with ui.element("div").classes("px-5 pt-4 pb-0"):
                        score = sess.get("score_percent")
                        title = sess.get("course_title", "")
                        item  = sess.get("item_number", "")
                        with ui.row().classes("items-start justify-between gap-3"):
                            with ui.column().classes("gap-0.5 flex-1"):
                                if item:
                                    ui.label(f"Item {item}").classes(
                                        "text-[11px] text-indigo-500 font-semibold "
                                        "uppercase tracking-wide"
                                    )
                                ui.label(title or "—").classes(
                                    "font-semibold text-slate-800 dark:text-slate-100 "
                                    "text-sm leading-snug"
                                )
                            if score is not None:
                                score_color = (
                                    "text-red-600 dark:text-red-400"
                                    if score < 60
                                    else "text-amber-600 dark:text-amber-400"
                                    if score < QCM_PASS_THRESHOLD
                                    else "text-green-600 dark:text-green-400"
                                )
                                ui.label(f"{score:.0f}%").classes(
                                    f"font-black text-xl {score_color} shrink-0"
                                )

                    # ── Formulaire ────────────────────────────────────────────
                    with ui.element("div").classes("px-5 py-4 flex flex-col gap-4"):

                        # Type d'erreur
                        with ui.element("div").classes("flex flex-col gap-2"):
                            ui.label("Type d'erreur").classes(
                                "text-[11px] font-semibold text-slate-500 dark:text-slate-400 "
                                "uppercase tracking-wide"
                            )
                            with ui.row().classes("gap-1.5 flex-wrap"):
                                for key, lbl, ico in ERROR_TYPES:
                                    is_sel = e["error_type"] == key
                                    def _sel_et(k=key):
                                        e["error_type"] = k
                                        _render()
                                    ui.button(lbl, icon=ico, on_click=_sel_et).props(
                                        f"{'unelevated' if is_sel else 'outline'} "
                                        f"color={'indigo' if is_sel else 'grey-7'} "
                                        "rounded dense"
                                    ).classes("text-xs")

                        # Sévérité
                        with ui.row().classes("items-center gap-3"):
                            ui.label("Sévérité").classes(
                                "text-[11px] font-semibold text-slate-500 dark:text-slate-400 "
                                "uppercase tracking-wide shrink-0"
                            )
                            with ui.row().classes("gap-1"):
                                for s in range(1, 6):
                                    is_sel = s == e["severity"]
                                    def _sel_sev(sv=s):
                                        e["severity"] = sv
                                        _render()
                                    ui.button(str(s), on_click=_sel_sev).props(
                                        f"{'unelevated' if is_sel else 'outline'} "
                                        f"color={SEV_COLORS[s]} dense rounded size=sm"
                                    ).style("min-width:32px")
                            ui.label(SEV_LABELS.get(e["severity"], "")).classes(
                                "text-xs text-slate-400 dark:text-slate-500"
                            )

                        # Détail (texte libre)
                        detail_inp = ui.input(
                            label="Détail (optionnel)",
                            value=e["detail"],
                            placeholder="Ce que tu n'as pas su / à retenir…",
                        ).props("outlined dense").classes("w-full text-sm")
                        detail_inp.on_value_change(
                            lambda ev, _e=e: _e.update({"detail": ev.value or ""})
                        )

                    # ── Footer ────────────────────────────────────────────────
                    with ui.element("div").classes(
                        "px-5 py-3.5 border-t border-slate-100 dark:border-slate-800 "
                        "flex items-center justify-between gap-2"
                    ):
                        # Obsidian toggle (gauche) — uniquement si sévérité > 3
                        if obsidian_ok and e["severity"] > 3:
                            with ui.row().classes("items-center gap-1.5"):
                                obs_sw = ui.switch(
                                    value=state["obsidian"]
                                ).props("color=violet dense size=xs")
                                obs_sw.on_value_change(
                                    lambda ev: state.update({"obsidian": ev.value})
                                )
                                ui.label("Obsidian").classes(
                                    "text-xs text-violet-600 dark:text-violet-400"
                                )
                        else:
                            ui.element("div")

                        # Boutons (droite)
                        with ui.row().classes("gap-2"):
                            is_last = idx == n - 1
                            next_lbl = "Terminer" if is_last else "Suivant"
                            if e["severity"] >= 3:
                                # Sévérité haute : propose la création de lacune
                                ui.button(
                                    next_lbl,
                                    on_click=lambda: _advance(create=False),
                                ).props("flat color=grey-8 dense").classes("text-sm")
                                ui.button(
                                    "Créer lacune" + (" ✓" if is_last else " →"),
                                    icon="report_problem",
                                    on_click=lambda: _advance(create=True),
                                ).props("unelevated color=red rounded dense").classes(
                                    "text-sm font-semibold"
                                )
                            else:
                                # Sévérité ≤ 3 : juste enregistrer les infos, pas de lacune
                                ui.button(
                                    next_lbl,
                                    icon="arrow_forward" if not is_last else "check",
                                    on_click=lambda: _advance(create=False),
                                ).props("unelevated color=indigo rounded dense").classes(
                                    "text-sm font-semibold"
                                )

            _render()

    dlg.open()
