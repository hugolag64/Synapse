def test_item_resource_panel_shows_verified_ednpro_video():
    from frontend.pages.course_detail_cockpit import build_item_resources

    rows = build_item_resources("221", [
        {
            "provider": "EDNpro",
            "resource_type": "video",
            "title": "Athérome",
            "url": "https://ednpro.app/videos/221",
            "confidence": 1.0,
        }
    ])

    assert rows[0]["label"] == "Athérome"
    assert rows[0]["provider"] == "EDNpro"


def test_item_resource_panel_does_not_show_ambiguous_video():
    from frontend.pages.course_detail_cockpit import build_item_resources

    assert build_item_resources("221", [{
        "provider": "EDNpro", "resource_type": "video", "title": "Ambigu",
        "url": "https://ednpro.app/videos/other", "confidence": 0.4,
    }]) == []


def test_item_resource_panel_labels_video_type_and_hypocampus_course():
    from frontend.pages.course_detail_cockpit import build_item_resources

    rows = build_item_resources("221", [
        {
            "provider": "Hypocampus",
            "resource_type": "course",
            "title": "Item 221",
            "url": "https://hypocampus.fr/items/221",
            "confidence": 0.95,
        },
        {
            "provider": "EDNpro",
            "resource_type": "video",
            "title": "Athérome",
            "url": "https://ednpro.app/videos/221",
            "confidence": 1.0,
        },
    ])

    assert rows[0]["display_label"] == "Cours Hypocampus"
    assert rows[0]["url"].endswith("/items/221")
    assert rows[1]["display_label"] == "Vidéo · Athérome"
