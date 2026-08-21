# Chantier B2 — Les deux wizards : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retokeniser les deux seuls composants encore en Tailwind brut de l'application — le dialogue mnémo/image et le dialogue de validation de séance — pour qu'ils réagissent au thème, n'affichent plus d'emoji, et n'utilisent de couleur que pour l'accent ou une vraie sémantique (rouge/ambre/vert = urgence/santé uniquement, jamais décoratif).

**Architecture:** Chaque tâche modifie un dialogue NiceGUI existant en place, sans changer sa structure, ses champs ni sa logique de soumission — uniquement les classes Tailwind/`props` codées en dur remplacées par des tokens `var(--*)` ou par `color=primary`/`positive`/`warning`/`negative`. Chaque tâche est vérifiée par un test qui inspecte la source du fichier (`Path(...).read_text()`), même convention que les chantiers A et B1.

**Tech Stack:** Python 3.12, NiceGUI (Quasar/Vue), pytest.

## Global Constraints

- Réponses et messages d'interface en français.
- Aucun changement de structure, de champs, de callbacks ou de logique de soumission dans les deux
  dialogues — uniquement l'apparence.
- Aucune couleur Quasar arbitraire (`indigo`, `red`, `orange`, `deep-orange`, `blue`, `purple`,
  `pink`, `teal`, `blue-grey`, `violet`) ne doit survivre en dehors des trois groupes déjà
  sémantiquement corrects (`DIFF_OPTS`, `QCM_OPTS`, et le triplet `solide`/`correct`/`flou` du
  bloc « Où en es-tu sur cet item ? »).
- `open_sr_help_dialog`, `show_bilan_session`, `open_lacune_inline_dialog` (même fichier que le
  wizard de séance) ne sont **pas** touchés — hors périmètre explicite.
- Toute recherche/remplacement de couleur dans `open_session_feedback_dialog` doit rester scopée
  au corps de cette fonction (lignes 210-539) : `open_sr_help_dialog` (lignes ~34-70, même fichier)
  utilise aussi `blue`, `indigo`, `purple` pour des badges de cycle J3/J7/J14/J30 sans rapport —
  un remplacement sur tout le fichier les toucherait par erreur.
- Commit après chaque tâche, message en anglais préfixé `fix:`/`refactor:` (convention du dépôt).
- Les tests tournent avec `./.venv/Scripts/python.exe -m pytest` depuis la racine du dépôt.

## File Structure

| Fichier | Changement | Tâche |
|---|---|---|
| `frontend/components/obsidian_quick_edit_dialog.py` | Carte/textarea/upload retokenisés, emojis retirés, `indigo` → `primary` | 1 |
| `frontend/pages/dashboard/_dialogs.py` | `open_session_feedback_dialog` : centrage + tokens généraux (tâche 2), puis simplification des couleurs de puces (tâche 3) | 2, 3 |
| `tests/test_b2_mnemo_wizard.py` | nouveau — couvre tâche 1 | 1 |
| `tests/test_b2_session_feedback_shell.py` | nouveau — couvre tâche 2 | 2 |
| `tests/test_b2_session_feedback_chips.py` | nouveau — couvre tâche 3 | 3 |

---

### Task 1: Wizard mnémo/image — thème réactif, zéro emoji

**Files:**
- Modify: `frontend/components/obsidian_quick_edit_dialog.py` (fichier entier, 94 lignes)
- Test: `tests/test_b2_mnemo_wizard.py` (créer)

**Interfaces:**
- Consumes: `obsidian_service.append_mnemonic_or_image` (inchangé).
- Produces: `open_obsidian_quick_edit_dialog(course, on_success=None) -> None` — signature inchangée.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b2_mnemo_wizard.py` :

```python
"""Le wizard mnémo/image réagit au thème (au lieu d'être toujours sombre) et
n'affiche plus aucun emoji, conformément au design system."""
from pathlib import Path

_SOURCE_PATH = "frontend/components/obsidian_quick_edit_dialog.py"


