"""
_monday.py — Diagnostic hebdomadaire du lundi.
"""
from __future__ import annotations

import datetime

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.reviews.service import review_service
from backend.state.store import data_store

from ._state import DashboardState


def render_monday_diagnostic(state: DashboardState) -> None:
    """Render (ou re-render) le diagnostic du lundi dans state.monday_container."""
    state.monday_container.clear()

    _is_monday = (datetime.date.today().weekday() == 0)
    if not _is_monday:
        return

    _monday_dism_key = f"monday_diag_{datetime.date.today().isoformat()}"
    if data_store.preferences.get(_monday_dism_key, False):
        return

    try:
        _history = local_store.get_all_history()
        _all = review_service.generate_reviews(
            context=state.review_context,
            history=_history,
            active_only=True,
        )
        _urgent = review_service.get_urgent_tasks(_all)
        _today = review_service.get_today_tasks(_all)
        _n_lac = local_store.get_open_lacunes_count()

        from collections import Counter as _Ctr
        _col_ctr = _Ctr(cg for t in _urgent for cg in (t.college or []))
        _weakest_col = _col_ctr.most_common(1)[0][0] if _col_ctr else None

        _top5 = sorted(
            _urgent,
            key=lambda t: (t.review_type != "J30", t.due_date),
        )[:5]

        with state.monday_container:
            with ui.card().classes(
                "w-full mb-4 rounded-2xl border-2 border-violet-300 dark:border-violet-700 "
                "bg-violet-50 dark:bg-violet-950/30 p-4 relative overflow-hidden"
            ):
                with ui.row().classes("items-start justify-between w-full gap-2"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("auto_awesome", size="sm").classes("text-violet-500 shrink-0")
                        ui.label("Diagnostic du lundi").classes(
                            "text-sm font-extrabold text-violet-700 dark:text-violet-300 uppercase tracking-wide"
                        )

                    def _dismiss(_key=_monday_dism_key, _cont=state.monday_container):
                        data_store.set_preference(_key, True)
                        _cont.clear()

                    ui.button(icon="close", on_click=_dismiss).props(
                        "flat round dense size=xs color=grey-6"
                    ).tooltip("Fermer jusqu'à lundi prochain")

                with ui.column().classes("w-full gap-1.5 mt-2"):
                    _diag_rows = [
                        (
                            "priority_high",
                            f"{len(_urgent)} révision{'s' if len(_urgent) != 1 else ''} en retard à rattraper cette semaine",
                            "text-red-500",
                            "text-red-700 dark:text-red-300" if _urgent else "text-slate-500",
                        ),
                        (
                            "today",
                            f"{len(_today)} révision{'s' if len(_today) != 1 else ''} prévue{'s' if len(_today) != 1 else ''} aujourd'hui",
                            "text-blue-400",
                            "text-blue-700 dark:text-blue-300",
                        ),
                        (
                            "warning",
                            f"{_n_lac} lacune{'s' if _n_lac != 1 else ''} active{'s' if _n_lac != 1 else ''} à retravailler",
                            "text-amber-500",
                            "text-amber-700 dark:text-amber-300" if _n_lac > 0 else "text-slate-400",
                        ),
                    ]
                    if _weakest_col:
                        _diag_rows.append((
                            "location_on",
                            f"Point faible n°1 : {_weakest_col} ({_col_ctr[_weakest_col]} retard{'s' if _col_ctr[_weakest_col] > 1 else ''})",
                            "text-orange-400",
                            "text-orange-700 dark:text-orange-300",
                        ))
                    for _icon, _txt, _icon_cls, _txt_cls in _diag_rows:
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(_icon, size="xs").classes(f"{_icon_cls} shrink-0")
                            ui.label(_txt).classes(f"text-[11px] font-semibold {_txt_cls}")

                    if _top5:
                        ui.separator().classes("my-1 opacity-30")
                        ui.label("5 cours à prioriser cette semaine :").classes(
                            "text-[11px] font-bold text-violet-600 dark:text-violet-400 uppercase tracking-wide"
                        )
                        for _t in _top5:
                            with ui.row().classes("items-center gap-1.5"):
                                ui.badge(_t.type_badge, color="violet").classes("text-[10px] px-1 py-0.5 shrink-0")
                                ui.label(_t.label).classes(
                                    "text-[11px] text-slate-700 dark:text-slate-300 truncate"
                                )
    except Exception:
        pass
