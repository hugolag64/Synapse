import pytest


def test_validate_uness_annale_url_accepts_course_url():
    from frontend.pages.settings import _validate_uness_annale_url

    value = " https://entrainement.uness.fr/annales/course/view.php?id=29135 "

    assert _validate_uness_annale_url(value) == value.strip()


def test_local_collector_uses_same_url_contract():
    from scripts.uness.collector import validate_annale_url

    assert validate_annale_url("https://entrainement.uness.fr/annales/course/view.php?id=29135").endswith("id=29135")


@pytest.mark.parametrize(
    "value",
    ["", "https://example.com/annales/course/view.php?id=29135", "http://entrainement.uness.fr/annales/course/view.php?id=29135", "https://entrainement.uness.fr/login"],
)
def test_validate_uness_annale_url_rejects_non_annales_urls(value):
    from frontend.pages.settings import _validate_uness_annale_url

    with pytest.raises(ValueError):
        _validate_uness_annale_url(value)