def test_mnemo_dialog_reacts_to_theme_instead_of_being_always_dark():
    source = Path(_SOURCE_PATH).read_text(encoding="utf-8")
    assert "bg-slate-900" not in source
    assert "text-white" not in source
    assert "outlined dark rows=3" not in source
    assert "flat bordered dark" not in source
    assert "background:var(--bg)" in source
    assert "color:var(--text)" in source


def test_mnemo_dialog_has_no_emoji():
    source = Path(_SOURCE_PATH).read_text(encoding="utf-8")
    for emoji in ("💡", "📷", "⚠️"):
        assert emoji not in source, f"emoji {emoji!r} still present"


def test_mnemo_dialog_uses_primary_instead_of_arbitrary_indigo():
    source = Path(_SOURCE_PATH).read_text(encoding="utf-8")
    assert "color=indigo" not in source
    assert "color=primary" in source


def test_mnemo_dialog_keeps_its_public_signature():
    """Non-régression : la fonction publique garde sa signature — seul
    l'habillage visuel change, aucune structure n'est touchée."""
    import inspect

    from frontend.components.obsidian_quick_edit_dialog import open_obsidian_quick_edit_dialog

    params = list(inspect.signature(open_obsidian_quick_edit_dialog).parameters)
    assert params == ["course", "on_success"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b2_mnemo_wizard.py -v`
Expected: FAIL sur les 3 premiers tests (les emojis, `bg-slate-900` et `color=indigo` sont toujours
présents) ; le 4ᵉ passe déjà (signature déjà correcte).

- [ ] **Step 3: Retokeniser le fichier**

Remplacer le contenu de `frontend/components/obsidian_quick_edit_dialog.py` en entier par :

```python
"""
obsidian_quick_edit_dialog.py — Synapse
---------------------------------------
Modale NiceGUI d'ajout rapide d'un moyen mnémotechnique, piège EDN ou d'une image
directement dans la note Obsidian du cours.
"""

from __future__ import annotations
from typing import Callable, Optional
from nicegui import ui, events
from loguru import logger

from backend.core.obsidian.service import obsidian_service


def open_obsidian_quick_edit_dialog(
    course,
    on_success: Optional[Callable[[], None]] = None,
) -> None:
    """Ouvre une modale permettant de saisir un texte et/ou d'uploader une image vers la note Obsidian."""
    if course is None:
        ui.notify("Aucun cours sélectionné", type="warning")
        return

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg p-6").style(
        "background:var(--bg); color:var(--text); border:1px solid var(--border); "
        "border-radius:var(--radius-lg); box-shadow:var(--shadow-popover);"
    ):
        ui.label(
            f"Ajouter à Obsidian — Item {getattr(course, 'display_item_number', '')}"
        ).classes("text-lg font-bold mb-2").style("color:var(--accent);")
        ui.label(course.title).classes("text-sm mb-4").style("color:var(--text-muted);")

        # Type d'élément
        target_section = ui.radio(
            options={"mnemo": "Moyen Mnémotechnique / À savoir", "piege": "Piège EDN / Zéro au dossier"},
            value="mnemo",
        ).props("inline color=primary").classes("mb-4 text-sm")

        # Zone de texte
        text_input = ui.textarea(
            label="Texte ou mnémotechnique",
            placeholder="Ex: TRAP: Tension / Remplissage / Atropine / Pace...",
        ).props("outlined rows=3").classes("w-full mb-4")

        # Zone upload image
        image_bytes: list[bytes] = []
        image_filename: list[str] = []

        def handle_upload(e: events.UploadEventArguments):
            try:
                content = e.content.read()
                image_bytes.clear()
                image_bytes.append(content)
                image_filename.clear()
                image_filename.append(e.name)
                ui.notify(f"Image chargée : {e.name}", type="positive")
            except Exception as exc:
                logger.error(f"Erreur upload image : {exc}")
                ui.notify("Erreur lors du chargement de l'image", type="negative")

        ui.label("Image / Schéma (optionnel)").classes("text-xs font-semibold mb-1").style(
            "color:var(--text-muted);"
        )
        ui.upload(
            on_upload=handle_upload,
            max_files=1,
            auto_upload=True,
        ).props("accept='image/*' flat bordered").classes("w-full mb-4 text-xs")

        def submit():
            txt = text_input.value or ""
            img_b = image_bytes[0] if image_bytes else None
            img_fn = image_filename[0] if image_filename else None

            if not txt and not img_b:
                ui.notify("Saisissez du texte ou joignez une image", type="warning")
                return

            ok = obsidian_service.append_mnemonic_or_image(
                course,
                text_content=txt if txt else None,
                image_bytes=img_b,
                image_filename=img_fn,
                target_section=target_section.value,
            )

            if ok:
                ui.notify("Note Obsidian mise à jour !", type="positive", icon="check_circle")
                dialog.close()
                if on_success:
                    on_success()
            else:
                ui.notify("Impossible de mettre à jour la note Obsidian", type="negative")

        with ui.row().classes("w-full justify-end gap-3 mt-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat color=grey")
            ui.button("Enregistrer sur Obsidian", on_click=submit).props("unelevated color=primary icon=save")

    dialog.open()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b2_mnemo_wizard.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/components/obsidian_quick_edit_dialog.py tests/test_b2_mnemo_wizard.py
