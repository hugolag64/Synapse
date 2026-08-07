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
