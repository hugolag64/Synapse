"""Liste groupée des annales UNESS importées, triable par matière/faculté/année/type."""

from __future__ import annotations

import re

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness.import_service import ANNALE_TYPE_LABELS
from backend.state.store import data_store
from frontend.theme import frame

_AUTRE = "Autre…"

_ANNALES_CSS = """
.ans-wrap { width:100%; max-width:1200px; align-self:stretch; margin:0 auto; min-width:0; }
.ans-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; padding:4px 0 18px; flex-wrap:wrap; }
.ans-title { font-size:20px; font-weight:600; color:var(--text); letter-spacing:-0.01em; }
.ans-subtitle { font-size:12.5px; color:var(--text-muted); margin-top:4px; }
.ans-filters { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid var(--border); }
.ans-list { display:flex; flex-direction:column; gap:8px; width:100%; }
.ans-card { width:100%; padding:14px 16px; border:1px solid var(--border); border-radius:8px; background:var(--surface); transition:background var(--duration-fast) ease; }
.ans-card:hover { background:var(--surface-hover); }
.ans-card-title { font-size:14.5px; font-weight:600; color:var(--text); }
.ans-card-sub { font-size:12px; color:var(--text-muted); margin-top:2px; }
.ans-card-meta { font-size:11.5px; color:var(--text-dim); margin-top:4px; }
.ans-empty { padding:36px 10px; text-align:center; color:var(--text-dim); font-size:13px; }
"""


def _filtered_annales(
    *,
    query: str = "",
    matiere: str = "",
    faculte: str = "",
    annee: int | None = None,
    type_annale: str = "",
) -> list[dict]:
    return local_store.list_uness_annales(
        query=query, matiere=matiere, faculte=faculte, annee=annee, type_annale=type_annale
    )


def _distinct_values(rows: list[dict], key: str) -> list[str]:
    return sorted({str(row[key]) for row in rows if row.get(key)})


# Tarif Google officiel pour gemini-3-flash-preview au 2026-07-31 (ai.google.dev/gemini-api/docs/pricing) :
# 0,50 $ / M tokens entrée, 3,00 $ / M tokens sortie — à revérifier périodiquement.
_GEMINI_FLASH_PRICE_PER_M_INPUT = 0.50
_GEMINI_FLASH_PRICE_PER_M_OUTPUT = 3.00


def _format_gemini_summary(result: dict) -> str:
    corrected = len(result["corrected"])
    errors = len(result["errors"])
    input_tokens = result["input_tokens"]
    output_tokens = result["output_tokens"]
    cost = (
        input_tokens / 1_000_000 * _GEMINI_FLASH_PRICE_PER_M_INPUT
        + output_tokens / 1_000_000 * _GEMINI_FLASH_PRICE_PER_M_OUTPUT
    )
    return (
        f"{corrected} quiz corrigé(s), {errors} erreur(s) — "
        f"~{input_tokens} tokens entrée / {output_tokens} sortie (≈ {cost:.4f} $)"
    )


def _gemini_partial_failure_message(result: dict) -> str | None:
    """A quiz-level failure (Gemini truncation, missing image, rate limit
    exhausted...) must never go unnoticed just because sibling quizzes from
    the same partiel corrected fine — that's how whole sous-parties (e.g. a
    SQI bank) silently vanish from an otherwise "successful" import. Returns
    None when every quiz corrected cleanly."""
    errors = result["errors"]
    if not errors:
        return None
    failed = "; ".join(f"{e.get('file', '?')} : {e.get('error', '?')[:120]}" for e in errors)
    return f"{len(errors)} échec(s) de correction (quiz manquant du partiel importé) — {failed}"