git commit -m "fix: make mnemo/image wizard theme-reactive and remove emoji icons"
```

---

### Task 2: Wizard de validation de séance — centrage et tokens généraux

**Files:**
- Modify: `frontend/pages/dashboard/_dialogs.py:244-276,509-513`
- Test: `tests/test_b2_session_feedback_shell.py` (créer)

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: `open_session_feedback_dialog(task, card, validate_fn, initial_duration_minutes=None, manual_date=None) -> None` — signature inchangée.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b2_session_feedback_shell.py` :

```python
"""Le wizard de validation de séance est centré (au lieu d'être ancré en bas à
droite) et utilise les tokens du design system plutôt que du Tailwind brut."""
import inspect

from frontend.pages.dashboard import _dialogs


def _source():
    return inspect.getsource(_dialogs.open_session_feedback_dialog)


def test_session_feedback_dialog_is_no_longer_docked_to_a_corner():
    source = _source()
    assert "self-end" not in source
    assert "mr-0" not in source
    assert "rounded-none sm:rounded-lg" not in source


def test_session_feedback_dialog_card_uses_design_tokens():
    source = _source()
    assert "bg-white" not in source
    assert "dark:bg-slate-900" not in source
    assert "border-slate-200" not in source
    assert "dark:border-slate-800" not in source
    assert "background:var(--bg)" in source
    assert "border:1px solid var(--border)" in source


def test_session_feedback_dialog_keeps_its_public_signature():
    """Non-régression : seule l'apparence change, pas la signature ni les
    callbacks de validation."""
    params = list(inspect.signature(_dialogs.open_session_feedback_dialog).parameters)
    assert params == ["task", "card", "validate_fn", "initial_duration_minutes", "manual_date"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b2_session_feedback_shell.py -v`
Expected: FAIL sur les 2 premiers tests (`self-end` et `bg-white` toujours présents) ; le 3ᵉ passe
déjà.

- [ ] **Step 3: Recentrer la carte et retokeniser l'en-tête**

Dans `frontend/pages/dashboard/_dialogs.py`, remplacer les lignes 244-276 :

