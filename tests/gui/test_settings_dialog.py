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


# -- Terminal/input font pickers (post-8b addition) ----------------------


def test_dialog_prefills_fonts_from_saved_settings(qapp):
    # Uses a font name pulled from the dialog's own populated combo
    # list, rather than a hardcoded name like "Courier New" -- that
    # isn't guaranteed to actually be installed on every OS/CI runner,
    # and Qt silently substitutes the nearest match for a missing font,
    # which would make a hardcoded-name assertion flaky by environment.
    probe = SettingsDialog(settings=Settings())
    scrollback_font_name = probe._scrollback_font_combo.itemText(0)
    input_font_name = probe._input_font_combo.itemText(0)

    dialog = SettingsDialog(
        settings=Settings(
            scrollback_font_family=scrollback_font_name,
            scrollback_font_size=14,
            input_font_family=input_font_name,
            input_font_size=11,
        )
    )

    assert dialog._scrollback_font_combo.currentFont().family() == scrollback_font_name
    assert dialog._scrollback_font_size_spin.value() == 14
    assert dialog._input_font_combo.currentFont().family() == input_font_name
    assert dialog._input_font_size_spin.value() == 11


def test_dialog_prefills_fonts_with_the_real_defaults_when_nothing_saved(qapp):
    from PySide6.QtGui import QFontInfo

    from gui.fonts import default_scrollback_font

    dialog = SettingsDialog(settings=Settings())

    # default_scrollback_font().family() can be a generic fontconfig
    # alias ("monospace") rather than a concrete installed font name --
    # QFontInfo resolves it to the same concrete family the combo box
    # (which only lists real installed fonts) ends up showing.
    expected = QFontInfo(default_scrollback_font()).family()
    assert dialog._scrollback_font_combo.currentFont().family() == expected


def test_result_settings_reflects_edited_fonts(qapp):
    dialog = SettingsDialog(settings=Settings())
    scrollback_font_name = dialog._scrollback_font_combo.itemText(
        dialog._scrollback_font_combo.count() - 1
    )
    input_font_name = dialog._input_font_combo.itemText(dialog._input_font_combo.count() - 1)
    dialog._scrollback_font_combo.setCurrentText(scrollback_font_name)
    dialog._scrollback_font_size_spin.setValue(16)
    dialog._input_font_combo.setCurrentText(input_font_name)
    dialog._input_font_size_spin.setValue(12)

    result = dialog.result_settings()

    assert result.scrollback_font_family == scrollback_font_name
    assert result.scrollback_font_size == 16
    assert result.input_font_family == input_font_name
    assert result.input_font_size == 12


def test_scrollback_font_combo_only_offers_monospaced_fonts(qapp):
    from PySide6.QtWidgets import QFontComboBox

    dialog = SettingsDialog(settings=Settings())

    assert dialog._scrollback_font_combo.fontFilters() == QFontComboBox.FontFilter.MonospacedFonts


def test_result_settings_preserves_splitter_sizes_unchanged(qapp):
    # The dialog has no UI for splitter size -- it must pass whatever
    # it was constructed with straight through, not reset it.
    dialog = SettingsDialog(settings=Settings(splitter_sizes=[300, 150]))

    result = dialog.result_settings()

    assert result.splitter_sizes == [300, 150]
