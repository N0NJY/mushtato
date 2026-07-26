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


# -- SSH support (post-Phase-13 addition) --------------------------------


def test_defaults_to_telnet_protocol_with_ssh_username_disabled(qapp):
    dialog = WorldEditDialog(None)
    assert dialog._selected_protocol() == "telnet"
    assert dialog.ssh_username_edit.isEnabled() is False


def test_switching_to_ssh_enables_the_username_field(qapp):
    dialog = WorldEditDialog(None)
    dialog.protocol_combo.setCurrentIndex(dialog.protocol_combo.findData("ssh"))
    assert dialog._selected_protocol() == "ssh"
    assert dialog.ssh_username_edit.isEnabled() is True


def test_new_ssh_world_round_trips_protocol_and_username(qapp):
    dialog = WorldEditDialog(None)
    dialog.name_edit.setText("My Server")
    dialog.host_edit.setText("silvren.com")
    dialog.port_spin.setValue(505)
    dialog.protocol_combo.setCurrentIndex(dialog.protocol_combo.findData("ssh"))
    dialog.ssh_username_edit.setText("rickn0njy")

    result = dialog.result_profile()

    assert result.protocol == "ssh"
    assert result.ssh_username == "rickn0njy"


def test_editing_an_existing_world_loads_its_saved_protocol(qapp):
    original = WorldProfile(
        name="X", host="h", port=505, protocol="ssh", ssh_username="rickn0njy"
    )
    dialog = WorldEditDialog(None, world=original)
    assert dialog._selected_protocol() == "ssh"
    assert dialog.ssh_username_edit.text() == "rickn0njy"
    assert dialog.ssh_username_edit.isEnabled() is True
