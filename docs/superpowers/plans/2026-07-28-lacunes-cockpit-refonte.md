# Refonte de l'écran Lacunes (cockpit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recentrer l'écran Lacunes du cockpit et remplacer sa carte par un composant sur tokens `--*`, en remplaçant la sidebar de navigation interne et le panneau « Pilotage » par des chips de filtre horizontales.

**Architecture:** Un nouveau composant `frontend/components/weak_point_row.py` (ligne plate, actions au survol, réutilisant les handlers métier déjà écrits dans `weak_point_card.py`) remplace `WeakPointCard` dans le rendu cockpit. `frontend/pages/weak_points_cockpit.py` perd sa grille deux colonnes (sidebar + pilotage) au profit d'une colonne unique centrée avec une rangée de chips. Le chemin classic (`weak_points.py`, `weak_point_card.py`, kanban + drag) n'est pas touché.

**Tech Stack:** NiceGUI (Python), tokens CSS cockpit (`frontend/design_tokens.py`), SQLite via `backend/core/reviews/local_store`, pytest.

## Global Constraints

- `ui.add_head_html` doit être appelé au build synchrone uniquement, jamais dans un `ui.timer`/callback post-load.
- `local_store` renvoie des `sqlite3.Row`, pas des `dict` : tout accès passe par un helper tolérant (`_get(row, key, default)`), jamais `.get()` direct sur une row.
- Grammaire de statut : une seule dimension porte la couleur (rouge/ambre/vert = urgence). Aucun émoji comme icône.
- Rayons plafond 8px, transitions ≤180ms (`var(--duration-fast)` = 120ms, `var(--duration-base)` = 180ms).
- Le chemin classic (`frontend/pages/weak_points.py`, `frontend/components/weak_point_card.py`) reste strictement inchangé.
- Référence de spec : `docs/superpowers/specs/2026-07-28-lacunes-cockpit-refonte-design.md`.

---

## File Structure

- **Create** `frontend/components/weak_point_row.py` — composant de ligne cockpit (helpers de grammaire de statut + rendu + actions), remplace l'usage de `WeakPointCard` dans le cockpit uniquement.
- **Create** `tests/test_weak_point_row.py` — tests unitaires des helpers de grammaire (`status_line`, `dot_color`, `status_text_color`).
- **Modify** `frontend/pages/weak_points_cockpit.py` — CSS (colonne centrée 860px, chips), suppression de la sidebar/pilotage, câblage au nouveau composant.
- **Modify** `tests/test_weak_points_cockpit_ui.py` — remplace les assertions qui verrouillaient l'ancienne mise en page (sidebar/pilotage/`WeakPointCard`) par des assertions sur la nouvelle.
- **Unchanged** `frontend/components/weak_point_card.py`, `frontend/pages/weak_points.py`, `tests/test_weak_points_cockpit.py` (teste `filter_weak_points_view`, logique inchangée).

---

### Task 1: Tests des helpers de grammaire de statut (`weak_point_row`)

**Files:**
- Create: `tests/test_weak_point_row.py`

**Interfaces:**
- Consumes : rien (tests purs sur des dicts simulant des rows).
- Produces : fixe le contrat de `frontend.components.weak_point_row.status_line(w) -> str`, `dot_color(w) -> str`, `status_text_color(w) -> str` que la Task 2 doit satisfaire. `w` est un mapping avec les clés `status`, `severity`, `recurrence_count`, `resolved_at` (accès par `w[key]`, comme une `sqlite3.Row`).

