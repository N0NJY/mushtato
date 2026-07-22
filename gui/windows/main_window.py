"""Session window: one connection, scrollback + dual input, spawn
windows.

Deliberately not wired to engine/scripting yet -- see CLAUDE.md's
Phase 5/6 notes for why that's an explicit deferral, not an oversight.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget

from engine.ansi import AnsiParser
from engine.storage import DEFAULT_HOTKEYS

from .history_line_edit import HistoryLineEdit
from .spawn_window import SpawnWindow
from .styled_text_qt import append_styled_segments
from .telnet_bridge import TelnetBridge


class MainWindow(QMainWindow):
    closed = Signal()

    def __init__(
        self,
        host: str,
        port: int,
        *,
        name: Optional[str] = None,
        bridge: Optional[TelnetBridge] = None,
        hotkeys: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._parser = AnsiParser()
        self.spawn_windows: List[SpawnWindow] = []
        # Defaults to the plain constant, never touching disk on its
        # own -- MainWindow itself does no settings I/O. Callers that
        # want the user's actually-saved hotkeys (gui/app.py's direct-
        # connect path, AddressBookWindow.connect_to) load Settings
        # themselves and pass hotkeys through explicitly. Keeps window
        # construction side-effect-free for tests: nothing here reads
        # ambient state from the real user-data directory.
        self._hotkeys = hotkeys if hotkeys is not None else DEFAULT_HOTKEYS

        self.setWindowTitle(f"MushTato — {name or f'{host}:{port}'}")

        self.scrollback = QTextEdit(self)
        self.scrollback.setReadOnly(True)
        # MUD output (banners, tables, ASCII-art borders, prompts) is
        # authored assuming a fixed-width terminal; the default
        # proportional GUI font breaks that alignment.
        self.scrollback.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        # Dual input (Phase 6): two independent boxes, both sending to
        # this same connection, each with its own recall history.
        # `input_line` (primary) is for ordinary commands -- once
        # scripting is wired into the GUI (a later phase), this is
        # where alias expansion would apply. `secondary_input` is for
        # longer free-form text (poses/says); it's meant to bypass
        # alias expansion once that exists, specifically so a pose
        # starting with a word that happens to match an alias (e.g.
        # "n") is never silently rewritten. Neither actually applies
        # alias expansion yet -- see _send()'s apply_aliases parameter,
        # which is currently a no-op hook, not real behavior.
        self.input_line = HistoryLineEdit(self)
        self.input_line.setPlaceholderText("Command...")
        self.input_line.returnPressed.connect(self._on_primary_send)

        self.secondary_input = HistoryLineEdit(self)
        self.secondary_input.setPlaceholderText("Pose/says...")
        self.secondary_input.returnPressed.connect(self._on_secondary_send)

        self.spawn_log_button = QPushButton("Spawn Log Window", self)
        self.spawn_log_button.clicked.connect(self.spawn_log_window)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.scrollback)
        layout.addWidget(self.input_line)
        layout.addWidget(self.secondary_input)
        layout.addWidget(self.spawn_log_button)
        self.setCentralWidget(central)

        self._apply_hotkeys()

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
            for spawn in self.spawn_windows:
                spawn.receive_segments(segments)

    def _on_connection_closed(self) -> None:
        self._append_plain("\n[Connection closed by server]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)

    def _on_connection_failed(self, message: str) -> None:
        self._append_plain(f"\n[Connection failed: {message}]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)

    def _send(self, box: HistoryLineEdit, *, apply_aliases: bool) -> None:
        # `apply_aliases` is an intentional no-op for now -- engine/
        # scripting isn't wired into the GUI yet (still deferred, see
        # CLAUDE.md). This parameter exists so that wiring only needs
        # to branch here later, not restructure how the two input
        # boxes dispatch sends.
        del apply_aliases
        text = box.text()
        box.clear()
        self._append_plain(text + "\n")
        self.bridge.send_line(text)

    def _on_primary_send(self) -> None:
        self._send(self.input_line, apply_aliases=True)

    def _on_secondary_send(self) -> None:
        self._send(self.secondary_input, apply_aliases=False)

    def _apply_hotkeys(self) -> None:
        QShortcut(
            QKeySequence(self._hotkeys["spawn_log_window"]), self, activated=self.spawn_log_window
        )
        QShortcut(
            QKeySequence(self._hotkeys["switch_input_focus"]),
            self,
            activated=self._switch_input_focus,
        )
        QShortcut(QKeySequence(self._hotkeys["close_window"]), self, activated=self.close)

    def _switch_input_focus(self) -> None:
        if self.input_line.hasFocus():
            self.secondary_input.setFocus()
        else:
            self.input_line.setFocus()

    def spawn_log_window(self) -> SpawnWindow:
        """Pop a new window that live-mirrors this connection's
        incoming text from this point forward (Potato's spawn-window
        feature; log-mirror is the concrete first example -- see
        CLAUDE.md's Phase 6 notes for why).
        """
        window = SpawnWindow(f"{self.windowTitle()} — Log", parent=None)
        window.closed.connect(lambda: self._remove_spawn_window(window))
        self.spawn_windows.append(window)
        window.resize(500, 400)
        window.show()
        return window

    def _remove_spawn_window(self, window: SpawnWindow) -> None:
        if window in self.spawn_windows:
            self.spawn_windows.remove(window)

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        self.closed.emit()
        self.bridge.stop()
        super().closeEvent(event)
