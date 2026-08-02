"""
weak_points.py — Synapse — Page Lacunes
----------------------------------------
Kanban 4 colonnes avec drag & drop (Sortable.js) :
  🔴 Très critiques  (active, severity ≥ 4)
  🟡 À revoir
  🔵 Actives         (active, severity < 4)
  🟠 Récurrentes
  ✓  Résolues récemment (accordion collapsé en bas)
"""

from nicegui import ui
from loguru import logger

from frontend.theme import frame
from backend.core.reviews import local_store
from backend.state.store import data_store
from backend.config.settings import settings


# ── Options ────────────────────────────────────────────────────────────────────

_CATEGORIES = {None: "— Aucune"} | {c: c for c in local_store.WEAK_POINT_CATEGORIES}
_SOURCE_OPTS = {"manuel": "Manuel", "qcm": "QCM", "séance": "Séance", "note": "Note"}

# JS Sortable.js init — injecté après render du kanban
_SORTABLE_JS = """
(function initLacuneKanban() {
  function _init() {
    if (typeof Sortable === 'undefined') {
      setTimeout(_init, 150);
      return;
    }
    document.querySelectorAll('.lacune-col-body').forEach(col => {
      if (col._sortable) { col._sortable.destroy(); }
      col._sortable = new Sortable(col, {
        group: 'lacunes',
        animation: 200,
        ghostClass: 'lacune-ghost',
        dragClass: 'lacune-dragging',
        onEnd: function(evt) {
          var id = evt.item.dataset.id;
          var status = evt.to.dataset.status;
          if (!id || !status) return;
          fetch('/api/lacune/move', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: parseInt(id), status: status})
          });
          [evt.from, evt.to].forEach(function(col) {
            var badge = col.closest('.lacune-col') &&
                        col.closest('.lacune-col').querySelector('.lacune-col-count');
            if (badge) badge.textContent = col.querySelectorAll('.lacune-card').length;
          });
        }
      });
    });
  }
  _init();
})();
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_unlinked_obsidian(w) -> bool:
    try:
        return bool(w["obsidian_path"]) and not (w["course_id"] or "").strip()
    except (IndexError, KeyError):
        return False


# ── Page principale ───────────────────────────────────────────────────────────

def weak_points_page(item_filter: str | None = None):
    _state = {"item": item_filter}

    with frame("Points faibles"):
        logger.info("ENTERING WEAK POINTS PAGE")

        # ── Vue cockpit ───────────────────────────────────────────────────────
        from frontend.pages.weak_points_cockpit import render_weak_points_cockpit
        render_weak_points_cockpit()
        return


# ── Dialog : Ajouter une lacune ───────────────────────────────────────────────

def open_add_dialog(refresh_fn):
    from types import SimpleNamespace

    state = SimpleNamespace(
        course_id="",
        course_title="",
        item_number="",
        category=None,
        detail="",
        severity=2,
        source_type="manuel",
    )

    with ui.dialog() as dialog:
        with ui.card().classes(
            "w-[520px] max-w-[92vw] rounded-3xl p-0 overflow-hidden "
            "bg-white dark:bg-slate-900 shadow-2xl"
        ).style("display:flex;flex-direction:column;"):

            # Header
            with ui.element("div").classes(
                "px-6 pt-5 pb-4 border-b border-slate-100 dark:border-slate-800 shrink-0"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Ajouter une lacune").classes(
                        "text-[15px] font-bold text-slate-900 dark:text-slate-50"
                    )
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense size=sm color=grey-7"
                    )

            # Body
            with ui.element("div").classes("px-6 py-5 flex flex-col gap-3"):
                def _section_lbl(text):
                    ui.label(text).classes(
                        "text-[11px] font-bold tracking-widest text-slate-400 uppercase"
                    )

                # Cours
                _section_lbl("Cours associé")
                course_display = ui.label("Aucun cours sélectionné").classes(
                    "text-xs text-slate-400 italic"
                )

                def _open_course_picker():
                    with ui.dialog() as picker_dlg:
                        with ui.card().classes("w-[480px] max-w-[90vw] rounded-2xl p-4 gap-3"):
                            ui.label("Sélectionner un cours").classes(
                                "font-bold text-slate-800 dark:text-slate-100"
                            )
                            result_col = ui.column().classes("w-full gap-1")

                            def _do_search(q: str):
                                result_col.clear()
                                q_l = q.lower().strip()
                                if len(q_l) < 2:
                                    return
                                matches = [
                                    c for c in data_store.cours
                                    if q_l in c.title.lower()
                                    or (c.item_number and q_l in c.item_number.lower())
                                ][:12]
                                with result_col:
                                    for c in matches:
                                        itxt = f"ITEM {c.item_number} — " if c.item_number else ""
                                        def _pick(course=c):
                                            state.course_id    = course.id
                                            state.course_title = course.title
                                            state.item_number  = course.item_number or ""
                                            course_display.set_text(
                                                f"ITEM {course.item_number} — {course.title}"
                                                if course.item_number else course.title
                                            )
                                            course_display.classes(remove="text-slate-400 italic")
                                            picker_dlg.close()
                                        with ui.item(on_click=_pick).classes(
                                            "cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 "
                                            "rounded px-3 py-2 w-full"
                                        ):
                                            ui.label(f"{itxt}{c.title}").classes(
                                                "text-sm font-medium text-slate-800 dark:text-slate-100"
                                            )

                            with ui.scroll_area().classes("w-full").style("max-height:280px"):
                                ui.column().classes("w-full")
                            ui.input(
                                "Rechercher un cours…",
                                on_change=lambda e: _do_search(e.value),
                            ).props("autofocus outlined dense").classes("w-full mt-2")

                    picker_dlg.open()

                ui.button(
                    "Choisir un cours…", icon="search", on_click=_open_course_picker
                ).props("outline dense rounded color=primary").classes("text-xs self-start")

                # Catégorie
                _section_lbl("Catégorie")
                ui.select(
                    options=_CATEGORIES,
                    value=None,
                    label="Catégorie",
                ).classes("w-full").props("outlined dense").on_value_change(
                    lambda e: setattr(state, "category", e.value)
                )

                # Détail
                _section_lbl("Description de la lacune")
                ui.textarea(
                    placeholder="Ex : oubli antibioprophylaxie post-splénectomie…",
                ).classes("w-full").props("outlined dense autogrow").on_value_change(
                    lambda e: setattr(state, "detail", e.value or "")
                )

                # Sévérité
                _section_lbl("Sévérité (1 = mineur · 5 = critique)")
                sev_btns: dict[int, ui.button] = {}
                with ui.row().classes("gap-2"):
                    for sv in range(1, 6):
                        col = "positive" if sv <= 2 else "warning" if sv == 3 else "negative"
                        b = ui.button(str(sv)).props(
                            f"{'unelevated' if sv == state.severity else 'outline'} "
                            f"round size=sm color={col}"
                        )
                        sev_btns[sv] = b

                        def _set_sev(s=sv):
                            state.severity = s
                            for sv2, btn2 in sev_btns.items():
                                col2 = "positive" if sv2 <= 2 else "warning" if sv2 == 3 else "negative"
                                if sv2 == s:
                                    btn2.props(f"unelevated round size=sm color={col2}")
                                else:
                                    btn2.props(f"outline round size=sm color={col2}")

                        b.on_click(_set_sev)

                # Source
                _section_lbl("Source")
                src_btns: dict[str, ui.button] = {}
                with ui.row().classes("gap-2 flex-wrap"):
                    for src_id, src_lbl in _SOURCE_OPTS.items():
                        b = ui.button(src_lbl).props(
                            f"{'unelevated' if src_id == state.source_type else 'outline'} "
                            "rounded size=sm color=primary"
                        )
                        src_btns[src_id] = b

                        def _set_src(s=src_id):
                            state.source_type = s
                            for si, sb in src_btns.items():
                                if si == s:
                                    sb.props("unelevated rounded size=sm color=primary")
                                else:
                                    sb.props("outline rounded size=sm color=primary")

                        b.on_click(_set_src)

            # Footer
            with ui.element("div").classes(
                "px-6 py-4 bg-slate-50 dark:bg-slate-800/50 "
                "border-t border-slate-100 dark:border-slate-800 "
                "flex justify-end gap-2 shrink-0"
            ):
                ui.button("Annuler", on_click=dialog.close).props("flat color=grey-8")

                def _submit():
                    detail = state.detail.strip()
                    if not detail:
                        ui.notify("La description est obligatoire.", type="warning")
                        return

                    wp_id = local_store.add_weak_point_full(
                        course_id=state.course_id or "—",
                        detail=detail,
                        course_title=state.course_title,
                        item_number=state.item_number,
                        category=state.category,
                        severity=state.severity,
                        source_type=state.source_type,
                    )

                    if settings.obsidian_vault_path:
                        try:
                            from backend.core.obsidian.weak_points_sync import create_obsidian_lacune_note
                            college = ""
                            if state.course_id:
                                c = next((x for x in data_store.cours if x.id == state.course_id), None)
                                if c and c.college:
                                    college = c.college[0] if isinstance(c.college, list) else str(c.college)
                            ok, obs_path, obs_uri = create_obsidian_lacune_note(
                                title=detail,
                                college=college,
                                severity=state.severity,
                                course_title=state.course_title,
                                item_number=state.item_number,
                                synapse_id=str(wp_id),
                                source=state.source_type,
                                status="active",
                            )
                            if ok:
                                local_store.update_weak_point_obsidian(wp_id, obs_path, obs_uri)
                        except Exception as _exc:
                            logger.warning(f"Création note Obsidian échouée (non bloquant): {_exc}")

                    dialog.close()
                    ui.notify("Lacune ajoutée", type="positive")
                    refresh_fn()

                ui.button(
                    "Ajouter", on_click=_submit
                ).props("unelevated color=primary rounded").classes("px-5 font-semibold")

    dialog.open()
