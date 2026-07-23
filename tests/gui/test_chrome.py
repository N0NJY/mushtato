"""Headless tests for the menu bar / toolbar / status bar chrome added
on top of MainWindow and AddressBookWindow, modeled on Potato's real
GUI (screenshot reviewed in this phase's checkpoint).

Every enabled action is expected to call the exact same handler its
typed "/" command, hotkey, or existing button already calls -- these
tests exist to catch a parallel-implementation regression, not just
"the menu exists."
"""

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from engine.storage import WorldProfile, save_address_book
from gui.windows.address_book_window import AddressBookWindow
from gui.windows.main_window import MainWindow, mushtato_version
from tests.gui.test_address_book_window import FakeSessionWindow
from tests.gui.test_main_window_smoke import FakeBridge


def make_window(**kwargs):
    return MainWindow("example.com", 4201, bridge=FakeBridge(), **kwargs)


def test_menu_bar_has_expected_top_level_menus(qapp):
    window = make_window()
    titles = [action.text().replace("&", "") for action in window.menuBar().actions()]
    assert titles == ["File", "Edit", "View", "Logging", "Options", "Tools", "Help"]


def test_connect_action_disabled_without_address_book(qapp):
    window = make_window()
    assert window.connect_action.isEnabled() is False


def test_connect_action_enabled_with_address_book(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)
    window = make_window(address_book=address_book)
    assert window.connect_action.isEnabled() is True


def test_connect_action_calls_show_address_book(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)
    window = make_window(address_book=address_book)

    window.connect_action.trigger()

    assert address_book.isVisible() is True


def test_settings_action_disabled_without_address_book(qapp):
    window = make_window()
    assert window.settings_action.isEnabled() is False


def test_settings_action_calls_same_method_as_settings_command(qapp, tmp_path: Path, monkeypatch):
    ab_path = tmp_path / "address_book.json"
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)
    calls = []
    monkeypatch.setattr(address_book, "_open_settings", lambda: calls.append("opened"))

    window = make_window(address_book=address_book)
    window.settings_action.trigger()

    assert calls == ["opened"]


def test_spawnlog_toolbar_action_calls_same_method_as_the_command(qapp):
    window = make_window()
    assert window.spawn_windows == []
    window.spawn_log_action.trigger()
    assert len(window.spawn_windows) == 1


def test_close_action_closes_the_window(qapp):
    window = make_window()
    window.show()
    window.close_action.trigger()
    assert window.isVisible() is False


def test_disconnect_action_stops_bridge_and_disables_input(qapp):
    window = make_window()
    window.disconnect_action.trigger()
    assert window.bridge.stopped is True
    assert window.input_line.isEnabled() is False
    assert window.secondary_input.isEnabled() is False


def test_disconnect_command_calls_the_same_method_as_the_action(qapp):
    window = make_window()
    window.input_line.setText("/disconnect")
    window.input_line.returnPressed.emit()
    assert window.bridge.stopped is True
    assert window.input_line.isEnabled() is False


def test_reconnect_action_restarts_the_bridge(qapp):
    window = make_window()
    window.disconnect_action.trigger()
    window.reconnect_action.trigger()
    assert window.bridge.started is True
    assert window.input_line.isEnabled() is True
    assert window.secondary_input.isEnabled() is True


def test_reconnect_command_calls_the_same_method_as_the_action(qapp):
    window = make_window()
    window.input_line.setText("/reconnect")
    window.input_line.returnPressed.emit()
    assert window.bridge.started is True


def test_help_registered_in_help_menu(qapp):
    window = make_window()
    assert "/quit" in window._commands.process("/help").text  # sanity: command exists
    assert window.help_action is not None


def test_help_action_shows_the_same_text_as_the_help_command(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda parent, title, text: shown.append(text))
    )
    window = make_window()
    window.help_action.trigger()
    assert shown == [window._commands.process("/help").text]


def test_about_action_shows_the_version(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda parent, title, text: shown.append(text))
    )
    window = make_window()
    window.about_action.trigger()
    assert mushtato_version() in shown[0]


def test_copy_action_copies_selected_scrollback_text(qapp):
    window = make_window()
    window.scrollback.selectAll()
    window.copy_action.trigger()
    clipboard_text = qapp.clipboard().text()
    assert "Connecting to example.com:4201" in clipboard_text


def test_placeholder_actions_are_disabled(qapp):
    window = make_window()
    for action in (
        window.find_action,
        window.editor_action,
        window.upload_action,
        window.mail_window_action,
        window.events_action,
    ):
        assert action.isEnabled() is False


def test_theme_menu_reflects_current_theme_and_switching_applies_it(qapp, tmp_path: Path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    window = make_window(theme="dark")
    assert window.dark_theme_action.isChecked() is True
    assert window.light_theme_action.isChecked() is False

    window.light_theme_action.trigger()

    assert window._theme == "light"
    from engine.storage import load_settings

    assert load_settings(settings_file).theme == "light"


def test_status_bar_shows_host_and_updates_on_connect(qapp):
    window = make_window()
    assert "example.com:4201" in window.status_addr_label.text()
    assert window.status_state_label.text() == "Connecting"

    window.bridge.connected.emit()

    assert window.status_state_label.text() == "Connected"


def test_status_bar_shows_disconnected_after_connection_closed(qapp):
    window = make_window()
    window.bridge.connected.emit()
    window.bridge.connectionClosed.emit()
    assert window.status_state_label.text() == "Disconnected"


def test_address_book_menu_bar_has_file_and_help(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)
    titles = [action.text().replace("&", "") for action in address_book.menuBar().actions()]
    assert titles == ["File", "Help"]


def test_address_book_menu_connect_calls_same_method_as_button(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    save_address_book(ab_path, [WorldProfile(name="Estrellita", host="silvren.com", port=4444)])
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)
    address_book.list_widget.setCurrentRow(0)

    address_book.connect_menu_action.trigger()

    assert len(address_book.open_windows) == 1


def test_address_book_about_shows_version(qapp, tmp_path: Path, monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda parent, title, text: shown.append(text))
    )
    ab_path = tmp_path / "address_book.json"
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)

    address_book.about_menu_action.trigger()

    assert mushtato_version() in shown[0]
