"""Headless tests for the address book window: list population, add/
edit/delete round-tripping through storage, and "Connect" asking the
host shell to open (or switch to) a tab -- Phase 7e changed this from
opening its own independent MainWindow to delegating to the persistent
host window that spawned it.
"""

from pathlib import Path

from engine.storage import DEFAULT_HOTKEYS, WorldProfile, load_address_book, save_address_book
from gui.dialogs.world_edit_dialog import WorldEditDialog
from gui.windows.address_book_window import AddressBookWindow


class FakeHostWindow:
    """Stands in for MainWindow -- records open_tab() calls instead of
    actually creating a SessionTab/TelnetBridge.
    """

    def __init__(self, hotkeys=None) -> None:
        self._hotkeys = hotkeys if hotkeys is not None else dict(DEFAULT_HOTKEYS)
        self.open_tab_calls = []
        self.reload_scripts_for_world_calls = []

    def open_tab(self, host, port, *, name=None, bridge=None, world=None, character=None):
        self.open_tab_calls.append((host, port, name, world, character))
        return (host, port, name)

    def tabs_for_world(self, world_name):
        return []  # no live tabs in these tests -- see test_scripting_integration.py for that

    def reload_scripts_for_world(self, world_name) -> None:
        self.reload_scripts_for_world_calls.append(world_name)


def make_address_book(tmp_path: Path, worlds=None, host_window=None) -> AddressBookWindow:
    path = tmp_path / "address_book.json"
    if worlds is not None:
        save_address_book(path, worlds)
    return AddressBookWindow(
        host_window or FakeHostWindow(), storage_path=path, scripts_dir=tmp_path / "scripts"
    )


def test_loads_existing_worlds_into_the_list(qapp, tmp_path: Path):
    worlds = [WorldProfile(name="Estrellita", host="silvren.com", port=4444)]
    window = make_address_book(tmp_path, worlds)

    assert window.list_widget.count() == 1
    assert "Estrellita" in window.list_widget.item(0).text()


def test_add_world_persists_and_refreshes_list(qapp, tmp_path: Path):
    window = make_address_book(tmp_path)

    dialog = WorldEditDialog(window)
    dialog.name_edit.setText("New World")
    dialog.host_edit.setText("example.com")
    dialog.port_spin.setValue(4201)
    profile = dialog.result_profile()
    window.worlds.append(profile)
    window._save()
    window._refresh_list()

    assert window.list_widget.count() == 1
    reloaded = load_address_book(window._path)
    assert reloaded == [WorldProfile(name="New World", host="example.com", port=4201, notes="")]


def test_edit_world_updates_persisted_entry(qapp, tmp_path: Path):
    worlds = [WorldProfile(name="Old", host="old.example.com", port=1)]
    window = make_address_book(tmp_path, worlds)

    window.list_widget.setCurrentRow(0)
    dialog = WorldEditDialog(window, world=window.worlds[0])
    dialog.name_edit.setText("Renamed")
    dialog.port_spin.setValue(2)
    window.worlds[0] = dialog.result_profile()
    window._save()
    window._refresh_list()

    assert load_address_book(window._path) == [
        WorldProfile(name="Renamed", host="old.example.com", port=2, notes="")
    ]


def test_delete_selected_removes_from_list_and_storage(qapp, tmp_path: Path):
    worlds = [
        WorldProfile(name="Keep", host="a.example.com", port=1),
        WorldProfile(name="Remove", host="b.example.com", port=2),
    ]
    window = make_address_book(tmp_path, worlds)

    window.list_widget.setCurrentRow(1)
    window._delete_selected()

    assert window.list_widget.count() == 1
    assert load_address_book(window._path) == [WorldProfile(name="Keep", host="a.example.com", port=1)]


def test_connect_asks_the_host_to_open_a_tab(qapp, tmp_path: Path):
    worlds = [WorldProfile(name="Estrellita", host="silvren.com", port=4444)]
    host = FakeHostWindow()
    window = make_address_book(tmp_path, worlds, host_window=host)

    window.list_widget.setCurrentRow(0)
    window._connect_selected()

    assert host.open_tab_calls == [("silvren.com", 4444, "Estrellita", worlds[0], None)]


def test_connecting_to_two_worlds_asks_the_host_twice(qapp, tmp_path: Path):
    worlds = [
        WorldProfile(name="World A", host="a.example.com", port=1),
        WorldProfile(name="World B", host="b.example.com", port=2),
    ]
    host = FakeHostWindow()
    window = make_address_book(tmp_path, worlds, host_window=host)

    window.connect_to(worlds[0])
    window.connect_to(worlds[1])

    assert host.open_tab_calls == [
        ("a.example.com", 1, "World A", worlds[0], None),
        ("b.example.com", 2, "World B", worlds[1], None),
    ]