def _best_matiere_guess(candidates: list[str], detected: str) -> str | None:
    """Best-effort match of the auto-detected free-text subject (parsed from the
    UNESS breadcrumb — often a category/session label rather than the real
    subject) against the canonical collège list, so the qualify dialog can
    pre-select a sensible default. Returns None rather than guessing wrong when
    nothing looks close enough — the user then picks manually via "Autre"."""
    needle = re.sub(r"[^a-z]", "", detected.lower())
    if not needle:
        return None
    for candidate in candidates:
        hay = re.sub(r"[^a-z]", "", candidate.lower())
        if hay and (needle == hay or needle in hay or hay in needle):
            return candidate
    return None


def _confirm_delete(annale_id: int, titre: str, on_deleted) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[420px] max-w-[95vw] p-5 gap-3").style("border-radius: 8px;"):
        ui.label("Supprimer cette annale ?").classes("text-lg font-semibold")
        ui.label(
            f"« {titre} » et toutes ses sous-parties importées seront supprimées "
            "définitivement. Cette action est irréversible."
        ).classes("text-sm text-slate-500")

        def _delete() -> None:
            local_store.delete_uness_annale(annale_id)
            dialog.close()
            on_deleted()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Annuler", on_click=dialog.close).props("flat")
            ui.button("Supprimer", on_click=_delete).props("unelevated color=negative")
    dialog.open()


