"""One connection's content: scrollback + dual input, spawn windows,
built-in commands (Phase 9: extracted from what used to be MainWindow's
entire content, now that MainWindow is a tabbed shell hosting one or
more of these instead of being one connection itself).

Deliberately not wired to engine/scripting yet -- see CLAUDE.md's
Phase 5/6 notes for why that's an explicit deferral, not an oversight.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QSizePolicy, QSplitter, QTextEdit, QVBoxLayout, QWidget

from engine.ansi import AnsiParser
from engine.commands import CommandTable
from engine.storage import DEFAULT_THEME

from ..theme import apply_scrollback_theme
from ..version import mushtato_version
from .history_line_edit import HistoryLineEdit
from .spawn_window import SpawnWindow
from .styled_text_qt import append_styled_segments
from .telnet_bridge import TelnetBridge


class SessionTab(QWidget):
    """A single connection's scrollback/input/bridge, embeddable as one
    page of MainWindow's QTabWidget. Constructible with
    ``host_window=None`` for standalone headless testing -- commands
    that need the shell (``/connect``, ``/settings``, ``/theme``)
    degrade to a "not available" message in that case, same pattern
    Phase 7c used for MainWindow's optional ``address_book``.
    """

    titleChanged = Signal(str)
    connectionStateChanged = Signal(str)

    def __init__(
        self,
        host: str,
        port: int,
        *,
        name: Optional[str] = None,
        bridge: Optional[TelnetBridge] = None,
        theme: Optional[str] = None,
        host_window=None,  # the MainWindow shell; None only in standalone tests
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.name = name or f"{host}:{port}"
        self.host_window = host_window
        self._theme = theme if theme is not None else DEFAULT_THEME
        self.connected_at: Optional[QDateTime] = None
        self.connection_state = "Connecting"
        self._parser = AnsiParser()
        self.spawn_windows: List[SpawnWindow] = []

        self.scrollback = QTextEdit(self)
        self.scrollback.setReadOnly(True)
        # MUD output (banners, tables, ASCII-art borders, prompts) is
        # authored assuming a fixed-width terminal; the default
        # proportional GUI font breaks that alignment.
        self.scrollback.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        # Dual input (Phase 6): two independent boxes, both sending to
        # this same connection, each with its own recall history.
        # `input_line` (primary) is for ordinary commands -- it's the
        # only one that checks for built-in "/" commands (Phase 7c) or
        # will apply alias expansion once scripting is wired into the
        # GUI (still deferred). `secondary_input` is for longer
        # free-form text (poses/says); it bypasses *both* -- a pose
        # starting with "/" or a word that happens to match an alias
        # must never be silently reinterpreted, same reasoning for both.
        self.input_line = HistoryLineEdit(self)
        self.input_line.setPlaceholderText("Command...")
        self.input_line.returnPressed.connect(self._on_primary_send)
        # A plain QLineEdit's default vertical size policy is Fixed, so
        # it would ignore any extra space the splitter below hands it.
        self.input_line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.secondary_input = HistoryLineEdit(self)
        self.secondary_input.setPlaceholderText("Pose/says...")
        self.secondary_input.returnPressed.connect(self._on_secondary_send)
        self.secondary_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        input_container = QWidget(self)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(self.secondary_input)

        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.addWidget(self.scrollback)
        self.splitter.addWidget(input_container)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        apply_scrollback_theme(self.scrollback, self._theme)

        self._commands = CommandTable()
        self._register_commands()

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

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        # Reapplies the scrollback theme every time this tab becomes
        # visible (e.g. switched to in the QTabWidget) -- see
        # gui/theme.apply_scrollback_theme's docstring for the real
        # viewport-palette bug this guards against.
        super().showEvent(event)
        apply_scrollback_theme(self.scrollback, self._theme)

    def _append_plain(self, text: str) -> None:
        cursor = QTextCursor(self.scrollback.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.scrollback.setTextCursor(cursor)
        self.scrollback.ensureCursorVisible()

    def _set_connection_state(self, state: str) -> None:
        self.connection_state = state
        self.connectionStateChanged.emit(state)

    def _on_connected(self) -> None:
        self._append_plain("Connected.\n")
        self.connected_at = QDateTime.currentDateTime()
        self._set_connection_state("Connected")

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
        self.connected_at = None
        self._set_connection_state("Disconnected")

    def _on_connection_failed(self, message: str) -> None:
        self._append_plain(f"\n[Connection failed: {message}]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self.connected_at = None
        self._set_connection_state("Disconnected")

    def _send_to_bridge(self, text: str, *, apply_aliases: bool) -> None:
        # `apply_aliases` is an intentional no-op for now -- engine/
        # scripting isn't wired into the GUI yet (still deferred, see
        # CLAUDE.md).
        del apply_aliases
        self._append_plain(text + "\n")
        self.bridge.send_line(text)

    def _on_primary_send(self) -> None:
        text = self.input_line.text()
        self.input_line.clear()
        outcome = self._commands.process(text)
        if outcome.action == "send":
            self._send_to_bridge(outcome.text, apply_aliases=True)
        elif outcome.text:
            self._append_plain(outcome.text + "\n")

    def _on_secondary_send(self) -> None:
        # Always bypasses command processing entirely -- a pose
        # starting with "/" must never be silently reinterpreted.
        text = self.secondary_input.text()
        self.secondary_input.clear()
        self._send_to_bridge(text, apply_aliases=False)

    def spawn_log_window(self) -> SpawnWindow:
        """Pop a new window that live-mirrors this connection's
        incoming text from this point forward. Bound to this one tab
        specifically -- to log a different connection, spawn a
        separate log window from that connection's own tab.
        """
        window = SpawnWindow(f"MushTato — {self.name} — Log", parent=None, theme=self._theme)
        window.closed.connect(lambda: self._remove_spawn_window(window))
        self.spawn_windows.append(window)
        window.resize(500, 400)
        window.show()
        return window

    def _remove_spawn_window(self, window: SpawnWindow) -> None:
        if window in self.spawn_windows:
            self.spawn_windows.remove(window)

    def disconnect_bridge(self) -> None:
        self.bridge.stop()
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self.connected_at = None
        self._set_connection_state("Disconnected")
        self._append_plain("\n[Disconnected]\n")

    def reconnect_bridge(self) -> None:
        # Calls stop() then start() on the *same* bridge instance --
        # TelnetBridge.start() spins up a fresh background thread/loop/
        # client each call, so the signal connections made once above
        # never need redoing.
        self.bridge.stop()
        self.input_line.setEnabled(True)
        self.secondary_input.setEnabled(True)
        self._set_connection_state("Connecting")
        self._append_plain(f"\nReconnecting to {self.host}:{self.port} ...\n")
        self.bridge.start()

    def shutdown(self) -> None:
        """Called by the host shell when this tab is being closed --
        stops the bridge and closes any spawn windows this tab owns.
        """
        self.bridge.stop()
        for spawn in list(self.spawn_windows):
            spawn.close()

    # -- built-in commands (Phase 7c, moved from MainWindow in Phase 9) --
    # Every command calls the exact same method its GUI equivalent
    # already calls. /connect, /settings, /theme need the host shell;
    # they degrade to "not available" when host_window is None (only
    # happens in standalone tests, never in the real app).

    def _register_commands(self) -> None:
        self._commands.register("quit", self._cmd_quit, "Close this tab")
        self._commands.register(
            "spawnlog", self._cmd_spawnlog, "Open a log-mirror spawn window"
        )
        self._commands.register(
            "connect", self._cmd_connect, "Connect to a saved world by name: /connect <name>"
        )
        self._commands.register("settings", self._cmd_settings, "Open the settings dialog")
        self._commands.register("version", self._cmd_version, "Show the MushTato version")
        self._commands.register(
            "theme", self._cmd_theme, "Switch theme: /theme <dark|light>"
        )
        self._commands.register("disconnect", self._cmd_disconnect, "Disconnect from the server")
        self._commands.register("reconnect", self._cmd_reconnect, "Reconnect to the server")

    def _cmd_quit(self, args: str) -> Optional[str]:
        del args
        if self.host_window is not None:
            self.host_window.close_tab(self)
        return None

    def _cmd_spawnlog(self, args: str) -> Optional[str]:
        del args
        self.spawn_log_window()
        return "Spawned a log window."

    def _cmd_connect(self, args: str) -> Optional[str]:
        if self.host_window is None:
            return "Not available in this session (no host window)."
        name = args.strip()
        if not name:
            return "Usage: /connect <world-name>"
        return self.host_window.connect_by_name(name)

    def _cmd_settings(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window.open_settings()
        return None

    def _cmd_version(self, args: str) -> Optional[str]:
        del args
        return f"MushTato {mushtato_version()}"

    def _cmd_theme(self, args: str) -> Optional[str]:
        theme = args.strip().lower()
        if theme not in ("dark", "light"):
            return "Usage: /theme <dark|light>"
        if self.host_window is None:
            return "Not available in this session (no host window)."
        return self.host_window.set_theme(theme)

    def _cmd_disconnect(self, args: str) -> Optional[str]:
        del args
        self.disconnect_bridge()
        return None

    def _cmd_reconnect(self, args: str) -> Optional[str]:
        del args
        self.reconnect_bridge()
        return None
