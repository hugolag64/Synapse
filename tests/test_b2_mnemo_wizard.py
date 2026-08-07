"""Le wizard mnémo/image réagit au thème (au lieu d'être toujours sombre) et
n'affiche plus aucun emoji, conformément au design system."""
from pathlib import Path

_SOURCE_PATH = "frontend/components/obsidian_quick_edit_dialog.py"


def test_mnemo_dialog_reacts_to_theme_instead_of_being_always_dark():
    source = Path(_SOURCE_PATH).read_text(encoding="utf-8")
    assert "bg-slate-900" not in source
    assert "text-white" not in source
    assert "outlined dark rows=3" not in source
    assert "flat bordered dark" not in source
    assert "background:var(--bg)" in source
    assert "color:var(--text)" in source


def test_mnemo_dialog_has_no_emoji():
    source = Path(_SOURCE_PATH).read_text(encoding="utf-8")
    for emoji in ("💡", "📷", "⚠️"):
        assert emoji not in source, f"emoji {emoji!r} still present"


def test_mnemo_dialog_uses_primary_instead_of_arbitrary_indigo():
    source = Path(_SOURCE_PATH).read_text(encoding="utf-8")
    assert "color=indigo" not in source
    assert "color=primary" in source


def test_mnemo_dialog_keeps_its_public_signature():
    """Non-régression : la fonction publique garde sa signature — seul
    l'habillage visuel change, aucune structure n'est touchée."""
    import inspect

    from frontend.components.obsidian_quick_edit_dialog import open_obsidian_quick_edit_dialog

    params = list(inspect.signature(open_obsidian_quick_edit_dialog).parameters)
    assert params == ["course", "on_success"]
