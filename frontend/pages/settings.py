from nicegui import ui
from frontend.theme import frame
from backend.state.store import data_store
from backend.core.reviews import local_store
from backend.config.settings import settings as _app_settings
import os
import datetime
import subprocess
import shutil
from pathlib import Path

def _show_uncertain_dialog(uncertain_matches: list) -> None:
    from backend.core.obsidian.sync import vault_sync_service
    selected: dict[str, bool] = {str(m.path): True for m in uncertain_matches}

    with ui.dialog().props("persistent") as dlg:
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

    def _section_header(label: str) -> None:
        with ui.row().classes("items-center gap-3 mt-8 mb-3"):
            ui.separator().classes("flex-1 opacity-30")
            ui.label(label).classes(
                "text-[11px] font-bold uppercase tracking-widest "
                "text-slate-400 dark:text-slate-500 px-2 shrink-0"
            )
            ui.separator().classes("flex-1 opacity-30")

    with ui.column().classes("w-full max-w-3xl mx-auto pb-24"):
        ui.label("Paramètres").classes('text-2xl font-bold text-slate-800 dark:text-slate-100')
        ui.label("Configuration de Synapse").classes('text-sm text-slate-400 dark:text-slate-500 mb-2')

        # ══════════════════ PERSONNALISATION ══════════════════
        _section_header("Personnalisation")

        # Affichage — inline card (toggle simple, pas besoin d'accordéon)
        with ui.card().classes(
            'w-full rounded-xl border border-slate-200 dark:border-slate-800 mb-3 shadow-sm px-4 py-3'
        ):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('dark_mode', color='indigo').classes('text-xl')
                    with ui.column().classes('gap-0'):
                        ui.label('Mode Sombre').classes('font-semibold text-sm text-slate-700 dark:text-slate-200')
                        ui.label('Basculer entre thème clair et sombre').classes('text-xs text-slate-400 dark:text-slate-500')
                dark_mode = ui.switch(value=data_store.preferences.get('dark_mode', False)).props('color=indigo')
                dark_mode.on('update:model-value', lambda e: toggle_dark_mode(e.value))

        # Pomodoro
        with ui.expansion('Pomodoro', icon='timer').classes(
            'w-full rounded-xl border border-slate-200 dark:border-slate-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-slate-800 dark:text-slate-100"'):
            with ui.column().classes('p-4 w-full gap-6'):
                ui.label('Configuration des profils Focus').classes('text-sm text-slate-500 dark:text-slate-400')
                with ui.grid(columns=1).classes('w-full gap-4 md:grid-cols-2'):
                    with ui.card().classes('w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4'):
                        ui.label('Profil 1 — Standard').classes('font-semibold text-sm text-slate-700 dark:text-slate-300 mb-3')
                        with ui.row().classes('w-full gap-2'):
                            pomo_1_work = ui.number('Focus (min)', value=data_store.preferences.get('pomo_1_work', 25), min=1, max=120).props('outlined dense').classes('w-full')
                            pomo_1_break = ui.number('Pause (min)', value=data_store.preferences.get('pomo_1_break', 5), min=1, max=30).props('outlined dense').classes('w-full')
                    with ui.card().classes('w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4'):
                        ui.label('Profil 2 — Intensif').classes('font-semibold text-sm text-slate-700 dark:text-slate-300 mb-3')
                        with ui.row().classes('w-full gap-2'):
                            pomo_2_work = ui.number('Focus (min)', value=data_store.preferences.get('pomo_2_work', 50), min=1, max=120).props('outlined dense').classes('w-full')
                            pomo_2_break = ui.number('Pause (min)', value=data_store.preferences.get('pomo_2_break', 10), min=1, max=30).props('outlined dense').classes('w-full')
                ui.label("Ces réglages mettent à jour les boutons du Dashboard.").classes('text-xs text-amber-600 dark:text-amber-400 italic')

        # Durées des activités
        with ui.expansion('Durées des activités', icon='schedule').classes(
            'w-full rounded-xl border border-slate-200 dark:border-slate-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-slate-800 dark:text-slate-100"'):
            with ui.column().classes('p-4 w-full gap-4'):
                ui.label('Durées utilisées par le planning automatique et pour estimer la charge journalière (minutes).').classes('text-sm text-slate-500 dark:text-slate-400')
                from backend.core.planning.service import _DUR_KEYS
                _dur_labels = {
                    "revision": "Révision", "lecture": "Lecture",
                    "anki": "Anki", "qcm": "QCM",
                    "video_ednpro": "Vidéo EDNpro", "obsidian": "Note Obsidian",
                    "lacune": "Revoir lacune", "fiche_edn": "Fiche EDN",
                }
                _dur_inputs: dict = {}
                with ui.grid(columns=2).classes('w-full gap-4 md:grid-cols-4'):
                    for key, (pref_key, default) in _DUR_KEYS.items():
                        label = _dur_labels.get(key, key.capitalize())
                        inp = ui.number(
                            label=f'{label} (min)',
                            value=int(data_store.preferences.get(pref_key, default)),
                            min=5, max=120, step=5,
                        ).props('outlined dense').classes('w-full')
                        _dur_inputs[pref_key] = inp

                def _save_durations():
                    for pref_key, inp in _dur_inputs.items():
                        try:
                            data_store.preferences[pref_key] = int(inp.value)
                        except Exception:
                            pass
                    data_store.save_to_disk()
                    ui.notify("Durées sauvegardées ✓", type="positive", icon="schedule")

                ui.button('Sauvegarder', icon='save', on_click=_save_durations).props('unelevated color=indigo size=sm rounded')

        # Objectif quotidien — inline card (input simple, pas besoin d'accordéon)
        with ui.card().classes(
            'w-full rounded-xl border border-indigo-100 dark:border-indigo-900/50 mb-3 shadow-sm px-4 py-3'
        ):
            with ui.row().classes('w-full items-center gap-4'):
                ui.icon('flag', color='indigo').classes('text-xl shrink-0')
                with ui.column().classes('gap-0 flex-1'):
                    ui.label('Objectif quotidien').classes('font-semibold text-sm text-slate-700 dark:text-slate-200')
                    ui.label('Révisions à valider par jour').classes('text-xs text-slate-400 dark:text-slate-500')
                _goal_inp = ui.number(
                    value=data_store.preferences.get('daily_goal', 5), min=1, max=50,
                ).props('outlined dense').classes('w-28')
                ui.label('/ jour').classes('text-xs text-slate-500 shrink-0')
            def _save_goal(e):
                try:
                    data_store.set_preference('daily_goal', int(e.value))
                    ui.notify(f"Objectif : {int(e.value)}/jour ✓", type='positive', timeout=1500)
                except Exception:
                    pass
            _goal_inp.on('blur', _save_goal)

        # Mode Examen
        with ui.expansion('Mode Examen', icon='event').classes(
            'w-full rounded-xl border border-red-200 dark:border-red-900/50 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-red-700 dark:text-red-400"'):
            with ui.column().classes('p-4 w-full gap-4'):
                with ui.row().classes('items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-100 dark:border-red-800'):
                    ui.icon('info_outline', color='red').classes('text-lg shrink-0 mt-0.5')
                    ui.label(
                        'Renseignez la date de votre prochain examen. '
                        'Un compte à rebours s\'affichera dans l\'en-tête.'
                    ).classes('text-xs text-red-700 dark:text-red-300')
                _exam_date_inp = ui.input(
                    label='Date de l\'examen',
                    value=data_store.preferences.get('exam_date', ''),
                    placeholder='AAAA-MM-JJ (ex: 2026-10-15)',
                ).props('outlined clearable').classes('w-64')
                ui.label('Format : AAAA-MM-JJ · Laissez vide pour désactiver.').classes('text-xs text-slate-400 -mt-2')
                _exam_label_inp = ui.input(
                    label='Nom de l\'examen (optionnel)',
                    value=data_store.preferences.get('exam_label', 'EDN'),
                    placeholder='EDN, Concours Interne, DFASM2...',
                ).props('outlined clearable').classes('w-64')
                def _save_exam():
                    raw = (_exam_date_inp.value or "").strip()
                    lbl = (_exam_label_inp.value or "EDN").strip()
                    if raw:
                        try:
                            datetime.date.fromisoformat(raw)
                        except ValueError:
                            ui.notify("Format de date invalide — utilisez AAAA-MM-JJ", type='negative')
                            return
                    data_store.set_preference('exam_date', raw)
                    data_store.set_preference('exam_label', lbl)
                    ui.notify("Date d'examen enregistrée ✓", type='positive', timeout=1500)
                ui.button('Enregistrer', icon='save', on_click=_save_exam).props('unelevated color=red size=sm rounded')

        # ══════════════════ COMPTE & SYNCHRONISATION ══════════════════
        _section_header("Compte & Synchronisation")

        # LiSA / UNESS
        with ui.expansion('LiSA / UNESS', icon='school').classes(
            'w-full rounded-xl border border-teal-200 dark:border-teal-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-teal-700 dark:text-teal-300"'):
            with ui.column().classes('p-4 w-full gap-4'):
                with ui.row().classes('items-start gap-2 p-3 bg-teal-50 dark:bg-teal-900/20 rounded-xl border border-teal-100 dark:border-teal-800'):
                    ui.icon('auto_awesome', color='teal').classes('text-lg shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label('Connexion automatique via CAS UNESS').classes('text-xs text-teal-700 dark:text-teal-300 font-semibold')
                        ui.label('Synapse se reconnecte automatiquement quand la session expire.').classes('text-xs text-slate-500')
                lisa_user_input = ui.input(
                    label='Identifiant UNESS',
                    value=_app_settings.lisa_username,
                    placeholder='prenom.nom@univ.fr ou identifiant ENT',
                ).props('outlined').classes('w-full')
                lisa_pass_input = ui.input(
                    label='Mot de passe UNESS',
                    value=_app_settings.lisa_password,
                    password=True, password_toggle_button=True,
                ).props('outlined').classes('w-full')
                lisa_status = ui.label('').classes('text-xs text-slate-400 -mt-1')
                if _app_settings.lisa_cookie:
                    lisa_status.set_text('Session active (cookie présent)')
                    lisa_status.classes('text-emerald-600', remove='text-slate-400')

                async def _connect_lisa():
                    from backend.core.lisa.auth import cas_login, LisaAuthError
                    username = (lisa_user_input.value or '').strip()
                    password = (lisa_pass_input.value or '').strip()
                    if not username or not password:
                        ui.notify('Remplissez identifiant et mot de passe', type='warning')
                        return
                    _write_env_var('LISA_USERNAME', username)
                    _write_env_var('LISA_PASSWORD', password)
                    _app_settings.lisa_username = username
                    _app_settings.lisa_password = password
                    lisa_status.set_text('Connexion en cours…')
                    lisa_status.classes('text-slate-400', remove='text-emerald-600 text-red-500')
                    try:
                        import asyncio
                        cookie = await asyncio.to_thread(cas_login, username, password)
                        _app_settings.lisa_cookie = cookie
                        _write_env_var('LISA_COOKIE', cookie)
                        lisa_status.set_text('Connecté ✓ — OIC disponibles')
                        lisa_status.classes('text-emerald-600', remove='text-slate-400 text-red-500')
                        ui.notify('Authentification LiSA réussie ✓', type='positive', icon='school')
                    except LisaAuthError as exc:
                        lisa_status.set_text(f'Échec : {exc}')
                        lisa_status.classes('text-red-500', remove='text-slate-400 text-emerald-600')
                        ui.notify(str(exc), type='negative')

                ui.button('Se connecter', icon='login', on_click=_connect_lisa).props('unelevated color=teal size=sm rounded')

                with ui.expansion('Cookie manuel (avancé)', icon='code').classes('w-full rounded-lg border border-slate-200 dark:border-slate-700'):
                    with ui.column().classes('p-3 gap-3'):
                        ui.label('Si la connexion automatique échoue, collez ici le cookie depuis DevTools (F12 → Network → Cookie header).').classes('text-xs text-slate-500')
                        lisa_cookie_input = ui.textarea(
                            label='Cookie brut',
                            value=_app_settings.lisa_cookie,
                            placeholder='mwdb_session=xxx; mwdbUserName=yyy; …',
                        ).props('outlined').classes('w-full font-mono text-xs')
                        def _save_cookie_manual():
                            val = (lisa_cookie_input.value or '').strip()
                            if _write_env_var('LISA_COOKIE', val):
                                _app_settings.lisa_cookie = val
                                ui.notify('Cookie sauvegardé', type='positive' if val else 'info')
                            else:
                                ui.notify('Erreur écriture .env', type='negative')
                        ui.button('Sauvegarder cookie', icon='save', on_click=_save_cookie_manual).props('outline color=teal size=sm rounded')


        # --- ANYTHINGLLM ---
        with ui.expansion('AnythingLLM', icon='smart_toy').classes(
            'w-full rounded-xl border border-indigo-200 dark:border-indigo-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-indigo-700 dark:text-indigo-300"'):
            with ui.column().classes('p-4 w-full gap-4'):
                with ui.row().classes('items-start gap-2 p-3 bg-indigo-50 dark:bg-indigo-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800'):
                    ui.icon('auto_awesome', color='indigo').classes('text-lg shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label('Évaluation des OIC par IA locale').classes('text-xs text-indigo-700 dark:text-indigo-300 font-semibold')
                        ui.label('AnythingLLM doit tourner en local avec un workspace par collège.').classes('text-xs text-slate-500')
                anythingllm_url_input = ui.input(
                    label='URL AnythingLLM',
                    value=_app_settings.anythingllm_url,
                    placeholder='http://localhost:3001',
                ).props('outlined').classes('w-full')
                anythingllm_key_input = ui.input(
                    label='Clé API',
                    value=_app_settings.anythingllm_api_key,
                    password=True, password_toggle_button=True,
                ).props('outlined').classes('w-full')
                anythingllm_status = ui.label('').classes('text-xs text-slate-400 -mt-1')

                async def _test_anythingllm():
                    import asyncio
                    url = (anythingllm_url_input.value or '').strip()
                    key = (anythingllm_key_input.value or '').strip()
                    _write_env_var('ANYTHINGLLM_URL', url)
                    _write_env_var('ANYTHINGLLM_API_KEY', key)
                    _app_settings.anythingllm_url = url
                    _app_settings.anythingllm_api_key = key
                    anythingllm_status.set_text('Connexion en cours…')
                    anythingllm_status.classes('text-slate-400', remove='text-emerald-600 text-red-500')
                    try:
                        from backend.core.lisa.anythingllm_client import list_workspaces, AnythingLLMUnavailableError
                        workspaces = await asyncio.to_thread(list_workspaces)
                        anythingllm_status.set_text(f'Connecté ✓ — {len(workspaces)} workspace(s) trouvé(s)')
                        anythingllm_status.classes('text-emerald-600', remove='text-slate-400 text-red-500')
                        ui.notify('Connexion AnythingLLM réussie ✓', type='positive', icon='smart_toy')
                    except AnythingLLMUnavailableError as exc:
                        anythingllm_status.set_text(f'Échec : {exc}')
                        anythingllm_status.classes('text-red-500', remove='text-slate-400 text-emerald-600')
                        ui.notify(str(exc), type='negative')

                ui.button('Tester la connexion', icon='wifi', on_click=_test_anythingllm).props('unelevated color=indigo size=sm rounded')


        # Agendas Google Calendar
        with ui.expansion('Agendas Google Calendar', icon='event').classes(
            'w-full rounded-xl border border-blue-200 dark:border-blue-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-blue-700 dark:text-blue-300"'):
            with ui.column().classes('p-4 w-full gap-4'):
                with ui.row().classes('items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-100 dark:border-blue-800'):
                    ui.icon('info_outline', color='blue').classes('text-lg shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label("L'agenda principal (primary) est toujours inclus.").classes('text-xs text-blue-700 dark:text-blue-300')
                        ui.label("Ajoutez les IDs des agendas supplémentaires. Trouvez l'ID dans Google Calendar → Paramètres de l'agenda → Intégration.").classes('text-xs text-slate-400')
                ids_col = ui.column().classes('w-full gap-2')
                current_ids = list(_app_settings.get_calendar_ids())
                cal_inputs: list = []

                def _render_cal_inputs():
                    ids_col.clear()
                    cal_inputs.clear()
                    with ids_col:
                        for i, cid in enumerate(current_ids):
                            with ui.row().classes('items-center gap-2 w-full'):
                                inp = ui.input(value=cid, placeholder='xxx@group.calendar.google.com').props('outlined dense clearable').classes('flex-1')
                                cal_inputs.append(inp)
                                def _remove(idx=i):
                                    if 0 <= idx < len(current_ids):
                                        current_ids.pop(idx)
                                    _render_cal_inputs()
                                ui.button(icon='delete', on_click=_remove).props('flat round dense size=sm color=red')
                        if not current_ids:
                            ui.label('Aucun agenda supplémentaire configuré.').classes('text-xs text-slate-400 italic')

                _render_cal_inputs()
                with ui.row().classes('gap-3 items-center mt-1'):
                    def _add_cal():
                        current_ids.append('')
                        _render_cal_inputs()
                    ui.button('+ Ajouter un agenda', icon='add', on_click=_add_cal).props('outline color=blue size=sm rounded')

                    def _save_calendars():
                        new_ids = [inp.value.strip() for inp in cal_inputs if inp.value and inp.value.strip()]
                        current_ids.clear()
                        current_ids.extend(new_ids)
                        ok = _write_env_var("GOOGLE_CALENDAR_IDS", ",".join(new_ids))
                        if ok:
                            _app_settings.google_calendar_ids = ",".join(new_ids)
                            ui.notify(f"{len(new_ids)} agenda(s) sauvegardé(s) ✓", type="positive", icon="event")
                            _render_cal_inputs()
                        else:
                            ui.notify("Erreur lors de l'écriture du .env", type="negative")

                    ui.button('Sauvegarder', icon='save', on_click=_save_calendars).props('unelevated color=blue size=sm rounded')

        # ══════════════════ INTÉGRATIONS ══════════════════
        _section_header("Intégrations")

        # Obsidian
        with ui.expansion('Obsidian', icon='edit_note').classes(
            'w-full rounded-xl border border-violet-200 dark:border-violet-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-violet-700 dark:text-violet-300"'):
            with ui.column().classes('p-4 w-full gap-5'):
                with ui.row().classes('items-start gap-2 p-3 bg-indigo-50 dark:bg-indigo-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800'):
                    ui.icon('info_outline', color='indigo').classes('text-lg shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label('Ces réglages sont écrits dans le fichier .env et appliqués immédiatement.').classes('text-xs text-indigo-700 dark:text-indigo-300')
                        ui.label('Redémarrez l\'application si les badges n\'apparaissent pas.').classes('text-xs text-slate-400')

                vault_path_input = ui.input(
                    label='Chemin du vault Obsidian',
                    value=_app_settings.obsidian_vault_path,
                    placeholder=r'Ex : G:\Mon Drive\Médecine\Médecine',
                ).props('outlined clearable').classes('w-full')
                ui.label('Chemin absolu vers le dossier racine du vault (contient 01 - Cours EDN/).').classes('text-xs text-slate-400 -mt-2')

                vault_name_input = ui.input(
                    label='Nom du vault Obsidian',
                    value=_app_settings.obsidian_vault_name,
                    placeholder='Ex : Médecine',
                ).props('outlined clearable').classes('w-full')
                ui.label('Nom exact du vault dans Obsidian (utilisé pour les URI obsidian://).').classes('text-xs text-slate-400 -mt-2')

                template_path_label = ui.label()

                def _refresh_template_status():
                    vp = vault_path_input.value or ""
                    if vp:
                        tpl = Path(vp) / "90 - Template" / "Template - Cours.md"
                        if tpl.exists():
                            template_path_label.set_text(f"✅ Template trouvé : {tpl}")
                            template_path_label.classes('text-xs text-green-600', remove='text-slate-400 text-orange-500')
                        else:
                            template_path_label.set_text(f"⚠️ Template absent : {tpl}  (template de secours utilisé)")
                            template_path_label.classes('text-xs text-orange-500', remove='text-slate-400 text-green-600')
                    else:
                        template_path_label.set_text("Entrez un chemin de vault pour vérifier le template.")
                        template_path_label.classes('text-xs text-slate-400', remove='text-green-600 text-orange-500')

                vault_path_input.on('blur', lambda: _refresh_template_status())
                _refresh_template_status()

                from backend.core.obsidian.service import COLLEGE_MAPPING
                with ui.expansion('Correspondances collèges Notion → Obsidian', icon='swap_horiz').classes('w-full rounded-lg border border-slate-200 dark:border-slate-700'):
                    with ui.column().classes('p-3 gap-1 w-full'):
                        ui.label('Les collèges ci-dessous ont un nom différent entre Notion et le vault.').classes('text-xs text-slate-400 mb-2')
                        with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-0.5'):
                            ui.label('Notion').classes('text-[11px] font-bold text-slate-500 uppercase tracking-wider')
                            ui.label('Dossier Obsidian').classes('text-[11px] font-bold text-slate-500 uppercase tracking-wider')
                            for notion_name, obsidian_name in COLLEGE_MAPPING.items():
                                ui.label(notion_name).classes('text-xs text-slate-600 dark:text-slate-300 font-mono border-t border-slate-100 dark:border-slate-800 py-0.5')
                                ui.label(obsidian_name).classes('text-xs text-violet-600 dark:text-violet-400 font-mono border-t border-slate-100 dark:border-slate-800 py-0.5')
                        ui.label('Pour modifier : backend/core/obsidian/service.py → COLLEGE_MAPPING').classes('text-[11px] text-slate-400 italic mt-2')

                with ui.row().classes('gap-3 items-center flex-wrap'):
                    ui.button(
                        'Sauvegarder', icon='save',
                        on_click=lambda: _save_obsidian_settings(vault_path_input.value, vault_name_input.value, _refresh_template_status),
                    ).props('unelevated color=violet size=sm rounded')

                    def _copy_env_snippet():
                        snippet = f"OBSIDIAN_VAULT_PATH={vault_path_input.value or ''}\nOBSIDIAN_VAULT_NAME={vault_name_input.value or ''}"
                        ui.run_javascript(f"navigator.clipboard.writeText({snippet!r})")
                        ui.notify("Snippet .env copié", type='info', icon='content_copy')

                    ui.button('Copier config .env', icon='content_copy', on_click=_copy_env_snippet).props('outline color=slate size=sm rounded')
                    ui.button(
                        'Ouvrir dossier vault', icon='folder_open',
                        on_click=lambda: subprocess.Popen(['explorer', vault_path_input.value]) if vault_path_input.value else ui.notify('Chemin vide', type='warning'),
                    ).props('flat color=slate size=sm')
                    ui.separator().props('vertical').classes('self-stretch mx-1 opacity-30')
                    ui.button(
                        'Scanner le vault', icon='manage_search',
                        on_click=lambda: _run_vault_scan(vault_path_input),
                    ).props('outline color=violet size=sm rounded').tooltip('Cherche les notes Obsidian non liées et les associe aux cours Synapse')

        # Import PDF → Notion
        with ui.expansion('Import PDF → Notion', icon='picture_as_pdf').classes(
            'w-full rounded-xl border border-emerald-200 dark:border-emerald-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-emerald-700 dark:text-emerald-300"'):
            with ui.column().classes('p-4 w-full gap-4'):
                with ui.row().classes('items-start gap-2 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl border border-emerald-100 dark:border-emerald-800'):
                    ui.icon('info_outline', color='green').classes('text-lg shrink-0 mt-0.5')
                    with ui.column().classes('gap-0.5'):
                        ui.label('Scanne les dossiers Collèges/{college}/items/ et crée dans Notion les cours dont le PDF est présent mais pas encore dans la base.').classes('text-xs text-emerald-700 dark:text-emerald-300')
                        ui.label('Le résultat est mémorisé — seuls les nouveaux PDFs sont vérifiés à chaque lancement.').classes('text-xs text-slate-400')

                stats_label = ui.label('…').classes('text-xs text-slate-500 italic')

                def _refresh_pdf_stats():
                    s = local_store.get_pdf_scan_stats()
                    if s['total'] == 0:
                        stats_label.set_text('Aucun scan effectué.')
                    else:
                        stats_label.set_text(f"{s['total']} PDFs vus · {s['created']} créés · {s['existing']} déjà présents · {s['failed']} erreurs")

                _refresh_pdf_stats()
                pdf_scan_status = ui.label('').classes('text-sm font-medium min-h-[1.25rem]')

                async def _run_pdf_scan(force: bool = False):
                    from backend.core.pdf_import import auto_import_courses_from_pdf_folders
                    pdf_scan_btn.disable()
                    pdf_force_btn.disable()
                    pdf_scan_status.set_text('Scan en cours…')
                    pdf_scan_status.classes('text-blue-600', remove='text-green-600 text-red-600 text-slate-400')
                    try:
                        r = await auto_import_courses_from_pdf_folders(list(data_store.cours), force=force)
                        if r['created'] > 0:
                            pdf_scan_status.set_text(f"✅ {r['created']} cours créés · {r['existing_skipped']} déjà présents · {r['failed']} erreurs")
                            pdf_scan_status.classes('text-green-600', remove='text-blue-600 text-red-600 text-slate-400')
                        elif r['failed'] > 0:
                            pdf_scan_status.set_text(f"⚠️ 0 créés · {r['failed']} erreur(s) — voir les logs")
                            pdf_scan_status.classes('text-red-600', remove='text-blue-600 text-green-600 text-slate-400')
                        else:
                            pdf_scan_status.set_text(f"Aucun cours manquant ({r['total_found']} PDFs scannés)")
                            pdf_scan_status.classes('text-slate-400', remove='text-blue-600 text-green-600 text-red-600')
                    except Exception as exc:
                        pdf_scan_status.set_text(f"Erreur : {exc}")
                        pdf_scan_status.classes('text-red-600', remove='text-blue-600 text-green-600 text-slate-400')
                    finally:
                        pdf_scan_btn.enable()
                        pdf_force_btn.enable()
                        _refresh_pdf_stats()

                with ui.row().classes('gap-3 items-center flex-wrap'):
                    pdf_scan_btn = ui.button('Scanner maintenant', icon='search', on_click=lambda: _run_pdf_scan(force=False)).props('unelevated color=green size=sm rounded')
                    pdf_force_btn = ui.button('Forcer rescan complet', icon='refresh', on_click=lambda: _run_pdf_scan(force=True)).props('outline color=slate size=sm rounded').tooltip('Efface le cache et revérifie tous les PDFs')

        # ══════════════════ SYSTÈME ══════════════════
        _section_header("Système")

        # Base locale
        with ui.expansion('Base locale — Révisions', icon='storage').classes(
            'w-full rounded-xl border border-slate-200 dark:border-slate-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-slate-800 dark:text-slate-100"'):
            with ui.column().classes('p-4 w-full gap-4'):
                stats_container = ui.column().classes('w-full gap-3')

                def _render_stats():
                    stats_container.clear()
                    s = local_store.get_stats()
                    with stats_container:
                        if 'error' in s:
                            ui.label(f"Erreur : {s['error']}").classes('text-xs text-red-500')
                            return
                        with ui.card().classes('w-full p-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700'):
                            with ui.row().classes('items-center gap-2 mb-2'):
                                ui.icon('database', size='sm').classes('text-indigo-500')
                                ui.label('Base SQLite').classes('font-bold text-sm text-slate-700 dark:text-slate-200')
                            with ui.grid(columns=2).classes('w-full gap-x-6 gap-y-1'):
                                ui.label('Fichier').classes('text-xs text-slate-400')
                                ui.label(s['db_path']).classes('text-xs text-slate-600 dark:text-slate-300 truncate font-mono')
                                ui.label('Taille').classes('text-xs text-slate-400')
                                ui.label(f"{s['db_size_kb']} Ko").classes('text-xs text-slate-600 dark:text-slate-300')
                                ui.label('Dernière validation').classes('text-xs text-slate-400')
                                ui.label(s['last_done'] or '—').classes('text-xs text-slate-600 dark:text-slate-300')
                        with ui.grid(columns=3).classes('w-full gap-3'):
                            for label, value, color, icon_name in [
                                ('Révisions total', s['nb_reviews'], 'indigo', 'history'),
                                ('Validées', s['nb_done'], 'green', 'check_circle'),
                                ('Reportées', s['nb_postponed'], 'orange', 'event_repeat'),
                                ('Ignorées', s['nb_ignored'], 'slate', 'block'),
                                ('Résultats QCM', s['nb_qcm'], 'blue', 'quiz'),
                                ('Sessions travail', s['nb_sessions'], 'violet', 'school'),
                            ]:
                                with ui.card().classes(f'p-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex flex-col items-center gap-1'):
                                    ui.icon(icon_name, size='sm').classes(f'text-{color}-500')
                                    ui.label(str(value)).classes(f'text-xl font-bold text-{color}-600 dark:text-{color}-400')
                                    ui.label(label).classes('text-[11px] text-slate-400 text-center')
                        with ui.row().classes('gap-3 flex-wrap'):
                            ui.button('Rafraîchir', icon='refresh', on_click=_render_stats).props('outline color=slate size=sm')

                            def _backup_sqlite():
                                try:
                                    src = local_store.DB_PATH
                                    if not src.exists():
                                        ui.notify("Aucune base à sauvegarder.", type='warning')
                                        return
                                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                    dst = src.parent / f"synapse_local_backup_{ts}.db"
                                    shutil.copy2(src, dst)
                                    ui.notify(f"Backup créé : {dst.name}", type='positive')
                                    subprocess.Popen(['explorer', f'/select,{str(dst)}'])
                                except Exception as e:
                                    ui.notify(f"Erreur backup : {e}", type='negative')

                            ui.button('Sauvegarder DB', icon='save', on_click=_backup_sqlite).props('outline color=green size=sm')

                            def _export_sqlite():
                                try:
                                    src = local_store.DB_PATH
                                    if not src.exists():
                                        ui.notify("Aucune base à exporter.", type='warning')
                                        return
                                    import csv, sqlite3 as _sqlite3
                                    export_dir = src.parent / "exports"
                                    export_dir.mkdir(exist_ok=True)
                                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                    con = _sqlite3.connect(src)
                                    con.row_factory = _sqlite3.Row
                                    for table in ("review_history", "qcm_results", "study_sessions"):
                                        rows = con.execute(f"SELECT * FROM {table}").fetchall()
                                        if not rows:
                                            continue
                                        out = export_dir / f"{table}_{ts}.csv"
                                        with open(out, "w", newline="", encoding="utf-8") as f:
                                            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                                            writer.writeheader()
                                            writer.writerows([dict(r) for r in rows])
                                    con.close()
                                    ui.notify(f"CSV exportés dans exports/", type='positive')
                                    subprocess.Popen(['explorer', str(export_dir)])
                                except Exception as e:
                                    ui.notify(f"Erreur export : {e}", type='negative')

                            ui.button('Exporter CSV', icon='download', on_click=_export_sqlite).props('outline color=blue size=sm')

                            def _open_data_folder():
                                subprocess.Popen(['explorer', str(local_store.DB_PATH.parent)])

                            ui.button('Ouvrir dossier data', icon='folder_open', on_click=_open_data_folder).props('outline color=indigo size=sm')

                _render_stats()

        # Maintenance
        with ui.expansion('Maintenance', icon='build').classes(
            'w-full rounded-xl border border-slate-200 dark:border-slate-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-slate-800 dark:text-slate-100"'):
            with ui.column().classes('p-4 w-full gap-4'):
                with ui.row().classes('gap-3 flex-wrap'):
                    ui.button('Créer une Sauvegarde', icon='save', on_click=backup_data).props('outline color=slate size=sm')
                    ui.button('Vider le Cache PDF', icon='cleaning_services', on_click=clear_pdf_cache).props('outline color=orange size=sm')

                    async def _force_autolink():
                        from backend.core.background import trigger_autolink_now
                        from backend.core.reviews.service import review_service
                        ui.notify("Re-scan auto-link en cours…", type="info", icon="sync", timeout=3000)
                        await trigger_autolink_now()
                        review_service.invalidate_cache()
                        ui.notify("Auto-link terminé ✓", type="positive", icon="link")

                    ui.button('Forcer rescan auto-link', icon='link', on_click=_force_autolink).props('outline color=indigo size=sm').tooltip('Relie les cours à leurs items Notion')

                    def _confirm_reset_qcm():
                        with ui.dialog() as dlg:
                            with ui.card().classes('rounded-2xl p-5 bg-white dark:bg-slate-900 shadow-xl flex flex-col gap-3').style('min-width:340px'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('delete_forever', size='sm').classes('text-red-500')
                                    ui.label('Vider toutes les données QCM ?').classes('font-bold text-slate-800 dark:text-slate-100 text-sm')
                                ui.label('Supprime définitivement toutes les sessions QCM de la base locale. Les données Notion ne sont pas affectées.').classes('text-xs text-slate-500 leading-snug')
                                with ui.row().classes('gap-2 justify-end mt-2'):
                                    ui.button('Annuler', on_click=dlg.close).props('flat color=grey-8 dense')
                                    def _do_reset_qcm():
                                        import sqlite3 as _sq
                                        con = _sq.connect(local_store.DB_PATH)
                                        r1 = con.execute('DELETE FROM qcm_results').rowcount
                                        r2 = con.execute('DELETE FROM qcm_sessions').rowcount
                                        con.commit(); con.close()
                                        _state = local_store.DB_PATH.parent / 'ednpro_sync_state.json'
                                        if _state.exists():
                                            _state.unlink()
                                        dlg.close()
                                        ui.notify(f'QCM réinitialisé — {r1 + r2} entrée(s) supprimée(s)', type='warning', icon='delete')
                                    ui.button('Vider les QCM', icon='delete_forever', on_click=_do_reset_qcm).props('unelevated color=red rounded dense')
                        dlg.open()

                    ui.button('Vider les données QCM', icon='quiz', on_click=_confirm_reset_qcm).props('outline color=red size=sm').tooltip('Supprime toutes les sessions QCM de la base locale')

        # Santé du système
        with ui.expansion('Santé du système', icon='monitor_heart').classes(
            'w-full rounded-xl border border-slate-200 dark:border-slate-800 mb-3 shadow-sm'
        ).props('header-class="font-semibold text-slate-800 dark:text-slate-100"'):
            with ui.column().classes('p-4 w-full gap-4'):
                ui.label('Vérifie en temps réel la connectivité Notion, SQLite, Obsidian et Google Calendar.').classes('text-sm text-slate-500 dark:text-slate-400')
                _health_col = ui.column().classes('w-full gap-4')

                async def _run_health_checks():
                    from frontend.pages.health import (
                        _check_notion, _check_sqlite,
                        _check_obsidian, _check_google_calendar, _check_cache,
                    )
                    _health_col.clear()
                    with _health_col:
                        ui.spinner(size='lg').classes('mx-auto my-6')
                    _health_col.clear()
                    with _health_col:
                        await _check_notion()
                        await _check_sqlite()
                        _check_obsidian()
                        _check_google_calendar()
                        _check_cache()

                ui.button('Lancer le diagnostic', icon='play_arrow', on_click=_run_health_checks).props('unelevated color=indigo rounded size=sm')

    # Sticky save button (saves pomodoro + dark mode + obsidian)
    with ui.row().classes('w-full justify-end mt-4 sticky bottom-6 bg-transparent'):
        ui.button(
            'Enregistrer Tout', icon='save',
            on_click=lambda: save_all(dark_mode, pomo_1_work, pomo_1_break, pomo_2_work, pomo_2_break, vault_path_input, vault_name_input)
        ).props('unelevated color=indigo size=lg').classes('shadow-xl')


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _find_env_file() -> Path:
    return Path(__file__).parent.parent.parent / ".env"


def _write_env_var(key: str, value: str) -> bool:
    env_path = _find_env_file()
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        found = False
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception as exc:
        from loguru import logger
        logger.error(f"_write_env_var({key}): {exc}")
        return False


def _save_obsidian_settings(vault_path: str, vault_name: str, refresh_fn=None) -> None:
    vault_path = (vault_path or "").strip()
    vault_name = (vault_name or "").strip()
    ok1 = _write_env_var("OBSIDIAN_VAULT_PATH", vault_path)
    ok2 = _write_env_var("OBSIDIAN_VAULT_NAME", vault_name)
    if ok1 and ok2:
        _app_settings.obsidian_vault_path = vault_path
        _app_settings.obsidian_vault_name = vault_name
        ui.notify("Paramètres Obsidian sauvegardés ✓", type="positive", icon="edit_note")
        if refresh_fn:
            refresh_fn()
    else:
        ui.notify("Erreur lors de l'écriture du .env", type="negative")


def toggle_dark_mode(value):
    ui.dark_mode(value)
    data_store.set_preference('dark_mode', value)


def backup_data():
    try:
        src = data_store.CACHE_FILE
        dst = data_store.CACHE_FILE.replace('.json', f'_backup_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        shutil.copy(src, dst)
        ui.notify(f"Backup créé : {os.path.basename(dst)}", type='positive')
        subprocess.Popen(['explorer', f'/select,{dst.replace("/", chr(92))}'])
    except Exception as e:
        ui.notify(f"Erreur backup: {e}", type='negative')


def clear_pdf_cache():
    from backend.core.files import file_service
    file_service.pdf_caches.clear()
    ui.notify("Cache PDF vidé.", type='warning')


async def save_all(dark_mode, p1w, p1b, p2w, p2b, vault_path_input=None, vault_name_input=None):
    try:
        data_store.preferences['dark_mode'] = dark_mode.value
        data_store.preferences['pomo_1_work'] = int(p1w.value)
        data_store.preferences['pomo_1_break'] = int(p1b.value)
        data_store.preferences['pomo_2_work'] = int(p2w.value)
        data_store.preferences['pomo_2_break'] = int(p2b.value)
        data_store.save_to_disk()
        if vault_path_input is not None and vault_name_input is not None:
            _save_obsidian_settings(vault_path_input.value, vault_name_input.value)
        ui.notify("Paramètres enregistrés avec succès !", type='positive')
    except Exception as e:
        ui.notify(f"Erreur sauvegarde: {e}", type='negative')
