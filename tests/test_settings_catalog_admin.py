from types import SimpleNamespace

import frontend.pages.catalog_admin as catalog_admin


class _Element:
    def __init__(self, value=None):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def classes(self, *_args, **_kwargs):
        return self

    def props(self, *_args, **_kwargs):
        return self

    def set_text(self, _text):
        return None


class _UI:
    def expansion(self, *_args, **_kwargs):
        return _Element()

    def label(self, *_args, **_kwargs):
        return _Element()

    def row(self, *_args, **_kwargs):
        return _Element()

    def tabs(self, *_args, **_kwargs):
        return _Element()

    def tab(self, name, label=None, icon=None):
        return _Element()

    def tab_panels(self, *_args, **_kwargs):
        return _Element()

    def tab_panel(self, *_args, **_kwargs):
        return _Element()

    def input(self, *_args, **_kwargs):
        return _Element()

    def select(self, *_args, **kwargs):
        return _Element(kwargs.get("value"))

    def button(self, *_args, **_kwargs):
        return _Element()

    def notify(self, *_args, **_kwargs):
        return None


def test_catalog_admin_renders_with_nicegui_tab_signature(monkeypatch):
    repository = SimpleNamespace(
        db_path=None,
        count_items=lambda: 1,
        count_fiches=lambda: 2,
        count_archived_courses=lambda: 3,
        list_audit_log=lambda limit=30: [],
        save_override=lambda *args: None,
    )
    service = SimpleNamespace()

    monkeypatch.setattr(catalog_admin, "ui", _UI())
    monkeypatch.setattr(catalog_admin, "CatalogRepository", lambda *_args: repository)
    monkeypatch.setattr(catalog_admin, "CatalogImportService", lambda **_kwargs: service)

    catalog_admin.render_catalog_admin()
