# College & CourseCard Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the off-brand orange in the college switcher and turn `CourseCard`'s hover-only action bar into a permanently visible toolbar with 5 primary actions (Notion, OIC LiSA, +Lecture, QCM, Séance), moving everything else into a header overflow menu.

**Architecture:** Two independent visual fixes in the existing NiceGUI frontend, no data-model or backend changes. Fix 1 is a pure-data dict edit (testable with pytest). Fixes 2-3 are NiceGUI render-tree edits (verified by running the dev server, since this codebase has no NiceGUI component test harness — see `tests/` which only covers `backend/*`).

**Tech Stack:** Python 3, NiceGUI (Quasar/Material icons), Tailwind utility classes, plain CSS (`static/synapse.css`).

## Global Constraints

- Fragile mastery color: fill `#B45309` (existing DA token `--s-amber-700`), ghost `rgba(180,83,9,0.12)`, tint `rgba(180,83,9,0.05)`. Other mastery levels (`solide`, `correct`, `non_commence`) stay unchanged.
- No change to dialog/action logic — `quick_mark_course_action`, `open_quick_session_dialog`, `open_lisa_dialog`, `_open_quick_qcm_dialog`, `open_pdf_wizard`, `open_start_tracking_dialog`, `_open_obsidian_note_action`, `_create_obsidian_note_action`, `_open_link_note_dialog` keep their exact signatures and behavior — only their visual entry point (toolbar button vs menu item) moves.
- `CourseCard(course, context="college", refresh_fn=None, client=None, accent_color=None, is_urgent=False)` keeps this exact signature — Semestres/Externat pages call it unchanged and must keep working without any caller-side edit.
- Dev server: `python main.py` (serves on `http://localhost:8082`). Stop with `kill_synapse.bat` (repo root) — it also cleans up orphaned `spawn_main` subprocesses NiceGUI's `reload=True` can leave behind holding the port.
- This repo has no automated UI test harness for NiceGUI pages — frontend changes are verified by running the dev server and checking in a browser, not by pytest.

---

## File Structure

