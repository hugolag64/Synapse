"""Tests for the shared practice-session action component."""

from __future__ import annotations

import inspect

from frontend.components import practice_session_card


def test_open_node_qcm_prefers_the_node_reader_when_built() -> None:
    source = inspect.getsource(practice_session_card.open_node_qcm)

    assert "qcm-app" in source
    assert "QCM_NODE_DIST.exists()" in source


def test_render_session_actions_dispatches_by_session_action_keys() -> None:
    source = inspect.getsource(practice_session_card.render_session_actions)

    assert "session_action_keys" in source
    assert "on_resume" in source
    assert "on_correction" in source
    assert "on_replay" in source
