"""Headless tests for the quick Add/Edit World dialog (Phase 6),
including a regression test for a real Phase 8b data-loss bug: editing
a world through this dialog used to always rebuild a brand new
WorldProfile from just its 4 visible fields (name/host/port/notes),
silently discarding characters/auto-sends/login settings that had been
set up via the newer World Properties dialog.
"""

from engine.storage import CharacterProfile, WorldProfile
from gui.dialogs.world_edit_dialog import WorldEditDialog


def test_add_world_builds_a_fresh_profile_with_defaults(qapp):
    dialog = WorldEditDialog(None)
    dialog.name_edit.setText("New World")
    dialog.host_edit.setText("example.com")
    dialog.port_spin.setValue(4201)

    result = dialog.result_profile()

    assert result == WorldProfile(name="New World", host="example.com", port=4201, notes="")
    assert result.characters == []


def test_editing_preserves_characters_and_autosends_not_shown_in_this_dialog(qapp):
    original = WorldProfile(
        name="Original",
        host="example.com",
        port=4201,
        characters=[CharacterProfile(name="Thoran", password="hunter2")],
        default_character="Thoran",
        autosend_connect="look",
        login_delay=2.0,
        connect_count=5,
    )
    dialog = WorldEditDialog(None, world=original)
    dialog.host_edit.setText("changed.example.com")

    result = dialog.result_profile()

    assert result.host == "changed.example.com"  # the field we actually changed
    # Everything this dialog doesn't show must survive unchanged.
    assert result.characters == [CharacterProfile(name="Thoran", password="hunter2")]
    assert result.default_character == "Thoran"
    assert result.autosend_connect == "look"
    assert result.login_delay == 2.0
    assert result.connect_count == 5


def test_editing_blank_host_still_returns_none(qapp):
    original = WorldProfile(name="X", host="h", port=1)
    dialog = WorldEditDialog(None, world=original)
    dialog.host_edit.setText("")
    assert dialog.result_profile() is None
