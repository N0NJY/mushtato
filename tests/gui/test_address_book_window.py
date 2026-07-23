"""Headless tests for the address book window: list population, add/
edit/delete round-tripping through storage, and "Connect" opening an
independent session window per world.

Uses an injected fake window factory (mirroring how MainWindow itself
accepts an injectable ``bridge``) so these never open a real
TelnetBridge/network connection.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from engine.storage import WorldProfile, load_address_book, save_address_book
from gui.dialogs.world_edit_dialog import WorldEditDialog
from gui.windows.address_book_window import AddressBookWindow


class FakeSessionWindow(QObject):
    """Stands in for MainWindow: same closed signal/resize/show shape,
    never opens a real connection.
    """

    closed = Signal()

    def __init__(
        self,
        host: str,
        port: int,
        *,
        name=None,
        bridge=None,
        hotkeys=None,
        theme=None,
        address_book=None,
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.name = name
        self.hotkeys = hotkeys
        self.theme = theme
        self.address_book = address_book
        self.shown = False

    def resize(self, *args) -> None:
        pass

    def show(self) -> None:
        self.shown = True


def make_address_book(tmp_path: Path, worlds=None) -> AddressBookWindow:
    path = tmp_path / "address_book.json"
    if worlds is not None:
        save_address_book(path, worlds)
    return AddressBookWindow(storage_path=path, window_factory=FakeSessionWindow)


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


def test_connect_opens_an_independent_session_window(qapp, tmp_path: Path):
    worlds = [WorldProfile(name="Estrellita", host="silvren.com", port=4444)]
    window = make_address_book(tmp_path, worlds)

    window.list_widget.setCurrentRow(0)
    window._connect_selected()

    assert len(window.open_windows) == 1
    opened = window.open_windows[0]
    assert opened.host == "silvren.com"
    assert opened.port == 4444
    assert opened.shown is True


def test_connecting_to_two_worlds_opens_two_independent_windows(qapp, tmp_path: Path):
    worlds = [
        WorldProfile(name="World A", host="a.example.com", port=1),
        WorldProfile(name="World B", host="b.example.com", port=2),
    ]
    window = make_address_book(tmp_path, worlds)

    window.connect_to(worlds[0])
    window.connect_to(worlds[1])

    assert len(window.open_windows) == 2
    assert window.open_windows[0].host != window.open_windows[1].host


def test_closing_a_session_window_removes_it_from_open_windows(qapp, tmp_path: Path):
    worlds = [WorldProfile(name="Estrellita", host="silvren.com", port=4444)]
    window = make_address_book(tmp_path, worlds)

    opened = window.connect_to(worlds[0])
    assert opened in window.open_windows

    opened.closed.emit()

    assert opened not in window.open_windows
