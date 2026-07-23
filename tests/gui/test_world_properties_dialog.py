"""Headless tests for the World Properties dialog (Phase 8b): the
Characters add/edit/delete flow, connection-specifics placeholders
being genuinely disabled, and round-tripping all fields through
result_profile(). Uses synthetic data only -- never anything from
~/.potato.
"""

from engine.storage import CharacterProfile, WorldProfile
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
        dialog.keepalive_checkbox,
        dialog.term_checkbox,
    ):
        assert widget.isEnabled() is False


def test_functional_connection_fields_are_enabled(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    assert dialog.login_format_edit.isEnabled() is True
    assert dialog.login_delay_spin.isEnabled() is True


def test_category_list_has_five_sections(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    titles = [dialog.category_list.item(i).text() for i in range(dialog.category_list.count())]
    assert titles == ["Basic", "Characters", "Connection", "Auto-Sends", "Notes"]


def test_switching_category_switches_the_visible_page(qapp):
    world = make_world()
    dialog = WorldPropertiesDialog(None, world=world)
    dialog.category_list.setCurrentRow(1)
    assert dialog.pages.currentWidget() is dialog._characters_page
