from deploy.cleanup_test_annales import is_test_annale


def test_cleanup_matches_only_known_test_urls_without_sessions():
    assert is_test_annale({
        "source_url": "https://ednpro.app/annales/2023-p1-provenance-test-abc",
        "total_parts": 0,
    }) is True
    assert is_test_annale({
        "source_url": "https://ednpro.app/annales/dossier-split-test",
        "total_parts": 0,
    }) is True
    assert is_test_annale({
        "source_url": "https://ednpro.app/annales/2023-p1-provenance-test-abc",
        "total_parts": 1,
    }) is False
    assert is_test_annale({
        "source_url": "https://ednpro.app/annales/real-exam",
        "total_parts": 0,
    }) is False
