"""Settings/hotkey configuration dialog (Phase 7)."""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QKeySequenceEdit, QVBoxLayout

from engine.storage import Settings

# Human-readable labels for each configurable action, in display order.
ACTION_LABELS: Dict[str, str] = {
    "add_world": "Add World",
    "connect": "Connect",
    "spawn_log_window": "Spawn Log Window",
    "switch_input_focus": "Switch Input Focus",
    "close_window": "Close Window",
}


class SettingsDialog(QDialog):
    def __init__(self, parent=None, *, settings: Settings) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self._editors: Dict[str, QKeySequenceEdit] = {}
        form = QFormLayout()
        for action, label in ACTION_LABELS.items():
            editor = QKeySequenceEdit(QKeySequence(settings.hotkeys.get(action, "")))
            self._editors[action] = editor
            form.addRow(f"{label}:", editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def result_settings(self) -> Settings:
        """Build a Settings object from the current field values."""
        return Settings(
            hotkeys={
                action: editor.keySequence().toString()
                for action, editor in self._editors.items()
            }
        )
