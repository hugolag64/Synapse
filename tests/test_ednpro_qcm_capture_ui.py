from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_qcm_cockpit_exposes_human_in_the_loop_capture_action():
    source = (ROOT / "frontend/pages/qcm_cockpit.py").read_text(encoding="utf-8")
    panel = (ROOT / "frontend/components/ednpro_capture_panel.py").read_text(encoding="utf-8")

    assert "Capturer une session EDNpro" in source
    assert "Arrêter et importer" in panel
    assert "127.0.0.1:8876" in panel


def test_capture_panel_starts_browser_capture_automatically():
    panel = (ROOT / "frontend/components/ednpro_capture_panel.py").read_text(encoding="utf-8")

    assert "fetch('http://127.0.0.1:8876/start')" in panel
    assert "https://ednpro.app/training-v2" in panel
    assert "Démarrer la capture" not in panel
