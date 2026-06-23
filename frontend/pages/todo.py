from nicegui import ui
from backend.core.notion.service import notion_service
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import local_store
from backend.state.store import data_store
from frontend.theme import frame
import asyncio
import datetime

_MONTHS = ['jan.','fév.','mars','avr.','mai','juin','juil.','août','sep.','oct.','nov.','déc.']
_DAYS   = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']


def _fmt_date(d: datetime.date) -> str:
    return f"{_DAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]} {d.year}"


async def _render_content(
    container: ui.column,
    date_obj: datetime.date,
    progress_state: dict,
    refresh_progress,
) -> None:
    container.clear()
    if container.is_deleted:
        return
    date_str = date_obj.isoformat()
    is_past  = date_obj < datetime.date.today()

    with container:
        # Routine : SQLite, instantané
        routine_col = ui.column().classes('w-full')
        _render_routine_block(routine_col, date_str, progress_state, refresh_progress)

        # Ajouté + Note : chargés en réseau (tâches 4 et 5)
        ajout_col = ui.column().classes('w-full')
        note_col  = ui.column().classes('w-full')

        asyncio.create_task(
            _load_and_render_network_blocs(
                ajout_col, note_col, date_obj, is_past,
                progress_state, refresh_progress,
            )
        )


def _render_routine_block(
    container: ui.column,
    date_str: str,
    progress_state: dict,
    refresh_progress,
) -> None:
    items  = local_store.get_routine_items()
    checks = local_store.get_routine_checks(date_str)

    progress_state['routine'] = [
        len(items),
        sum(1 for name in items if checks.get(name, False)),
    ]

    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-sky-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('ROUTINE').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')
                with ui.element('div').classes(
                        'grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1'):
                    for name in items:
                        checked = checks.get(name, False)

                        def _on_toggle(e, item_name=name):
                            progress_state['routine'][1] += 1 if e.value else -1
                            refresh_progress()
                            local_store.set_routine_check(date_str, item_name, e.value)

                        ui.checkbox(name, value=checked, on_change=_on_toggle).props('dense').classes(
                            'text-slate-700 dark:text-slate-200 transition-opacity duration-200')

    refresh_progress()


def _build_course_list(events, manual_titles, all_courses) -> list[dict]:
    """Pure function — fusionne événements GCal et révisions Notion en une liste unifiée."""
    result = []
    for evt in (events or []):
        summary = evt.get('summary', '')
        if 'Collège' in summary or 'Révision Manuelle' in summary:
            for c in all_courses:
                if c.title in summary:
                    result.append({'course': c, 'type': 'gcal', 'summary': summary})
                    break
    for title in (manual_titles or []):
        c = next((x for x in all_courses if x.title == title), None)
        if c and not any(r['course'].id == c.id for r in result):
            result.append({'course': c, 'type': 'notion_manual', 'summary': title})
    return result


def _render_skeleton_bloc(container: ui.column, marker_css: str, title: str) -> None:
    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes(
                f'w-1 rounded-full {marker_css} self-stretch min-h-[2rem] opacity-30')
            with ui.column().classes('flex-1 gap-2'):
                ui.label(title).classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')
                for w in ['w-3/4', 'w-1/2', 'w-2/3']:
                    ui.element('div').classes(
                        f'h-5 rounded-md animate-pulse bg-slate-200 dark:bg-slate-700 {w}')


async def _load_and_render_network_blocs(
    ajout_col: ui.column,
    note_col: ui.column,
    date_obj: datetime.date,
    is_past: bool,
    progress_state: dict,
    refresh_progress,
) -> None:
    _render_skeleton_bloc(ajout_col, 'bg-violet-500', 'AJOUTÉ')
    _render_skeleton_bloc(note_col,  'bg-amber-500',  'NOTE DU JOUR')

    task, events = await asyncio.gather(
        notion_service.get_daily_task_by_date(date_obj),
        calendar_service.get_events_for_day(date_obj),
    )

    reviewed_titles: list[str] = []
    manual_titles:   list[str] = []
    if task:
        reviewed_titles, manual_titles = await asyncio.gather(
            notion_service.get_daily_reviewed_courses(task.id),
            notion_service.get_daily_manual_revision_courses(task.id),
        )

    if ajout_col.is_deleted or note_col.is_deleted:
        return

    course_items = _build_course_list(events, manual_titles, data_store.cours)

    await _render_ajout_block(
        ajout_col, date_obj, task, course_items,
        reviewed_titles, progress_state, refresh_progress,
    )
    _render_note_block(note_col, task, is_past)
    refresh_progress()


