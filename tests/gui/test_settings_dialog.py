"""Headless tests for the settings/hotkey dialog itself. Its wiring
into the app (Phase 9: MainWindow.open_settings(), not
AddressBookWindow) is covered in tests/gui/test_host_window.py.
"""

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel

from engine.storage import DEFAULT_HOTKEYS, Settings
from gui.dialogs.settings_dialog import SettingsDialog


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
