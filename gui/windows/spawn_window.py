"""Spawn window: Potato's "pop a stream into its own pane" feature.

Concrete first example (see CLAUDE.md's Phase 6 notes for the reasoning):
a log-mirror window. It doesn't parse or filter content -- it just
live-mirrors whatever StyledSegments the owning MainWindow feeds it
from the moment it's created onward. Content-aware spawn windows (e.g.
routing only WHO-list output here) need engine/scripting's triggers
wired into the GUI, which is still deferred.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from engine.storage import DEFAULT_THEME, logs_dir

from ..theme import apply_scrollback_theme
from .styled_text_qt import append_styled_segments


class SpawnWindow(QMainWindow):
    closed = Signal()

    def __init__(
        self,
        title: str,
        parent=None,
        *,
        theme: Optional[str] = None,
        logs_dir_override: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._theme = theme if theme is not None else DEFAULT_THEME
        # Phase 11: same override pattern as script_store_path elsewhere
        # in this codebase -- defaults to the real per-user logs
        # directory, overridable so tests never touch it (see
        # save_spawnlog's docstring).
        self._logs_dir_override = logs_dir_override

        # QTextBrowser, not plain QTextEdit -- a spawn window mirrors
        # the same StyledSegments the owning tab's scrollback shows, so
        # a URL clicked here must work identically (see session_tab.py's
        # own comment on why QTextBrowser is required for this).
        self.scrollback = QTextBrowser(self)
        self.scrollback.setReadOnly(True)
        self.scrollback.setOpenExternalLinks(True)
        self.scrollback.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        # Same dimmer output-pane colors as MainWindow's scrollback --
        # see gui/theme.py's apply_scrollback_theme (sets the palette
        # on both the widget and its viewport -- a real-desktop bug
        # found the viewport alone staying white otherwise).
        apply_scrollback_theme(self.scrollback, self._theme)

        # Phase 11: Save Spawnlog. A small button row below the
        # scrollback, matching AddressBookWindow's existing
        # button-row-not-toolbar convention rather than introducing a
        # new chrome pattern for one button.
        self.save_button = QPushButton("Save Spawnlog", self)
        self.save_button.clicked.connect(self.save_spawnlog)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.save_button)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scrollback)
        layout.addLayout(button_row)
        self.setCentralWidget(container)

    def receive_segments(self, segments) -> None:
        append_styled_segments(self.scrollback, segments)

    def save_spawnlog(self) -> None:
        """Save this window's full text to disk as UTF-8 plaintext with
        a timestamp header. Default location is engine/storage/paths'
        real logs_dir() (the actual, already-established per-OS data
        directory -- not the ad-hoc ``~/.mushtato/logs/`` path an
        earlier planning doc guessed without checking that module);
        default filename is ``spawnlog_YYYYMMDD_HHMMSS.txt``. The file
        dialog lets the user override either -- these are just the
        starting suggestion, not enforced.
        """
        default_dir = self._logs_dir_override if self._logs_dir_override is not None else logs_dir()
        default_dir.mkdir(parents=True, exist_ok=True)
        default_name = f"spawnlog_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save Spawnlog",
            str(default_dir / default_name),
            "Text files (*.txt);;All files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        header = f"Spawnlog saved: {datetime.now():%Y-%m-%d %H:%M:%S}\n{'=' * 40}\n"
        path.write_text(header + self.scrollback.toPlainText(), encoding="utf-8")
        QMessageBox.information(self, "Spawnlog Saved", f"Spawnlog saved to {path}")

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        super().showEvent(event)
        apply_scrollback_theme(self.scrollback, self._theme)

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        self.closed.emit()
        super().closeEvent(event)
