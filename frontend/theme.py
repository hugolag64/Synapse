from nicegui import ui
from contextlib import contextmanager

# ── Google Fonts — loaded once globally ───────────────────────────────────────
ui.add_head_html(
    '<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Plus+Jakarta+Sans:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">',
    shared=True,
)
ui.add_head_html(
    '<link rel="stylesheet" href="/static/clinical-black.css">',
    shared=True,
)

# ── Navigation items ───────────────────────────────────────────────────────────
_NAV_ITEMS = [
    ('Dashboard',   '/'),
    ('Collèges',    '/colleges'),
    ('QCM',         '/qcm'),
    ('Lacunes',     '/lacunes'),
    ('Progression', '/stats'),
    ('Planning',    '/planning'),
    ('To Do',       '/todo'),
    ('Externat',    '/externat'),
]

# Map frame page_title → active nav label
_TITLE_TO_NAV = {
    'Dashboard':        'Dashboard',
    'Tableau de Bord':  'Dashboard',
    'Collèges':         'Collèges',
    'QCM':              'QCM',
    'Lacunes':          'Lacunes',
    'Ma Progression':   'Progression',
    'Stats':            'Progression',
    'Statistiques':     'Progression',
    'Planning':         'Planning',
    'Suivi Quotidien':  'To Do',
    'Externat':         'Externat',
    'Paramètres':       '',
    'Santé':            '',
}


def _nav_link(label: str, route: str, is_active: bool = False) -> None:
    """Single nav link in the top bar."""
    cls = 'synapse-nav-link active' if is_active else 'synapse-nav-link'
    with ui.link(target=route).style('text-decoration: none;'):
        ui.label(label).classes(cls)


# Keep for any external code that still imports menu_link
def menu_link(text: str, target: str, icon: str):
    with ui.link(target=target).classes(
        'w-full flex items-center gap-3 py-2 px-4 text-slate-700 dark:text-slate-300 '
        'hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md transition-colors'
    ).style('text-decoration: none;'):
        ui.icon(icon).classes('text-lg')
        ui.label(text).classes('font-medium text-sm')


