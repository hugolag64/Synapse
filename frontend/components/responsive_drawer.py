"""Shared responsive drawer shell for cockpit secondary panels."""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

from nicegui import ui


_CONTRACT = {
    "root": "synapse-responsive-drawer",
    "scrim": "synapse-responsive-drawer__scrim",
    "panel": "synapse-responsive-drawer__panel",
    "close": "synapse-responsive-drawer__close",
    "breakpoint": "(min-width: 900px) and (max-width: 1199.98px)",
}
_injected = {"done": False}


def drawer_css_contract() -> dict[str, str]:
    """Return stable class names shared by responsive panel integrations."""
    return dict(_CONTRACT)


def ensure_styles() -> None:
    """Inject the drawer CSS synchronously and only once per process."""
    if _injected["done"]:
        return
    ui.add_head_html(
        """<style>
.synapse-responsive-drawer { position:relative; min-width:0; }
.synapse-responsive-drawer__scrim,
.synapse-responsive-drawer__close { display:none; }
.synapse-responsive-drawer__panel { min-width:0; box-sizing:border-box; }
@media (min-width: 900px) and (max-width: 1199.98px) {
  .synapse-responsive-drawer.is-closed .synapse-responsive-drawer__scrim,
  .synapse-responsive-drawer.is-closed .synapse-responsive-drawer__panel { display:none; }
  .synapse-responsive-drawer__scrim { display:block; position:fixed; inset:0; z-index:1090;
    background:color-mix(in srgb, var(--text) 45%, transparent); }
  .synapse-responsive-drawer__panel { display:flex; flex-direction:column; position:fixed;
    top:0; right:0; bottom:0; z-index:1100; width:min(420px, calc(100vw - 56px));
    overflow-y:auto; padding:16px; background:var(--bg); border-left:1px solid var(--border);
    box-shadow:var(--shadow-popover); transition:transform var(--duration-fast) var(--ease-standard); }
  .synapse-responsive-drawer__close { display:flex; align-items:center; justify-content:center;
    align-self:flex-end; width:28px; height:28px; margin:-4px -4px 4px 0; border:0;
    border-radius:6px; background:transparent; color:var(--text-muted); cursor:pointer;
    font-size:16px; line-height:1; }
  .synapse-responsive-drawer__close:hover { background:var(--surface); color:var(--text); }
}
</style>""",
        shared=True,
    )
    _injected["done"] = True


@contextmanager
def responsive_drawer(*, on_close=None, aria_label: str = "Panneau contextuel",
                      include_close: bool = True) -> Iterator[Any]:
    """Render a panel that becomes an overlay drawer at the session breakpoint."""
    ensure_styles()
    with ui.element("div").classes(_CONTRACT["root"]) as root:
        scrim = ui.element("div").classes(_CONTRACT["scrim"]).props(
            'aria-hidden="true" tabindex="-1"'
        )
        if on_close is not None:
            scrim.on("click", on_close)
        panel = ui.element("aside").classes(_CONTRACT["panel"]).props(
            f'role="dialog" aria-modal="true" aria-label="{aria_label}"'
        )
        with panel:
            if on_close is not None and include_close:
                ui.button("×", on_click=on_close).classes(_CONTRACT["close"]).props(
                    'aria-label="Fermer" flat'
                )
            yield root


def close_drawer(root: Any) -> None:
    root.classes(add="is-closed")


def open_drawer(root: Any) -> None:
    root.classes(remove="is-closed")