- **Modify** `frontend/pages/colleges.py` — `_FILL`, `_GHOST`, `_TINT` dicts (lines 26-43): fragile color values only.
- **Create** `tests/test_colleges_mastery_colors.py` — regression test locking the fragile color tokens.
- **Modify** `static/synapse.css` — `.synapse-action-bar` rule (lines 1020-1042): remove hover-reveal opacity/transform, make the bar visible by default.
- **Modify** `frontend/components/course_card.py` — `CourseCard()` function body: relocate the `⋯` overflow menu trigger into the header row (next to the mastery dot), add PDF/Obsidian entries to that menu, remove the entries now promoted to the toolbar (Nouvelle séance, Fiche LISA's OIC dialog, Notion), and rebuild the action bar with Notion / OIC / +Lecture / QCM / Séance.

---

### Task 1: Fix mastery "fragile" color to match DA token

**Files:**
- Modify: `frontend/pages/colleges.py:26-43`
- Test: `tests/test_colleges_mastery_colors.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_FILL["fragile"]`, `_GHOST["fragile"]`, `_TINT["fragile"]` — read elsewhere in `colleges.py` (`_show()` closure) to color the college-switcher border, stats text class lookup key, and coverage gauge. No signature changes, so no downstream code needs edits.

- [ ] **Step 1: Write the failing test**

Create `tests/test_colleges_mastery_colors.py`:

```python
"""Tests pour les tokens de couleur de mastery du switch collèges."""
from frontend.pages.colleges import _FILL, _GHOST, _TINT


def test_fragile_uses_da_amber_token():
    assert _FILL["fragile"] == "#B45309"


def test_fragile_ghost_matches_fill_rgb():
    assert _GHOST["fragile"] == "rgba(180,83,9,0.12)"


def test_fragile_tint_matches_fill_rgb():
    assert _TINT["fragile"] == "rgba(180,83,9,0.05)"


def test_other_levels_unchanged():
    assert _FILL["solide"] == "#059669"
    assert _FILL["correct"] == "#3B82F6"
    assert _FILL["non_commence"] == "#CBD5E1"
    assert _GHOST["solide"] == "rgba(5,150,105,0.12)"
    assert _TINT["non_commence"] == "transparent"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_colleges_mastery_colors.py -v`
Expected: `test_fragile_uses_da_amber_token` and the two rgba tests FAIL — actual values are `#D97706` / `rgba(217,119,6,...)`. `test_other_levels_unchanged` PASSES (those levels are untouched).

- [ ] **Step 3: Edit the color dicts**

In `frontend/pages/colleges.py`, replace:

```python
_FILL = {
    "solide":       "#059669",
    "correct":      "#3B82F6",
    "fragile":      "#D97706",
    "non_commence": "#CBD5E1",
}
_GHOST = {
    "solide":       "rgba(5,150,105,0.12)",
    "correct":      "rgba(59,130,246,0.12)",
    "fragile":      "rgba(217,119,6,0.12)",
    "non_commence": "rgba(203,213,225,0.20)",
}
_TINT = {
    "solide":       "rgba(5,150,105,0.05)",
    "correct":      "rgba(59,130,246,0.05)",
    "fragile":      "rgba(217,119,6,0.05)",
    "non_commence": "transparent",
}
```

with:

```python
_FILL = {
    "solide":       "#059669",
    "correct":      "#3B82F6",
    "fragile":      "#B45309",
    "non_commence": "#CBD5E1",
}
_GHOST = {
    "solide":       "rgba(5,150,105,0.12)",
    "correct":      "rgba(59,130,246,0.12)",
    "fragile":      "rgba(180,83,9,0.12)",
    "non_commence": "rgba(203,213,225,0.20)",
}
_TINT = {
    "solide":       "rgba(5,150,105,0.05)",
    "correct":      "rgba(59,130,246,0.05)",
    "fragile":      "rgba(180,83,9,0.05)",
    "non_commence": "transparent",
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_colleges_mastery_colors.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/colleges.py tests/test_colleges_mastery_colors.py
git commit -m "fix: use DA amber token for fragile mastery color in college switcher"
```

---

### Task 2: Make the CourseCard action bar permanently visible

**Files:**
- Modify: `static/synapse.css:1020-1042`

**Interfaces:**
- Consumes: `.synapse-action-bar` class, applied by `CourseCard()` in `frontend/components/course_card.py` (unchanged by this task — Task 3 edits its contents).
- Produces: `.synapse-action-bar` renders visible by default in both themes; no more `opacity`/`transform` gated by `:hover`. Task 3 relies on this being already in place before restructuring the bar's contents (so the intermediate state — old buttons, always visible — is itself reviewable/testable in the browser).

- [ ] **Step 1: Edit the CSS rule**

In `static/synapse.css`, replace:

```css
/* Action bar — émerge du bas au hover */
.synapse-action-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border-top: 1px solid #F1F5F9;
  background: #F8FAFC;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 200ms ease-out, transform 200ms ease-out;
  pointer-events: none;
  flex-shrink: 0;
}
.q-card.synapse-course-card:hover .synapse-action-bar {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}
body.body--dark .synapse-action-bar {
  border-top-color: #1E2D3D;
  background: #0F172A;
}
```

with:

```css
/* Action bar — toujours visible (plus de hover-reveal) */
.synapse-action-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border-top: 1px solid #F1F5F9;
  background: #F8FAFC;
  flex-shrink: 0;
}
body.body--dark .synapse-action-bar {
  border-top-color: #1E2D3D;
  background: #0F172A;
}
```

- [ ] **Step 2: Start the dev server**

Run: `python main.py` (from repo root; leave it running in the background)
Expected: log line showing NiceGUI listening on `http://localhost:8082` with no startup errors.

- [ ] **Step 3: Manually verify in the browser**

Navigate to `http://localhost:8082/colleges`, pick a college with courses.
Expected: every `CourseCard` shows its action-bar row (PDF/QCM/Obsidian/+1/⋯ — still the old button set at this point) immediately, without needing to hover. Toggle dark mode (moon icon in top nav) and confirm the bar's background/border stay legible in both themes.

- [ ] **Step 4: Stop the dev server**

Run: `kill_synapse.bat` (repo root)
Expected: `Done.` printed, port 8082 free (`netstat -ano | findstr :8082` returns nothing).

- [ ] **Step 5: Commit**

```bash
git add static/synapse.css
git commit -m "fix: make CourseCard action bar permanently visible instead of hover-only"
```

---

### Task 3: Restructure CourseCard toolbar and overflow menu

**Files:**
- Modify: `frontend/components/course_card.py` (full `CourseCard()` function body — header row, action bar, and menu all move together since the menu trigger relocates from the action bar into the header)

**Interfaces:**
- Consumes: `quick_mark_course_action`, `open_quick_session_dialog`, `open_start_tracking_dialog`, `_open_quick_qcm_dialog`, `_open_obsidian_note_action`, `_create_obsidian_note_action`, `_open_link_note_dialog`, `open_pdf_wizard` from `frontend.components.course_quick_actions` (signatures unchanged, imports unchanged); `open_lisa_dialog(course)` from `frontend.components.lisa_dialog` (unchanged).
- Produces: `CourseCard(course, context="college", refresh_fn=None, client=None, accent_color=None, is_urgent=False)` — same public signature, same import path (`frontend.components.course_card.CourseCard`), so `colleges.py`, `semestres.py`, and any other caller need zero changes.

- [ ] **Step 1: Replace the `CourseCard()` function body**

In `frontend/components/course_card.py`, the imports and `_ACCENT_HEX` dict (lines 1-48) stay unchanged. Replace everything from `def CourseCard(` to the end of the file with:

```python
def CourseCard(
    course,
    context: str = "college",
    refresh_fn=None,
    client=None,
    accent_color: str | None = None,
    is_urgent: bool = False,
) -> None:
    if client is None:
        try:
            client = ui.context.client
        except Exception:
            client = None

    # ── Données ───────────────────────────────────────────────────────────────
    if context == "college":
        has_pdf   = bool(getattr(course, "url_pdf", None))
        nb_lec    = getattr(course, "nb_lectures", 0) or 0
        date_1ere = getattr(course, "date_1ere_lecture", None)
    else:
        has_pdf   = bool(getattr(course, "url_pdf_ue", None))
        nb_lec    = getattr(course, "nb_lectures_ue", 0) or 0
        date_1ere = getattr(course, "date_1ere_lecture_ue", None)

    anki_done    = getattr(course, "anki", False)
    qcm_done     = getattr(course, "qcm_done", False)
    resume_done  = getattr(course, "resume_done", False)
    chatgpt_done = getattr(course, "chatgpt_done", False)
    item_lbl     = (
        f"ITEM {course.display_item_number}"
        if getattr(course, "display_item_number", None) else None
    )

    accent_hex = "#DC2626" if is_urgent else _ACCENT_HEX.get(accent_color or "", "#94A3B8")

    date_str = None
    if date_1ere:
        date_str = (
            date_1ere.strftime("%d/%m")
            if hasattr(date_1ere, "strftime") else str(date_1ere)
        )

    def _run(action_key: str):
        return lambda: asyncio.create_task(
            quick_mark_course_action(course, action_key, context=context, refresh_fn=refresh_fn, client=client)
        )

    # Obsidian
    _obs_configured = bool(_settings.obsidian_vault_path)
    _obs_uri        = getattr(course, "obsidian_uri", None)
    _obs_exists     = obsidian_service.note_exists(course) if _obs_configured else False

    # URLs externes
    from backend.core.lisa.item_map import lisa_url as _lisa_url_from_map
    _lisa_url   = _lisa_url_from_map(course.display_item_number, course.title)
    _notion_url = f"https://www.notion.so/{course.id.replace('-', '')}"

    # ── Card ──────────────────────────────────────────────────────────────────
    with ui.card().classes(
        "synapse-course-card w-full"
    ).style(f"--card-accent:{accent_hex};"):

        # ── Corps ─────────────────────────────────────────────────────────────
        with ui.element("div").classes("px-3.5 pt-3.5 pb-3 flex flex-col gap-2 flex-1"):

            # Header : ITEM · [spacer] · dot · statut lecture · menu ⋯
            with ui.row().classes("items-center gap-1.5 w-full"):
                if item_lbl:
                    ui.label(item_lbl).classes(
                        "synapse-item-mono px-1.5 py-0.5 rounded "
                        "bg-slate-100 dark:bg-slate-800 "
                        "text-slate-500 dark:text-slate-400 shrink-0"
                    )
                if is_urgent:
                    ui.badge("En retard", color="red").classes(
                        "text-[10px] font-bold px-1.5 py-0.5 shrink-0 cursor-pointer"
                    ).on("click", lambda: open_start_tracking_dialog(
                        course, context, refresh_fn, client, is_restart=True
                    )).tooltip("Révision J30 dépassée — cliquer pour redémarrer le suivi espacé")
                ui.element("div").classes("flex-1")

                # Dot maîtrise + label court
                _mastery_labels = {
                    "green": "Solide", "blue": "Correct",
                    "orange": "Fragile", "red": "Critique",
                    "gray": "Non commencé", "slate": "Non commencé",
                }
                _mastery_lbl = _mastery_labels.get(accent_color or "gray", "")
                _tooltip_txt = f"Maîtrise : {_mastery_lbl}" if _mastery_lbl else "Maîtrise non évaluée"
                with ui.row().classes("items-center gap-1 shrink-0").tooltip(_tooltip_txt):
                    ui.element("div").style(
                        f"width:7px;height:7px;border-radius:50%;"
                        f"background:{accent_hex};flex-shrink:0;"
                    )
                    if _mastery_lbl:
                        ui.label(_mastery_lbl).classes(
                            "text-[10px] text-slate-400 dark:text-slate-500 shrink-0 leading-none"
                        )

                # Statut lecture
                _lec_parts = []
                if date_str:
                    _lec_parts.append(f"1ère {date_str}")
                if nb_lec > 0:
                    _lec_parts.append(f"Lu {nb_lec}×")
                if _lec_parts:
                    ui.label(" · ".join(_lec_parts)).classes(
                        "synapse-lec-mono text-slate-400 dark:text-slate-500 shrink-0"
                    )

                # ⋯ Menu — actions secondaires (PDF, suivi, liens, Obsidian, complétion)
                with ui.button(icon="more_vert").props(
                    "flat round dense size=xs"
                ).classes("text-slate-300 dark:text-slate-600 shrink-0 -mr-1"):
                    with ui.menu().classes("w-64"):

                        # ── 1. PDF ─────────────────────────────────────────────
                        if has_pdf:
                            ui.menu_item(
                                "Ouvrir le PDF",
                                on_click=lambda c=course: ui.navigate.to(f"/pdf/{c.id}", new_tab=True),
                            ).props("dense").classes("text-[13px]")
                        else:
                            ui.menu_item(
                                "Chercher un PDF…",
                                on_click=lambda c=course: open_pdf_wizard(c, context, refresh_fn, client),
                            ).props("dense").classes("text-[13px]")

                        ui.separator().classes("my-1")

                        # ── 2. Suivi de lecture ───────────────────────────────
                        _is_relance = bool(date_1ere)
                        if _is_relance:
                            ui.menu_item(
                                f"Suivi depuis {date_str}…",
                                on_click=lambda: open_start_tracking_dialog(
                                    course, context, refresh_fn, client, True
                                ),
                            ).props("dense").classes("text-[13px]")
                        else:
                            ui.menu_item(
                                "Démarrer le suivi J3/J7/J14/J30",
                                on_click=lambda: open_start_tracking_dialog(
                                    course, context, refresh_fn, client, False
                                ),
                            ).props("dense").classes("text-[13px]")

                        ui.separator().classes("my-1")

                        # ── 3. Liens externes & Obsidian ──────────────────────
                        ui.menu_item(
                            "Fiche LISA",
                            on_click=lambda url=_lisa_url: ui.navigate.to(url, new_tab=True),
                        ).props("dense").classes("text-[13px]")

                        if getattr(course, "agregation_fiche_edn", None):
                            ui.menu_item(
                                "Fiche EDN",
                                on_click=lambda url=course.agregation_fiche_edn: ui.navigate.to(
                                    url, new_tab=True
                                ),
                            ).props("dense").classes("text-[13px]")

                        if _obs_configured:
                            if _obs_uri or _obs_exists:
                                ui.menu_item(
                                    "Ouvrir note Obsidian",
                                    on_click=lambda c=course: _open_obsidian_note_action(c),
                                ).props("dense").classes("text-[13px]")
                            else:
                                ui.menu_item(
                                    "Créer note Obsidian",
                                    on_click=lambda c=course: asyncio.create_task(
                                        _create_obsidian_note_action(c, refresh_fn, client)
                                    ),
                                ).props("dense").classes("text-[13px]")
                            ui.menu_item(
                                "Lier note Obsidian…",
                                on_click=lambda c=course: _open_link_note_dialog(c, refresh_fn),
                            ).props("dense").classes("text-[13px]")

                        ui.separator().classes("my-1")

                        # ── 4. Section complétion ─────────────────────────────
                        with ui.element("div").classes("px-2 pt-1 pb-1.5"):
                            ui.label("Complétion").classes(
                                "text-[10px] font-bold uppercase tracking-wider "
                                "text-slate-400 px-2 mb-1.5 block"
                            )

                            _completions = [
                                ("Résumé",  resume_done,  "resume"),
                                ("ChatGPT", chatgpt_done, "chatgpt"),
                                ("Anki",    anki_done,    "anki"),
                            ]
                            for lbl, done, key in _completions:
                                with ui.element("div").classes(
                                    "flex items-center gap-2.5 px-2 py-1.5 rounded-md "
                                    "cursor-pointer select-none "
                                    "hover:bg-slate-50 dark:hover:bg-slate-800/60"
                                ).on("click", _run(key)):
                                    ui.icon(
                                        "check_circle" if done else "radio_button_unchecked"
                                    ).classes(
                                        "text-[18px] shrink-0 " + (
                                            "text-green-500" if done
                                            else "text-slate-300 dark:text-slate-600"
                                        )
                                    )
                                    ui.label(lbl).classes(
                                        "text-[13px] " + (
                                            "text-slate-800 dark:text-slate-100 font-medium" if done
                                            else "text-slate-400 dark:text-slate-500"
                                        )
                                    )

            # Titre
            ui.label(course.title).classes(
                "text-[14px] font-semibold text-slate-900 dark:text-slate-100 leading-snug"
            ).style(
                "display:-webkit-box;-webkit-line-clamp:2;"
                "-webkit-box-orient:vertical;overflow:hidden;word-break:break-word"
            ).tooltip(course.title)

        # ── Barre d'actions — toujours visible : les 5 actions les + fréquentes ──
        with ui.element("div").classes("synapse-action-bar"):

            # Notion
            ui.button(
                icon="description",
                on_click=lambda url=_notion_url: ui.navigate.to(url, new_tab=True),
            ).props("flat round dense size=sm").classes(
                "text-slate-700 dark:text-slate-300 shrink-0"
            ).tooltip("Ouvrir dans Notion")

            # OIC LiSA
            ui.button(
                icon="flag",
                on_click=lambda c=course: open_lisa_dialog(c),
            ).props("flat round dense size=sm color=violet").classes(
                "shrink-0"
            ).tooltip("Objectifs OIC (LiSA)")

            # +1 lecture
            ui.button(
                icon="add_circle",
                on_click=_run("lecture"),
            ).props("flat round dense size=sm color=green").classes(
                "shrink-0"
            ).tooltip(f"Ajouter une lecture (actuellement {nb_lec}×)")

            # QCM — état reflète qcm_done, comportement inchangé
            if qcm_done:
                ui.button(
                    icon="quiz",
                    on_click=_run("qcm"),
                ).props("flat round dense size=sm color=violet").classes(
                    "shrink-0"
                ).tooltip("QCM fait — cliquer pour basculer")
            else:
                ui.button(
                    icon="quiz",
                    on_click=lambda c=course: _open_quick_qcm_dialog(c, refresh_fn),
                ).props("flat round dense size=sm color=grey").classes(
                    "shrink-0"
                ).tooltip("Logger un résultat QCM")

            ui.element("div").classes("flex-1")

            # Séance — CTA principal
            ui.button(
                "Séance",
                icon="add_task",
                on_click=lambda: open_quick_session_dialog(course, refresh_fn, client),
            ).props("unelevated rounded dense size=sm color=violet").classes(
                "shrink-0 text-white"
            ).tooltip("Nouvelle séance de travail")
```

- [ ] **Step 2: Start the dev server**

Run: `python main.py`
Expected: NiceGUI listening on `http://localhost:8082`, no traceback in the console (a Python `SyntaxError`/`NameError` in this file would show up here immediately).

- [ ] **Step 3: Manually verify the toolbar**

Navigate to `http://localhost:8082/colleges`, select a college with at least one course that has a PDF and one without.
Expected:
- Every card shows, without hovering: Notion icon, OIC flag icon (opens the OIC dialog on click), a green "+" icon (increments the "Lu N×" counter in the header on click), a QCM icon (grey if not done, violet if done), and a violet "Séance" button on the right that opens the session dialog.
- Click the grey QCM icon on a card where `qcm_done` is false → the quick QCM dialog opens (not a toggle).
- Click a violet QCM icon (where `qcm_done` is true) → it toggles off immediately (same as before this change).

- [ ] **Step 4: Manually verify the header overflow menu**

Click the small `⋯` (`more_vert`) icon next to the mastery dot in the card header.
Expected: menu opens with, in order: PDF entry (label depends on whether the course has a PDF), separator, tracking entry ("Suivi depuis …" or "Démarrer le suivi …"), separator, "Fiche LISA", "Fiche EDN" (only if the course has `agregation_fiche_edn`), Obsidian entries (only if `OBSIDIAN_VAULT_PATH` is configured in `.env`), separator, "Complétion" section with Résumé/ChatGPT/Anki toggles. Confirm there is **no** "Nouvelle séance", "Ouvrir dans Notion", or "Objectifs (OIC)" entry left in this menu (they're now toolbar buttons).

- [ ] **Step 5: Verify Semestres/Externat pages still render**

Navigate to `http://localhost:8082/semestres` (or the equivalent UE page) and confirm `CourseCard` renders there too with the same new toolbar — this page calls `CourseCard(..., context="ue", ...)` and must work with zero code changes on its side.

- [ ] **Step 6: Stop the dev server**

Run: `kill_synapse.bat`
Expected: `Done.`, port 8082 free.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/course_card.py
git commit -m "feat: promote Notion/OIC/+Lecture/QCM/Séance to a permanent CourseCard toolbar"
```

---

## Self-Review Notes

- **Spec coverage:** §1 (color fix) → Task 1. §2.2 (toolbar) and §2.3 (header overflow) → Task 3, staged after Task 2 makes the bar visible. §2.4 (CSS) → Task 2. §3 (blue dot) → no task, explicitly out of scope per spec. "Hors scope" section (no dialog logic changes, no Semestres/Externat code changes) → verified in Task 3 Step 5 and preserved by keeping every consumed function's call signature identical.
- **Placeholder scan:** none — every step has literal file paths, full code blocks, and exact commands.
- **Type/signature consistency:** `CourseCard()` signature identical before/after. All consumed functions (`quick_mark_course_action`, `open_quick_session_dialog`, `open_start_tracking_dialog`, `_open_quick_qcm_dialog`, `open_pdf_wizard`, `_open_obsidian_note_action`, `_create_obsidian_note_action`, `_open_link_note_dialog`, `open_lisa_dialog`) called with the exact same argument lists as in the current file — verified against `frontend/components/course_card.py` and `frontend/components/course_quick_actions.py` as they exist today.
