from nicegui import ui
from backend.core.notion.service import notion_service
from backend.core.google.calendar_service import calendar_service
from backend.core.reviews import local_store
from backend.state.store import data_store
from frontend.theme import frame
from dataclasses import dataclass
import asyncio
import datetime

_MONTHS = ['jan.','fév.','mars','avr.','mai','juin','juil.','août','sep.','oct.','nov.','déc.']
_DAYS   = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']


@dataclass
class _DaySummary:
    routine_total: int = 0
    routine_done: int = 0
    ajoute_total: int = 0
    ajoute_done: int = 0
    ajoute_loaded: bool = False

    @property
    def total(self) -> int:
        return self.routine_total + self.ajoute_total

    @property
    def done(self) -> int:
        return self.routine_done + self.ajoute_done

    @property
    def pct(self) -> float:
        return (self.done / self.total) if self.total > 0 else 0.0


def _pill_color(summary: "_DaySummary") -> str:
    if summary.total == 0:
        return '#CBD5E1'
    if summary.pct >= 1.0:
        return '#059669'
    return '#2563EB'


def _fmt_date(d: datetime.date) -> str:
    return f"{_DAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]} {d.year}"


def _safe_item_number(n: str | None) -> float:
    if not n:
        return 999999.0
    try:
        return float(n.replace(',', '.'))
    except ValueError:
        return 999999.0


def _compute_ajoute_progress(
    course_items: list[dict],
    reviewed_titles: list[str],
    dynamic_tasks: dict,
) -> tuple[int, int]:
    """Retourne (total, done) pour le bloc Ajouté : cours + tâches libres."""
    total = len(course_items) + len(dynamic_tasks)
    done = (
        sum(1 for r in course_items if r['course'].title in reviewed_titles)
        + sum(1 for d in dynamic_tasks.values() if d['checked'])
    )
    return total, done


def _compute_carryover(manual_titles: list[str], reviewed_titles: list[str]) -> list[str]:
    """Titres de cours manuels programmés qui ne sont pas (encore) marqués révisés."""
    return [t for t in manual_titles if t not in reviewed_titles]


def _week_dates(center: datetime.date) -> list[datetime.date]:
    """Fenêtre de 7 jours centrée sur `center` (J-3 à J+3)."""
    return [center + datetime.timedelta(days=offset) for offset in range(-3, 4)]


def _get_routine_summary(date_obj: datetime.date) -> _DaySummary:
    date_str = date_obj.isoformat()
    items = local_store.get_routine_items()
    checks = local_store.get_routine_checks(date_str)
    return _DaySummary(
        routine_total=len(items),
        routine_done=sum(1 for name in items if checks.get(name, False)),
    )


def _refresh_routine_in_cache(date_obj: datetime.date, cache: dict) -> "_DaySummary":
    """(Re)calcule la partie routine et la fusionne dans le cache, en conservant
    Ajouté si déjà chargé (évite d'écraser un résumé déjà enrichi par la strip)."""
    date_str = date_obj.isoformat()
    routine = _get_routine_summary(date_obj)
    existing = cache.get(date_str)
    if existing and existing.ajoute_loaded:
        existing.routine_total = routine.routine_total
        existing.routine_done = routine.routine_done
        cache[date_str] = existing
        return existing
    cache[date_str] = routine
    return routine


async def _render_content(
    container: ui.column,
    date_obj: datetime.date,
    cache: dict,
    on_update,
) -> None:
    container.clear()
    if container.is_deleted:
        return
    date_str = date_obj.isoformat()
    is_past  = date_obj < datetime.date.today()

    _refresh_routine_in_cache(date_obj, cache)

    with container:
        # Routine : SQLite, instantané
        routine_col = ui.column().classes('w-full')
        _render_routine_block(routine_col, date_str, cache, on_update)

        # Ajouté + Note : chargés en réseau (tâches 4 et 5)
        ajout_col = ui.column().classes('w-full')
        note_col  = ui.column().classes('w-full')

        asyncio.create_task(
            _load_and_render_network_blocs(
                ajout_col, note_col, date_obj, is_past, cache, on_update,
            )
        )