def _open_import_dialog(refresh_fn) -> None:
    import asyncio
    import sys
    from pathlib import Path
    from backend.core.uness import gemini_autocorrect
    from backend.core.uness.import_service import (
        ANNALE_TYPE_LABELS,
        import_verified_directory,
    )
    from backend.state.store import data_store
    from scripts.uness.collector import validate_annale_url

    with ui.dialog() as dialog, ui.card().classes("w-[560px] max-w-[95vw] p-5 gap-3").style("border-radius: 8px;"):
        ui.label("Importer une annale UNESS").classes("text-lg font-semibold")
        ui.label(
            "Collez une URL d'annale UNESS pour lancer la collecte automatique Playwright, "
            "ou scannez les fichiers JSON vérifiés déjà présents."
        ).classes("text-xs text-slate-500 mb-1")

        url_input = ui.input(
            label="URL de l'annale UNESS",
            placeholder="https://entrainement.uness.fr/annales/course/view.php?id=...",
        ).props("outlined dense").classes("w-full")

        status_lbl = ui.label("").classes("text-xs text-slate-500 min-h-[18px]")

        ui.separator().classes("my-2")
        ui.label("Ou corriger un dossier existant avec Gemini").classes("text-xs text-slate-500")
        folder_input = ui.input(
            label="Dossier du partiel (JSON + images)",
            placeholder="UNESS/à_vérifier/session-...",
        ).props("outlined dense").classes("w-full")

        def _finalize_scan(
            tags: dict[str, str] | None = None, matieres: dict[str, str] | None = None
        ) -> None:
            result = import_verified_directory(tags=tags, matieres=matieres)
            pending = result["pending_tag"]
            if pending:
                _open_tag_dialog(pending)
                return
            imported_count = len(result["imported"])
            error_count = len(result["errors"])
            if imported_count > 0:
                ui.notify(f"{imported_count} annale(s) importée(s) avec succès !", type="positive")
                dialog.close()
                refresh_fn()
            elif result["skipped"]:
                status_lbl.set_text("Les annales correspondantes sont déjà importées.")
                status_lbl.classes("text-slate-500", remove="text-negative text-primary")
            elif error_count:
                err_msg = result["errors"][0].get("error", "Erreur lors de la lecture des fichiers vérifiés.")
                file_name = result["errors"][0].get("file", "")
                status_lbl.set_text(f"Erreur ({file_name}) : {err_msg}")
                status_lbl.classes("text-negative", remove="text-slate-500 text-primary")

        def _open_tag_dialog(pending: list[dict]) -> None:
            chosen: dict[str, str] = {}
            matiere_widgets: dict[str, tuple] = {}
            college_options = sorted(data_store.get_colleges() or []) if data_store.is_loaded else []
            with ui.dialog() as sub_dialog, ui.card().classes("w-[560px] max-w-[95vw] p-5 gap-3").style("border-radius: 8px;"):
                ui.label("Nouvelles annales à qualifier").classes("text-lg font-semibold")
                ui.label(
                    "Indiquez le type et validez la matière de chaque annale avant de finaliser "
                    "l'importation — la matière détectée automatiquement n'est qu'une suggestion "
                    "et doit correspondre au référentiel des collèges pour rester liée au reste de l'app."
                ).classes("text-xs text-slate-500 mb-1")
                for group in pending:
                    source_url = group["source_url"]
                    chosen[source_url] = "matiere"
                    detected = str(group["matiere"] or "")
                    guess = _best_matiere_guess(college_options, detected)
                    matiere_options = [*college_options, _AUTRE]
                    with ui.column().classes("w-full gap-1 p-3 border border-slate-200 dark:border-slate-800 rounded-md mb-2"):
                        ui.label(group["titre"] or source_url).classes("font-semibold text-sm")
                        ui.label(f"{group['faculte'] or '—'} · {group['annee'] or '—'}").classes("text-xs text-slate-500")
                        ui.select(
                            ANNALE_TYPE_LABELS,
                            value="matiere",
                            label="Type",
                            on_change=lambda e, url=source_url: chosen.__setitem__(url, e.value),
                        ).props("outlined dense").classes("w-full mt-1")
                        matiere_select = ui.select(
                            matiere_options, value=guess or _AUTRE, label="Matière"
                        ).props("outlined dense").classes("w-full mt-1")
                        matiere_autre = ui.input(
                            "Matière (saisie libre)", value="" if guess else detected
                        ).props("outlined dense").classes("w-full")
                        matiere_autre.bind_visibility_from(matiere_select, "value", value=_AUTRE)
                        matiere_widgets[source_url] = (matiere_select, matiere_autre)

                def _submit() -> None:
                    matieres: dict[str, str] = {}
                    missing = []
                    for url, (select, autre) in matiere_widgets.items():
                        value = str((autre.value if select.value == _AUTRE else select.value) or "").strip()
                        matieres[url] = value
                        # Only a "Matière" annale needs one canonical subject — a concours
                        # blanc or un EDN complet legitimately spans several.
                        if chosen.get(url) == "matiere" and not value:
                            missing.append(url)
                    if missing:
                        ui.notify(
                            "Choisis une matière pour chaque annale de type « Matière » avant de continuer.",
                            type="warning",
                        )
                        return
                    sub_dialog.close()
                    _finalize_scan(tags=chosen, matieres=matieres)

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Ignorer", on_click=sub_dialog.close).props("flat")
                    ui.button("Valider et importer", on_click=_submit).props("unelevated color=primary")
            sub_dialog.open()

        async def _launch_collect_and_import() -> None:
            raw_url = (url_input.value or "").strip()
            if not raw_url:
                # If URL is empty, just attempt to scan existing verified JSONs
                status_lbl.set_text("Scan des annales vérifiées locales en cours…")
                _finalize_scan()
                return

            try:
                url = validate_annale_url(raw_url)
            except ValueError as exc:
                status_lbl.set_text(str(exc))
                status_lbl.classes("text-negative", remove="text-slate-500 text-primary")
                ui.notify(str(exc), type="negative")
                return

            data_store.set_preference("uness_annale_url", url)
            dialog.close()
            ui.notify("🚀 Importation lancée en arrière-plan ! Vous pouvez continuer à utiliser Synapse.", type="info", duration=5)

            async def _bg_pipeline() -> None:
                script = Path("scripts/uness/collector.py").resolve()
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(script),
                    url,
                    "--submit",
                    cwd=str(Path.cwd()),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                output, _ = await process.communicate()
                if process.returncode != 0:
                    message = output.decode(errors="replace").strip()[-200:]
                    ui.notify(f"❌ Échec collecte UNESS : {message}", type="negative", duration=8)
                    return

                out_text = output.decode(errors="replace")
                session_dir = None
                for line in out_text.splitlines():
                    if "UNESS\\à_vérifier\\" in line or "UNESS/à_vérifier/" in line:
                        p = Path(line.strip())
                        session_dir = p.parent if p.is_file() else p
                        break

                if not session_dir or not session_dir.is_dir():
                    candidates = sorted(Path("UNESS/à_vérifier").glob("session-*"))
                    if candidates:
                        session_dir = candidates[-1]

                if session_dir and session_dir.is_dir():
                    ui.notify("⚡ Collecte réussie ! Correction automatique Gemini en cours…", type="info", duration=5)
                    result = await asyncio.to_thread(gemini_autocorrect.correct_directory, session_dir)
                    partial_failure = _gemini_partial_failure_message(result)
                    if result["corrected"]:
                        if partial_failure:
                            ui.notify(f"⚠️ Correction partielle : {partial_failure}", type="warning", duration=12)
                        else:
                            ui.notify("✨ Annale prête ! Veuillez qualifier la matière.", type="positive", duration=6)
                        _finalize_scan()
                    else:
                        err_msg = result["errors"][0]["error"] if result["errors"] else "Erreur Gemini"
                        ui.notify(f"❌ Échec correction Gemini : {err_msg}", type="negative", duration=8)
                else:
                    _finalize_scan()

            asyncio.create_task(_bg_pipeline())

        async def _run_gemini_autocorrect() -> None:
            raw_path = (folder_input.value or "").strip()
            if not raw_path:
                status_lbl.set_text("Indique le dossier à corriger.")
                status_lbl.classes("text-negative", remove="text-slate-500 text-primary")
                return
            status_lbl.set_text("Correction Gemini en cours (peut prendre 1-2 min)…")
            status_lbl.classes("text-primary", remove="text-negative")
            result = await asyncio.to_thread(gemini_autocorrect.correct_directory, Path(raw_path))
            status_lbl.set_text(_format_gemini_summary(result))
            status_lbl.classes(
                "text-positive" if result["corrected"] else "text-negative",
                remove="text-primary text-slate-500",
            )
            if result["corrected"]:
                _finalize_scan()

        with ui.row().classes("w-full justify-between items-center mt-3"):
            ui.button("Scanner les JSON existants", icon="fact_check", on_click=lambda: _finalize_scan()).props("flat size=sm color=slate")
            with ui.row().classes("gap-2"):
                ui.button("Annuler", on_click=dialog.close).props("flat")
                ui.button("Corriger dossier existant", icon="auto_awesome", on_click=_run_gemini_autocorrect).props("flat color=primary")
                ui.button("🚀 Tout faire (URL)", icon="auto_mode", on_click=_launch_collect_and_import).props("unelevated color=primary")
    dialog.open()


