"""Headless tests for Phase 7c's built-in command wiring: the primary
input processes "/" commands, the secondary always bypasses them, and
each command calls the exact same handler its GUI equivalent uses.
"""

from pathlib import Path

from engine.storage import WorldProfile, load_settings, save_address_book
from gui.windows.address_book_window import AddressBookWindow
from gui.windows.main_window import MainWindow, mushtato_version
from tests.gui.test_address_book_window import FakeSessionWindow
from tests.gui.test_main_window_smoke import FakeBridge


def make_window(**kwargs):
    return MainWindow("example.com", 4201, bridge=FakeBridge(), **kwargs)


def test_plain_text_still_sends_normally(qapp):
    window = make_window()
    window.input_line.setText("look")
    window.input_line.returnPressed.emit()
    assert window.bridge.sent == ["look"]


def test_double_slash_escape_sends_literal_slash_text(qapp):
    window = make_window()
    window.input_line.setText("//pose waves")
    window.input_line.returnPressed.emit()
    assert window.bridge.sent == ["/pose waves"]


def test_unrecognized_command_shows_error_and_does_not_send(qapp):
    window = make_window()
    window.input_line.setText("/nonsense")
    window.input_line.returnPressed.emit()
    assert window.bridge.sent == []
    assert "No such command" in window.scrollback.toPlainText()


def test_secondary_input_never_processes_commands(qapp):
    """The core dual-input principle: a pose starting with "/" must
    never be reinterpreted as a client command.
    """
    window = make_window()
    window.show()
    window.secondary_input.setText("/quit")
    window.secondary_input.returnPressed.emit()

    assert window.bridge.sent == ["/quit"]  # sent to the MUD literally, not executed
    assert window.isVisible() is True  # window did NOT close itself


def test_quit_command_calls_the_same_close_method_as_the_hotkey(qapp):
    window = make_window()
    window.show()
    window.input_line.setText("/quit")
    window.input_line.returnPressed.emit()
    assert window.isVisible() is False


def test_spawnlog_command_calls_the_same_method_as_the_button(qapp):
    window = make_window()
    assert window.spawn_windows == []
    window.input_line.setText("/spawnlog")
    window.input_line.returnPressed.emit()
    assert len(window.spawn_windows) == 1


def test_version_command_matches_the_about_button_s_string(qapp):
    window = make_window()
    window.input_line.setText("/version")
    window.input_line.returnPressed.emit()
    assert mushtato_version() in window.scrollback.toPlainText()


def test_help_lists_all_registered_built_in_commands(qapp):
    window = make_window()
    window.input_line.setText("/help")
    window.input_line.returnPressed.emit()
    text = window.scrollback.toPlainText()
    for name in ("/quit", "/spawnlog", "/connect", "/settings", "/version", "/theme"):
        assert name in text


def test_connect_and_settings_report_unavailable_without_an_address_book(qapp):
    window = make_window()  # no address_book passed -> direct-connect-like

    window.input_line.setText("/connect somewhere")
    window.input_line.returnPressed.emit()
    assert "not available" in window.scrollback.toPlainText().lower()

    window.input_line.setText("/settings")
    window.input_line.returnPressed.emit()
    assert window.scrollback.toPlainText().lower().count("not available") == 2


def test_connect_command_calls_the_same_connect_to_as_the_address_book_button(
    qapp, tmp_path: Path
):
    ab_path = tmp_path / "address_book.json"
    save_address_book(ab_path, [WorldProfile(name="Estrellita", host="silvren.com", port=4444)])
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)

    window = make_window(address_book=address_book)
    window.input_line.setText("/connect Estrellita")
    window.input_line.returnPressed.emit()

    assert len(address_book.open_windows) == 1
    assert address_book.open_windows[0].host == "silvren.com"


def test_connect_command_with_unknown_world_name_reports_it(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    save_address_book(ab_path, [WorldProfile(name="Estrellita", host="silvren.com", port=4444)])
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)

    window = make_window(address_book=address_book)
    window.input_line.setText("/connect NoSuchWorld")
    window.input_line.returnPressed.emit()

    assert address_book.open_windows == []
    assert "No saved world" in window.scrollback.toPlainText()


def test_settings_command_opens_the_same_dialog_path(qapp, tmp_path: Path, monkeypatch):
    ab_path = tmp_path / "address_book.json"
    address_book = AddressBookWindow(storage_path=ab_path, window_factory=FakeSessionWindow)

    calls = []
    monkeypatch.setattr(address_book, "_open_settings", lambda: calls.append("opened"))

    window = make_window(address_book=address_book)
    window.input_line.setText("/settings")
    window.input_line.returnPressed.emit()

    assert calls == ["opened"]


def test_theme_command_persists_and_applies_the_new_theme(qapp, tmp_path: Path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("gui.windows.main_window.settings_path", lambda: settings_file)

    window = make_window(theme="dark")
    window.input_line.setText("/theme light")
    window.input_line.returnPressed.emit()

    assert load_settings(settings_file).theme == "light"
    assert "light" in window.scrollback.toPlainText()


def test_theme_command_rejects_an_invalid_value(qapp):
    window = make_window()
    window.input_line.setText("/theme neon")
    window.input_line.returnPressed.emit()
    assert "Usage" in window.scrollback.toPlainText()
