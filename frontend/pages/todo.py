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


async def _load_and_render_network_blocs(
    ajout_col, note_col, date_obj, is_past, progress_state, refresh_progress
) -> None:
    # Stub — implémenté en Task 4
    with ajout_col:
        ui.label('Chargement…').classes('text-sm text-slate-400 italic')
    with note_col:
        ui.label('').classes('')


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