async def _render_ajout_block(
    container: ui.column,
    date_obj: datetime.date,
    task,
    course_items: list[dict],
    reviewed_titles: list[str],
    progress_state: dict,
    refresh_progress,
) -> None:
    dynamic_tasks = task.dynamic_checkboxes if task else {}
    ajout_total = len(course_items) + len(dynamic_tasks)
    ajout_done  = (sum(1 for r in course_items if r['course'].title in reviewed_titles)
                   + sum(1 for d in dynamic_tasks.values() if d['checked']))
    # Écrase (ne cumule pas) pour éviter le double-comptage lors des re-renders
    progress_state['ajout'] = [ajout_total, ajout_done]

    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-violet-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('AJOUTÉ').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')

                # ── Cours ─────────────────────────────────────────────────────
                for item in course_items:
                    _render_course_item(
                        item['course'], item['course'].title in reviewed_titles,
                        item['type'], task, progress_state, refresh_progress,
                    )

                # ── Tâches dynamiques ─────────────────────────────────────────
                for b_id, data in dynamic_tasks.items():
                    async def _toggle_dyn(e, bid=b_id):
                        progress_state['ajout'][1] += 1 if e.value else -1
                        refresh_progress()
                        await notion_service.toggle_dynamic_task(bid, e.value)

                    ui.checkbox(data['text'], value=data['checked'],
                                on_change=_toggle_dyn).props('dense').classes(
                        'text-slate-700 dark:text-slate-200')

                if not course_items and not dynamic_tasks:
                    ui.label('Rien de planifié pour ce jour.').classes(
                        'text-sm text-slate-400 italic')

                # ── Contrôles d'ajout ─────────────────────────────────────────
                with ui.row().classes(
                        'items-center gap-2 mt-2 pt-2 '
                        'border-t border-slate-100 dark:border-slate-800'):
                    ui.button('+ Cours',
                              on_click=lambda: _open_add_course_dialog(date_obj, task)).props(
                        'flat dense').classes(
                        'text-violet-600 dark:text-violet-400 text-sm font-medium')

                    new_task_input = ui.input(placeholder='+ Tâche libre…').props(
                        'borderless dense').classes('flex-1 text-sm text-slate-600 dark:text-slate-300')

                    async def _add_task_free():
                        val = new_task_input.value.strip()
                        if not val or not task:
                            return
                        new_task_input.value = ''
                        if await notion_service.add_dynamic_task(task.id, val):
                            ui.notify('Tâche ajoutée', type='positive')
                            updated = await notion_service.get_daily_task_by_date(date_obj)
                            if updated and not container.is_deleted:
                                await _render_ajout_block(
                                    container, date_obj, updated, course_items,
                                    reviewed_titles, progress_state, refresh_progress,
                                )

                    new_task_input.on('keydown.enter',
                                      lambda: asyncio.create_task(_add_task_free()))
                    ui.button(icon='send',
                              on_click=lambda: asyncio.create_task(_add_task_free())).props(
                        'flat round dense').classes('text-violet-500')


def _render_course_item(
    c,
    is_reviewed: bool,
    source_type: str,
    task,
    progress_state: dict,
    refresh_progress,
) -> None:
    bg = ('bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
          if is_reviewed else
          'bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700')

    with ui.row().classes(
            f'w-full items-center justify-between p-2.5 rounded-xl {bg} '
            f'transition-all duration-300'):
        with ui.column().classes('gap-0.5 flex-1 min-w-0'):
            title_cls = ('text-sm font-medium text-slate-400 line-through'
                         if is_reviewed else
                         'text-sm font-medium text-slate-700 dark:text-slate-200 truncate')
            ui.label(c.title).classes(title_cls)
            badge_color = 'text-blue-400' if source_type == 'gcal' else 'text-violet-400'
            badge_text  = 'GCal' if source_type == 'gcal' else 'Manuel'
            ui.label(badge_text).classes(f'text-xs {badge_color}')

        if is_reviewed:
            ui.icon('check_circle', color='green', size='sm')
        else:
            async def _validate(course=c, s=source_type):
                ui.notify(f'Validation de {course.title}…', type='ongoing')
                await notion_service.increment_lecture_college(course.id, course.nb_lectures)
                if task:
                    if s == 'notion_manual':
                        await notion_service.mark_manual_revision_done(task.id, course.title)
                    else:
                        await notion_service.add_course_to_daily_reviewed(task.id, course.title)
                course.nb_lectures += 1
                progress_state['ajout'][1] += 1
                refresh_progress()
                ui.notify('Validé !', type='positive')

            ui.button(icon='check', on_click=_validate).props('flat round dense').classes(
                'text-green-500').tooltip('Marquer comme révisé')


