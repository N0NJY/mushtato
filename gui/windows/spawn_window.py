"""Spawn window: Potato's "pop a stream into its own pane" feature.

Concrete first example (see CLAUDE.md's Phase 6 notes for the reasoning):
a log-mirror window. It doesn't parse or filter content -- it just
live-mirrors whatever StyledSegments the owning MainWindow feeds it
from the moment it's created onward. Content-aware spawn windows (e.g.
routing only WHO-list output here) need engine/scripting's triggers
wired into the GUI, which is still deferred.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QMainWindow, QTextEdit

from .styled_text_qt import append_styled_segments


class SpawnWindow(QMainWindow):
    closed = Signal()

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        self.scrollback = QTextEdit(self)
        self.scrollback.setReadOnly(True)
        self.scrollback.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setCentralWidget(self.scrollback)

    def receive_segments(self, segments) -> None:
        append_styled_segments(self.scrollback, segments)

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        self.closed.emit()
        super().closeEvent(event)
