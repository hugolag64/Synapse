from backend.core.anki.media import embed_anki_media


def test_embed_anki_media_replaces_local_image_sources_with_data_urls():
    html = '<p><img src="question.svg"></p><img src="photo.png">'

    result = embed_anki_media(html, lambda name: b"data-" + name.encode())

    assert 'src="data:image/svg+xml;base64,' in result
    assert 'src="data:image/png;base64,' in result
    assert "question.svg" not in result


def test_embed_anki_media_keeps_unavailable_media_reference():
    html = '<img src="missing.png">'

    assert embed_anki_media(html, lambda _name: None) == html
