import inspect

from frontend.pages import qcm_cockpit


def test_qcm_wizards_allow_backdrop_dismiss():
    assert "persistent" not in inspect.getsource(qcm_cockpit._open_add_dialog)
