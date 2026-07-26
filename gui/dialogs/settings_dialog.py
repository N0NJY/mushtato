"""Settings/hotkey/theme configuration dialog (Phase 7, extended in
Phase 7b with theme support and first-run mode; post-8b with terminal/
input font pickers).
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from engine.storage import Settings

from ..fonts import resolve_editor_font, resolve_input_font, resolve_scrollback_font

# Human-readable labels for each configurable action, in display order.
ACTION_LABELS: Dict[str, str] = {
    "add_world": "Add World",
    "connect": "Connect",
    "spawn_log_window": "Spawn Log Window",
    "switch_input_focus": "Switch Input Focus",
    "close_window": "Close Window",
    "open_text_editor": "Open Text Editor",
    "new_tab": "New Tab",
}

# Display label -> stored value, in display order.
THEME_LABELS: Dict[str, str] = {
    "Dark": "dark",
    "Light": "light",
}


def _effective_point_size(font) -> int:
    # A QFont built from a family name alone (no explicit point size)
    # can report pointSize() == -1 if it was actually sized in pixels
    # instead -- falls back to a sane default rather than feeding a
    # negative number into the size spinbox.
    size = font.pointSize()
    return size if size > 0 else 10


def _font_row(combo, size_spin):
    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.addWidget(combo, 1)
    row_layout.addWidget(size_spin)
    return row


class SettingsDialog(QDialog):
    def __init__(
        self, parent=None, *, settings: Settings, first_run: bool = False
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        # Not editable in this dialog -- passed through unchanged in
        # result_settings() so saving Settings never clobbers it. Same
        # reasoning for the Phase 12 editor_* fields below: they're set
        # by the editor windows themselves (toggles, dragging/resizing),
        # not through this dialog.
        self._splitter_sizes = settings.splitter_sizes
        self._editor_line_numbers = settings.editor_line_numbers
        self._editor_word_wrap = settings.editor_word_wrap
        self._editor_window_geometry = settings.editor_window_geometry
        self._editor_last_dir = settings.editor_last_dir
        self._upload_last_dir = settings.upload_last_dir

        layout = QVBoxLayout(self)

        if first_run:
            intro = QLabel(
                "Welcome to MushTato! Review your starting theme and hotkeys below."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

        form = QFormLayout()

        self._theme_combo = QComboBox()
        for label in THEME_LABELS:
            self._theme_combo.addItem(label)
        current_label = next(
            (label for label, value in THEME_LABELS.items() if value == settings.theme),
            "Dark",
        )
        self._theme_combo.setCurrentText(current_label)
        form.addRow("Theme:", self._theme_combo)

        # Two independent font pickers (Rick's explicit choice over one
        # shared font for both) -- the terminal/scrollback pane is
        # filtered to monospaced fonts only, since MUD output (banners,
        # ASCII-art borders, tables) assumes a fixed-width terminal and
        # a proportional font would break that alignment (the exact
        # real bug Phase 5 found and fixed by defaulting to a fixed-
        # width font in the first place); the input boxes have no such
        # constraint, so any installed font is offered.
        scrollback_default = resolve_scrollback_font(
            settings.scrollback_font_family, settings.scrollback_font_size
        )
        self._scrollback_font_combo = QFontComboBox()
        self._scrollback_font_combo.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        self._scrollback_font_combo.setCurrentFont(scrollback_default)
        self._scrollback_font_size_spin = QSpinBox()
        self._scrollback_font_size_spin.setRange(6, 72)
        self._scrollback_font_size_spin.setValue(_effective_point_size(scrollback_default))
        form.addRow("Terminal Font:", _font_row(self._scrollback_font_combo, self._scrollback_font_size_spin))

        input_default = resolve_input_font(settings.input_font_family, settings.input_font_size)
        self._input_font_combo = QFontComboBox()
        self._input_font_combo.setCurrentFont(input_default)
        self._input_font_size_spin = QSpinBox()
        self._input_font_size_spin.setRange(6, 72)
        self._input_font_size_spin.setValue(_effective_point_size(input_default))
        form.addRow("Input Font:", _font_row(self._input_font_combo, self._input_font_size_spin))

        # Phase 12 (Text Editor): a third font category, same pattern as
        # the two above. Not filtered to monospaced-only like Terminal
        # Font -- the editor's own use cases include drafting prose, not
        # just macros/code, so any installed font is offered (matching
        # Input Font's own unrestricted picker).
        editor_default = resolve_editor_font(settings.editor_font_family, settings.editor_font_size)
        self._editor_font_combo = QFontComboBox()
        self._editor_font_combo.setCurrentFont(editor_default)
        self._editor_font_size_spin = QSpinBox()
        self._editor_font_size_spin.setRange(6, 72)
        self._editor_font_size_spin.setValue(_effective_point_size(editor_default))
        form.addRow("Editor Font:", _font_row(self._editor_font_combo, self._editor_font_size_spin))

        self._editors: Dict[str, QKeySequenceEdit] = {}
        for action, label in ACTION_LABELS.items():
            editor = QKeySequenceEdit(QKeySequence(settings.hotkeys.get(action, "")))
            self._editors[action] = editor
            form.addRow(f"{label}:", editor)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_settings(self) -> Settings:
        """Build a Settings object from the current field values."""
        return Settings(
            hotkeys={
                action: editor.keySequence().toString()
                for action, editor in self._editors.items()
            },
            theme=THEME_LABELS[self._theme_combo.currentText()],
            scrollback_font_family=self._scrollback_font_combo.currentFont().family(),
            scrollback_font_size=self._scrollback_font_size_spin.value(),
            input_font_family=self._input_font_combo.currentFont().family(),
            input_font_size=self._input_font_size_spin.value(),
            splitter_sizes=self._splitter_sizes,
            editor_font_family=self._editor_font_combo.currentFont().family(),
            editor_font_size=self._editor_font_size_spin.value(),
            editor_line_numbers=self._editor_line_numbers,
            editor_word_wrap=self._editor_word_wrap,
            editor_window_geometry=self._editor_window_geometry,
            editor_last_dir=self._editor_last_dir,
            upload_last_dir=self._upload_last_dir,
        )
