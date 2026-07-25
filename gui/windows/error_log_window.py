"""Error Log window (Phase 11): displays the unhandled-exception crash
guard's captured records (engine/errorlog.py). Deliberately narrow in
scope per checkpoint -- this is not a mirror of errors this app already
shows per-tab (script/trigger/connection errors stay exactly where they
already are); it only ever shows genuinely unhandled exceptions.

A lazily-constructed singleton satellite, same pattern as
AddressBookWindow/HelpWindow -- refreshed on every open rather than
left stale, since new errors can accumulate between opens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from engine.errorlog import ErrorLog, ErrorRecord


class _ErrorLogSignalBridge(QObject):
    """A record can arrive from any thread (a background connection
    thread's uncaught exception, via threading.excepthook) -- this
    bridge's one job is to be a real QObject whose signal Qt will
    marshal onto the GUI thread regardless of which thread emits it,
    the exact same pattern telnet_bridge.py's own signals already rely
    on for the identical reason.
    """

    newError = Signal(object)


class ErrorLogWindow(QMainWindow):
    def __init__(self, error_log: ErrorLog, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MushTato — Error Log")
        self.resize(700, 500)
        self._error_log = error_log
        self._bridge = _ErrorLogSignalBridge()
        self._bridge.newError.connect(self._on_new_error)
        # Never removed on close -- this window is a reused singleton
        # (MainWindow keeps one instance, just hides/shows it, same
        # pattern as AddressBookWindow/HelpWindow), so the listener
        # needs to stay live across hide/show cycles for as long as the
        # app runs, not just while the window happens to be visible.
        self._error_log.add_listener(self._bridge.newError.emit)

        self.search_field = QLineEdit(self)
        self.search_field.setPlaceholderText("Search...")
        self.search_field.textChanged.connect(self.refresh)

        self.list_widget = QListWidget(self)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)

        self.detail_view = QTextEdit(self)
        self.detail_view.setReadOnly(True)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self.list_widget)
        splitter.addWidget(self.detail_view)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self.export_button = QPushButton("Export...", self)
        self.export_button.clicked.connect(self.export_errors)
        self.clear_button = QPushButton("Clear", self)
        self.clear_button.clicked.connect(self.clear_errors)
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.refresh)

        button_row = QHBoxLayout()
        button_row.addWidget(self.export_button)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.refresh_button)
        button_row.addStretch()

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        search_row.addWidget(self.search_field)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(search_row)
        layout.addWidget(splitter)
        layout.addLayout(button_row)
        self.setCentralWidget(central)

        self.refresh()

    def _matching_records(self):
        term = self.search_field.text().strip().lower()
        records = self._error_log.records
        if not term:
            return records
        return [
            r
            for r in records
            if term in r.message.lower() or term in r.module.lower() or term in r.traceback_text.lower()
        ]

    def refresh(self) -> None:
        """Re-render the list from the ErrorLog's current in-memory
        records. (The source planning doc described this button as
        "reload from file" -- simplified deliberately: the in-memory
        list is already kept live via the listener/signal mechanism, so
        there's no separate on-disk state to re-read that could be more
        current than what's already showing.)
        """
        self.list_widget.clear()
        for record in reversed(self._matching_records()):  # most recent first
            item = QListWidgetItem(
                f"{record.timestamp:%Y-%m-%d %H:%M:%S}  [{record.level}]  {record.module}: {record.message}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.list_widget.addItem(item)
        self.detail_view.clear()

    def _on_selection_changed(self, current: Optional[QListWidgetItem], previous) -> None:
        del previous
        if current is None:
            self.detail_view.clear()
            return
        record: ErrorRecord = current.data(Qt.ItemDataRole.UserRole)
        self.detail_view.setPlainText(record.traceback_text or record.message)

    def _on_new_error(self, record: ErrorRecord) -> None:
        del record
        self.refresh()

    def export_errors(self) -> None:
        """Exports whatever's currently listed (i.e. respects the
        active search filter) as plaintext -- simpler than a
        multi-select mechanism, and the search field already gives a
        way to narrow down what gets exported.
        """
        records = self._matching_records()
        if not records:
            QMessageBox.information(self, "Export Error Log", "No errors to export.")
            return
        default_name = "mushtato_error_log.txt"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export Error Log", default_name, "Text files (*.txt);;All files (*)"
        )
        if not path_str:
            return
        lines = []
        for record in records:
            lines.append(f"[{record.timestamp:%Y-%m-%d %H:%M:%S}] [{record.level}] {record.module}: {record.message}")
            if record.traceback_text:
                lines.append(record.traceback_text)
            lines.append("")
        Path(path_str).write_text("\n".join(lines), encoding="utf-8")
        QMessageBox.information(self, "Export Error Log", f"Exported to {path_str}")

    def clear_errors(self) -> None:
        self._error_log.clear()
        self.refresh()
