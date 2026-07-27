"""
Keybindings — Synapse "Zéro Friction"
--------------------------------------
Raccourcis clavier globaux, injectés depuis theme.frame().

  Ctrl+K / /   → Command Palette
  1            → /  (Dashboard)
  2            → /planning
  3            → /qcm
  4            → /lacunes
  5            → /colleges
  6            → /stats
  Escape       → ferme les dialogs ouverts (géré côté JS)

Les touches numériques sont ignorées quand un <input> est focalisé.
"""
from __future__ import annotations

from nicegui import ui
from loguru import logger


_NAV_ROUTES: dict[str, str] = {
    "1": "/",
    "2": "/planning",
    "3": "/qcm",
    "4": "/lacunes",
    "5": "/colleges",
    "6": "/stats",
}


def register_keybindings() -> None:
    """
    À appeler une fois dans le contexte NiceGUI d'une page (e.g. depuis theme.frame).
    Crée un ui.keyboard qui capte les raccourcis globaux.
    """
    from frontend.components.command_palette import open_command_palette

    def _on_key(e) -> None:
        if not e.action.keydown:
            return

        key = e.key.name

        # Ctrl+K ou Ctrl+/ → palette
        if e.modifiers.ctrl and key in ("k", "/"):
            open_command_palette()
            return

        # Touche / seule (hors input) → palette
        if key == "/":
            open_command_palette()
            return

        # Touches numériques 1-6 → navigation
        if key in _NAV_ROUTES:
            ui.navigate.to(_NAV_ROUTES[key])
            return

    ui.keyboard(
        on_key=_on_key,
        ignore=["input", "select", "textarea"],
    )


def register_item_search_keybinding(open_palette) -> None:
    """Enregistre Ctrl+Alt+P pour une page Items sans modifier les raccourcis globaux."""
    def _on_key(e) -> None:
        if (e.action.keydown and e.modifiers.ctrl and e.modifiers.alt
                and e.key.name.lower() == "p"):
            open_palette()

    ui.keyboard(on_key=_on_key, ignore=["input", "select", "textarea"])