def test_open_properties_saves_edited_world(qapp, tmp_path: Path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from gui.dialogs.world_properties_dialog import WorldPropertiesDialog

    worlds = [WorldProfile(name="Original", host="example.com", port=1)]
    window = make_address_book(tmp_path, worlds)
    window.list_widget.setCurrentRow(0)

    def fake_exec(self):
        self.name_edit.setText("Renamed")
        self.autosend_connect_edit.setPlainText("look")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(WorldPropertiesDialog, "exec", fake_exec)
    window._open_properties()

    assert window.worlds[0].name == "Renamed"
    assert window.worlds[0].autosend_connect == "look"
    assert load_address_book(window._path)[0].name == "Renamed"


# -- Regression: selection-dependent buttons must not silently no-op ----


def test_selection_dependent_buttons_start_disabled_even_with_worlds_present(qapp, tmp_path: Path):
    # The real bug: a freshly-opened address book has nothing selected
    # in the list (currentRow() == -1) even when worlds exist, and
    # clicking Properties/Edit/Delete/Connect used to silently do
    # nothing -- no dialog, no error, no feedback at all.
    worlds = [WorldProfile(name="Only World", host="example.com", port=1)]
    window = make_address_book(tmp_path, worlds)

    assert window.list_widget.currentRow() == -1
    assert window.edit_button.isEnabled() is False
    assert window.delete_button.isEnabled() is False
    assert window.connect_button.isEnabled() is False
    assert window.properties_button.isEnabled() is False


def test_selection_dependent_buttons_enable_once_a_row_is_selected(qapp, tmp_path: Path):
    worlds = [WorldProfile(name="Only World", host="example.com", port=1)]
    window = make_address_book(tmp_path, worlds)

    window.list_widget.setCurrentRow(0)

    assert window.edit_button.isEnabled() is True
    assert window.delete_button.isEnabled() is True
    assert window.connect_button.isEnabled() is True
    assert window.properties_button.isEnabled() is True


def test_buttons_disable_again_after_deleting_the_last_world(qapp, tmp_path: Path):
    worlds = [WorldProfile(name="Only World", host="example.com", port=1)]
    window = make_address_book(tmp_path, worlds)
    window.list_widget.setCurrentRow(0)

    window._delete_selected()

    assert window.edit_button.isEnabled() is False
    assert window.properties_button.isEnabled() is False


# -- Character picker + Log In (post-8b addition) ------------------------


def test_selecting_a_world_populates_its_character_list(qapp, tmp_path: Path):
    from engine.storage import CharacterProfile

    worlds = [
        WorldProfile(
            name="Estrellita",
            host="silvren.com",
            port=4444,
            characters=[CharacterProfile(name="Thoran"), CharacterProfile(name="Guest1")],
        )
    ]
    window = make_address_book(tmp_path, worlds)

    window.list_widget.setCurrentRow(0)

    names = [window.character_list.item(i).text() for i in range(window.character_list.count())]
    assert names == ["Thoran", "Guest1"]


def test_character_list_clears_for_a_world_with_no_characters(qapp, tmp_path: Path):
    from engine.storage import CharacterProfile

    worlds = [
        WorldProfile(
            name="Has Chars", host="a.example.com", port=1,
            characters=[CharacterProfile(name="Thoran")],
        ),
        WorldProfile(name="No Chars", host="b.example.com", port=2),
    ]
    window = make_address_book(tmp_path, worlds)

    window.list_widget.setCurrentRow(0)
    assert window.character_list.count() == 1
    window.list_widget.setCurrentRow(1)
    assert window.character_list.count() == 0


def test_login_button_disabled_until_a_character_is_selected(qapp, tmp_path: Path):
    from engine.storage import CharacterProfile

    worlds = [
        WorldProfile(
            name="Estrellita", host="silvren.com", port=4444,
            characters=[CharacterProfile(name="Thoran")],
        )
    ]
    window = make_address_book(tmp_path, worlds)

    assert window.login_button.isEnabled() is False
    window.list_widget.setCurrentRow(0)
    assert window.login_button.isEnabled() is False  # world selected, no character yet
    window.character_list.setCurrentRow(0)
    assert window.login_button.isEnabled() is True


def test_log_in_as_selected_character_calls_open_tab_with_that_character(qapp, tmp_path: Path):
    from engine.storage import CharacterProfile

    thoran = CharacterProfile(name="Thoran", password="hunter2")
    worlds = [
        WorldProfile(
            name="Estrellita", host="silvren.com", port=4444,
            characters=[thoran, CharacterProfile(name="Guest1")],
        )
    ]
    host = FakeHostWindow()
    window = make_address_book(tmp_path, worlds, host_window=host)

    window.list_widget.setCurrentRow(0)
    window.character_list.setCurrentRow(0)
    window._log_in_as_selected_character()

    assert host.open_tab_calls == [("silvren.com", 4444, "Estrellita", worlds[0], thoran)]


def test_log_in_as_public_method_does_not_require_list_selection_state(qapp, tmp_path: Path):
    from engine.storage import CharacterProfile

    world = WorldProfile(name="X", host="h", port=1)
    character = CharacterProfile(name="Alt", password="")
    host = FakeHostWindow()
    window = make_address_book(tmp_path, [world], host_window=host)

    window.log_in_as(world, character)

    assert host.open_tab_calls == [("h", 1, "X", world, character)]


# -- Auto-login checkbox + sorting/reordering (post-Character-picker) ---


def test_world_with_no_default_character_shows_no_checkbox(qapp, tmp_path: Path):
    from PySide6.QtCore import Qt

    worlds = [WorldProfile(name="No Default", host="h", port=1)]
    window = make_address_book(tmp_path, worlds)

    item = window.list_widget.item(0)
    assert not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
    # The row itself must still be usable -- only the checkbox is gated.
    assert item.flags() & Qt.ItemFlag.ItemIsEnabled
    assert item.flags() & Qt.ItemFlag.ItemIsSelectable


def test_world_with_default_character_shows_a_checkbox_reflecting_auto_login(
    qapp, tmp_path: Path
):
    from engine.storage import CharacterProfile
    from PySide6.QtCore import Qt

    worlds = [
        WorldProfile(
            name="Has Default", host="h", port=1,
            characters=[CharacterProfile(name="Thoran")],
            default_character="Thoran",
            auto_login=True,
        )
    ]
    window = make_address_book(tmp_path, worlds)

    item = window.list_widget.item(0)
    assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert item.checkState() == Qt.CheckState.Checked


def test_checking_the_box_persists_auto_login(qapp, tmp_path: Path):
    from engine.storage import CharacterProfile, load_address_book
    from PySide6.QtCore import Qt

    worlds = [
        WorldProfile(
            name="Has Default", host="h", port=1,
            characters=[CharacterProfile(name="Thoran")],
            default_character="Thoran",
        )
    ]
    window = make_address_book(tmp_path, worlds)
    item = window.list_widget.item(0)
    assert item.checkState() == Qt.CheckState.Unchecked

    item.setCheckState(Qt.CheckState.Checked)

    assert window.worlds[0].auto_login is True
    assert load_address_book(window._path)[0].auto_login is True


def test_sort_a_to_z_reorders_and_persists(qapp, tmp_path: Path):
    from engine.storage import load_address_book

    worlds = [
        WorldProfile(name="Charlie", host="a", port=1),
        WorldProfile(name="alpha", host="b", port=2),
        WorldProfile(name="Bravo", host="c", port=3),
    ]
    window = make_address_book(tmp_path, worlds)

    window._sort_alpha()

    assert [w.name for w in window.worlds] == ["alpha", "Bravo", "Charlie"]
    assert [w.name for w in load_address_book(window._path)] == ["alpha", "Bravo", "Charlie"]


def test_sort_z_to_a_reorders_and_persists(qapp, tmp_path: Path):
    worlds = [
        WorldProfile(name="alpha", host="a", port=1),
        WorldProfile(name="Bravo", host="b", port=2),
        WorldProfile(name="Charlie", host="c", port=3),
    ]
    window = make_address_book(tmp_path, worlds)

    window._sort_reverse_alpha()

    assert [w.name for w in window.worlds] == ["Charlie", "Bravo", "alpha"]


def test_dragging_a_world_to_a_new_position_persists_the_new_order(qapp, tmp_path: Path):
    # Simulates the actual operation Qt's InternalMove drag-and-drop
    # performs under the hood -- QAbstractItemModel.moveRow() is the
    # one operation that emits rowsMoved; a plain takeItem/insertItem
    # pair would emit rowsRemoved/rowsInserted instead and wouldn't
    # exercise the same code path a real drag uses.
    from PySide6.QtCore import QModelIndex

    from engine.storage import load_address_book

    worlds = [
        WorldProfile(name="A", host="a", port=1),
        WorldProfile(name="B", host="b", port=2),
        WorldProfile(name="C", host="c", port=3),
    ]
    window = make_address_book(tmp_path, worlds)

    window.list_widget.model().moveRow(QModelIndex(), 2, QModelIndex(), 0)

    assert [w.name for w in window.worlds] == ["C", "A", "B"]
    assert [w.name for w in load_address_book(window._path)] == ["C", "A", "B"]
