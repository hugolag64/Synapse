"""
ui_kit.py — Synapse Design System v2
--------------------------------------
Composants réutilisables : stat_card, badge, chip, empty_state, section_header.
Palette : Indigo primary · Slate neutrals · Inter/Plus Jakarta Sans typography.
"""
from __future__ import annotations
from nicegui import ui


def stat_card(
    icon: str,
    label: str,
    value: str,
    trend: str | None = None,
    color: str = 'violet',
    on_click=None,
) -> None:
    """Carte KPI — icône + label + valeur + tendance optionnelle."""
    _base = (
        'p-5 rounded-2xl border border-slate-200 dark:border-slate-800 '
        'bg-white dark:bg-slate-900 flex flex-col gap-2 '
        'transition-all duration-150'
    )
    _cls = _base + (' cursor-pointer hover:shadow-md hover:-translate-y-px' if on_click else '')

    _color_map = {
        'violet': ('text-violet-600 dark:text-violet-400', 'bg-violet-50 dark:bg-violet-900/20'),
        'indigo': ('text-violet-600 dark:text-violet-400', 'bg-violet-50 dark:bg-violet-900/20'),
        'green':  ('text-emerald-600 dark:text-emerald-400', 'bg-emerald-50 dark:bg-emerald-900/20'),
        'red':    ('text-red-500 dark:text-red-400', 'bg-red-50 dark:bg-red-900/20'),
        'amber':  ('text-amber-600 dark:text-amber-400', 'bg-amber-50 dark:bg-amber-900/20'),
        'blue':   ('text-blue-600 dark:text-blue-400', 'bg-blue-50 dark:bg-blue-900/20'),
        'slate':  ('text-slate-500 dark:text-slate-400', 'bg-slate-50 dark:bg-slate-800'),
    }
    icon_cls, icon_bg = _color_map.get(color, _color_map['violet'])

    with ui.card().classes(_cls).on('click', on_click) if on_click else ui.card().classes(_cls):
        with ui.row().classes('items-center justify-between mb-1'):
            with ui.element('div').classes(
                f'w-10 h-10 rounded-xl {icon_bg} flex items-center justify-center'
            ):
                ui.icon(icon, size='sm').classes(icon_cls)
        ui.label(value).classes(
            'text-[30px] font-extrabold tabular-nums text-slate-900 dark:text-slate-100 '
            'leading-none tracking-tight'
        )
        ui.label(label).classes(
            'text-[13px] font-medium text-slate-500 dark:text-slate-400 leading-none'
        )
        if trend:
            _t_cls = (
                'text-emerald-600 dark:text-emerald-400' if trend.startswith('+')
                else 'text-red-500 dark:text-red-400' if trend.startswith('-')
                else 'text-slate-400 dark:text-slate-500'
            )
            ui.label(trend).classes(f'text-[12px] font-semibold {_t_cls} mt-0.5')


