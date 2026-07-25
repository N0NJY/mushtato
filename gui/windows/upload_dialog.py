"""File-selection + options dialog for the Upload feature (Tools >
Upload / /upload), modeled on Potato's real ``uploadWindowStart``/
``uploadWindowInvoke`` (potato.tcl ~1071-1195, verified against the
real source): Ignore Empty Lines / Add to History / MPP Formatted
checkboxes, a Delay (seconds) spinbox, a Prefix field, and a disabled
file-path display + "..." browse button.

Validation on accept (file selected, exists, is a file, readable)
matches Potato's own ``uploadWindowInvoke`` checks. The one check
Potato makes that this dialog deliberately does *not* -- "is the
connection actually connected" -- is the caller's (SessionTab's)
concern, not something a file-picker dialog should need to know about
a bridge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.upload_format import UploadOptions


class UploadDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, *, initial_dir: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("File Upload")
        self._initial_dir = initial_dir
        self._selected_file: str = ""

        self.ignore_empty_checkbox = QCheckBox("Ignore empty lines?", self)
        self.ignore_empty_checkbox.setChecked(True)  # Potato's own real default
        self.history_checkbox = QCheckBox("Add to History?", self)
        self.mpp_checkbox = QCheckBox("MPP Formatted?", self)

        self.delay_spin = QDoubleSpinBox(self)
        self.delay_spin.setRange(0.0, 60.0)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setDecimals(1)
        self.delay_spin.setValue(0.0)
        self.delay_spin.setSuffix(" s")

        self.prefix_edit = QLineEdit(self)

        options_layout = QFormLayout()
        options_layout.addRow(self.ignore_empty_checkbox)
        options_layout.addRow(self.history_checkbox)
        options_layout.addRow(self.mpp_checkbox)
        options_layout.addRow("Delay (seconds):", self.delay_spin)
        options_layout.addRow("Prefix:", self.prefix_edit)
        options_group = QGroupBox("Options", self)
        options_group.setLayout(options_layout)

        self.file_display = QLineEdit(self)
        self.file_display.setReadOnly(True)
        self.file_display.setPlaceholderText("No file selected")
        self.browse_button = QPushButton("...", self)
        self.browse_button.clicked.connect(self._browse)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_display)
        file_row.addWidget(self.browse_button)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Upload")
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(options_group)
        layout.addLayout(file_row)
        layout.addWidget(self.button_box)

    def _browse(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select File to Upload", self._initial_dir or "", "All files (*)"
        )
        if filepath:
            self._selected_file = filepath
            self.file_display.setText(filepath)

    def _on_accept(self) -> None:
        if not self._selected_file:
            QMessageBox.critical(self, "File Upload", "You must select a file.")
            return
        path = Path(self._selected_file)
        if not path.exists() or not path.is_file():
            QMessageBox.critical(self, "File Upload", f'Unable to read file "{path}".')
            return
        try:
            path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.critical(self, "File Upload", f'Unable to open file "{path}": {exc}')
            return
        self.accept()

    def selected_file(self) -> str:
        return self._selected_file

    def selected_directory(self) -> str:
        return str(Path(self._selected_file).parent) if self._selected_file else self._initial_dir

    def options(self) -> UploadOptions:
        return UploadOptions(
            ignore_empty=self.ignore_empty_checkbox.isChecked(),
            mpp_formatted=self.mpp_checkbox.isChecked(),
            prefix=self.prefix_edit.text(),
            delay_seconds=self.delay_spin.value(),
            add_to_history=self.history_checkbox.isChecked(),
        )
