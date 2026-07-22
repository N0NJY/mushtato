"""Settings/hotkey/theme configuration dialog (Phase 7, extended in
Phase 7b with theme support and first-run mode).
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QVBoxLayout,
)

from engine.storage import Settings

# Human-readable labels for each configurable action, in display order.
ACTION_LABELS: Dict[str, str] = {
    "add_world": "Add World",
    "connect": "Connect",
    "spawn_log_window": "Spawn Log Window",
    "switch_input_focus": "Switch Input Focus",
    "close_window": "Close Window",
}

# Display label -> stored value, in display order.
THEME_LABELS: Dict[str, str] = {
    "Dark": "dark",
    "Light": "light",
}


class SettingsDialog(QDialog):
    def __init__(
        self, parent=None, *, settings: Settings, first_run: bool = False
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

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
        )
