"""Les trois derniers blocs Tailwind bruts (jamais migrés lors de la construction
initiale de ces écrans) passent aux tokens du design system."""
from pathlib import Path


def test_annales_import_blocks_use_design_tokens():
    source = Path("frontend/pages/annales.py").read_text(encoding="utf-8")
    assert "border-slate-200" not in source
    assert "bg-slate-50" not in source
    assert "dark:bg-slate-900/40" not in source


def test_annale_detail_history_card_uses_design_tokens():
    source = Path("frontend/pages/annale_detail.py").read_text(encoding="utf-8")
    assert "border-slate-200" not in source
    assert "dark:border-slate-800" not in source
