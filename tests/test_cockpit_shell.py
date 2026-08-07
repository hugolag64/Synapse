from pathlib import Path
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


def test_uness_failures_badge_reads_pending_count(monkeypatch):
    monkeypatch.setattr(
        "backend.core.reviews.local_store.count_pending_uness_correction_failures", lambda: 3
    )

    assert cockpit_shell._uness_failures_badge() == ("count", "3")


def test_annales_nav_entry_has_a_dynamic_uness_failures_badge():
    from frontend.cockpit_shell import _NAV_GROUPS

    annales_entries = [
        badge
        for _group_label, items in _NAV_GROUPS
        for _glyph, label, _route, badge in items
        if label == "Épreuves & Annales"
    ]
    assert annales_entries == [("dynamic_count", "uness_failures")]


def test_shell_forces_icon_only_sidebar_between_768_and_900():
    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert "@media (min-width: 768px) and (max-width: 899.98px) {" in source
    assert ".cockpit-sidebar { width:56px; }" in source
    assert ".cockpit-main { margin-left:56px; width:calc(100% - 56px); }" in source
    assert ".cockpit-chevron { display:none; }" in source


def test_shell_replaces_sidebar_with_topbar_and_bottomnav_below_768():
    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert "@media (max-width: 767.98px) {" in source
    assert ".cockpit-sidebar { display:none; }" in source
    assert ".cockpit-main { margin-left:0; width:100%; padding:68px 16px 76px; }" in source
    assert ".cockpit-topbar-mobile { display:flex; }" in source
    assert ".cockpit-bottomnav { display:flex; }" in source


def test_shell_main_occupies_available_desktop_width():
    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

    assert "width:calc(100% - 200px)" in source
    assert "flex:1 1 auto" in source
    assert "width:calc(100% - 56px)" in source


def test_mobile_topbar_reuses_command_palette_for_search():
    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")

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

    source = Path("frontend/cockpit_shell.py").read_text(encoding="utf-8")
    assert "def _bottom_nav_item(" in source
    assert '"cockpit-bottomnav-item" + (" active" if active_key == active else "")' in source
    assert len(_BOTTOM_NAV) == 5


def test_semestres_is_no_longer_in_the_sidebar():
    from frontend.cockpit_shell import _NAV_GROUPS, _TITLE_TO_NAV

    routes = [route for _group, items in _NAV_GROUPS for _glyph, _label, route, _badge in items]
    assert "/semestres" not in routes
    assert "Semestres" not in _TITLE_TO_NAV.values()


def test_semestres_page_module_is_kept():
    assert Path("frontend/pages/semestres_cockpit.py").exists()
    assert Path("frontend/pages/semestres.py").exists()


def test_course_sheet_links_the_college_to_its_filtered_item_list():
    source = Path("frontend/pages/course_detail_cockpit.py").read_text(encoding="utf-8")

    assert 'ui.link(college, f"/items?college={college}")' in source
    assert 'ui.link(college, "/colleges")' not in source
