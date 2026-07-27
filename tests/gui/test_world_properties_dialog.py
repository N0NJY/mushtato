"""Headless tests for the World Properties dialog (Phase 8b): the
Characters add/edit/delete flow, connection-specifics placeholders
being genuinely disabled, and round-tripping all fields through
result_profile(). Uses synthetic data only -- never anything from
~/.potato.

Phase 9 additions: the Scripts page, built on the exact same list+
detail pattern as Characters (reused deliberately, see
world_properties_dialog.py's _ScriptsPage docstring).
"""

from engine.storage import CharacterProfile, ScriptRecord, WorldProfile
from gui.dialogs.world_properties_dialog import WorldPropertiesDialog


def make_world(**kwargs):
    defaults = dict(name="Test World", host="example.com", port=4201)
    defaults.update(kwargs)
    return WorldProfile(**defaults)


def test_dialog_loads_basic_fields_from_the_world(qapp):
    world = make_world(name="Estrellita", host="silvren.com", port=4444)
    dialog = WorldPropertiesDialog(None, world=world)

    assert dialog.name_edit.text() == "Estrellita"
    assert dialog.host_edit.text() == "silvren.com"
    assert dialog.port_spin.value() == 4444


def test_dialog_loads_autosends_and_notes(qapp):
    world = make_world(
        autosend_firstconnect="fc", autosend_connect="c", autosend_login="l", notes="some notes"
    )
    dialog = WorldPropertiesDialog(None, world=world)

    assert dialog.autosend_firstconnect_edit.toPlainText() == "fc"
    assert dialog.autosend_connect_edit.toPlainText() == "c"
    assert dialog.autosend_login_edit.toPlainText() == "l"
    assert dialog.notes_edit.toPlainText() == "some notes"


def test_dialog_loads_existing_characters_into_the_list(qapp):
    world = make_world(characters=[CharacterProfile(name="Thoran", password="hunter2")])
    dialog = WorldPropertiesDialog(None, world=world)

    chars_page = dialog._characters_page
    assert chars_page.list_widget.count() == 1
    assert chars_page.list_widget.item(0).text() == "Thoran"


