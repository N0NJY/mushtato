"""Spawn window: Potato's "pop a stream into its own pane" feature.

Concrete first example (see CLAUDE.md's Phase 6 notes for the reasoning):
a log-mirror window. It doesn't parse or filter content -- it just
live-mirrors whatever StyledSegments the owning MainWindow feeds it
from the moment it's created onward. Content-aware spawn windows (e.g.
routing only WHO-list output here) need engine/scripting's triggers
wired into the GUI, which is still deferred.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QMainWindow, QTextBrowser

from engine.storage import DEFAULT_THEME

from ..theme import apply_scrollback_theme
from .styled_text_qt import append_styled_segments


class SpawnWindow(QMainWindow):
    closed = Signal()

    def __init__(self, title: str, parent=None, *, theme: Optional[str] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._theme = theme if theme is not None else DEFAULT_THEME

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
        self.setCentralWidget(self.scrollback)

    def receive_segments(self, segments) -> None:
        append_styled_segments(self.scrollback, segments)

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        super().showEvent(event)
        apply_scrollback_theme(self.scrollback, self._theme)

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        self.closed.emit()
        super().closeEvent(event)