- [ ] **Step 1: Écrire les tests (échoueront — le module n'existe pas encore)**

```python
from frontend.components.weak_point_row import status_line, dot_color, status_text_color


def _row(status="active", severity=2, recurrence_count=0, resolved_at=None):
    return {
        "status": status,
        "severity": severity,
        "recurrence_count": recurrence_count,
        "resolved_at": resolved_at,
    }


def test_status_line_active_simple():
    assert status_line(_row(status="active", severity=2)) == "Active"


def test_status_line_critique_prioritaire_sur_statut_brut():
    # sévérité >= 4 et pas résolue => "critique" remplace le statut brut
    assert status_line(_row(status="active", severity=4)) == "Critique"


def test_status_line_critique_et_recurrente():
    assert status_line(_row(status="récurrente", severity=5, recurrence_count=3)) == "Critique · récurrente 3×"


def test_status_line_recurrente_non_critique():
    assert status_line(_row(status="récurrente", severity=2, recurrence_count=3)) == "Récurrente 3×"


def test_status_line_a_revoir_avec_recurrence():
    assert status_line(_row(status="à revoir", severity=2, recurrence_count=2)) == "À revoir · 2×"


def test_status_line_resolue_avec_date():
    line = status_line(_row(status="résolue", severity=1, resolved_at="2026-06-02"))
    assert line == "Résolue · 02 juin"


def test_status_line_resolue_sans_date():
    assert status_line(_row(status="résolue", severity=1)) == "Résolue"


def test_dot_color_critique_rouge():
    assert dot_color(_row(status="active", severity=5)) == "var(--danger)"


def test_dot_color_active_ambre():
    assert dot_color(_row(status="active", severity=2)) == "var(--warning)"


def test_dot_color_resolue_vert():
    assert dot_color(_row(status="résolue", severity=5)) == "var(--success)"


def test_status_text_color_neutre_hors_urgence():
    assert status_text_color(_row(status="active", severity=2)) == "var(--text-muted)"
    assert status_text_color(_row(status="récurrente", severity=2, recurrence_count=3)) == "var(--text-muted)"
    assert status_text_color(_row(status="résolue", severity=5)) == "var(--text-muted)"


def test_status_text_color_urgence_coloree():
    assert status_text_color(_row(status="active", severity=4)) == "var(--danger)"
    assert status_text_color(_row(status="à revoir", severity=2)) == "var(--warning)"
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weak_point_row.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'frontend.components.weak_point_row'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_weak_point_row.py
git commit -m "test: grammaire de statut de la future ligne cockpit Lacunes"
```

---

### Task 2: Composant `weak_point_row` (cockpit)

**Files:**
- Create: `frontend/components/weak_point_row.py`
- Test: `tests/test_weak_point_row.py` (Task 1, déjà écrit)

**Interfaces:**
- Consumes : `frontend.components.weak_point_card._get(row, key, default=None)` (helper tolérant existant, réutilisé tel quel) ; `backend.core.reviews.local_store` (`mark_weak_point_reviewed`, `update_weak_point_status`, `update_weak_point_obsidian_path`, `increment_recurrence`, `update_weak_point_severity`, `delete_weak_point`) ; `backend.core.obsidian.weak_points_sync` (`write_obsidian_reviewed_at`, `write_obsidian_lacune_status`, `move_obsidian_lacune_file`, `delete_obsidian_lacune_file`) ; `backend.state.store.data_store`.
- Produces : `status_line(w) -> str`, `dot_color(w) -> str`, `status_text_color(w) -> str` (validés par Task 1) ; `ensure_styles() -> None` ; `weak_point_row(w, on_refresh: Callable[[], None] | None = None) -> None` — rendu NiceGUI, consommé par la Task 3.

- [ ] **Step 1: Créer le fichier**

```python
"""weak_point_row.py — Ligne cockpit pour une lacune (refonte, écran Lacunes).

Ligne plate sur tokens `--*`, actions révélées au survol — même grammaire que
`study_task_row` (Révisions). Distinct de `weak_point_card.py` (carte
Tailwind du classic), qui reste inchangé et sert uniquement le kanban
`frontend/pages/weak_points.py`.
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
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils passent**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weak_point_row.py -v`
Expected: PASS (12 tests)

- [ ] **Step 3: Commit**

```bash
git add frontend/components/weak_point_row.py
git commit -m "feat: composant weak_point_row sur tokens cockpit"
```

---

### Task 3: Recentrer `weak_points_cockpit.py` — chips + colonne unique

**Files:**
- Modify: `frontend/pages/weak_points_cockpit.py`

**Interfaces:**
- Consumes : `weak_point_row(w, on_refresh)` et `ensure_styles()` de la Task 2 ; `filter_weak_points_view(rows, view)` (inchangé, déjà testé par `tests/test_weak_points_cockpit.py`) ; `local_store.get_all_weak_points_table(limit=300)` (inchangé) ; `open_add_dialog` (classic, inchangé) ; `weak_points_sync_service.sync` (inchangé).
- Produces : `render_weak_points_cockpit() -> None` (signature inchangée — c'est le point d'entrée appelé par `weak_points.py`, aucune autre page n'importe le reste du module).

- [ ] **Step 1: Remplacer l'en-tête du module et le bloc CSS**

Dans `frontend/pages/weak_points_cockpit.py`, remplacer la docstring du module (lignes 1-25) par :

```python
"""weak_points_cockpit.py — Vue « Lacunes » cockpit (refonte, session 11 puis
recentrage du 28/07/2026, cf. docs/superpowers/specs/2026-07-28-lacunes-cockpit-refonte-design.md).

Rendu quand preferences['ui_mode'] == 'cockpit' (early-return depuis
weak_points.py). Topbar (titre, compteurs, actions) + chips de filtre
(remplacent la sidebar interne d'origine) + colonne centrée de lignes
`weak_point_row` (tokens cockpit). Le chemin classic (kanban 4 colonnes +
drag SortableJS + carte Tailwind `weak_point_card.py`) reste strictement
inchangé.
"""
from __future__ import annotations

import asyncio

from nicegui import ui
from loguru import logger

from backend.core.reviews import local_store
from backend.core.reviews.anchors import anchor_priority, anchor_status, is_anchor_due
from backend.config.settings import settings
from frontend.components.weak_point_card import _get
from frontend.components.weak_point_row import weak_point_row
from frontend.pages.weak_points import open_add_dialog
```

(Suppression de `import datetime` et des imports désormais inutiles ici — `datetime` était utilisé par `_fmt_date`/`_status_line`, déplacés dans `weak_point_row.py`.)

Remplacer le bloc `_CSS` (ancien : lignes ~43-103, incluant `.wp-layout`, `.wp-sidebar*`, `.wp-nav*`, `.wp-content*`, `.wp-pilotage*`, `.wp-kpis`, `.wp-source-*`, `.wp-card*`, `.wp-dot`, `.wp-main`, `.wp-meta*`) par :

```python
_CSS = """
.wp-wrap { max-width:860px; width:100%; margin:0 auto; display:flex; flex-direction:column; gap:18px; }
.wp-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 0; flex-wrap:wrap; }
.wp-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.wp-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.wp-subtitle .critical { color:var(--danger); font-weight:500; }
.wp-actions { display:flex; gap:8px; flex:0 0 auto; }
.wp-btn { display:inline-flex; align-items:center; gap:6px; height:32px; padding:0 14px; border-radius:6px;
  font-size:12.5px; font-weight:500; cursor:pointer; border:1px solid var(--border); background:var(--bg);
  color:var(--text) !important; white-space:nowrap;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard); }
.wp-btn:hover { background:var(--surface); border-color:var(--border-strong); }
.wp-btn.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-text) !important; }
.wp-btn.primary:hover { background:var(--accent-hover); }
.wp-btn.loading { opacity:.6; cursor:default; }
.wp-chips { display:flex; gap:6px; flex-wrap:wrap; }
.wp-chip { font-size:12px; font-weight:500; padding:5px 12px; border-radius:6px; cursor:pointer;
  border:1px solid var(--border); background:var(--bg); color:var(--text-muted);
  display:flex; align-items:center; gap:6px;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.wp-chip:hover { background:var(--surface); color:var(--text); }
.wp-chip.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
.wp-chip .n { font-family:var(--font-mono); font-size:10.5px; opacity:.75; }
.wp-list { display:flex; flex-direction:column; border-top:1px solid var(--border); }
.wp-empty { padding:32px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
@media (max-width: 640px) {
  .wp-topbar { flex-direction:column; }
  .wp-actions { width:100%; }
  .wp-btn { flex:1 1 auto; justify-content:center; }
}
"""
```

Ce bloc `_CSS` remplace l'ancien intégralement — rien d'autre n'est ajouté entre lui et la suite du fichier.

- [ ] **Step 2: Supprimer les fonctions déplacées ou mortes**

Supprimer entièrement de `frontend/pages/weak_points_cockpit.py` : `_MONTHS_FR`, `_fmt_date`, `_status_line`, `_dot_color`, `_STATUS_LABEL`, `_weak_point_summary` (les quatre premières déplacées dans `weak_point_row.py`, `_STATUS_LABEL` n'était utilisée que par `_status_line` donc supprimée avec elle, `_weak_point_summary` morte avec le panneau « Pilotage » supprimé). Conserver `filter_weak_points_view` sans modification (testée par `tests/test_weak_points_cockpit.py`).

- [ ] **Step 3: Réécrire `render_weak_points_cockpit` et les fonctions de dessin**

Remplacer tout le corps de `render_weak_points_cockpit()` jusqu'à la fin du fichier par :

```python
def render_weak_points_cockpit() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)

    state = {"view": "overview"}
    with ui.element("div").classes("wp-wrap"):
        topbar = ui.element("div").classes("wp-topbar")
        chips_row = ui.element("div").classes("wp-chips")
        list_col = ui.element("div").classes("wp-list")

    def _select_view(view: str) -> None:
        state["view"] = view
        _render()

    def _draw_chips(rows: list) -> None:
        chips_row.clear()
        counts = {
            "overview": len(filter_weak_points_view(rows, "overview")),
            "lacunes": len(filter_weak_points_view(rows, "lacunes")),
            "anchors": len(filter_weak_points_view(rows, "anchors")),
            "due": len(filter_weak_points_view(rows, "due")),
            "resolved": len(filter_weak_points_view(rows, "resolved")),
        }
        with chips_row:
            for key, label in (
                ("overview", "Toutes"),
                ("lacunes", "Lacunes"),
                ("anchors", "Ancrages"),
                ("due", "À revoir"),
                ("resolved", "Résolues"),
            ):
                chip = ui.element("div").classes(
                    "wp-chip active" if state["view"] == key else "wp-chip"
                )
                with chip:
                    ui.label(label)
                    ui.label(str(counts[key])).classes("n")
                chip.on("click", lambda key=key: _select_view(key))

    def _draw_topbar(rows: list) -> None:
        topbar.clear()
        n_critical = sum(
            1 for w in rows
            if int(_get(w, "severity", 2) or 2) >= 4
            and _get(w, "status", "active") != "résolue"
        )
        n_active = len(filter_weak_points_view(rows, "overview"))
        n_anchors = len(filter_weak_points_view(rows, "anchors"))
        n_resolved = len(filter_weak_points_view(rows, "resolved"))

        with topbar:
            with ui.column().classes("gap-0"):
                ui.label("Points faibles").classes("wp-title")
                with ui.element("div").classes("wp-subtitle"):
                    ui.label(f"{n_critical} critique{'s' if n_critical != 1 else ''}").classes("critical")
                    ui.label(
                        f" · {n_active} actif{'s' if n_active != 1 else ''}"
                        f" · {n_anchors} ancrage{'s' if n_anchors != 1 else ''}"
                        f" · {n_resolved} résolue{'s' if n_resolved != 1 else ''}"
                    )

            with ui.element("div").classes("wp-actions"):
                vault_ok = bool(settings.obsidian_vault_path)
                sync_btn = ui.element("div").classes(
                    "wp-btn" + ("" if vault_ok else " loading")
                )
                with sync_btn:
                    ui.label("Synchroniser Obsidian")
                if not vault_ok:
                    sync_btn.tooltip("Configurez OBSIDIAN_VAULT_PATH dans les paramètres")
                else:
                    sync_btn.on("click", lambda: asyncio.create_task(_run_sync(sync_btn)))

                add_btn = ui.element("div").classes("wp-btn primary")
                with add_btn:
                    ui.label("Créer une lacune")
                add_btn.on("click", lambda: open_add_dialog(_render))

    async def _run_sync(btn) -> None:
        btn.classes(add="loading")
        try:
            from backend.core.obsidian.weak_points_sync import weak_points_sync_service
            result = await asyncio.to_thread(weak_points_sync_service.sync)
            ui.notify(result.summary(), type="positive" if not result.errors else "warning")
            if result.errors:
                for err in result.errors:
                    logger.error(f"Sync lacune : {err}")
            _render()
        except Exception as exc:
            logger.exception("Erreur sync Obsidian lacunes")
            ui.notify(f"Erreur : {exc}", type="negative")
        finally:
            btn.classes(remove="loading")

    def _draw_list(rows: list) -> None:
        list_col.clear()
        with list_col:
            if not rows:
                with ui.element("div").classes("wp-empty"):
                    ui.label("Aucun point faible dans cette vue.")
                return
            for w in rows:
                weak_point_row(w, on_refresh=_render)

    def _render() -> None:
        rows = local_store.get_all_weak_points_table(limit=300)
        _draw_topbar(rows)
        _draw_chips(rows)
        _draw_list(filter_weak_points_view(rows, state["view"]))

    _render()
```

- [ ] **Step 4: Vérifier qu'aucune référence morte ne subsiste**

Run: `grep -n "wp-sidebar\|wp-pilotage\|wp-content\|WeakPointCard\|_weak_point_summary\|_status_line\|_dot_color" frontend/pages/weak_points_cockpit.py`
Expected: aucune sortie.

- [ ] **Step 5: Lancer la suite de tests existante sur ce fichier (doit encore passer sans modification)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weak_points_cockpit.py -v`
Expected: PASS (`filter_weak_points_view` inchangée)

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/weak_points_cockpit.py
git commit -m "refactor: écran Lacunes cockpit recentré, chips au lieu de sidebar+pilotage"
```

---

### Task 4: Réécrire les tests de régression de mise en page

**Files:**
- Modify: `tests/test_weak_points_cockpit_ui.py`

**Interfaces:**
- Consumes : lit le texte source de `frontend/pages/weak_points_cockpit.py` (Task 3) par assertions de chaîne — même pattern que `tests/test_todo_cockpit_ui.py::test_revision_page_uses_shared_grid_and_full_width_layout`.
- Produces : rien consommé par d'autres tâches.

Le fichier actuel teste `_weak_point_summary` (fonction supprimée en Task 3) et verrouille l'ancienne mise en page (`WeakPointCard`, `max-width:none`, `Pilotage des lacunes`) — les deux sont devenus incorrects après ce refactor.

- [ ] **Step 1: Remplacer tout le contenu du fichier**

```python
def test_weak_point_cockpit_uses_row_component_and_centered_column():
    source = open("frontend/pages/weak_points_cockpit.py", encoding="utf-8").read()

    assert "weak_point_row(w, on_refresh=_render)" in source
    assert ".wp-wrap { max-width:860px; width:100%; margin:0 auto;" in source
    assert '"wp-chip active" if state["view"] == key else "wp-chip"' in source
    assert "Créer une lacune" in source
    assert "WeakPointCard" not in source
    assert "Pilotage des lacunes" not in source
    assert "_weak_point_summary" not in source
```

- [ ] **Step 2: Lancer le test, vérifier qu'il passe**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weak_points_cockpit_ui.py -v`
Expected: PASS

- [ ] **Step 3: Lancer toute la suite liée aux lacunes pour confirmer l'absence de régression**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weak_points_cockpit.py tests/test_weak_points_cockpit_ui.py tests/test_weak_point_row.py tests/test_weak_points_sync.py -v`
Expected: PASS (tous)

- [ ] **Step 4: Commit**

```bash
git add tests/test_weak_points_cockpit_ui.py
git commit -m "test: verrouille la nouvelle mise en page (chips + colonne centrée) de l'écran Lacunes"
```

---

### Task 5: Vérification navigateur et commit final

**Files:** aucun (vérification manuelle uniquement — le projet exige une vérification au navigateur avant de considérer un écran cockpit terminé).

**Interfaces:** N/A.

- [ ] **Step 1: Démarrer le serveur**

Utiliser `preview_start` avec la configuration `.claude/launch.json` existante (`name: "synapse"`), ou :

Run: `.venv/Scripts/python.exe main.py` (avec `SYNAPSE_ENV=prod` déjà posé par `.claude/run_synapse.bat`), port 8082.

- [ ] **Step 2: Naviguer sur `/lacunes` en mode cockpit**

Vérifier au navigateur (`read_page` + `computer` screenshot) :
- Topbar centrée, colonne à 860px (comparer visuellement à `design_handoff_synapse_refonte/screenshots/09-lacunes.png`).
- Chips « Toutes / Lacunes / Ancrages / À revoir / Résolues » cliquables, filtrent la liste (vérifier avec la vraie donnée existante : « Point faible : traitement », active).
- Ligne au survol : les métadonnées (collège + id) cèdent la place aux icônes d'action sans saut de mise en page.
- Ligne résolue (s'il en existe une, sinon utiliser un point faible de test ajouté puis supprimé immédiatement comme fait à l'étape 14 Externat) : opacité réduite.
- Bascule sombre : vérifier que les tokens `--*` s'appliquent (pas de couleur en dur oubliée).
- Bouton « Synchroniser Obsidian » et « Créer une lacune » fonctionnent toujours comme avant (comportement inchangé, non retesté fonctionnellement ici — déjà couvert par `tests/test_weak_points_sync.py`).

- [ ] **Step 3: Confirmer zéro exception serveur**

Vérifier les logs serveur (`preview_logs` ou console) : aucune trace Python pendant la navigation et les clics de chips.

- [ ] **Step 4: Mettre à jour le journal de la refonte**

Ajouter cette entrée à la fin de la section **Journal** de `design_handoff_synapse_refonte/CLAUDE.md` (après la dernière entrée « 2026-07-27 — Étape 15 »), même format que les entrées existantes :

```markdown
- **2026-07-28 — Recentrage Lacunes.** Modifiés : `frontend/pages/weak_points_cockpit.py`, nouveau `frontend/components/weak_point_row.py`. Voir `docs/superpowers/specs/2026-07-28-lacunes-cockpit-refonte-design.md` et `docs/superpowers/plans/2026-07-28-lacunes-cockpit-refonte.md`.
  - **Correction d'une dérive de l'étape 11.** La sidebar de navigation interne et le panneau « Pilotage des lacunes » (ajoutés par le spec du 28/07 sur l'interactivité de la carte) n'avaient pas de base dans le README §9 ni dans `09-lacunes.png` ; supprimés au profit de chips horizontales (même pattern qu'Items) et d'une colonne unique recentrée à 860px.
  - **La carte cockpit réutilisait encore `WeakPointCard` (classic, Tailwind)** — jamais remplacée par les classes `.wp-card`/`.wp-dot` déjà écrites (et jamais utilisées) à l'étape 11. Nouveau composant `weak_point_row.py` sur tokens `--*`, ligne plate 50px, actions révélées au survol comme `study_task_row` (Révisions). `_status_line`/`_dot_color` (mortes depuis l'étape 11) déplacées et enfin branchées.
  - Chemin classic (`weak_points.py`, kanban, `weak_point_card.py`) non touché.
```

- [ ] **Step 5: Commit final**

```bash
git add design_handoff_synapse_refonte/CLAUDE.md
git commit -m "docs: journal — recentrage écran Lacunes cockpit"
```