@contextmanager
def frame(page_title: str):
    """Top navigation frame — 60px bar, full-width content."""
    from backend.state.store import data_store

    dark = ui.dark_mode()
    is_dark = data_store.preferences.get('dark_mode', False)
    dark.value = is_dark

    ui.colors(
        primary='#7C3AED',
        accent='#1E293B',
        dark='#080E1A',
        positive='#059669',
        negative='#DC2626',
    )

    ui.add_head_html('<link rel="stylesheet" href="/static/synapse.css">', shared=True)
    ui.add_head_html('<script src="/static/synapse.js"></script>', shared=True)

    active_nav = _TITLE_TO_NAV.get(page_title, page_title)

    # ── TOP NAVIGATION BAR ─────────────────────────────────────────────────────
    with ui.header().classes(
        'synapse-topnav bg-white dark:bg-slate-950 '
        'border-b border-slate-200 dark:border-slate-800 '
        'items-center px-5 gap-0'
    ):
        # Zone 1 — Logo
        ui.html(
            '<a href="/" style="text-decoration:none;display:flex;align-items:center;">'
            '<img src="/static/LogoSynapseTransparent.png" '
            'style="height:32px;width:auto;object-fit:contain;display:block;">'
            '</a>',
            sanitize=False,
        ).classes('shrink-0')

        # Séparateur zone logo / nav
        ui.element('div').classes('synapse-nav-sep')

        # Zone 2 — Nav links
        with ui.row().classes('items-center gap-0.5 flex-1'):
            for lbl, route in _NAV_ITEMS:
                _nav_link(lbl, route, is_active=(lbl == active_nav))

        # Séparateur nav / utility
        ui.element('div').classes('synapse-nav-sep')

        # ── Zone 3 — Utility (droite) ─────────────────────────────────────────

        # 🔥 Streak
        try:
            from backend.core.reviews import local_store as _ls
            _streak = _ls.get_streak_days()
        except Exception:
            _streak = 0
        if _streak > 0:
            _streak_cls = (
                'text-orange-600 dark:text-orange-400' if _streak >= 7
                else 'text-amber-600 dark:text-amber-400'
            )
            with ui.element('div').classes(
                'flex items-center gap-1 px-2 py-1 rounded-full '
                'bg-orange-50 dark:bg-orange-900/20 cursor-default mr-1'
            ).tooltip(
                f"{'🔥 ' if _streak >= 3 else ''}{_streak} jour{'s' if _streak > 1 else ''} "
                f"consécutif{'s' if _streak > 1 else ''} de révision"
            ):
                ui.label('🔥').classes('text-sm leading-none')
                ui.label(f'{_streak}j').classes(f'text-[11px] font-extrabold {_streak_cls}')

        # Exam countdown
        try:
            _exam_date_str = data_store.preferences.get('exam_date', '')
            _exam_lbl_str = data_store.preferences.get('exam_label', 'EDN')
            if _exam_date_str:
                import datetime as _dt2
                _exam_dt = _dt2.date.fromisoformat(_exam_date_str)
                _days_left = (_exam_dt - _dt2.date.today()).days
                if _days_left >= 0:
                    _urg = (
                        'bg-red-500 text-white' if _days_left <= 7
                        else 'bg-orange-500 text-white' if _days_left <= 30
                        else 'bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300'
                    )
                    with ui.element('div').classes(
                        f'flex items-center gap-1 px-2.5 py-1 rounded-full '
                        f'mr-1 cursor-pointer {_urg}'
                    ).tooltip(
                        f"{_exam_lbl_str} : {_exam_dt.strftime('%d/%m/%Y')} — J-{_days_left} · Configurer dans Paramètres"
                    ).on('click', lambda: ui.navigate.to('/settings')):
                        ui.icon('event', size='xs')
                        ui.label(f'J-{_days_left}').classes('text-[11px] font-extrabold')
        except Exception:
            pass

        # Sync badge
        _offline = data_store.preferences.get('_offline_mode', False)
        _synced = data_store.items_last_synced
        _sync_icon = 'cloud_done' if (_synced and not _offline) else 'cloud_off'
        _sync_cls = 'text-emerald-500' if (_synced and not _offline) else 'text-amber-500'
        _sync_tip = (
            f"Sync Notion : {_synced.strftime('%H:%M')}" if (_synced and not _offline)
            else ('Hors-ligne — cache expiré' if _offline else 'Non synchronisé')
        )
        with ui.element('div').classes(
            'flex items-center gap-1 px-2 py-1 rounded-full '
            'hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer mr-1 transition-colors'
        ).tooltip(_sync_tip).on('click', lambda: ui.navigate.to('/colleges')):
            ui.icon(_sync_icon, size='xs').classes(_sync_cls)
            if _synced and not _offline:
                ui.label(_synced.strftime('%H:%M')).classes(
                    f'text-[11px] font-medium {_sync_cls}'
                )

        # Search bar (desktop)
        from frontend.components.command_palette import open_command_palette

        with ui.element('div').classes(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg mr-1 '
            'bg-slate-50 dark:bg-slate-800/70 '
            'border border-slate-200 dark:border-slate-700 '
            'cursor-pointer hover:border-slate-300 dark:hover:border-slate-600 '
            'transition-colors min-w-[148px]'
        ).on('click', open_command_palette):
            ui.icon('search', size='xs').classes('text-slate-400')
            ui.label('Rechercher…').classes(
                'text-[12px] text-slate-400 font-medium select-none flex-1'
            )
            ui.label('⌘K').classes(
                'text-[11px] text-slate-300 dark:text-slate-600 font-mono select-none'
            )


        # Dark minimal mode
        ui.button(
            icon='nights_stay',
            on_click=lambda: ui.run_javascript('toggleMinimalMode()'),
        ).props('flat round dense size=sm').classes(
            'text-slate-400 dark:text-slate-500 ml-0.5'
        ).tooltip('Mode Minimal Sombre (révision de nuit)')

        # Keyboard shortcuts
        def _open_shortcuts():
            with ui.dialog() as _dlg, ui.card().classes(
                'w-[400px] max-w-[92vw] rounded-2xl p-0 overflow-hidden '
                'bg-white dark:bg-slate-900'
            ):
                with ui.element('div').classes(
                    'px-5 pt-4 pb-3 border-b border-slate-100 dark:border-slate-800'
                ):
                    with ui.row().classes('items-center justify-between'):
                        ui.label('Raccourcis clavier').classes(
                            'text-[15px] font-semibold text-slate-900 dark:text-slate-50'
                        )
                        ui.button(icon='close', on_click=_dlg.close).props(
                            'flat round dense size=sm color=grey-7'
                        )
                with ui.element('div').classes('px-5 py-4 flex flex-col gap-2.5'):
                    _SHORTCUTS = [
                        ('Ctrl + K', 'Ouvrir la recherche globale'),
                        ('Espace',   'Démarrer / Pauser le Pomodoro (Dashboard)'),
                        ('1 – 6',    'Naviguer entre les pages principales'),
                    ]
                    for key, desc in _SHORTCUTS:
                        with ui.row().classes('items-center gap-3'):
                            ui.label(key).classes(
                                'font-mono text-[11px] font-bold px-2 py-1 rounded shrink-0 '
                                'bg-slate-100 dark:bg-slate-700 '
                                'text-slate-700 dark:text-slate-200'
                            )
                            ui.label(desc).classes(
                                'text-[13px] text-slate-600 dark:text-slate-300'
                            )
                with ui.element('div').classes(
                    'px-5 pb-4 flex justify-end border-t border-slate-100 dark:border-slate-800 pt-3'
                ):
                    ui.button('Fermer', on_click=_dlg.close).props('flat color=grey-8 rounded')
            _dlg.open()

        ui.button(icon='help_outline', on_click=_open_shortcuts).props(
            'flat round dense size=sm'
        ).classes('text-slate-400 dark:text-slate-500 ml-0.5').tooltip('Raccourcis clavier')

        # Settings
        _settings_active = (page_title in ('Paramètres', 'Settings'))
        ui.button(
            icon='settings',
            on_click=lambda: ui.navigate.to('/settings'),
        ).props('flat round dense size=sm').classes(
            ('text-violet-600 dark:text-violet-400' if _settings_active
             else 'text-slate-400 dark:text-slate-500') + ' ml-0.5'
        ).tooltip('Paramètres')

    # ── Keyboard shortcuts ─────────────────────────────────────────────────────
    try:
        from frontend.keybindings import register_keybindings
        register_keybindings()
    except Exception as _kb_err:
        from loguru import logger as _log
        _log.warning(f'keybindings non chargés: {_kb_err}')

    # ── Main content — full width, centered, breathing room ───────────────────
    with ui.column().classes(
        'w-full max-w-7xl mx-auto px-5 pt-5 pb-10 synapse-content '
        'text-slate-900 dark:text-slate-100'
    ):
        yield
