"""weak_point_row.py — Ligne cockpit pour une lacune (refonte, écran Lacunes).

Ligne plate sur tokens `--*`, actions révélées au survol — même grammaire que
`study_task_row` (Révisions).
"""
from __future__ import annotations

import datetime
import webbrowser

from nicegui import ui

from backend.core.reviews import local_store
from frontend.components.weak_point_card import _get

_MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin",
              "juil", "août", "sep", "oct", "nov", "déc"]

_STATUS_LABEL = {
    "active": "active",
    "à revoir": "à revoir",
    "récurrente": "récurrente",
    "résolue": "résolue",
}

_CSS = """
.wpr-row { position:relative; display:flex; align-items:center; gap:12px;
  min-height:50px; padding:7px 8px 7px 4px; border-bottom:1px solid var(--border);
  border-radius:6px; transition: background var(--duration-fast) var(--ease-standard); }
.wpr-row:hover { background:var(--surface); }
.wpr-row.resolved { opacity:.55; }
.wpr-dot { width:8px; height:8px; border-radius:50%; flex:0 0 8px; margin-left:4px; }
.wpr-main { min-width:0; flex:1 1 auto; display:flex; flex-direction:column; gap:2px; }
.wpr-title { font-size:13.5px; font-weight:500; color:var(--text);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wpr-status { font-size:11.5px; }
.wpr-right { flex:0 0 auto; position:relative; height:22px; display:flex;
  align-items:center; min-width:132px; justify-content:flex-end; }
.wpr-meta { display:flex; align-items:center; gap:10px; font-size:12px;
  color:var(--text-muted); transition:opacity var(--duration-fast) var(--ease-standard);
  white-space:nowrap; }
.wpr-meta .wpr-id { font-family:var(--font-mono); color:var(--text-dim); font-size:11px; }
.wpr-actions { position:absolute; right:0; top:50%; transform:translateY(-50%);
  display:flex; align-items:center; gap:1px; opacity:0; visibility:hidden;
  transition:opacity var(--duration-fast) var(--ease-standard); }
.wpr-row:hover .wpr-meta { opacity:0; }
.wpr-row:hover .wpr-actions { opacity:1; visibility:visible; }
.wpr-row:focus-within .wpr-actions { opacity:1; visibility:visible; }
"""

_injected = {"done": False}


def ensure_styles() -> None:
    """Injecte le CSS du composant (à appeler au build synchrone de la page)."""
    if not _injected["done"]:
        ui.add_head_html(f"<style>{_CSS}</style>", shared=True)
        _injected["done"] = True


def _fmt_date(d: str) -> str:
    try:
        date_obj = datetime.date.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return "—"
    base = f"{date_obj.day:02d} {_MONTHS_FR[date_obj.month - 1]}"
    return base if date_obj.year == datetime.date.today().year else f"{base} {date_obj.year}"


def status_line(w) -> str:
    """Grammaire : « critique » (sévérité≥4, non résolue, prioritaire sur le
    statut brut) · statut brut sinon · « récurrente Nx » si statut='récurrente'
    · « Nx » si récurrence≥2 sur un autre statut · date de résolution si
    résolue. Une seule chaîne, casse phrase (majuscule initiale uniquement)."""
    severity = int(_get(w, "severity", 2) or 2)
    status = _get(w, "status", "active") or "active"
    recurrence = int(_get(w, "recurrence_count", 0) or 0)
    critical = severity >= 4 and status != "résolue"

    parts: list[str] = []
    if status == "résolue":
        parts.append("résolue")
        resolved = _get(w, "resolved_at", None)
        if resolved:
            parts.append(_fmt_date(resolved))
    else:
        if critical:
            parts.append("critique")
        if status == "récurrente":
            parts.append(f"récurrente {recurrence}×")
        elif not critical:
            parts.append(_STATUS_LABEL.get(status, status))
            if recurrence >= 2:
                parts.append(f"{recurrence}×")
        elif recurrence >= 2:
            parts.append(f"{recurrence}×")

    line = " · ".join(parts) if parts else "active"
    return line[0].upper() + line[1:] if line else line


