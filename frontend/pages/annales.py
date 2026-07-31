"""Liste groupée des annales UNESS importées, triable par matière/faculté/année/type."""

from __future__ import annotations

from nicegui import ui

from backend.core.reviews import local_store
from backend.core.uness.import_service import ANNALE_TYPE_LABELS
from frontend.theme import frame


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


@ui.page("/annales")
def annales_page() -> None:
    with frame("Annales"):
        ui.label("Annales UNESS").classes("text-xl font-semibold")
        ui.label("Partiels importés, regroupés par annale").classes("text-sm text-slate-500")

        all_rows = _filtered_annales()
        if not all_rows:
            ui.label("Aucune annale importée pour le moment.").classes("text-sm text-slate-500 mt-6")
            return

        matieres = _distinct_values(all_rows, "matiere")
        facultes = _distinct_values(all_rows, "faculte")
        annees = sorted({int(row["annee"]) for row in all_rows if row.get("annee")})

        with ui.row().classes("w-full gap-3 mt-4 flex-wrap items-end"):
            search = ui.input(label="Recherche").props("outlined dense").classes("w-56")
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

        rows_column = ui.column().classes("w-full gap-3 mt-4")

        def _render() -> None:
            rows_column.clear()
            rows = _filtered_annales(
                query=str(search.value or ""),
                matiere=str(matiere_filter.value or ""),
                faculte=str(faculte_filter.value or ""),
                annee=int(annee_filter.value) if annee_filter.value else None,
                type_annale=str(type_filter.value or ""),
            )
            # Exclut les vrais concours sauf si l'utilisateur les filtre explicitement
            if not type_filter.value:
                rows = [r for r in rows if r["type_annale"] != "vrai_concours"]
            with rows_column:
                if not rows:
                    ui.label("Aucune annale ne correspond à ces filtres.").classes("text-sm text-slate-500")
                    return
                for row in rows:
                    annale_id = int(row["id"])
                    total = int(row["total_parts"] or 0)
                    completed = int(row["completed_parts"] or 0)
                    avg_score = row.get("avg_score")
                    score_label = "—" if avg_score is None else f"{float(avg_score):.0f} %"
                    with ui.card().classes("w-full p-4"):
                        with ui.row().classes("w-full items-center justify-between gap-4"):
                            with ui.column().classes("gap-1"):
                                ui.label(str(row["matiere"] or "—")).classes("font-semibold")
                                ui.label(
                                    f"{row['faculte'] or '—'} · {row['annee'] or '—'} · "
                                    f"{ANNALE_TYPE_LABELS.get(row['type_annale'], row['type_annale'])}"
                                ).classes("text-xs text-slate-500")
                                ui.label(
                                    f"{completed}/{total} sous-parties terminées · Score moyen : {score_label}"
                                ).classes("text-xs text-slate-500")
                            ui.button(
                                "Ouvrir",
                                icon="chevron_right",
                                on_click=lambda aid=annale_id: ui.navigate.to(f"/annales/{aid}"),
                            ).props("unelevated color=teal size=sm rounded")

        for control in (search, matiere_filter, faculte_filter, annee_filter, type_filter):
            control.on_value_change(lambda _e=None: _render())
        _render()
