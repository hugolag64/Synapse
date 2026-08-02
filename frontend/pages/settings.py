from nicegui import ui
from frontend.theme import frame
from backend.state.store import data_store
from urllib.parse import urlparse


def _validate_uness_annale_url(value: str) -> str:
    """Validate and normalize a public UNESS annales URL."""
    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "entrainement.uness.fr"
        or not parsed.path.startswith("/annales/")
    ):
        raise ValueError(
            "Utilisez une URL HTTPS d'annale UNESS "
            "(entrainement.uness.fr/annales/...)."
        )
    return candidate

def _show_uncertain_dialog(uncertain_matches: list) -> None:
    from backend.core.obsidian.sync import vault_sync_service
    selected: dict[str, bool] = {str(m.path): True for m in uncertain_matches}

    with ui.dialog() as dlg:
        with ui.card().classes("w-full max-w-2xl p-0 rounded-2xl overflow-hidden"):
            with ui.row().classes(
                "items-center gap-3 px-5 py-4 "
                "bg-amber-50 dark:bg-amber-900/20 "
                "border-b border-amber-200 dark:border-amber-800"
            ):
                ui.icon("help_outline", color="amber").classes("text-2xl shrink-0")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(
                        f"{len(uncertain_matches)} match(s) douteux — à confirmer"
                    ).classes("font-bold text-amber-800 dark:text-amber-200")
                    ui.label(
                        "Ces notes ont été appariées par titre approchant. "
                        "Cochez celles à lier puis cliquez sur « Appliquer »."
                    ).classes("text-xs text-amber-600 dark:text-amber-400")

            with ui.scroll_area().classes("max-h-[28rem] w-full"):
                with ui.column().classes("px-4 py-3 gap-2 w-full"):
                    for match in uncertain_matches:
                        path_key = str(match.path)
                        with ui.card().classes(
                            "w-full p-3 bg-slate-50 dark:bg-slate-800 "
                            "border border-slate-200 dark:border-slate-700"
                        ):
                            with ui.row().classes("items-start gap-3 w-full"):
                                chk = ui.checkbox(value=True)
                                def _on_change(e, k=path_key):
                                    selected[k] = e.value
                                chk.on("update:model-value", _on_change)
                                with ui.column().classes("gap-0.5 flex-1 min-w-0"):
                                    ui.label(match.path.name).classes(
                                        "text-xs font-mono text-slate-500 dark:text-slate-400 truncate"
                                    )
                                    ui.label(f"→  {match.course_title}").classes(
                                        "text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug"
                                    )
                                    with ui.row().classes("items-center gap-1"):
                                        ui.icon("auto_awesome", size="xs").classes("text-amber-400 shrink-0")
                                        ui.label(match.reason).classes(
                                            "text-[11px] text-amber-600 dark:text-amber-400 italic"
                                        )

            with ui.row().classes(
                "items-center justify-end gap-3 px-5 py-3 "
                "border-t border-slate-100 dark:border-slate-700"
            ):
                ui.button("Tout rejeter", on_click=dlg.close).props("flat color=slate size=sm")

                async def _apply_selected():
                    from backend.core.obsidian.service import obsidian_service
                    from backend.core.notion.service import notion_service
                    from backend.core.notion.payloads import rich_text
                    from backend.config.settings import NOTION_PROPS as P
                    from loguru import logger
                    to_apply = [m for m in uncertain_matches if selected.get(str(m.path), False)]
                    if not to_apply:
                        ui.notify("Aucune note sélectionnée.", type="info")
                        dlg.close()
                        return
                    updated_pairs = vault_sync_service.apply_matches_and_get_paths(to_apply)
                    course_map = {c.id: c for c in data_store.cours}
                    for course_id, path in updated_pairs:
                        try:
                            uri = obsidian_service.build_obsidian_uri(path)
                            await notion_service.update_course(course_id, {P.OBSIDIAN: rich_text(uri)})
                            cours = course_map.get(course_id)
                            if cours is not None:
                                cours.obsidian_uri = uri
                        except Exception as exc:
                            logger.warning(f"Uncertain apply — Notion update échoué: {exc}")
                    s = "s" if len(updated_pairs) > 1 else ""
                    ui.notify(f"{len(updated_pairs)} note{s} liée{s} ✓ · Notion mis à jour", type="positive", icon="link")
                    dlg.close()

                ui.button("Appliquer la sélection", icon="check", on_click=_apply_selected).props("unelevated color=amber size=sm")

    dlg.open()


async def _run_vault_scan(vault_path_input) -> None:
    from loguru import logger
    from backend.core.obsidian.sync import vault_sync_service
    from backend.core.obsidian.service import obsidian_service
    from backend.core.notion.service import notion_service
    from backend.core.notion.payloads import rich_text
    from backend.config.settings import NOTION_PROPS as P

    vp = (vault_path_input.value or "").strip()
    if not vp:
        ui.notify("Configurez d'abord le chemin du vault.", type="warning", icon="warning")
        return
    courses = list(data_store.cours)
    if not courses:
        ui.notify("Aucun cours chargé — synchronisez d'abord avec Notion.", type="warning")
        return

    ui.notify("Scan en cours…", type="info", icon="sync", timeout=2000)
    result = vault_sync_service.scan_unlinked_notes(vp, courses)

    updated_pairs: list = []
    if result.confirmed:
        updated_pairs = vault_sync_service.apply_matches_and_get_paths(result.confirmed)

    course_map = {c.id: c for c in data_store.cours}
    notion_ok = 0
    for course_id, path in updated_pairs:
        try:
            uri = obsidian_service.build_obsidian_uri(path)
            ok = await notion_service.update_course(course_id, {P.OBSIDIAN: rich_text(uri)})
            if ok:
                notion_ok += 1
            cours = course_map.get(course_id)
            if cours is not None:
                cours.obsidian_uri = uri
        except Exception as exc:
            logger.warning(f"Vault scan — Notion update échoué ({course_id}): {exc}")

    parts: list[str] = []
    if updated_pairs:
        s = "s" if len(updated_pairs) > 1 else ""
        parts.append(f"✅ {len(updated_pairs)} note{s} liée{s}")
        if notion_ok:
            parts.append(f"Notion mis à jour ({notion_ok})")
    if result.uncertain:
        parts.append(f"⚠️ {len(result.uncertain)} match(s) douteux à confirmer")
    if not result.confirmed and not result.uncertain:
        parts.append("Aucune nouvelle note à lier")
    if result.errors:
        parts.append(f"⛔ {len(result.errors)} erreur(s)")

    msg = " · ".join(parts)
    ui.notify(msg, type="positive" if updated_pairs else "info", icon="edit_note", timeout=6000)
    for err in result.errors:
        logger.warning(f"Vault scan (manuel) : {err}")
    if result.uncertain:
        _show_uncertain_dialog(result.uncertain)


@ui.page('/settings')
@frame('Paramètres')
def settings_page():
    # ── Refonte : liste de connexions + apparence cockpit (feature-flag) ──────
    from frontend.pages.settings_cockpit import render_settings_cockpit
    render_settings_cockpit()
    return


def toggle_dark_mode(value):
    ui.dark_mode(value)
    data_store.set_preference('dark_mode', value)