def status_badge(level: str, text: str | None = None) -> None:
    """Badge statut standardisé : success / warning / danger / info / muted."""
    _cfg: dict[str, tuple[str, str, str]] = {
        'success': ('check_circle', 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300', 'Maîtrisé'),
        'warning': ('warning',      'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300',         'Fragile'),
        'danger':  ('error',        'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400',                 'Critique'),
        'info':    ('info',         'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300',             'Info'),
        'muted':   ('circle',       'bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400',            'Normal'),
    }
    _icon, _cls, _default = _cfg.get(level, ('circle', 'bg-slate-50 text-slate-500', level))
    _lbl = text or _default
    with ui.element('div').classes(
        f'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full {_cls}'
    ):
        ui.icon(_icon, size='xs')
        ui.label(_lbl).classes('text-[12px] font-semibold')


def mastery_chip(level: str, score: int | None = None) -> None:
    """Chip de maîtrise avec couleur sémantique adoucie."""
    _map = {
        'solide':   ('bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/60', '●'),
        'correct':  ('bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800/60', '◐'),
        'fragile':  ('bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/60', '◑'),
        'critique': ('bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800/60', '○'),
    }
    _cls, _dot = _map.get(level, (_map['correct'][0], '◐'))
    _score_txt = f' {score}%' if score is not None else ''
    with ui.element('div').classes(
        f'inline-flex items-center gap-1.5 px-3 py-1 rounded-full border {_cls}'
    ):
        ui.label(_dot).classes('text-[12px] leading-none')
        ui.label(f'{level.capitalize()}{_score_txt}').classes('text-[13px] font-semibold')


def badge_chip(
    text: str,
    color: str = 'slate',
    icon: str | None = None,
    dot: bool = False,
) -> None:
    """Chip minimaliste pour activités (ANKI, RÉSUMÉ, QCM)."""
    _map = {
        'violet': 'bg-violet-50 dark:bg-violet-900/20 text-violet-700 dark:text-violet-300',
        'green':  'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300',
        'amber':  'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300',
        'red':    'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400',
        'blue':   'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300',
        'slate':  'bg-slate-100 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300',
    }
    _cls = _map.get(color, _map['slate'])
    with ui.element('div').classes(
        f'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[12px] font-semibold {_cls}'
    ):
        if dot:
            ui.label('●').classes('text-[8px] opacity-60 leading-none')
        elif icon:
            ui.icon(icon, size='xs')
        ui.label(text)


def empty_state(
    message: str,
    icon: str = 'inbox',
    action_label: str | None = None,
    action_fn=None,
    detail: str | None = None,
) -> None:
    """État vide élégant avec icône, message, et action optionnelle."""
    with ui.column().classes('w-full items-center py-12 gap-3'):
        with ui.element('div').classes(
            'w-14 h-14 rounded-2xl bg-slate-50 dark:bg-slate-800/60 '
            'flex items-center justify-center'
        ):
            ui.icon(icon, size='md').classes('text-slate-300 dark:text-slate-600')
        ui.label(message).classes(
            'text-sm font-medium text-slate-500 dark:text-slate-400 text-center'
        )
        if detail:
            ui.label(detail).classes(
                'text-[12px] text-slate-400 dark:text-slate-500 text-center max-w-xs'
            )
        if action_label and action_fn:
            ui.button(action_label, on_click=action_fn).props(
                'unelevated rounded-lg size=sm color=violet'
            ).classes('text-[12px] font-semibold mt-1')


def section_header(
    title: str,
    subtitle: str | None = None,
    action_label: str | None = None,
    action_fn=None,
    icon: str | None = None,
) -> None:
    """En-tête de section standardisé avec typographie hiérarchique."""
    with ui.row().classes('w-full items-center justify-between mb-3 gap-2'):
        with ui.row().classes('items-center gap-2'):
            if icon:
                ui.icon(icon, size='sm').classes('text-slate-400 dark:text-slate-500')
            with ui.column().classes('gap-0'):
                ui.label(title).classes(
                    'text-[15px] font-semibold text-slate-900 dark:text-slate-100 leading-snug'
                )
                if subtitle:
                    ui.label(subtitle).classes(
                        'text-[11px] text-slate-400 dark:text-slate-500 leading-none mt-0.5'
                    )
        if action_label and action_fn:
            ui.button(action_label, on_click=action_fn).props(
                'flat rounded size=sm color=violet'
            ).classes('text-[12px] font-semibold')


def page_header(
    title: str,
    subtitle: str | None = None,
) -> None:
    """Grand titre de page — utilise la font display."""
    ui.label(title).classes(
        'synapse-display text-2xl font-bold text-slate-900 dark:text-slate-50 '
        'tracking-tight leading-none'
    )
    if subtitle:
        ui.label(subtitle).classes(
            'text-sm text-slate-500 dark:text-slate-400 mt-1'
        )


def info_banner(
    text: str,
    icon: str = 'info',
    color: str = 'violet',
    dismissible: bool = False,
) -> None:
    """Bannière d'information contextuelle."""
    _map = {
        'violet': 'bg-violet-50 dark:bg-violet-900/20 border-violet-200 dark:border-violet-800/50 text-violet-800 dark:text-violet-200',
        'amber':  'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/50 text-amber-800 dark:text-amber-200',
        'green':  'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800/50 text-emerald-800 dark:text-emerald-200',
        'red':    'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800/50 text-red-800 dark:text-red-200',
    }
    _cls = _map.get(color, _map['violet'])
    with ui.element('div').classes(
        f'w-full flex items-start gap-2.5 px-4 py-3 rounded-lg border {_cls}'
    ) as _banner:
        ui.icon(icon, size='xs').classes('mt-0.5 shrink-0')
        ui.label(text).classes('text-[12px] font-medium flex-1 leading-snug')
        if dismissible:
            def _hide(): _banner.set_visibility(False)
            ui.button(icon='close', on_click=_hide).props(
                'flat round dense size=xs'
            ).classes('shrink-0 -mr-1 -mt-0.5 opacity-60 hover:opacity-100')
