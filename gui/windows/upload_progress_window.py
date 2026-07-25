"""Progress window for an in-flight Upload (Tools > Upload), modeled
on Potato's real ``uploadProgressWindow``/``uploadCancel`` (potato.tcl
~1289-1360): bytes-sent-of-total with a progress bar, a Hide button
(dismisses the window without stopping the upload) and a Cancel
button (confirmed via a yes/no prompt before actually stopping,
matching Potato's own "Do you really want to cancel..." dialog).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class UploadProgressWindow(QWidget):
    cancel_requested = Signal()

    def __init__(self, file_name: str, total_bytes: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Upload Status - {file_name}")
        self._file_name = file_name

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(max(1, total_bytes))
        self.progress_label = QLabel(f"Progress: 0 of {total_bytes} bytes", self)

        self.hide_button = QPushButton("Hide", self)
        self.hide_button.clicked.connect(self.hide)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self.hide_button)
        button_row.addWidget(self.cancel_button)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addLayout(button_row)

    def set_progress(self, bytes_consumed: int, total_bytes: int) -> None:
        self.progress_bar.setMaximum(max(1, total_bytes))
        self.progress_bar.setValue(min(bytes_consumed, total_bytes))
        self.progress_label.setText(f"Progress: {bytes_consumed} of {total_bytes} bytes")

    def _on_cancel_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "File Upload",
            f'Do you really want to cancel the file upload for "{self._file_name}"?',
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cancel_requested.emit()
