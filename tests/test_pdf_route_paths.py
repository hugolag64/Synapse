import os


def test_resolve_pdf_path_accepts_unix_file_uri(monkeypatch):
    from backend.config.settings import settings
    from main import _resolve_pdf_path

    monkeypatch.setattr(settings, "medicine_dir", "/data/medicine")
    monkeypatch.setattr(settings, "fac_dir", "")
    monkeypatch.setattr(os, "sep", "/")
    monkeypatch.setattr(os.path, "realpath", lambda path: path)
    monkeypatch.setattr(
        os.path,
        "isfile",
        lambda path: path == "/data/medicine/sample.pdf",
    )

    assert _resolve_pdf_path("file:///data/medicine/sample.pdf") == "/data/medicine/sample.pdf"
