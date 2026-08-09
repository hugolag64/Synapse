from types import SimpleNamespace

from nicegui import ui

from frontend.components.course_quick_actions import _open_obsidian_note_action


def test_open_obsidian_note_navigates_in_the_user_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(
        ui.navigate,
        "to",
        lambda uri, new_tab=False: opened.append((uri, new_tab)),
    )
    course = SimpleNamespace(obsidian_uri="obsidian://open?vault=Medecine&file=note.md")

    _open_obsidian_note_action(course)

    assert opened == [(course.obsidian_uri, True)]