```python
        with ui.card().classes(
            "w-[520px] max-w-[calc(100vw-24px)] max-h-[calc(100vh-24px)] self-end mr-0 "
            "flex flex-col rounded-none sm:rounded-lg p-0 overflow-hidden bg-white "
            "dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl"
        ):

            with ui.element("div").classes(
                "px-6 pt-5 pb-4 border-b border-slate-100 dark:border-slate-800"
            ):
                with ui.row().classes("items-start justify-between w-full gap-3"):
                    with ui.column().classes("gap-0.5 min-w-0 flex-1"):
                        ui.label("RETOUR DE SÉANCE").classes(
                            "text-[11px] font-bold tracking-[0.16em] text-slate-500"
                        )
                        ui.label(
                            item_label
                        ).classes("text-sm font-semibold text-slate-900 dark:text-slate-50").style(
                            "overflow:hidden;white-space:nowrap;text-overflow:ellipsis"
                        )
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense size=sm color=grey-7"
                    )

            with ui.element("div").classes(
                "flex-1 min-h-0 overflow-y-auto px-5 py-4 flex flex-col gap-4"
            ):

                ui.label("Comment s'est passée cette séance ?").classes(
                    "text-base font-semibold text-slate-900 dark:text-slate-50"
                )
                ui.label(
                    "La validation mettra à jour la maîtrise de l'item et sa prochaine révision."
                ).classes("text-xs text-slate-500")
```

par :

```python
        with ui.card().classes(
            "w-[520px] max-w-[calc(100vw-24px)] max-h-[calc(100vh-24px)] "
            "flex flex-col rounded-lg p-0 overflow-hidden"
        ).style(
            "background:var(--bg); border:1px solid var(--border); box-shadow:var(--shadow-popover);"
        ):

            with ui.element("div").classes("px-6 pt-5 pb-4").style(
                "border-bottom:1px solid var(--border);"
            ):
                with ui.row().classes("items-start justify-between w-full gap-3"):
                    with ui.column().classes("gap-0.5 min-w-0 flex-1"):
                        ui.label("RETOUR DE SÉANCE").classes(
                            "text-[11px] font-bold tracking-[0.16em]"
                        ).style("color:var(--text-muted);")
                        ui.label(
                            item_label
                        ).classes("text-sm font-semibold").style(
                            "color:var(--text); overflow:hidden;white-space:nowrap;text-overflow:ellipsis"
                        )
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense size=sm color=grey-7"
                    )

            with ui.element("div").classes(
                "flex-1 min-h-0 overflow-y-auto px-5 py-4 flex flex-col gap-4"
            ):

                ui.label("Comment s'est passée cette séance ?").classes(
                    "text-base font-semibold"
                ).style("color:var(--text);")
                ui.label(
                    "La validation mettra à jour la maîtrise de l'item et sa prochaine révision."
                ).classes("text-xs").style("color:var(--text-muted);")
```

- [ ] **Step 4: Retokeniser le pied de dialogue**

Remplacer les lignes 509-513 :

```python
            with ui.element("div").classes(
                "shrink-0 sticky bottom-0 px-5 py-3 bg-slate-50 dark:bg-slate-800/50 "
                "border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2"
            ):
                ui.button("Annuler", on_click=dialog.close).props("flat color=grey-8")
```

par :

```python
            with ui.element("div").classes(
                "shrink-0 sticky bottom-0 px-5 py-3 flex justify-end gap-2"
            ).style("background:var(--bg-alt); border-top:1px solid var(--border);"):
                ui.button("Annuler", on_click=dialog.close).props("flat color=grey-8")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b2_session_feedback_shell.py -v`
Expected: 3 passed

- [ ] **Step 6: Vérifier l'absence de régression**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cockpit_today_session_feedback.py tests/test_knowledge_session_dialog_gating.py -v`
Expected: PASS (ces tests ne portent que sur le câblage du callback, pas sur le style)

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/dashboard/_dialogs.py tests/test_b2_session_feedback_shell.py
git commit -m "fix: center the session feedback wizard and switch its shell to design tokens"
```

---

### Task 3: Wizard de validation de séance — simplification des couleurs de puces

**Files:**
- Modify: `frontend/pages/dashboard/_dialogs.py:255,260,271-276,305,311,314,328,341,343,352,358-363,442-452`
- Test: `tests/test_b2_session_feedback_chips.py` (créer)

**Interfaces:**
- Consumes: `_chip_on(col) -> str`, `_chip_off() -> str` (helpers déjà définis lignes 240-241, signatures inchangées).
- Produces: rien de nouveau.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_b2_session_feedback_chips.py` :

