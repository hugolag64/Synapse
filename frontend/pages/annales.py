"""Liste groupée des annales UNESS importées, triable par matière/faculté/année/type."""

from __future__ import annotations

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness.import_service import ANNALE_TYPE_LABELS
from backend.state.store import data_store
from frontend.theme import frame

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

        def _finalize_scan(tags: dict[str, str] | None = None) -> None:
            result = import_verified_directory(tags=tags)
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
            with ui.dialog() as sub_dialog, ui.card().classes("w-[520px] max-w-[95vw] p-5 gap-3").style("border-radius: 8px;"):
                ui.label("Nouvelles annales à qualifier").classes("text-lg font-semibold")
                ui.label("Indiquez le type de chaque annale avant de finaliser l'importation.").classes("text-xs text-slate-500 mb-1")
                for group in pending:
                    source_url = group["source_url"]
                    chosen[source_url] = "matiere"
                    with ui.column().classes("w-full gap-1 p-3 border border-slate-200 dark:border-slate-800 rounded-md mb-2"):
                        ui.label(group["titre"] or source_url).classes("font-semibold text-sm")
                        ui.label(f"{group['matiere'] or '—'} · {group['faculte'] or '—'} · {group['annee'] or '—'}").classes("text-xs text-slate-500")
                        ui.select(
                            ANNALE_TYPE_LABELS,
                            value="matiere",
                            on_change=lambda e, url=source_url: chosen.__setitem__(url, e.value),
                        ).props("outlined dense").classes("w-full mt-1")
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Ignorer", on_click=sub_dialog.close).props("flat")
                    ui.button("Valider et importer", on_click=lambda: (sub_dialog.close(), _finalize_scan(tags=chosen))).props("unelevated color=primary")
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
            status_lbl.set_text("Ouverture du navigateur Playwright pour la collecte local UNESS…")
            status_lbl.classes("text-primary", remove="text-negative")

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
            if process.returncode == 0:
                status_lbl.set_text("Collecte terminée ✓ — Vérification et enregistrement en cours…")
                status_lbl.classes("text-positive", remove="text-negative text-primary")
                _finalize_scan()
            else:
                message = output.decode(errors="replace").strip()[-300:]
                status_lbl.set_text(f"Échec collecte : {message}")
                status_lbl.classes("text-negative", remove="text-primary text-positive")

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
                ui.button("Corriger avec Gemini", icon="auto_awesome", on_click=_run_gemini_autocorrect).props("flat color=primary")
                ui.button("Lancer la collecte", icon="play_arrow", on_click=_launch_collect_and_import).props("unelevated color=primary")
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

