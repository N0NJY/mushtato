"""Headless tests for the settings/hotkey dialog and its wiring into
AddressBookWindow.
"""

from pathlib import Path

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel

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


def test_dialog_prefills_theme_combo_from_current_settings(qapp):
    dialog = SettingsDialog(settings=Settings(theme="light"))
    assert dialog._theme_combo.currentText() == "Light"

    dialog_dark = SettingsDialog(settings=Settings(theme="dark"))
    assert dialog_dark._theme_combo.currentText() == "Dark"


def test_result_settings_reflects_selected_theme(qapp):
    dialog = SettingsDialog(settings=Settings(theme="dark"))
    dialog._theme_combo.setCurrentText("Light")

    result = dialog.result_settings()

    assert result.theme == "light"


def test_first_run_mode_shows_an_intro_label(qapp):
    first_run_dialog = SettingsDialog(settings=Settings(), first_run=True)
    normal_dialog = SettingsDialog(settings=Settings(), first_run=False)

    def has_welcome_label(dialog):
        return any("Welcome" in label.text() for label in dialog.findChildren(QLabel))

    assert has_welcome_label(first_run_dialog) is True
    assert has_welcome_label(normal_dialog) is False


def test_connecting_passes_current_theme_to_the_session_window(qapp, tmp_path: Path):
    from engine.storage import WorldProfile, save_address_book, save_settings

    ab_path = tmp_path / "address_book.json"
    settings_path = tmp_path / "settings.json"
    save_address_book(ab_path, [WorldProfile(name="X", host="h", port=1)])
    save_settings(settings_path, Settings(theme="light"))

    window = AddressBookWindow(
        storage_path=ab_path, settings_storage_path=settings_path, window_factory=FakeSessionWindow
    )
    opened = window.connect_to(window.worlds[0])

    assert opened.theme == "light"