```python
"""Les puces Activité, Durée, Confiance et Catégorie d'erreur n'utilisent plus
de couleurs Quasar arbitraires (indigo, rouge, orange, bleu, sarcelle, violet,
rose, orange foncé, gris-bleu) : elles passent à `primary`, seule couleur de
sélection sans signification propre. Difficulté et Résultat QCM, déjà corrects
(positive/warning/negative), ne sont pas touchés."""
import inspect

from frontend.pages.dashboard import _dialogs


def _source():
    return inspect.getsource(_dialogs.open_session_feedback_dialog)


def test_no_arbitrary_decorative_color_remains():
    source = _source()
    for color in (
        "indigo", "red", "orange", "deep-orange", "blue", "purple", "pink", "teal", "blue-grey",
    ):
        assert f'"{color}"' not in source, f"decorative color {color!r} still present"


def test_activity_and_duration_chips_use_primary():
    source = _source()
    assert '_chip_on("primary") if is_on else _chip_off()' in source
    # Les deux groupes (Activité et Durée) partagent ce même motif de construction.
    assert source.count('_chip_on("primary") if is_on else _chip_off()') == 2


def test_confidence_and_category_configs_use_primary():
    source = _source()
    assert '(1, "Très incertain", "primary")' in source
    assert '(2, "Incertain", "primary")' in source
    assert '(3, "Correct", "primary")' in source
    assert '(4, "Solide", "primary")' in source
    assert '(5, "Très solide", "primary")' in source
    assert '("diagnostic",             "Diagnostic",  "primary")' in source
    assert '("physiopathologie",       "Physiopath.", "primary")' in source
    assert '("autre",                  "Autre",       "primary")' in source


def test_difficulty_and_qcm_result_stay_semantic():
    """Non-régression : ces deux groupes encodent une vraie sémantique et ne
    doivent pas être touchés par la simplification des couleurs."""
    source = _source()
    assert 'DIFF_OPTS   = [("facile","Facile","positive"),("moyen","Moyen","warning"),("difficile","Difficile","negative")]' in source
    assert 'QCM_OPTS    = [(None,"—","grey"),("réussi","Réussi","positive"),("moyen","Moyen","warning"),("raté","Raté","negative")]' in source


def test_none_placeholder_in_error_categories_stays_grey():
    """L'option « aucune catégorie » n'est pas une catégorie décorative :
    elle garde son gris neutre."""
    source = _source()
    assert '(None,                     "—",           "grey")' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b2_session_feedback_chips.py -v`
Expected: FAIL sur les 3 premiers tests (les couleurs décoratives sont toujours présentes) ; les 2
derniers passent déjà.

- [ ] **Step 3: Simplifier les puces Activité et Durée**

Dans `frontend/pages/dashboard/_dialogs.py`, remplacer la ligne 305 :
```python
                        b = ui.button(a_lbl).props(_chip_on("indigo") if is_on else _chip_off())
```
par :
```python
                        b = ui.button(a_lbl).props(_chip_on("primary") if is_on else _chip_off())
```

Remplacer les lignes 311 et 314 :
```python
                        act_btns[a].props(_chip_off(), remove=_chip_on("indigo"))
                    else:
                        state_fb.activity_types.append(a)
                        act_btns[a].props(_chip_on("indigo"), remove=_chip_off())
```
par :
```python
                        act_btns[a].props(_chip_off(), remove=_chip_on("primary"))
                    else:
                        state_fb.activity_types.append(a)
                        act_btns[a].props(_chip_on("primary"), remove=_chip_off())
```

Remplacer la ligne 328 :
```python
                        b = ui.button(f"{d}′").props(_chip_on("indigo") if is_on else _chip_off())
```
par :
```python
                        b = ui.button(f"{d}′").props(_chip_on("primary") if is_on else _chip_off())
```

Remplacer les lignes 341 et 343 :
```python
                        if dv == val:
                            db.props(_chip_on("indigo"), remove=_chip_off())
                        else:
                            db.props(_chip_off(), remove=_chip_on("indigo"))
```
par :
```python
                        if dv == val:
                            db.props(_chip_on("primary"), remove=_chip_off())
                        else:
                            db.props(_chip_off(), remove=_chip_on("primary"))
```

