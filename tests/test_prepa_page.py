def test_prepa_groups_shortcuts_by_provider_and_category():
    from frontend.pages.prepa import build_prepa_view

    view = build_prepa_view(
        [
            {"provider": "EDNpro", "category": "annales", "title": "Annales", "url": "https://ednpro.app/annales", "enabled": 1},
            {"provider": "EDNpro", "category": "videos", "title": "ECG", "url": "https://ednpro.app/videos", "enabled": 1},
        ]
    )

    assert view["providers"] == ["EDNpro"]
    assert [row["category"] for row in view["categories"]] == ["annales", "videos"]
