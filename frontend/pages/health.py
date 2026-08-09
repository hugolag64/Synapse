"""
Page « Santé du système » — /health
Vérifie en temps réel : Notion, Google Calendar, Obsidian, SQLite.
"""
from nicegui import ui
from frontend.theme import frame
from loguru import logger


def _status_chip(ok: bool | None, label_ok: str, label_ko: str):
    """Chip vert/rouge/gris selon le statut."""
    if ok is None:
        ui.badge("…", color="grey").classes("text-xs font-semibold px-2 py-1")
    elif ok:
        ui.badge(label_ok, color="positive").classes("text-xs font-semibold px-2 py-1")
    else:
        ui.badge(label_ko, color="negative").classes("text-xs font-semibold px-2 py-1")


@ui.page('/health')
async def health_page():
    with frame('Santé du système'):
        with ui.column().classes("w-full gap-5 max-w-4xl mx-auto"):
            ui.label("Santé du système").classes(
                "text-2xl font-bold text-slate-800 dark:text-slate-100"
            )
            ui.label(
                "Vérifiez que chaque service est correctement configuré et accessible."
            ).classes("text-sm text-slate-400 -mt-3")

            results_col = ui.column().classes("w-full gap-4")

            async def run_checks():
                results_col.clear()
                with results_col:
                    ui.spinner(size="lg").classes("mx-auto my-6")

                results_col.clear()
                with results_col:
                    await _check_notion()
                    await _check_sqlite()
                    _check_obsidian()
                    _check_google_calendar()
                    _check_cache()

            ui.button("Lancer le diagnostic", icon="play_arrow", on_click=run_checks).props(
                "unelevated color=indigo rounded"
            )

            # Lancement automatique à l'ouverture
            await run_checks()


async def _check_notion():
    from backend.core.notion.health import notion_health

    with ui.card().classes(
        "w-full p-0 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden"
    ):
        # En-tête
        with ui.row().classes(
            "items-center gap-3 px-5 py-3 bg-slate-50 dark:bg-slate-900 "
            "border-b border-slate-200 dark:border-slate-800"
        ):
            ui.icon("cloud", color="indigo").classes("text-xl")
            ui.label("Notion API").classes("font-bold text-slate-800 dark:text-slate-100 flex-1")
            placeholder = ui.element("div")

        with ui.column().classes("px-5 py-4 gap-2 w-full"):
            try:
                result = await notion_health.check()

                # Mettre à jour le badge dans l'en-tête
                placeholder.clear()
                with placeholder:
                    _status_chip(result.ok, "OK", "Erreur")

                for check in result.required_checks + result.optional_checks:
                    color = "positive" if check.ok else ("warning" if check.optional else "negative")
                    icon = "check_circle" if check.ok else ("warning" if check.optional else "cancel")
                    with ui.row().classes("items-center gap-2 w-full"):
                        ui.icon(icon, color=color, size="xs").classes("shrink-0")
                        ui.label(check.name).classes("text-xs font-semibold text-slate-700 dark:text-slate-200 w-56 shrink-0")
                        ui.label(check.message).classes("text-xs text-slate-400 dark:text-slate-500")

            except Exception as e:
                with placeholder:
                    _status_chip(False, "OK", "Erreur")
                ui.label(f"Impossible de contacter Notion : {e}").classes("text-sm text-red-500")
                logger.error(f"[health] Notion check failed: {e}")


async def _check_sqlite():
    from backend.core.reviews.local_store import get_stats, DB_PATH

    with ui.card().classes(
        "w-full p-0 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden"
    ):
        with ui.row().classes(
            "items-center gap-3 px-5 py-3 bg-slate-50 dark:bg-slate-900 "
            "border-b border-slate-200 dark:border-slate-800"
        ):
            ui.icon("storage", color="teal").classes("text-xl")
            ui.label("Base SQLite locale").classes("font-bold text-slate-800 dark:text-slate-100 flex-1")
            placeholder = ui.element("div")

        with ui.column().classes("px-5 py-4 gap-2 w-full"):
            try:
                stats = get_stats()
                ok = "error" not in stats

                with placeholder:
                    _status_chip(ok, "OK", "Erreur")

                if ok:
                    rows = [
                        ("Fichier", stats.get("db_path", str(DB_PATH))),
                        ("Taille", f"{stats.get('db_size_kb', '?')} Ko"),
                        ("Révisions enregistrées", str(stats.get("nb_done", 0))),
                        ("Sessions de travail", str(stats.get("nb_sessions", 0))),
                        ("Dernière validation", stats.get("last_done") or "—"),
                    ]
                    with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1"):
                        for label, val in rows:
                            ui.label(label).classes("text-xs text-slate-400")
                            ui.label(val).classes("text-xs font-mono text-slate-600 dark:text-slate-300")
                else:
                    ui.label(f"Erreur SQLite : {stats['error']}").classes("text-sm text-red-500")

            except Exception as e:
                with placeholder:
                    _status_chip(False, "OK", "Erreur")
                ui.label(f"Erreur : {e}").classes("text-sm text-red-500")