def test_add_character_flow(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    chars_page = dialog._characters_page

    chars_page._start_add()
    chars_page.name_edit.setText("NewChar")
    chars_page.password_edit.setText("secret")
    chars_page._save_current()

    assert chars_page.characters == [CharacterProfile(name="NewChar", password="secret")]
    assert chars_page.list_widget.count() == 1


def test_edit_character_flow(qapp):
    world = make_world(characters=[CharacterProfile(name="Old", password="oldpw")])
    dialog = WorldPropertiesDialog(None, world=world)
    chars_page = dialog._characters_page

    chars_page.list_widget.setCurrentRow(0)
    chars_page._start_edit()
    chars_page.name_edit.setText("Renamed")
    chars_page.password_edit.setText("newpw")
    chars_page._save_current()

    assert chars_page.characters == [CharacterProfile(name="Renamed", password="newpw")]


def test_delete_character_flow(qapp):
    world = make_world(
        characters=[
            CharacterProfile(name="Keep", password=""),
            CharacterProfile(name="Remove", password=""),
        ]
    )
    dialog = WorldPropertiesDialog(None, world=world)
    chars_page = dialog._characters_page

    chars_page.list_widget.setCurrentRow(1)
    chars_page._delete_selected()

    assert chars_page.characters == [CharacterProfile(name="Keep", password="")]


def test_cancel_edit_discards_in_progress_changes(qapp):
    world = make_world(characters=[CharacterProfile(name="Original", password="")])
    dialog = WorldPropertiesDialog(None, world=world)
    chars_page = dialog._characters_page

    chars_page.list_widget.setCurrentRow(0)
    chars_page._start_edit()
    chars_page.name_edit.setText("Changed")
    chars_page._cancel_edit()

    assert chars_page.characters == [CharacterProfile(name="Original", password="")]


def test_default_character_combo_includes_saved_characters(qapp):
    world = make_world(
        characters=[CharacterProfile(name="Alice"), CharacterProfile(name="Bob")],
        default_character="Bob",
    )
    dialog = WorldPropertiesDialog(None, world=world)

    items = [dialog.default_character_combo.itemText(i) for i in range(dialog.default_character_combo.count())]
    assert items == ["(None)", "Alice", "Bob"]
    assert dialog.default_character_combo.currentText() == "Bob"


def test_result_profile_builds_updated_world_with_new_character(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    dialog.name_edit.setText("Renamed World")
    dialog._characters_page._start_add()
    dialog._characters_page.name_edit.setText("Thoran")
    dialog._characters_page.password_edit.setText("hunter2")
    dialog._characters_page._save_current()
    dialog._refresh_default_character_combo()
    dialog.default_character_combo.setCurrentText("Thoran")
    dialog.autosend_connect_edit.setPlainText("look")

    result = dialog.result_profile()

    assert result.name == "Renamed World"
    assert result.characters == [CharacterProfile(name="Thoran", password="hunter2")]
    assert result.default_character == "Thoran"
    assert result.autosend_connect == "look"


def test_result_profile_preserves_connect_count(qapp):
    world = make_world(connect_count=7)
    dialog = WorldPropertiesDialog(None, world=world)
    assert dialog.result_profile().connect_count == 7


def test_result_profile_returns_none_for_blank_name(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    dialog.name_edit.setText("")
    assert dialog.result_profile() is None


def test_connection_specifics_placeholders_are_disabled(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)

    for widget in (
        dialog.ssl_checkbox,
        dialog.host2_edit,
        dialog.port2_spin,
        dialog.proxy_combo,
        dialog.naws_checkbox,
        dialog.term_checkbox,
    ):
        assert widget.isEnabled() is False


def test_functional_connection_fields_are_enabled(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    assert dialog.login_format_edit.isEnabled() is True
    assert dialog.login_delay_spin.isEnabled() is True
    # No longer a placeholder (post-Phase-9) -- real and functional,
    # unlike its disabled Connection-page neighbors above.
    assert dialog.keepalive_checkbox.isEnabled() is True


def test_category_list_has_six_sections(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    titles = [dialog.category_list.item(i).text() for i in range(dialog.category_list.count())]
    assert titles == ["Basic", "Characters", "Connection", "Auto-Sends", "Notes", "Scripts"]


def test_switching_category_switches_the_visible_page(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    dialog.category_list.setCurrentRow(1)
    assert dialog.pages.currentWidget() is dialog._characters_page


# -- Regression: adding a Character should be enough to use it on connect --


def test_adding_the_first_character_becomes_the_default_automatically(qapp):
    # Rick's real report: he added a Character and expected it to be
    # used on connect, but nothing happened until he also visited the
    # separate Basic page and picked it from Default Character by hand.
    world = make_world()  # no characters, no default
    dialog = WorldPropertiesDialog(None, world=world)

    dialog._characters_page._start_add()
    dialog._characters_page.name_edit.setText("Thoran")
    dialog._characters_page.password_edit.setText("hunter2")
    dialog._characters_page._save_current()

    assert dialog.default_character_combo.currentText() == "Thoran"
    assert dialog.result_profile().default_character == "Thoran"


def test_adding_a_second_character_does_not_override_an_existing_default(qapp):
    world = make_world(
        characters=[CharacterProfile(name="First", password="")], default_character="First"
    )
    dialog = WorldPropertiesDialog(None, world=world)

    dialog._characters_page._start_add()
    dialog._characters_page.name_edit.setText("Second")
    dialog._characters_page.password_edit.setText("")
    dialog._characters_page._save_current()

    assert dialog.default_character_combo.currentText() == "First"


def test_editing_an_existing_character_does_not_trigger_auto_default(qapp):
    world = make_world(characters=[CharacterProfile(name="Original", password="")])
    dialog = WorldPropertiesDialog(None, world=world)
    assert dialog.default_character_combo.currentText() == "(None)"

    dialog._characters_page.list_widget.setCurrentRow(0)
    dialog._characters_page._start_edit()
    dialog._characters_page.name_edit.setText("Renamed")
    dialog._characters_page._save_current()

    # Editing isn't adding -- the default should still be unset.
    assert dialog.default_character_combo.currentText() == "(None)"


# -- Scripts page (Phase 9) -----------------------------------------------


def test_dialog_loads_existing_scripts_into_the_list(qapp):
    dialog = WorldPropertiesDialog(
        None, world=make_world(), scripts=[ScriptRecord(name="my-script", source="pass")]
    )

    page = dialog._scripts_page
    assert page.list_widget.count() == 1
    assert page.list_widget.item(0).text() == "my-script"


def test_disabled_script_shows_disabled_suffix_in_the_list(qapp):
    dialog = WorldPropertiesDialog(
        None,
        world=make_world(),
        scripts=[ScriptRecord(name="off", source="pass", enabled=False)],
    )

    assert dialog._scripts_page.list_widget.item(0).text() == "off (disabled)"


def test_add_script_flow(qapp):
    dialog = WorldPropertiesDialog(None, world=make_world())
    page = dialog._scripts_page

    page._start_add()
    page.name_edit.setText("new-script")
    page.source_edit.setPlainText("on_trigger('x', lambda m: None)")
    page._save_current()

    assert page.list_widget.count() == 1
    assert dialog.result_scripts() == [
        ScriptRecord(name="new-script", source="on_trigger('x', lambda m: None)")
    ]


def test_edit_script_flow_preserves_trusted_flag(qapp):
    dialog = WorldPropertiesDialog(
        None,
        world=make_world(),
        scripts=[ScriptRecord(name="s1", source="old", trusted=True)],
    )
    page = dialog._scripts_page

    page.list_widget.setCurrentRow(0)
    page._start_edit()
    page.source_edit.setPlainText("new source")
    page._save_current()

    result = dialog.result_scripts()
    assert result == [ScriptRecord(name="s1", source="new source", trusted=True)]


def test_delete_script_flow(qapp):
    dialog = WorldPropertiesDialog(
        None, world=make_world(), scripts=[ScriptRecord(name="s1", source="pass")]
    )
    page = dialog._scripts_page

    page.list_widget.setCurrentRow(0)
    page._delete_selected()

    assert dialog.result_scripts() == []


def test_unchecking_enabled_persists_through_result_scripts(qapp):
    dialog = WorldPropertiesDialog(
        None, world=make_world(), scripts=[ScriptRecord(name="s1", source="pass")]
    )
    page = dialog._scripts_page

    page.list_widget.setCurrentRow(0)
    page._start_edit()
    page.enabled_checkbox.setChecked(False)
    page._save_current()

    assert dialog.result_scripts()[0].enabled is False


def test_a_script_with_a_disabled_trigger_shows_a_visible_marker(qapp):
    dialog_marked = WorldPropertiesDialog(
        None,
        world=make_world(),
        scripts=[ScriptRecord(name="s1", source="pass")],
        disabled_trigger_scripts={"s1"},
    )
    dialog_unmarked = WorldPropertiesDialog(
        None, world=make_world(), scripts=[ScriptRecord(name="s1", source="pass")]
    )

    marked_item = dialog_marked._scripts_page.list_widget.item(0)
    unmarked_item = dialog_unmarked._scripts_page.list_widget.item(0)
    assert marked_item.toolTip() != ""
    assert unmarked_item.toolTip() == ""


# -- NOP keepalive (post-Phase-9 addition) --------------------------------


def test_dialog_loads_nop_keepalive_from_the_world(qapp):
    dialog_on = WorldPropertiesDialog(None, world=make_world(nop_keepalive=True))
    dialog_off = WorldPropertiesDialog(None, world=make_world(nop_keepalive=False))

    assert dialog_on.keepalive_checkbox.isChecked() is True
    assert dialog_off.keepalive_checkbox.isChecked() is False


def test_result_profile_reflects_edited_nop_keepalive(qapp):
    dialog = WorldPropertiesDialog(None, world=make_world(nop_keepalive=False))

    dialog.keepalive_checkbox.setChecked(True)

    assert dialog.result_profile().nop_keepalive is True


# -- Regression: auto_login used to be silently dropped by this dialog --


def test_result_profile_preserves_auto_login_unchanged(qapp):
    # Real bug found and fixed alongside nop_keepalive: this dialog has
    # no UI for auto_login (that checkbox lives on the Address Book's
    # own Worlds list) -- result_profile() used to never carry the
    # field through at all, meaning saving *any* Properties change
    # (even something unrelated, like a Character edit) silently reset
    # auto_login back to False.
    world = make_world(
        characters=[CharacterProfile(name="Guest")], default_character="Guest", auto_login=True
    )
    dialog = WorldPropertiesDialog(None, world=world)

    result = dialog.result_profile()

    assert result.auto_login is True


# -- SSH support (post-Phase-13 addition) --------------------------------


def test_dialog_defaults_to_telnet_with_ssh_username_disabled(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)

    assert dialog._selected_protocol() == "telnet"
    assert dialog.ssh_username_edit.isEnabled() is False


def test_dialog_loads_ssh_protocol_and_username_from_the_world(qapp):
    world = make_world(protocol="ssh", ssh_username="rickn0njy")
    dialog = WorldPropertiesDialog(None, world=world)

    assert dialog._selected_protocol() == "ssh"
    assert dialog.ssh_username_edit.text() == "rickn0njy"
    assert dialog.ssh_username_edit.isEnabled() is True


def test_result_profile_reflects_edited_protocol_and_username(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    dialog.protocol_combo.setCurrentIndex(dialog.protocol_combo.findData("ssh"))
    dialog.ssh_username_edit.setText("rickn0njy")

    result = dialog.result_profile()

    assert result.protocol == "ssh"
    assert result.ssh_username == "rickn0njy"


# -- Mail Window settings preservation (bug found during SSH work) -------


def test_result_profile_preserves_mail_settings_unchanged(qapp):
    # Real bug found while adding SSH support: this dialog has no UI for
    # any mail_* field (those are set from the Mail Window itself, on
    # Send) -- result_profile() never threaded them through at all,
    # meaning saving *any* Properties change (even something unrelated,
    # like renaming the world) silently reset a world's Mail Window
    # settings back to defaults.
    world = make_world(
        mail_format="MUX @mail",
        mail_format_custom="custom template %to% %body%",
        mail_convert_returns=False,
        mail_convert_returns_to="\\n",
    )
    dialog = WorldPropertiesDialog(None, world=world)
    dialog.name_edit.setText("Renamed World")  # an unrelated change

    result = dialog.result_profile()

    assert result.mail_format == "MUX @mail"
    assert result.mail_format_custom == "custom template %to% %body%"
    assert result.mail_convert_returns is False
    assert result.mail_convert_returns_to == "\\n"


def test_result_profile_preserves_splitter_sizes_unchanged(qapp):
    # Same class of bug as auto_login/mail_* above: this dialog has no
    # UI for splitter_sizes at all (it's only ever set by dragging the
    # splitter in an open tab) -- must be carried through unchanged.
    world = make_world(splitter_sizes=[300, 200])
    dialog = WorldPropertiesDialog(None, world=world)
    dialog.name_edit.setText("Renamed World")  # an unrelated change

    result = dialog.result_profile()

    assert result.splitter_sizes == [300, 200]