@ui.page("/annales")
def annales_page() -> None:
    ui.add_head_html(f"<style>{_ANNALES_CSS}</style>", shared=True)

    with frame("Annales"):
        with ui.column().classes("ans-wrap gap-0").style("flex:1 1 auto;"):
            def _toggle_exam_mode(val: bool) -> None:
                data_store.preferences["exam_mode"] = bool(val)
                data_store.save_to_disk()
                _render()

            with ui.element("div").classes("ans-topbar"):
                with ui.column().classes("gap-0"):
                    ui.label("Annales UNESS").classes("ans-title")
                    ui.label("Partiels et examens importés, regroupés par sujet").classes("ans-subtitle")
                with ui.row().classes("items-center gap-2"):
                    exam_mode_switch = ui.switch(
                        "Mode Concours Blanc",
                        value=bool(data_store.preferences.get("exam_mode", False)),
                        on_change=lambda e: _toggle_exam_mode(e.value),
                    ).props("dense color=primary").tooltip("Masque les scores passés pour s'entraîner sans biais")
                    ui.button(
                        "+ IMPORTER UNE ANNALES",
                        icon="add",
                        on_click=lambda: _open_import_dialog(refresh_fn=_render),
                    ).props("unelevated color=primary size=sm")

            all_rows = _filtered_annales()
            if not all_rows:
                ui.label("Aucune annale importée pour le moment.").classes("ans-empty")
                return

            matieres = _distinct_values(all_rows, "matiere")
            facultes = _distinct_values(all_rows, "faculte")
            annees = sorted({int(row["annee"]) for row in all_rows if row.get("annee")})

            with ui.element("div").classes("ans-filters"):
                search = ui.input(placeholder="Recherche…").props("outlined dense clearable").classes("w-56")
                matiere_filter = ui.select(
                    {"": "Toutes matières", **{m: m for m in matieres}}, value=""
                ).props("outlined dense").classes("w-52")
                faculte_filter = ui.select(
                    {"": "Toutes facultés", **{f: f for f in facultes}}, value=""
                ).props("outlined dense").classes("w-56")
                annee_filter = ui.select(
                    {"": "Toutes années", **{str(a): str(a) for a in annees}}, value=""
                ).props("outlined dense").classes("w-40")
                type_filter = ui.select(
                    {"": "Tous types", **ANNALE_TYPE_LABELS}, value=""
                ).props("outlined dense").classes("w-44")

            rows_column = ui.column().classes("ans-list")

            def _render() -> None:
                rows_column.clear()
                rows = _filtered_annales(
                    query=str(search.value or ""),
                    matiere=str(matiere_filter.value or ""),
                    faculte=str(faculte_filter.value or ""),
                    annee=int(annee_filter.value) if annee_filter.value else None,
                    type_annale=str(type_filter.value or ""),
                )
                rows = [r for r in rows if r["type_annale"] != "vrai_concours"]
                with rows_column:
                    if not rows:
                        ui.label("Aucune annale ne correspond à ces filtres.").classes("ans-empty")
                        return
                    for row in rows:
                        annale_id = int(row["id"])
                        total = int(row["total_parts"] or 0)
                        completed = int(row["completed_parts"] or 0)
                        avg_score = row.get("avg_score")
                        score_label = "—" if avg_score is None else f"{float(avg_score):.0f} %"
                        with ui.element("div").classes("ans-card"):
                            with ui.row().classes("w-full items-center justify-between gap-4"):
                                with ui.column().classes("gap-0 min-w-0 flex-1"):
                                    ui.label(str(row["titre"] or row["matiere"] or "Annale")).classes("ans-card-title truncate")
                                    ui.label(
                                        f"{row['matiere'] or '—'} · {row['faculte'] or '—'} · {row['annee'] or '—'} · "
                                        f"{ANNALE_TYPE_LABELS.get(row['type_annale'], row['type_annale'])}"
                                    ).classes("ans-card-sub")
                                    is_exam_mode = bool(data_store.preferences.get("exam_mode", False))
                                    meta_text = (
                                        "Mode Concours Blanc (Scores et progression masqués)"
                                        if is_exam_mode
                                        else f"{completed}/{total} sous-parties terminées · Score moyen : {score_label}"
                                    )
                                    ui.label(meta_text).classes("ans-card-meta")
                                with ui.row().classes("gap-2 items-center shrink-0"):
                                    ui.button(
                                        icon="delete_outline",
                                        on_click=lambda _e=None, aid=annale_id, t=row["titre"]: _confirm_delete(
                                            aid, str(t), on_deleted=_render
                                        ),
                                    ).props("flat dense round color=negative").tooltip("Supprimer l'annale")
                                    ui.button(
                                        "Ouvrir",
                                        icon="chevron_right",
                                        on_click=lambda _e=None, aid=annale_id: ui.navigate.to(f"/annales/{aid}"),
                                    ).props("flat color=primary size=sm")

            for control in (search, matiere_filter, faculte_filter, annee_filter, type_filter):
                control.on_value_change(lambda _e=None: _render())
            _render()