def _check_obsidian():
    from backend.config.settings import settings as _cfg
    import os

    with ui.card().classes(
        "w-full p-0 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden"
    ):
        with ui.row().classes(
            "items-center gap-3 px-5 py-3 bg-slate-50 dark:bg-slate-900 "
            "border-b border-slate-200 dark:border-slate-800"
        ):
            ui.icon("edit_note", color="indigo").classes("text-xl")
            ui.label("Obsidian").classes("font-bold text-slate-800 dark:text-slate-100 flex-1")
            placeholder = ui.element("div")

        with ui.column().classes("px-5 py-4 gap-2 w-full"):
            vault_path = _cfg.obsidian_vault_path
            vault_name = _cfg.obsidian_vault_name

            if not vault_path:
                with placeholder:
                    _status_chip(None, "", "Non configuré")
                ui.label("Vault non configuré (optionnel). Renseignez OBSIDIAN_VAULT_PATH dans les Paramètres.").classes(
                    "text-xs text-slate-400 italic"
                )
                return

            vault_exists = os.path.isdir(vault_path)
            with placeholder:
                _status_chip(vault_exists, "OK", "Introuvable")

            rows = [
                ("Chemin", vault_path),
                ("Nom du vault", vault_name or "—"),
                ("Dossier accessible", "✓ Oui" if vault_exists else "✗ Introuvable"),
            ]
            with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1"):
                for label, val in rows:
                    ui.label(label).classes("text-xs text-slate-400")
                    ui.label(val).classes("text-xs font-mono text-slate-600 dark:text-slate-300 truncate")


def _check_google_calendar():
    from backend.core.google.calendar_service import calendar_service

    with ui.card().classes(
        "w-full p-0 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden"
    ):
        with ui.row().classes(
            "items-center gap-3 px-5 py-3 bg-slate-50 dark:bg-slate-900 "
            "border-b border-slate-200 dark:border-slate-800"
        ):
            ui.icon("calendar_month", color="red").classes("text-xl")
            ui.label("Google Calendar").classes("font-bold text-slate-800 dark:text-slate-100 flex-1")
            placeholder = ui.element("div")

        with ui.column().classes("px-5 py-4 gap-2 w-full"):
            creds_ok = os.path.isfile(calendar_service.credentials_path)
            token_ok = os.path.isfile(calendar_service.token_path)
            overall = creds_ok and token_ok

            with placeholder:
                _status_chip(overall, "Authentifié", "Non configuré")

            rows = [
                ("credentials.json", "✓ Présent" if creds_ok else "✗ Manquant — téléchargez-le depuis Google Cloud Console"),
                ("token.json", "✓ Présent" if token_ok else "✗ Manquant — lancez l'autorisation OAuth"),
            ]
            with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1"):
                for label, val in rows:
                    ui.label(label).classes("text-xs text-slate-400 font-mono")
                    color = "text-slate-600 dark:text-slate-300" if "✓" in val else "text-red-500"
                    ui.label(val).classes(f"text-xs {color}")


def _check_cache():
    from backend.state.store import data_store
    import os

    with ui.card().classes(
        "w-full p-0 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden"
    ):
        with ui.row().classes(
            "items-center gap-3 px-5 py-3 bg-slate-50 dark:bg-slate-900 "
            "border-b border-slate-200 dark:border-slate-800"
        ):
            ui.icon("memory", color="slate").classes("text-xl")
            ui.label("Cache applicatif").classes("font-bold text-slate-800 dark:text-slate-100 flex-1")
            _status_chip(data_store.is_preloaded, "Chargé", "En cours")

        with ui.column().classes("px-5 py-4 gap-2 w-full"):
            cache_size = os.path.getsize(data_store.CACHE_FILE) // 1024 if os.path.isfile(data_store.CACHE_FILE) else 0
            last_sync = data_store.items_last_synced.strftime("%d/%m/%Y %H:%M") if data_store.items_last_synced else "—"

            rows = [
                ("Cours chargés", str(len(data_store.cours))),
                ("Items en cache", str(len(data_store.items_map))),
                ("Dernier sync items", last_sync),
                ("Taille cache JSON", f"{cache_size} Ko"),
            ]
            with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1"):
                for label, val in rows:
                    ui.label(label).classes("text-xs text-slate-400")
                    ui.label(val).classes("text-xs font-mono text-slate-600 dark:text-slate-300")