def _open_add_course_dialog(date_obj: datetime.date, task) -> None:
    college_courses = sorted(
        [c for c in data_store.cours if c.college],
        key=lambda c: (float(c.item_number.replace(',', '.'))
                       if c.item_number else 999999),
    )
    options = {
        c.id: (f"ITEM {c.item_number} — " if c.item_number else '') + c.title
        for c in college_courses
    }
    sel = {'id': None}

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-4 gap-3'):
        ui.label('Programmer une révision').classes(
            'text-base font-bold text-slate-700 dark:text-slate-200')
        ui.label(f"Date : {date_obj.strftime('%d/%m/%Y')}").classes('text-sm text-slate-400')
        ui.select(options=options, label='Cours (ITEM XXX)',
                  with_input=True).bind_value(sel, 'id').props(
            'outlined use-input clearable').classes('w-full')

        async def _confirm():
            if not sel['id']:
                ui.notify('Sélectionnez un cours', type='warning')
                return
            dlg.close()
            dlg.delete()
            c = next((x for x in college_courses if x.id == sel['id']), None)
            if not c:
                return
            target = task or await notion_service.get_daily_task_by_date(date_obj)
            if not target:
                created = await notion_service.create_daily_task(
                    date_obj, f"Suivi - {date_obj.strftime('%d/%m/%Y')}")
                if created:
                    target = await notion_service.get_daily_task_by_date(date_obj)
            if target:
                ok = await notion_service.add_course_to_daily_manual(target.id, c.title)
                ui.notify('Programmé !' if ok else 'Erreur Notion',
                          type='positive' if ok else 'negative')
            else:
                ui.notify('Impossible de créer la fiche', type='negative')

        with ui.row().classes('w-full justify-end gap-2 mt-2'):
            ui.button('Annuler', on_click=dlg.close).props('flat')
            ui.button('Programmer', on_click=_confirm).props('unelevated color=primary rounded')

    dlg.open()


def _render_note_block(
    container: ui.column,
    task,
    is_past: bool,
) -> None:
    container.clear()
    with container:
        with ui.row().classes('w-full gap-4 items-start'):
            ui.element('div').classes('w-1 rounded-full bg-amber-500 self-stretch min-h-[2rem]')
            with ui.column().classes('flex-1 gap-2'):
                ui.label('NOTE DU JOUR').classes(
                    'text-xs font-bold uppercase tracking-widest text-slate-400 mb-1')

                if is_past:
                    ui.label('Journée passée — notes visibles dans Notion.').classes(
                        'text-sm italic text-slate-400')
                    return

                note_ta = ui.textarea(
                    placeholder='Comment s\'est passée la journée ?'
                ).props('outlined rows=2 autogrow').classes('w-full text-sm')

                save_row = ui.row().classes('w-full justify-end hidden')
                with save_row:
                    save_btn = ui.button('Enregistrer').props(
                        'unelevated dense rounded').classes(
                        'bg-amber-500 text-white text-sm')

                def _on_input(e):
                    if e.value.strip():
                        save_row.classes(remove='hidden')
                    else:
                        save_row.classes(add='hidden')

                note_ta.on('update:model-value', _on_input)

                async def _save():
                    val = note_ta.value.strip()
                    if not val:
                        return
                    if not task:
                        ui.notify('Pas de fiche pour ce jour', type='warning')
                        return
                    note_ta.value = ''
                    save_row.classes(add='hidden')
                    if await notion_service.add_daily_comment(task.id, val):
                        ui.notify('Note enregistrée', type='positive')
                    else:
                        ui.notify('Erreur Notion', type='negative')

                save_btn.on('click', lambda: asyncio.create_task(_save()))


