import inspect

from frontend.pages import qcm


def test_qcm_wizards_allow_backdrop_dismiss():
    for wizard in (
        qcm._open_add_dialog,
        qcm._propose_lacune,
        qcm._propose_resolve_lacune,
        qcm._open_session_wizard,
    ):
        assert "persistent" not in inspect.getsource(wizard)