def _render_routine_block(
    container: ui.column,
    date_str: str,
    cache: dict,
    on_update,
) -> None:
    items  = local_store.get_routine_items()
    checks = local_store.get_routine_checks(date_str)
    summary = cache[date_str]

    with container:
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label('ROUTINE').classes('synapse-section-label mb-2')
            with ui.element('div').classes(
                    'grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2'):
                for name in items:
                    checked = checks.get(name, False)

                    def _on_toggle(e, item_name=name):
                        delta = 1 if e.value else -1
                        summary.routine_done = max(
                            0, min(summary.routine_total, summary.routine_done + delta))
                        on_update()
                        local_store.set_routine_check(date_str, item_name, e.value)

                    ui.checkbox(name, value=checked, on_change=_on_toggle).props('dense').classes(
                        'text-slate-700 dark:text-slate-200 transition-opacity duration-200')

    on_update()


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
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label(title).classes('synapse-section-label mb-2')
            for w in ['w-3/4', 'w-1/2', 'w-2/3']:
                ui.element('div').classes(
                    f'h-5 rounded-md animate-pulse bg-slate-200 dark:bg-slate-700 {w}')


async def _get_day_summary(date_obj: datetime.date, cache: dict) -> "_DaySummary":
    """Résout (et met en cache) le résumé complet (routine + ajouté) d'une date.
    Ne refait jamais l'appel Notion si ajoute_loaded est déjà True pour cette date."""
    date_str = date_obj.isoformat()
    summary = cache.get(date_str)
    if summary is None:
        summary = _get_routine_summary(date_obj)
        cache[date_str] = summary
    if summary.ajoute_loaded:
        return summary

    task = await notion_service.get_daily_task_by_date(date_obj)
    reviewed_titles: list[str] = []
    manual_titles: list[str] = []
    if task:
        reviewed_titles, manual_titles = await asyncio.gather(
            notion_service.get_daily_reviewed_courses(task.id),
            notion_service.get_daily_manual_revision_courses(task.id),
        )
    events = await calendar_service.get_events_for_day(date_obj)
    course_items = _build_course_list(events, manual_titles, data_store.cours)
    dynamic_tasks = task.dynamic_checkboxes if task else {}

    summary.ajoute_total, summary.ajoute_done = _compute_ajoute_progress(
        course_items, reviewed_titles, dynamic_tasks)
    summary.ajoute_loaded = True
    return summary


async def _get_yesterday_carryover(date_obj: datetime.date) -> list[str]:
    """Cours manuels programmés hier et non marqués révisés (lecture seule, pas de déplacement)."""
    if date_obj != datetime.date.today():
        return []
    yesterday = date_obj - datetime.timedelta(days=1)
    task = await notion_service.get_daily_task_by_date(yesterday)
    if not task:
        return []
    reviewed_titles, manual_titles = await asyncio.gather(
        notion_service.get_daily_reviewed_courses(task.id),
        notion_service.get_daily_manual_revision_courses(task.id),
    )
    return _compute_carryover(manual_titles, reviewed_titles)


async def _load_and_render_network_blocs(
    ajout_col: ui.column,
    note_col: ui.column,
    date_obj: datetime.date,
    is_past: bool,
    cache: dict,
    on_update,
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
        reviewed_titles, cache, on_update,
    )
    _render_note_block(note_col, task, is_past)
    on_update()


