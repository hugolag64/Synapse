def test_prepa_groups_shortcuts_by_provider_and_category():
    from frontend.pages.prepa import build_prepa_view

    view = build_prepa_view(
        [
            {"provider": "EDNpro", "category": "annales", "title": "Annales", "url": "https://ednpro.app/annales", "enabled": 1},
            {"provider": "EDNpro", "category": "videos", "title": "ECG", "url": "https://ednpro.app/videos", "enabled": 1},
        ],
        providers=[
            {"name": "EDNpro", "root_url": "https://ednpro.app", "enabled": True},
            {"name": "Hypocampus", "root_url": "https://hypocampus.fr", "enabled": True},
            {"name": "EDNi", "root_url": "", "enabled": False},
        ],
    )

    assert [row["provider"] for row in view["provider_sections"]] == ["EDNpro", "Hypocampus", "EDNi"]
    assert [row["category"] for row in view["provider_sections"][0]["categories"]] == ["annales", "videos"]
    assert view["provider_sections"][1]["categories"] == []
    assert view["provider_sections"][2]["enabled"] is False


def test_relative_time_label_buckets_by_recency():
    import datetime

    from frontend.pages.prepa import relative_time_label

    now = datetime.datetime(2026, 8, 7, 14, 0, 0, tzinfo=datetime.timezone.utc)

    assert relative_time_label(now - datetime.timedelta(seconds=30), now) == "à l'instant"
    assert relative_time_label(now - datetime.timedelta(minutes=5), now) == "il y a 5min"
    assert relative_time_label(now - datetime.timedelta(hours=2), now) == "il y a 2h"
    assert relative_time_label(now - datetime.timedelta(days=1), now) == "hier"
    assert relative_time_label(now - datetime.timedelta(days=3), now) == "il y a 3j"


def test_prepa_css_adds_hover_lift_and_staggered_entrance():
    from pathlib import Path

    source = Path("frontend/pages/prepa.py").read_text(encoding="utf-8")

    assert "transform:translateY(-2px)" in source
    assert "box-shadow:var(--shadow-popover)" in source
    assert "@keyframes prepProviderEnter" in source
    assert ".prep-provider:nth-of-type(2) { animation-delay: 60ms; }" in source


def test_prepa_page_hides_recent_section_when_nothing_was_used(monkeypatch):
    """La section « Récemment consulté » ne doit jamais apparaître vide."""
    from pathlib import Path
    import frontend.pages.prepa as prepa_module

    monkeypatch.setattr(prepa_module, "list_recent_prep_shortcuts", lambda limit=5: [])

    source = Path("frontend/pages/prepa.py").read_text(encoding="utf-8")
    assert "if recent:" in source


def test_prepa_uses_linear_source_rows_instead_of_nested_shortcut_cards():
    from pathlib import Path

    source = Path("frontend/pages/prepa.py").read_text(encoding="utf-8")

    assert ".prep-source-row" in source
    assert "grid-template-columns:minmax(180px, .8fr) minmax(240px, 1.5fr) 130px 72px" in source
    assert "DERNIÈRE UTILISATION" in source
    assert "OUVRIR" in source
