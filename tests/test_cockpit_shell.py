from types import SimpleNamespace

from frontend import cockpit_shell


def test_revision_badge_uses_overdue_task_count(monkeypatch):
    class ReviewService:
        def generate_reviews(self, context, history):
            assert context == "college"
            return [SimpleNamespace(id="a"), SimpleNamespace(id="b"), SimpleNamespace(id="c")]

        def get_urgent_tasks(self, tasks):
            return tasks[:2]

    monkeypatch.setattr("backend.core.reviews.local_store.get_all_history", lambda: {})
    monkeypatch.setattr(cockpit_shell, "_revision_badge", cockpit_shell._revision_badge)
    monkeypatch.setattr("backend.core.reviews.service.review_service", ReviewService())

    assert cockpit_shell._revision_badge() == ("count", "2")


def test_shell_forces_icon_only_sidebar_between_768_and_900():
    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()

    assert "@media (min-width: 768px) and (max-width: 899.98px) {" in source
    assert ".cockpit-sidebar { width:56px; }" in source
    assert ".cockpit-main { margin-left:56px; }" in source
    assert ".cockpit-chevron { display:none; }" in source


def test_shell_replaces_sidebar_with_topbar_and_bottomnav_below_768():
    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()

    assert "@media (max-width: 767.98px) {" in source
    assert ".cockpit-sidebar { display:none; }" in source
    assert ".cockpit-main { margin-left:0; padding:68px 16px 76px; }" in source
    assert ".cockpit-topbar-mobile { display:flex; }" in source
    assert ".cockpit-bottomnav { display:flex; }" in source


def test_mobile_topbar_reuses_command_palette_for_search():
    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()

    assert '.on("click", open_command_palette)' in source
    assert source.count("open_command_palette") >= 2  # sidebar desktop + topbar mobile


def test_bottom_nav_has_five_entries_matching_readme():
    from frontend.cockpit_shell import _BOTTOM_NAV

    routes = [route for _glyph, _label, route, _active_key in _BOTTOM_NAV]
    assert routes == ["/", "/planning", "/todo", "/items", "/lacunes"]

    active_keys = [active_key for _glyph, _label, _route, active_key in _BOTTOM_NAV]
    assert active_keys == ["Aujourd'hui", "Planning", "Révisions", "Items", "Points faibles"]


def test_bottom_nav_item_highlights_active_page():
    from frontend.cockpit_shell import _BOTTOM_NAV

    source = open("frontend/cockpit_shell.py", encoding="utf-8").read()
    assert "def _bottom_nav_item(" in source
    assert '"cockpit-bottomnav-item" + (" active" if active_key == active else "")' in source
    assert len(_BOTTOM_NAV) == 5