async def _render_ajout_block(
    container: ui.column,
    date_obj: datetime.date,
    task,
    course_items: list[dict],
    reviewed_titles: list[str],
    cache: dict,
    on_update,
) -> None:
    date_str = date_obj.isoformat()
    dynamic_tasks = task.dynamic_checkboxes if task else {}
    ajoute_total, ajoute_done = _compute_ajoute_progress(course_items, reviewed_titles, dynamic_tasks)

    summary = cache[date_str]
    summary.ajoute_total = ajoute_total
    summary.ajoute_done = ajoute_done
    summary.ajoute_loaded = True

    container.clear()
    with container:
        with ui.element('div').classes('synapse-panel w-full p-4').props('id=todo-ajoute-panel'):
            ui.label('AJOUTÉ').classes('synapse-section-label mb-2')

            # ── Contrôles d'ajout — en haut, avant la liste ────────────────
            with ui.row().classes('items-center gap-2 pb-2'):
                ui.button('+ Cours', icon='add',
                          on_click=lambda: _open_add_course_dialog(date_obj, task)).props(
                    'unelevated dense rounded').classes(
                    'bg-violet-600 text-white text-sm font-medium')

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
                                reviewed_titles, cache, on_update,
                            )

                new_task_input.on('keydown.enter',
                                  lambda: asyncio.create_task(_add_task_free()))
                ui.button(icon='send',
                          on_click=lambda: asyncio.create_task(_add_task_free())).props(
                    'flat round dense').classes('text-violet-500')

            # ── Cours ─────────────────────────────────────────────────────
            for item in course_items:
                _render_course_item(
                    item['course'], item['course'].title in reviewed_titles,
                    item['type'], task, cache, date_str, on_update,
                )

            # ── Tâches dynamiques ─────────────────────────────────────────
            for b_id, data in dynamic_tasks.items():
                async def _toggle_dyn(e, bid=b_id):
                    delta = 1 if e.value else -1
                    summary.ajoute_done = max(
                        0, min(summary.ajoute_total, summary.ajoute_done + delta))
                    on_update()
                    await notion_service.toggle_dynamic_task(bid, e.value)

                ui.checkbox(data['text'], value=data['checked'],
                            on_change=_toggle_dyn).props('dense').classes(
                    'text-slate-700 dark:text-slate-200')

            # ── État vide ─────────────────────────────────────────────────
            if not course_items and not dynamic_tasks:
                with ui.column().classes('w-full items-center gap-1 py-4'):
                    ui.icon('event_available', size='md').classes('text-slate-300 dark:text-slate-600')
                    ui.label('Rien de planifié pour ce jour').classes(
                        'text-sm text-slate-400 italic')
                    ui.button('+ Ajouter un cours',
                              on_click=lambda: _open_add_course_dialog(date_obj, task)).props(
                        'flat dense').classes(
                        'text-violet-600 dark:text-violet-400 text-sm font-medium mt-1')


