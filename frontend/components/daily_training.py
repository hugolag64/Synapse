"""daily_training — bloc unique « Entraînement du jour » de la vue Aujourd'hui.

Regroupe les deux entraînements quotidiens, jusqu'ici affichés en deux cartes
sans lien visible l'une avec l'autre :

  • Pièges éliminatoires (Flash-Zéro) — banque éditoriale, priorisée par les
    erreurs récentes et répétées.
  • Tes questions en attente (« Les 5 du jour ») — QCM déjà présents en base et
    jamais joués, priorisés par fréquence EDN × déficit de rétention.

Les juxtaposer sous un même titre rend la différence lisible : même forme de
ligne, sous-titres qui disent d'où viennent les questions.
"""
from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from backend.core.qcm.items_mapping import item_title

# Au-delà, la ligne de sous-titre déborde du panneau central en 1280 px.
MAX_LISTED_ITEMS = 2

_CSS = """
.dt-block { border:1px solid var(--border); border-radius:8px; background:var(--bg);
  overflow:hidden; margin:16px 0; }
.dt-head { display:flex; align-items:center; gap:8px; padding:9px 14px 8px;
  border-bottom:1px solid var(--border); background:var(--surface); }
.dt-head-title { font-family:var(--font-mono); font-size:10px; font-weight:600;
  letter-spacing:.06em; text-transform:uppercase; color:var(--text-muted); }
.dt-row { display:flex; align-items:center; gap:12px; padding:11px 14px; min-width:0; }
.dt-row + .dt-row { border-top:1px solid var(--border); }
.dt-row:hover { background:var(--surface); }
.dt-icon { width:28px; height:28px; flex:0 0 28px; display:flex; align-items:center;
  justify-content:center; border-radius:6px; font-size:15px; }
.dt-icon.zero { background:rgba(229,162,63,.12); color:var(--warning-text); }
.dt-icon.queue { background:var(--accent-wash); color:var(--accent); }
.dt-copy { flex:1; min-width:0; }
.dt-title { font-size:13px; font-weight:600; color:var(--text); }
.dt-sub { font-size:11.5px; color:var(--text-muted); white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
.dt-meta { flex:0 0 auto; font-family:var(--font-mono); font-size:10.5px; color:var(--text-dim); }
/* Réservée même masquée : sinon le survol décale toute la ligne. */
.dt-dismiss { flex:0 0 auto; opacity:0; pointer-events:none; color:var(--text-muted);
  transition:opacity var(--duration-fast) var(--ease-standard),
             color var(--duration-fast) var(--ease-standard); }
.dt-row:hover .dt-dismiss, .dt-row:focus-within .dt-dismiss { opacity:1; pointer-events:auto; }
.dt-dismiss:hover { color:var(--danger-text); }
@media (max-width: 560px) { .dt-meta { display:none; } }
"""


def daily_queue_summary(rows: list[dict]) -> dict:
    """Résume la file du jour : volume et items distincts, désignés par leur titre.

    L'ancien libellé itérait sur les questions et affichait « ITEM 147, ITEM 147 »
    quand plusieurs questions venaient du même item — ce qui est le cas courant,
    puisque le score de priorité est calculé par item.
    """
    seen: dict[str, str] = {}
    for row in rows or []:
        number = str(row.get("item_number") or "").strip()
        if not number or number in seen:
            continue
        seen[number] = item_title(number) or f"ITEM {number}"

    names = list(seen.values())
    shown = names[:MAX_LISTED_ITEMS]
    hidden = len(names) - len(shown)
    label = ", ".join(shown)
    if hidden > 0:
        label = f"{label} +{hidden}"
    if not names:
        label = "Items non classés"
    return {
        "count": len(rows or []),
        "items": [{"number": n, "title": t} for n, t in seen.items()],
        "label": label,
        "full_label": ", ".join(names) or "Items non classés",
    }


def ensure_styles() -> None:
    ui.add_head_html(f"<style>{_CSS}</style>", shared=True)


def _row(
    *, icon: str, icon_class: str, title: str, subtitle: str, subtitle_tooltip: str,
    meta: str, action: str, on_action: Callable[[], None],
    on_dismiss: Callable[[], None] | None, dismiss_label: str,
) -> None:
    with ui.element("div").classes("dt-row"):
        ui.label(icon).classes(f"dt-icon {icon_class}")
        with ui.element("div").classes("dt-copy"):
            ui.label(title).classes("dt-title")
            _sub = ui.label(subtitle).classes("dt-sub")
            if subtitle_tooltip and subtitle_tooltip != subtitle:
                _sub.tooltip(subtitle_tooltip)
        ui.label(meta).classes("dt-meta")
        if on_dismiss is not None:
            ui.button(icon="close", on_click=on_dismiss).props(
                f'flat round dense aria-label="{dismiss_label}"'
            ).classes("dt-dismiss")
        ui.button(action, on_click=on_action).props(
            "unelevated color=primary size=sm rounded"
        )


def render_daily_training_block(
    *,
    flash_zero: dict | None = None,
    flash_zero_completed: bool = False,
    on_open_flash_zero: Callable[[], None] | None = None,
    on_dismiss_flash_zero: Callable[[], None] | None = None,
    daily_queue: list[dict] | None = None,
    on_open_daily_queue: Callable[[], None] | None = None,
) -> bool:
    """Rend le bloc. Retourne False (sans rien rendre) si rien à proposer."""
    has_flash = bool(flash_zero) and on_open_flash_zero is not None
    has_queue = bool(daily_queue) and on_open_daily_queue is not None
    if not has_flash and not has_queue:
        return False

    ensure_styles()
    with ui.element("div").classes("dt-block"):
        with ui.element("div").classes("dt-head"):
            ui.label("Entraînement du jour").classes("dt-head-title")

        if has_flash:
            duration = int((flash_zero or {}).get("duration_minutes") or 5)
            _row(
                icon="⚡", icon_class="zero",
                title="Pièges éliminatoires",
                subtitle="Tes erreurs récentes et répétées",
                subtitle_tooltip="",
                meta=f"10 questions · {duration} min · "
                     f"{'fait' if flash_zero_completed else 'à faire'}",
                action="Rejouer" if flash_zero_completed else "Lancer",
                on_action=on_open_flash_zero,
                on_dismiss=on_dismiss_flash_zero,
                dismiss_label="Ignorer les pièges éliminatoires pour aujourd'hui",
            )

        if has_queue:
            summary = daily_queue_summary(daily_queue or [])
            count = summary["count"]
            _row(
                icon="📚", icon_class="queue",
                title="Tes questions en attente",
                subtitle=summary["label"],
                subtitle_tooltip=summary["full_label"],
                meta=f"{count} question{'s' if count > 1 else ''} · déjà dans ta base",
                action="Ouvrir",
                on_action=on_open_daily_queue,
                on_dismiss=None,
                dismiss_label="",
            )
    return True
