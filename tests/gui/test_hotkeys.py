"""Headless tests that hotkeys actually fire via real Qt key-event
dispatch (not just calling the underlying method directly) -- proving
the QShortcut wiring itself works, not just that the action it triggers
works.

Phase 9: hotkeys are host-level (MainWindow), acting on whichever tab
is currently active, rather than per-connection-window as before.

Under the offscreen test platform, a shortcut only dispatches once its
window is registered as the *active* window -- ``activateWindow()``
must be called explicitly (a real window manager would do this on
show()/click(), which offscreen doesn't emulate).
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gui.windows.address_book_window import AddressBookWindow
from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def _fire(window, key, modifier=Qt.KeyboardModifier.ControlModifier):
    window.activateWindow()
    QApplication.processEvents()  # activation takes effect asynchronously
    QTest.keyClick(window, key, modifier)
    QApplication.processEvents()


def test_close_window_hotkey_closes_the_active_tab(qapp, tmp_path: Path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    host.open_tab("example.com", 4201, bridge=FakeBridge())
    host.show()

    assert host.tab_widget.count() == 1
    _fire(host, Qt.Key.Key_W)
    assert host.tab_widget.count() == 0
    assert host.isVisible() is True  # closing the tab, not the host window


def test_spawn_log_window_hotkey_creates_a_spawn_window_for_the_active_tab(qapp, tmp_path: Path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    host.show()

    assert tab.spawn_windows == []
    _fire(host, Qt.Key.Key_L)
    assert len(tab.spawn_windows) == 1


def test_switch_input_focus_hotkey_moves_focus_between_boxes(qapp, tmp_path: Path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    host.show()
    tab.input_line.setFocus()
    host.activateWindow()
    QApplication.processEvents()
    assert tab.input_line.hasFocus() is True

    _fire(host, Qt.Key.Key_Tab)
    assert tab.secondary_input.hasFocus() is True

    _fire(host, Qt.Key.Key_Tab)
    assert tab.input_line.hasFocus() is True


def test_custom_hotkey_binding_is_honored_not_just_the_default(qapp, tmp_path: Path):
    """Confirms the shortcut actually reads from the injected hotkeys
    dict rather than being hardcoded to the default binding.
    """
    custom_hotkeys = {
        "spawn_log_window": "Ctrl+Shift+G",
        "switch_input_focus": "Ctrl+Tab",
        "close_window": "Ctrl+W",
        "add_world": "Ctrl+N",
        "connect": "Ctrl+Return",
    }
    host = MainWindow(hotkeys=custom_hotkeys, address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("example.com", 4201, bridge=FakeBridge())
    host.show()

    # The old default (Ctrl+L) must no longer do anything.
    _fire(host, Qt.Key.Key_L)
    assert tab.spawn_windows == []

    # The newly-configured binding must work.
    host.activateWindow()
    QApplication.processEvents()
    QTest.keyClick(
        host,
        Qt.Key.Key_G,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert len(tab.spawn_windows) == 1


def test_address_book_add_world_hotkey_opens_the_dialog(qapp, tmp_path, monkeypatch):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    window = AddressBookWindow(host, storage_path=tmp_path / "ab.json")
    window.show()

    calls = []
    monkeypatch.setattr(window, "_add_world", lambda: calls.append("add_world"))
    _fire(window, Qt.Key.Key_N)

    assert calls == ["add_world"]


def test_address_book_close_window_hotkey_closes_it(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    window = AddressBookWindow(host, storage_path=tmp_path / "ab.json")
    window.show()
    _fire(window, Qt.Key.Key_W)
    assert window.isVisible() is False