async def todo_page():
    with frame("Suivi Quotidien"):
        state          = {'date': datetime.date.today()}
        # Chaque entrée = [total, done] — isolé par bloc pour éviter le double-comptage
        # lors des re-renders partiels (ex: ajout d'une tâche libre)
        progress_state = {'routine': [0, 0], 'ajout': [0, 0]}

        # ── Header sticky ──────────────────────────────────────────────────────
        with ui.element('div').style(
            'position: sticky; top: 0; z-index: 10;'
        ).classes(
            'bg-white/90 dark:bg-slate-900/90 backdrop-blur-md '
            'border-b border-slate-200 dark:border-slate-700 '
            'px-4 pt-3 pb-2 w-full'
        ):
            with ui.row().classes('w-full items-center gap-1'):
                btn_prev = ui.button(icon='chevron_left').props('flat round dense')

                with ui.row().classes('items-center gap-1 flex-1 justify-center'):
                    btn_hier = ui.button('Hier').props('flat dense size=sm rounded')
                    btn_auj  = ui.button("Auj.").props('flat dense size=sm rounded')
                    btn_dem  = ui.button('Demain').props('flat dense size=sm rounded')

                date_btn = ui.button('').props('flat dense').classes(
                    'font-semibold text-slate-700 dark:text-slate-100 min-w-[190px] text-sm')

                btn_next = ui.button(icon='chevron_right').props('flat round dense')

            progress_bar   = ui.linear_progress(value=0, show_value=False).classes(
                'h-1.5 rounded-full mt-2 mb-0')
            progress_label = ui.label('0 / 0 · 0%').classes(
                'text-xs text-slate-400 text-right mt-0.5')

        # ── Zone de contenu ────────────────────────────────────────────────────
        content = ui.column().classes('w-full px-4 py-5 gap-6')

        # ── Helpers ────────────────────────────────────────────────────────────
        def _refresh_progress():
            t = sum(b[0] for b in progress_state.values())
            d = sum(b[1] for b in progress_state.values())
            p = d / t if t > 0 else 0
            progress_bar.set_value(p)
            progress_label.set_text(f"{d} / {t} · {int(p * 100)}%")

        def _update_header():
            today = datetime.date.today()
            d     = state['date']
            date_btn.set_text(_fmt_date(d))
            for btn, delta in [(btn_hier, -1), (btn_auj, 0), (btn_dem, 1)]:
                if d == today + datetime.timedelta(days=delta):
                    btn.props(remove='flat').props('unelevated color=primary size=sm rounded')
                else:
                    btn.props(remove='unelevated color=primary').props('flat size=sm rounded')

        async def _render_day(date_obj: datetime.date):
            state['date'] = date_obj
            for k in progress_state:
                progress_state[k] = [0, 0]
            _update_header()
            _refresh_progress()
            await _render_content(content, date_obj, progress_state, _refresh_progress)

        # ── Bindings ───────────────────────────────────────────────────────────
        btn_prev.on('click', lambda: asyncio.create_task(
            _render_day(state['date'] - datetime.timedelta(days=1))))
        btn_next.on('click', lambda: asyncio.create_task(
            _render_day(state['date'] + datetime.timedelta(days=1))))
        btn_hier.on('click', lambda: asyncio.create_task(
            _render_day(datetime.date.today() - datetime.timedelta(days=1))))
        btn_auj.on('click',  lambda: asyncio.create_task(
            _render_day(datetime.date.today())))
        btn_dem.on('click',  lambda: asyncio.create_task(
            _render_day(datetime.date.today() + datetime.timedelta(days=1))))

        def _open_date_picker():
            with ui.dialog() as dlg, ui.card().classes('items-center gap-3 p-4'):
                dp = ui.date(value=state['date'].isoformat()).props('no-unset')
                async def _confirm():
                    if dp.value:
                        dlg.close()
                        await _render_day(datetime.date.fromisoformat(dp.value))
                ui.button('OK', on_click=_confirm).props('unelevated color=primary rounded')
            dlg.open()

        date_btn.on('click', _open_date_picker)

        _update_header()
        ui.timer(0.1, lambda: asyncio.create_task(
            _render_day(datetime.date.today())), once=True)