def dot_color(w) -> str:
    status = _get(w, "status", "active") or "active"
    severity = int(_get(w, "severity", 2) or 2)
    if status == "résolue":
        return "var(--success)"
    if severity >= 4:
        return "var(--danger)"
    return "var(--warning)"


def status_text_color(w) -> str:
    """Couleur du texte de statut — colorée seulement si urgence (critique
    ou à revoir), sinon neutre : une seule dimension porte la couleur."""
    status = _get(w, "status", "active") or "active"
    severity = int(_get(w, "severity", 2) or 2)
    if status == "résolue":
        return "var(--text-muted)"
    if severity >= 4:
        return "var(--danger)"
    if status == "à revoir":
        return "var(--warning)"
    return "var(--text-muted)"


def weak_point_row(w, on_refresh=None) -> None:
    ensure_styles()

    status = _get(w, "status", "active") or "active"
    college = _get(w, "college", "") or ""
    item_nb = _get(w, "item_number", "") or ""
    detail = _get(w, "detail", "") or ""
    obs_title = _get(w, "obsidian_title", "") or ""
    obs_path = _get(w, "obsidian_path", "") or ""
    obs_uri = _get(w, "obsidian_uri", "") or ""
    title = obs_title or detail or "(sans titre)"
    is_obsidian = bool(obs_path)
    wp_id = w["id"]

    def _refresh():
        if on_refresh:
            on_refresh()

    row_cls = "wpr-row" + (" resolved" if status == "résolue" else "")
    with ui.element("div").classes(row_cls).props(f'data-id="{wp_id}" tabindex="0"'):
        ui.element("span").classes("wpr-dot").style(f"background:{dot_color(w)}")

        with ui.element("div").classes("wpr-main"):
            ui.label(title).classes("wpr-title")
            ui.label(status_line(w)).classes("wpr-status").style(
                f"color:{status_text_color(w)}"
            )

        with ui.element("div").classes("wpr-right"):
            with ui.element("div").classes("wpr-meta"):
                if college:
                    ui.label(college[:22])
                ui.label(item_nb or "—").classes("wpr-id")

            with ui.element("div").classes("wpr-actions"):
                if is_obsidian:
                    def _on_open_obsidian(uri=obs_uri, path=obs_path):
                        target = uri or path
                        if not target:
                            ui.notify("Chemin Obsidian indisponible", type="warning")
                            return
                        try:
                            webbrowser.open(target)
                        except Exception as exc:
                            try:
                                import os
                                os.startfile(path.replace("/", "\\"))
                            except Exception:
                                ui.notify(f"Impossible d'ouvrir : {exc}", type="negative")

                    ui.button(icon="auto_stories", on_click=_on_open_obsidian).props(
                        "flat round dense size=sm color=indigo"
                    ).tooltip("Ouvrir dans Obsidian")

                if status != "résolue":
                    def _on_revoir(wid=wp_id, cid=w["course_id"], opath=obs_path):
                        local_store.mark_weak_point_reviewed(wid)
                        if opath:
                            from backend.core.obsidian.weak_points_sync import write_obsidian_reviewed_at
                            write_obsidian_reviewed_at(
                                opath.replace("/", "\\"),
                                datetime.date.today().isoformat(),
                            )
                        from backend.state.store import data_store
                        c = next((x for x in data_store.cours if x.id == cid), None)
                        if c and (c.url_pdf or c.url_pdf_ue):
                            ui.navigate.to(f"/pdf/{cid}", new_tab=True)
                        else:
                            ui.notify("Lacune marquée comme revue", type="info")
                        _refresh()

                    ui.button(icon="menu_book", on_click=_on_revoir).props(
                        "flat round dense size=sm color=indigo"
                    ).tooltip("Revoir le cours")

                    def _on_resolve(wid=wp_id, opath=obs_path):
                        local_store.update_weak_point_status(wid, "résolue")
                        if opath:
                            from backend.core.obsidian.weak_points_sync import (
                                write_obsidian_lacune_status, move_obsidian_lacune_file,
                            )
                            new_path = move_obsidian_lacune_file(opath, "résolue")
                            write_obsidian_lacune_status(
                                new_path.replace("/", "\\"),
                                "résolue",
                                resolved_at=datetime.date.today().isoformat(),
                            )
                            if new_path != opath:
                                local_store.update_weak_point_obsidian_path(wid, new_path)
                        ui.notify("Lacune résolue ✓", type="positive")
                        _refresh()

                    ui.button(icon="check_circle", on_click=_on_resolve).props(
                        "flat round dense size=sm color=positive"
                    ).tooltip("Marquer résolue")
                else:
                    def _on_reopen(wid=wp_id, opath=obs_path):
                        local_store.update_weak_point_status(wid, "active")
                        if opath:
                            from backend.core.obsidian.weak_points_sync import (
                                write_obsidian_lacune_status, move_obsidian_lacune_file,
                            )
                            new_path = move_obsidian_lacune_file(opath, "active")
                            write_obsidian_lacune_status(new_path.replace("/", "\\"), "active")
                            if new_path != opath:
                                local_store.update_weak_point_obsidian_path(wid, new_path)
                        ui.notify("Lacune réactivée", type="warning")
                        _refresh()

                    ui.button(icon="refresh", on_click=_on_reopen).props(
                        "flat round dense size=sm color=indigo"
                    ).tooltip("Réactiver")

                with ui.button(icon="more_horiz").props("flat round dense size=sm"):
                    with ui.menu().classes("text-sm"):
                        if status not in ("récurrente", "résolue"):
                            def _on_recur(wid=wp_id, opath=obs_path):
                                local_store.increment_recurrence(wid)
                                if opath:
                                    from backend.core.obsidian.weak_points_sync import (
                                        write_obsidian_lacune_status, move_obsidian_lacune_file,
                                    )
                                    new_path = move_obsidian_lacune_file(opath, "récurrente")
                                    write_obsidian_lacune_status(new_path.replace("/", "\\"), "récurrente")
                                    if new_path != opath:
                                        local_store.update_weak_point_obsidian_path(wid, new_path)
                                ui.notify("Lacune marquée récurrente ↺", type="warning")
                                _refresh()
                            ui.menu_item("Rendre récurrente", on_click=_on_recur).classes("text-xs")

                        if status not in ("à revoir", "résolue"):
                            def _on_to_review(wid=wp_id, opath=obs_path):
                                local_store.update_weak_point_status(wid, "à revoir")
                                if opath:
                                    from backend.core.obsidian.weak_points_sync import (
                                        write_obsidian_lacune_status, move_obsidian_lacune_file,
                                    )
                                    new_path = move_obsidian_lacune_file(opath, "à revoir")
                                    write_obsidian_lacune_status(new_path.replace("/", "\\"), "à revoir")
                                    if new_path != opath:
                                        local_store.update_weak_point_obsidian_path(wid, new_path)
                                ui.notify("Lacune marquée à revoir", type="info")
                                _refresh()
                            ui.menu_item("Marquer à revoir", on_click=_on_to_review).classes("text-xs")

                        ui.separator()
                        ui.menu_item("Sévérité").classes(
                            "text-[11px] text-slate-400 font-bold uppercase pointer-events-none"
                        )
                        sev = int(_get(w, "severity", 2) or 2)
                        with ui.row().classes("px-3 pb-2 gap-1"):
                            for sv in range(1, 6):
                                def _set_sev(s=sv, wid=wp_id):
                                    local_store.update_weak_point_severity(wid, s)
                                    _refresh()
                                ui.button(str(sv)).props(
                                    f"{'unelevated' if sv == sev else 'outline'} round dense size=xs "
                                    f"color={'positive' if sv <= 2 else 'warning' if sv == 3 else 'negative'}"
                                ).on_click(_set_sev)

                        ui.separator()
                        def _on_delete(wid=wp_id, obs=obs_path):
                            if obs:
                                try:
                                    from backend.core.obsidian.weak_points_sync import delete_obsidian_lacune_file
                                    delete_obsidian_lacune_file(obs)
                                except Exception:
                                    pass
                            local_store.delete_weak_point(wid)
                            ui.notify("Lacune supprimée", type="warning")
                            _refresh()
                        ui.menu_item("Supprimer", on_click=_on_delete).classes(
                            "text-xs text-red-400"
                        )
