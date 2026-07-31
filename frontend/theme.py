"""Shared page frame for the Synapse cockpit UI."""

from contextlib import contextmanager

from frontend.design_tokens import apply_design_tokens

apply_design_tokens()


@contextmanager
def frame(page_title: str):
    """Render the application-wide cockpit shell for a page."""
    from frontend.cockpit_shell import cockpit_frame

    with cockpit_frame(page_title):
        yield
