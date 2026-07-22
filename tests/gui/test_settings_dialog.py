"""Headless tests for the settings/hotkey dialog and its wiring into
AddressBookWindow.
"""

from pathlib import Path

from PySide6.QtGui import QKeySequence

from engine.storage import DEFAULT_HOTKEYS, Settings, load_settings
from gui.dialogs.settings_dialog import SettingsDialog
from gui.windows.address_book_window import AddressBookWindow
from tests.gui.test_address_book_window import FakeSessionWindow


def test_dialog_prefills_editors_from_current_settings(qapp):
    settings = Settings(hotkeys={**DEFAULT_HOTKEYS, "spawn_log_window": "Ctrl+Shift+L"})
    dialog = SettingsDialog(settings=settings)

    assert dialog._editors["spawn_log_window"].keySequence() == QKeySequence("Ctrl+Shift+L")
    assert dialog._editors["close_window"].keySequence() == QKeySequence(
        DEFAULT_HOTKEYS["close_window"]
    )


def test_result_settings_reflects_edited_values(qapp):
    dialog = SettingsDialog(settings=Settings())
    dialog._editors["add_world"].setKeySequence(QKeySequence("Ctrl+Shift+N"))

    result = dialog.result_settings()

    assert result.hotkeys["add_world"] == "Ctrl+Shift+N"
    # Untouched fields keep their original (default) value.
    assert result.hotkeys["close_window"] == DEFAULT_HOTKEYS["close_window"]


def test_opening_settings_from_address_book_saves_to_disk(qapp, tmp_path: Path):
    ab_path = tmp_path / "address_book.json"
    settings_path = tmp_path / "settings.json"
    window = AddressBookWindow(
        storage_path=ab_path, settings_storage_path=settings_path, window_factory=FakeSessionWindow
    )

    dialog = SettingsDialog(window, settings=window.settings)
    dialog._editors["spawn_log_window"].setKeySequence(QKeySequence("Ctrl+Shift+L"))
    window.settings = dialog.result_settings()
    from engine.storage import save_settings

    save_settings(window._settings_path, window.settings)

    reloaded = load_settings(settings_path)
    assert reloaded.hotkeys["spawn_log_window"] == "Ctrl+Shift+L"


def test_address_book_loads_existing_settings_on_construction(qapp, tmp_path: Path):
    from engine.storage import save_settings

    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, Settings(hotkeys={**DEFAULT_HOTKEYS, "close_window": "Ctrl+Q"}))

    window = AddressBookWindow(
        storage_path=tmp_path / "address_book.json",
        settings_storage_path=settings_path,
        window_factory=FakeSessionWindow,
    )

    assert window.settings.hotkeys["close_window"] == "Ctrl+Q"


def test_connecting_passes_current_hotkeys_to_the_session_window(qapp, tmp_path: Path):
    from engine.storage import WorldProfile, save_address_book, save_settings

    ab_path = tmp_path / "address_book.json"
    settings_path = tmp_path / "settings.json"
    save_address_book(ab_path, [WorldProfile(name="X", host="h", port=1)])
    save_settings(settings_path, Settings(hotkeys={**DEFAULT_HOTKEYS, "close_window": "Ctrl+Q"}))

    window = AddressBookWindow(
        storage_path=ab_path, settings_storage_path=settings_path, window_factory=FakeSessionWindow
    )
    opened = window.connect_to(window.worlds[0])

    assert opened.hotkeys["close_window"] == "Ctrl+Q"
