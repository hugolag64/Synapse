"""Caractérisation de la note Obsidian canonique d'un item multi-collèges."""

from types import SimpleNamespace


def _course(course_id: str, college: str):
    return SimpleNamespace(
        id=course_id,
        title="Addiction au tabac",
        display_item_number="75",
        college=[college],
        obsidian_uri="",
    )


def test_one_canonical_note_is_visible_from_all_synapse_college_aliases(
    tmp_path, monkeypatch
):
    from backend.config import settings as settings_module
    from backend.core.obsidian.service import ObsidianService

    note = (
        tmp_path
        / "01 - Cours EDN"
        / "Psychiatrie - Addictologie 🧩"
        / "Cours"
        / "Addiction au tabac.md"
    )
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\nitem: 75\ncollege: Psychiatrie\n---\n# Addiction au tabac\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module.settings, "obsidian_vault_path", str(tmp_path))

    service = ObsidianService()
    courses = [
        _course("mg-75", "Médecine générale"),
        _course("psy-75", "Psychiatrie"),
        _course("pneumo-75", "Pneumologie"),
    ]

    found = [service.find_course_note(course) for course in courses]

    assert found == [note, note, note]
    assert [service.note_exists(course) for course in courses] == [True, True, True]
    info = service.get_note_info(courses[0])
    assert info is not None
    assert info.path == note
    assert info.exists is True


def test_stale_obsidian_uri_does_not_claim_a_note_exists(tmp_path, monkeypatch):
    from backend.config import settings as settings_module
    from backend.core.obsidian.service import ObsidianService

    monkeypatch.setattr(settings_module.settings, "obsidian_vault_path", str(tmp_path))
    course = _course("pneumo-75", "Pneumologie")
    course.obsidian_uri = "obsidian://open?vault=Synapse&file=missing.md"

    assert ObsidianService().note_exists(course) is False


def test_ambiguous_item_notes_are_not_assigned_automatically(tmp_path, monkeypatch):
    from backend.config import settings as settings_module
    from backend.core.obsidian.service import ObsidianService

    for college in ("Psychiatrie - Addictologie", "Pneumologie"):
        folder = tmp_path / "01 - Cours EDN" / college / "Cours"
        folder.mkdir(parents=True)
        (folder / f"75 - Addiction au tabac ({college}).md").write_text(
            "---\nitem: 75\n---\n", encoding="utf-8"
        )
    monkeypatch.setattr(settings_module.settings, "obsidian_vault_path", str(tmp_path))

    assert ObsidianService().find_course_note(_course("mg-75", "Médecine générale")) is None


def test_item_match_has_priority_over_the_course_college_folder(tmp_path, monkeypatch):
    from backend.config import settings as settings_module
    from backend.core.obsidian.service import ObsidianService

    wrong_folder = tmp_path / "01 - Cours EDN" / "Pneumologie" / "Cours"
    right_folder = tmp_path / "01 - Cours EDN" / "Psychiatrie - Addictologie" / "Cours"
    wrong_folder.mkdir(parents=True)
    right_folder.mkdir(parents=True)
    (wrong_folder / "75 - Wrong note.md").write_text("---\nitem: 76\n---\n", encoding="utf-8")
    expected = right_folder / "75 - Correct note.md"
    expected.write_text("---\nitem: 75\n---\n", encoding="utf-8")
    monkeypatch.setattr(settings_module.settings, "obsidian_vault_path", str(tmp_path))

    assert ObsidianService().find_course_note(_course("pneumo-75", "Pneumologie")) == expected
