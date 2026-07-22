"""Phase 5 minimal main window: one connection, scrollback + input.

Deliberately not wired to engine/scripting yet -- see CLAUDE.md's
Phase 5 notes for why that's an explicit deferral, not an oversight.
No address book, no multi-window, no dual input -- those are Phase 6.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtWidgets import QLineEdit, QMainWindow, QTextEdit, QVBoxLayout, QWidget

from engine.ansi import AnsiParser

from .styled_text_qt import append_styled_segments
from .telnet_bridge import TelnetBridge


class MainWindow(QMainWindow):
    def __init__(
        self, host: str, port: int, *, bridge: Optional[TelnetBridge] = None
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._parser = AnsiParser()

        self.setWindowTitle(f"MushTato — {host}:{port}")

        self.scrollback = QTextEdit(self)
        self.scrollback.setReadOnly(True)
        # MUD output (banners, tables, ASCII-art borders, prompts) is
        # authored assuming a fixed-width terminal; the default
        # proportional GUI font breaks that alignment.
        self.scrollback.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        self.input_line = QLineEdit(self)
        self.input_line.returnPressed.connect(self._on_send)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.scrollback)
        layout.addWidget(self.input_line)
        self.setCentralWidget(central)

        # Dependency-injectable so tests can supply a fake bridge that
        # never touches the network (see tests/gui) -- the real
        # runtime path just omits this argument.
        self.bridge = bridge if bridge is not None else TelnetBridge(host, port)
        self.bridge.connected.connect(self._on_connected)
        self.bridge.textReceived.connect(self._on_text_received)
        self.bridge.connectionClosed.connect(self._on_connection_closed)
        self.bridge.connectionFailed.connect(self._on_connection_failed)

        self._append_plain(f"Connecting to {host}:{port} ...\n")
        self.bridge.start()

    def _append_plain(self, text: str) -> None:
        cursor = QTextCursor(self.scrollback.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.scrollback.setTextCursor(cursor)
        self.scrollback.ensureCursorVisible()

    def _on_connected(self) -> None:
        self._append_plain("Connected.\n")

    def _on_text_received(self, text: str) -> None:
        segments = self._parser.feed(text)
        if segments:
            append_styled_segments(self.scrollback, segments)

    def _on_connection_closed(self) -> None:
        self._append_plain("\n[Connection closed by server]\n")
        self.input_line.setEnabled(False)

    def _on_connection_failed(self, message: str) -> None:
        self._append_plain(f"\n[Connection failed: {message}]\n")
        self.input_line.setEnabled(False)

    def _on_send(self) -> None:
        text = self.input_line.text()
        self.input_line.clear()
        self._append_plain(text + "\n")
        self.bridge.send_line(text)

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        self.bridge.stop()
        super().closeEvent(event)