def _render_course_item(
    c,
    is_reviewed: bool,
    source_type: str,
    task,
    cache: dict,
    date_str: str,
    on_update,
) -> None:
    bg = ('bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
          if is_reviewed else
          'bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700')

    with ui.row().classes(
            f'w-full items-center justify-between p-3 rounded-xl {bg} '
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
                summary = cache[date_str]
                summary.ajoute_done = min(summary.ajoute_total, summary.ajoute_done + 1)
                on_update()

                async def _undo():
                    course.nb_lectures = max(0, course.nb_lectures - 1)
                    if task:
                        if s == 'notion_manual':
                            await notion_service.unmark_manual_revision_done(task.id, course.title)
                        else:
                            await notion_service.remove_course_from_daily_reviewed(task.id, course.title)
                    summary.ajoute_done = max(0, summary.ajoute_done - 1)
                    on_update()
                    ui.notify('Validation annulée', type='info')

                ui.notify(
                    'Validé !', type='positive', timeout=5000,
                    actions=[{'label': 'ANNULER', 'color': 'white',
                              'handler': lambda: asyncio.create_task(_undo())}],
                )

            ui.button(icon='check', on_click=_validate).props('flat round dense').classes(
                'text-green-500').tooltip('Marquer comme révisé')


def _open_add_course_dialog(date_obj: datetime.date, task) -> None:
    college_courses = sorted(
        [c for c in data_store.cours if c.college],
        key=lambda c: _safe_item_number(c.item_number),
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
        with ui.element('div').classes('synapse-panel w-full p-4'):
            ui.label('NOTE DU JOUR').classes('synapse-section-label mb-2')

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


def _render_week_strip(
    container: ui.row,
    week: list[datetime.date],
    active_date: datetime.date,
    cache: dict,
    on_pick_day,
) -> None:
    container.clear()
    with container:
        with ui.element('div').classes('todo-week-strip'):
            for d in week:
                summary = cache.get(d.isoformat(), _DaySummary())
                pct = summary.pct
                color = _pill_color(summary)
                is_active = d == active_date

                cls = 'todo-day-pill active' if is_active else 'todo-day-pill'
                with ui.element('div').classes(cls).on(
                        'click', lambda _e, dd=d: asyncio.create_task(on_pick_day(dd))):
                    ui.label(_DAYS[d.weekday()]).classes('todo-day-pill-name')
                    ui.label(str(d.day)).classes('todo-day-pill-num')
                    with ui.element('div').classes('todo-day-pill-bar'):
                        ui.element('div').classes('todo-day-pill-bar-fill').style(
                            f'width:{int(pct * 100)}%;background:{color}')


async def _load_week_ajoute(container: ui.row, week: list[datetime.date], cache: dict, redraw) -> None:
    """Enrichit chaque pastille avec les données Ajouté (Notion), une par une
    (throttle volontaire : jamais en parallèle)."""
    for d in week:
        if container.is_deleted:
            return
        summary = cache.get(d.isoformat())
        if summary and summary.ajoute_loaded:
            continue
        await _get_day_summary(d, cache)
        if container.is_deleted:
            return
        redraw()


def _render_hero_nav(container: ui.column, state: dict) -> dict:
    """Ligne de navigation date du hero. Reconstruite à chaque changement de jour."""
    container.clear()
    refs = {}
    with container:
        with ui.row().classes('w-full items-center gap-1'):
            refs['prev'] = ui.button(icon='chevron_left').props('flat round dense')
            with ui.row().classes('items-center gap-1 flex-1 justify-center'):
                refs['hier'] = ui.button('Hier').props('flat dense size=sm rounded')
                refs['auj']  = ui.button("Auj.").props('flat dense size=sm rounded')
                refs['dem']  = ui.button('Demain').props('flat dense size=sm rounded')
            refs['date_btn'] = ui.button(_fmt_date(state['date'])).props('flat dense').classes(
                'font-semibold text-slate-700 dark:text-slate-100 min-w-[190px] text-sm')
            refs['next'] = ui.button(icon='chevron_right').props('flat round dense')
    return refs


def _wire_nav_handlers(refs: dict, render_day, state: dict, on_date_click) -> None:
    today = datetime.date.today()
    refs['prev'].on('click', lambda: asyncio.create_task(
        render_day(state['date'] - datetime.timedelta(days=1))))
    refs['next'].on('click', lambda: asyncio.create_task(
        render_day(state['date'] + datetime.timedelta(days=1))))
    refs['hier'].on('click', lambda: asyncio.create_task(
        render_day(today - datetime.timedelta(days=1))))
    refs['auj'].on('click', lambda: asyncio.create_task(render_day(today)))
    refs['dem'].on('click', lambda: asyncio.create_task(
        render_day(today + datetime.timedelta(days=1))))
    refs['date_btn'].on('click', on_date_click)


def _update_header(refs: dict, state: dict) -> None:
    today = datetime.date.today()
    d = state['date']
    for btn, delta in [(refs['hier'], -1), (refs['auj'], 0), (refs['dem'], 1)]:
        if d == today + datetime.timedelta(days=delta):
            btn.props(remove='flat').props('unelevated color=primary size=sm rounded')
        else:
            btn.props(remove='unelevated color=primary').props('flat size=sm rounded')


def _render_hero_stats(
    container: ui.row,
    state: dict,
    cache: dict,
    carryover_holder: dict,
) -> None:
    container.clear()
    date_str = state['date'].isoformat()
    summary = cache.get(date_str, _DaySummary())
    pct = summary.pct
    color = _pill_color(summary)
    streak = local_store.get_streak_days()
    carryover = carryover_holder.get(date_str, [])

    with container:
        with ui.element('div').classes('synapse-ring').style(
                f'--ring-pct:{pct * 100};--ring-color:{color}'):
            ui.label(f'{int(pct * 100)}%').classes('synapse-ring-label').style(f'color:{color}')

        if streak > 0:
            with ui.row().classes('items-center gap-1'):
                ui.icon('local_fire_department',
                        color='orange-6' if streak >= 3 else 'amber-6', size='sm')
                ui.label(f'{streak}j').classes(
                    'text-sm font-bold text-slate-600 dark:text-slate-300')

        if carryover:
            with ui.row().classes(
                    'items-center gap-1 px-2 py-1 rounded-full cursor-pointer '
                    'bg-amber-50 dark:bg-amber-900/20'
            ).tooltip(', '.join(carryover)).on('click', lambda: ui.run_javascript(
                "document.getElementById('todo-ajoute-panel')?.scrollIntoView({behavior: 'smooth', block: 'start'})"
            )):
                ui.icon('history', color='amber-7', size='xs')
                ui.label(f"{len(carryover)} reporté(s) d'hier").classes(
                    'text-xs font-semibold text-amber-700 dark:text-amber-400')


async def todo_page():
    with frame("Suivi Quotidien"):
        state: dict = {'date': datetime.date.today()}
        cache: dict = {}
        carryover_holder: dict = {}
        week = _week_dates(datetime.date.today())

        # Pré-remplit le cache avec la routine (instantané, local) pour les 7 jours
        # de la strip, avant le premier rendu — sans ça, les pastilles autres que
        # "aujourd'hui" resteraient vides jusqu'à ce que _load_week_ajoute les atteigne
        # séquentiellement (spec section 3 : la routine doit être immédiate pour les 7 jours).
        for _d in week:
            cache[_d.isoformat()] = _get_routine_summary(_d)

        # ── Hero (sticky) ───────────────────────────────────────────────────────
        with ui.element('div').classes(
                'synapse-hero flex-col gap-3 items-stretch w-full'
        ).style('position: sticky; top: 0; z-index: 10;'):
            nav_container   = ui.column().classes('w-full gap-0')
            stats_container = ui.row().classes('w-full items-center gap-4')

        # ── Strip 7 jours ──────────────────────────────────────────────────────
        strip_container = ui.row().classes('w-full mt-3')

        # ── Zone de contenu ────────────────────────────────────────────────────
        content = ui.column().classes('w-full px-4 py-5 gap-6')

        # ── Helpers ────────────────────────────────────────────────────────────
        def _refresh_stats():
            _render_hero_stats(stats_container, state, cache, carryover_holder)

        def _draw_strip():
            _render_week_strip(strip_container, week, state['date'], cache, _render_day)

        def _open_date_picker():
            with ui.dialog() as dlg, ui.card().classes('items-center gap-3 p-4'):
                dp = ui.date(value=state['date'].isoformat()).props('no-unset')
                async def _confirm():
                    if dp.value:
                        dlg.close()
                        await _render_day(datetime.date.fromisoformat(dp.value))
                ui.button('OK', on_click=_confirm).props('unelevated color=primary rounded')
            dlg.open()

        async def _load_carryover(date_obj: datetime.date):
            titles = await _get_yesterday_carryover(date_obj)
            carryover_holder[date_obj.isoformat()] = titles
            if date_obj == state['date']:
                _refresh_stats()

        async def _render_day(date_obj: datetime.date):
            state['date'] = date_obj

            nav_refs = _render_hero_nav(nav_container, state)
            _wire_nav_handlers(nav_refs, _render_day, state, _open_date_picker)
            _update_header(nav_refs, state)

            # Rafraîchit la routine dans le cache AVANT le premier affichage des stats/strip,
            # sinon la ligne hero et la strip liraient un _DaySummary manquant ou périmé
            # (celui d'une date jamais visitée, ou d'un ancien jour) pendant l'instant
            # qui précède la résolution de _render_content.
            _refresh_routine_in_cache(date_obj, cache)
            _refresh_stats()
            _draw_strip()

            asyncio.create_task(_load_carryover(date_obj))
            await _render_content(content, date_obj, cache, _refresh_stats)
            _refresh_stats()
            _draw_strip()

        # ── Démarrage ──────────────────────────────────────────────────────────
        ui.timer(0.1, lambda: asyncio.create_task(
            _render_day(datetime.date.today())), once=True)
        ui.timer(0.5, lambda: asyncio.create_task(
            _load_week_ajoute(strip_container, week, cache, _draw_strip)), once=True)