Remplacer la ligne 352 :
```python
                        for db in dur_btns.values():
                            db.props(_chip_off(), remove=_chip_on("indigo"))
```
par :
```python
                        for db in dur_btns.values():
                            db.props(_chip_off(), remove=_chip_on("primary"))
```

- [ ] **Step 4: Simplifier la configuration Confiance**

Remplacer les lignes 358-363 :
```python
                        _CONF_CONFIG = [
                            (1, "Très incertain", "red"),
                            (2, "Incertain", "orange"),
                            (3, "Correct", "blue"),
                            (4, "Solide", "teal"),
                            (5, "Très solide", "green"),
                        ]
```
par :
```python
                        _CONF_CONFIG = [
                            (1, "Très incertain", "primary"),
                            (2, "Incertain", "primary"),
                            (3, "Correct", "primary"),
                            (4, "Solide", "primary"),
                            (5, "Très solide", "primary"),
                        ]
```

- [ ] **Step 5: Simplifier la configuration Catégorie d'erreur/piège**

Remplacer les lignes 442-453 :
```python
                            _ERR_CATS = [
                                (None,                     "—",           "grey"),
                                ("diagnostic",             "Diagnostic",  "red"),
                                ("clinique",               "Clinique",    "orange"),
                                ("examens complémentaires","Examens",     "deep-orange"),
                                ("traitement",             "Traitement",  "blue"),
                                ("complications",          "Complic.",    "purple"),
                                ("physiopathologie",       "Physiopath.", "indigo"),
                                ("piège EDN",              "Piège EDN",   "pink"),
                                ("valeur chiffrée",        "Valeur chif.","teal"),
                                ("autre",                  "Autre",       "blue-grey"),
                            ]
```
par :
```python
                            _ERR_CATS = [
                                (None,                     "—",           "grey"),
                                ("diagnostic",             "Diagnostic",  "primary"),
                                ("clinique",               "Clinique",    "primary"),
                                ("examens complémentaires","Examens",     "primary"),
                                ("traitement",             "Traitement",  "primary"),
                                ("complications",          "Complic.",    "primary"),
                                ("physiopathologie",       "Physiopath.", "primary"),
                                ("piège EDN",              "Piège EDN",   "primary"),
                                ("valeur chiffrée",        "Valeur chif.","primary"),
                                ("autre",                  "Autre",       "primary"),
                            ]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b2_session_feedback_chips.py -v`
Expected: 5 passed

- [ ] **Step 7: Vérifier l'absence de régression sur l'ensemble du chantier B2**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_b2_mnemo_wizard.py tests/test_b2_session_feedback_shell.py tests/test_b2_session_feedback_chips.py tests/test_cockpit_today_session_feedback.py tests/test_knowledge_session_dialog_gating.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/dashboard/_dialogs.py tests/test_b2_session_feedback_chips.py
git commit -m "fix: stop using decorative rainbow colors for non-semantic chip selections"
```

---

## Vérification finale

- [ ] **Suite complète**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: aucune nouvelle défaillance par rapport à la ligne de base établie avant la Task 1 (1125
tests passés en sortie du chantier B1). Relever la ligne de base avec la même commande avant de
commencer, comparer après la Task 3.

- [ ] **Vérification manuelle dans l'application**

Lancer l'application et confirmer visuellement :

1. Le wizard mnémo/image s'affiche en clair quand le thème de l'app est clair (et en sombre quand
   il est sombre) — plus jamais figé en sombre.
2. Aucun emoji visible dans le wizard mnémo/image.
3. Le wizard de validation de séance s'ouvre centré à l'écran, plus ancré en bas à droite.
4. Les puces Activité, Durée, Confiance et Catégorie d'erreur n'affichent plus qu'une seule
   couleur (l'accent) quand sélectionnées.
5. Les puces Difficulté (facile/moyen/difficile) et Résultat QCM (réussi/moyen/raté) gardent leurs
   couleurs vert/ambre/rouge — inchangées.
