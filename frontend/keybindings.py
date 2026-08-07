"""
Keybindings — Synapse
---------------------
Raccourci clavier global, injecté depuis cockpit_shell.cockpit_frame().

  Ctrl+Alt+P   → palette de recherche
  Escape       → ferme les dialogs ouverts (géré côté Quasar)

Historique : trois raccourcis (Ctrl+K, Ctrl+/, et la touche « / » seule) étaient
déclarés ici, mais register_keybindings() n'était appelé nulle part — ils n'ont
jamais fonctionné. La touche « / » seule était de toute façon un piège : elle
ouvrait la palette dès qu'un slash était saisi hors champ de texte.
"""
from __future__ import annotations

from nicegui import ui


def register_keybindings() -> None:
    """À appeler une fois par page, depuis cockpit_frame."""
    from frontend.components.command_palette import open_command_palette

    def _on_key(e) -> None:
        if (e.action.keydown and e.modifiers.ctrl and e.modifiers.alt
                and e.key.name.lower() == "p"):
            open_command_palette()

    ui.keyboard(on_key=_on_key, ignore=["input", "select", "textarea"])
