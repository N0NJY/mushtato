"""Session window: one connection, scrollback + dual input, spawn
windows, built-in commands.

Deliberately not wired to engine/scripting yet -- see CLAUDE.md's
Phase 5/6 notes for why that's an explicit deferral, not an oversight.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Dict, List, Optional

from PySide6.QtCore import QDateTime, Qt, Signal, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QFontDatabase,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from engine.ansi import AnsiParser
from engine.commands import CommandTable
from engine.storage import (
    DEFAULT_HOTKEYS,
    DEFAULT_THEME,
    Settings,
    save_settings,
    settings_path,
)

from ..theme import apply_scrollback_theme, apply_theme
from .history_line_edit import HistoryLineEdit
from .spawn_window import SpawnWindow
from .styled_text_qt import append_styled_segments
from .telnet_bridge import TelnetBridge


def mushtato_version() -> str:
    """The single source of truth is pyproject.toml's version field;
    this reads it back via package metadata rather than duplicating it
    as a separate hardcoded string that could drift out of sync.
    """
    try:
        return _pkg_version("mushtato")
    except PackageNotFoundError:
        return "dev"


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
        theme: Optional[str] = None,
        address_book: Optional["AddressBookWindow"] = None,  # noqa: F821
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._parser = AnsiParser()
        self.spawn_windows: List[SpawnWindow] = []
        # Same pattern as hotkeys below: defaults to the plain constant,
        # never touching disk on its own -- MainWindow itself does no
        # settings I/O. Callers that want the user's actually-saved
        # values (gui/app.py's direct-connect path, AddressBookWindow.
        # connect_to) load Settings themselves and pass them through
        # explicitly. Keeps window construction side-effect-free for
        # tests: nothing here reads ambient state from the real
        # user-data directory.
        self._hotkeys = hotkeys if hotkeys is not None else DEFAULT_HOTKEYS
        self._theme = theme if theme is not None else DEFAULT_THEME
        # Only set when this window was opened via AddressBookWindow.
        # connect_to() -- None in direct-connect mode (gui/app.py host
        # port), where there's no address book at all. /connect and
        # /settings check for this and report "not available" rather
        # than erroring, since there's genuinely nothing to call.
        self.address_book = address_book
        self._name = name or f"{host}:{port}"
        self._connected_at: Optional[QDateTime] = None

        self.setWindowTitle(f"MushTato — {self._name}")

        self.scrollback = QTextEdit(self)
        self.scrollback.setReadOnly(True)
        # MUD output (banners, tables, ASCII-art borders, prompts) is
        # authored assuming a fixed-width terminal; the default
        # proportional GUI font breaks that alignment.
        self.scrollback.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        # Output pane gets its own dimmer Base/Text than the rest of the
        # app's palette (matching Potato's own real distinction between
        # its brighter input box and dimmer output pane) -- see
        # gui/theme.py. The actual setPalette() call is deferred to
        # after _build_chrome() below, not done here -- see that call
        # site for why.

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
        # it would ignore any extra space a splitter hands it -- switch
        # to Expanding so dragging the splitter below actually resizes
        # the visible box, not just the invisible layout space around it.
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

        # A vertical splitter between scrollback and the input boxes --
        # Rick asked to be able to resize the command input area, which
        # a fixed QVBoxLayout ratio can't do; dragging the splitter
        # handle reallocates space between the two.
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.addWidget(self.scrollback)
        self.splitter.addWidget(input_container)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 1)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.splitter)
        self.setCentralWidget(central)

        self._apply_hotkeys()

        self._commands = CommandTable()
        self._register_commands()
        self._build_chrome()

        # Applied after _build_chrome(), and via both the widget and
        # its viewport (see apply_scrollback_theme's docstring -- real
        # pixel-sampling on a real desktop found the viewport itself
        # staying white regardless of what was set on the QTextEdit).
        # Also reapplied in showEvent() below as a second guard.
        apply_scrollback_theme(self.scrollback, self._theme)

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
        # Second guard, on top of the __init__-time call: some real
        # desktops' style/theme integration re-applies its own palette
        # to a widget's viewport around show time, so this re-asserts
        # the scrollback's theme every time the window becomes visible,
        # not just once at construction.
        super().showEvent(event)
        apply_scrollback_theme(self.scrollback, self._theme)

    def _append_plain(self, text: str) -> None:
        cursor = QTextCursor(self.scrollback.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.scrollback.setTextCursor(cursor)
        self.scrollback.ensureCursorVisible()

    def _on_connected(self) -> None:
        self._append_plain("Connected.\n")
        self._connected_at = QDateTime.currentDateTime()
        self.status_state_label.setText("Connected")

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
        self._connected_at = None
        self.status_state_label.setText("Disconnected")

    def _on_connection_failed(self, message: str) -> None:
        self._append_plain(f"\n[Connection failed: {message}]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self._connected_at = None
        self.status_state_label.setText("Disconnected")

    def _send_to_bridge(self, text: str, *, apply_aliases: bool) -> None:
        # `apply_aliases` is an intentional no-op for now -- engine/
        # scripting isn't wired into the GUI yet (still deferred, see
        # CLAUDE.md). This parameter exists so that wiring only needs
        # to branch here later, not restructure how the two input
        # boxes dispatch sends.
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
        # Always bypasses command processing entirely -- see the
        # constructor comment above for why.
        text = self.secondary_input.text()
        self.secondary_input.clear()
        self._send_to_bridge(text, apply_aliases=False)

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
        window = SpawnWindow(f"{self.windowTitle()} — Log", parent=None, theme=self._theme)
        window.closed.connect(lambda: self._remove_spawn_window(window))
        self.spawn_windows.append(window)
        window.resize(500, 400)
        window.show()
        return window

    def _remove_spawn_window(self, window: SpawnWindow) -> None:
        if window in self.spawn_windows:
            self.spawn_windows.remove(window)

    def _show_about(self) -> None:
        QMessageBox.information(self, "About MushTato", f"MushTato {mushtato_version()}")

    def _show_help(self) -> None:
        # Reuses the exact same CommandTable.process() path a typed
        # "/help" would take -- not a second copy of the command list.
        outcome = self._commands.process("/help")
        if outcome.text:
            QMessageBox.information(self, "MushTato Help", outcome.text)

    def _show_address_book(self) -> None:
        if self.address_book is None:
            return
        self.address_book.show()
        self.address_book.raise_()
        self.address_book.activateWindow()

    def _disconnect(self) -> None:
        self.bridge.stop()
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self._connected_at = None
        self.status_state_label.setText("Disconnected")
        self._append_plain("\n[Disconnected]\n")

    def _reconnect(self) -> None:
        # Calls stop() then start() on the *same* bridge instance,
        # rather than constructing a new TelnetBridge -- start() spins
        # up a fresh background thread/loop/client each time it's
        # called (see TelnetBridge._thread_main), and this way the
        # signal connections made once in __init__ never need redoing.
        self.bridge.stop()
        self.input_line.setEnabled(True)
        self.secondary_input.setEnabled(True)
        self.status_state_label.setText("Connecting")
        self._append_plain(f"\nReconnecting to {self._host}:{self._port} ...\n")
        self.bridge.start()

    def _set_theme(self, theme: str) -> str:
        hotkeys = (
            self.address_book.settings.hotkeys if self.address_book is not None else self._hotkeys
        )
        settings = Settings(hotkeys=hotkeys, theme=theme)
        save_settings(settings_path(), settings)
        if self.address_book is not None:
            self.address_book.settings = settings
        self._theme = theme
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        return f"Theme set to {theme}."

    def _on_theme_menu_triggered(self, theme: str) -> None:
        self._set_theme(theme)

    def _update_clock(self) -> None:
        now = QDateTime.currentDateTime()
        self.status_time_label.setText(now.toString("dd/MM/yyyy - HH:mm:ss"))
        if self._connected_at is not None:
            elapsed = self._connected_at.secsTo(now)
            hours, remainder = divmod(elapsed, 3600)
            minutes = remainder // 60
            self.status_duration_label.setText(f"Connected For: {hours}h {minutes}m")
        else:
            self.status_duration_label.setText("Not connected")

    def _build_chrome(self) -> None:
        """Menu bar, toolbar, and status bar modeled on Potato's real
        GUI chrome (screenshot reviewed in this phase's checkpoint).

        Every enabled action calls the exact same method its typed "/"
        command, hotkey, or other existing entry point already calls --
        never a parallel implementation, same principle as Phase 7c.
        Potato has a tab bar for multiple worlds in one window; that's
        deliberately NOT replicated here -- MushTato keeps its existing
        one-window-per-connection model (Phase 5), confirmed as the
        right call in this phase's checkpoint discussion. Actions with
        no backing MushTato feature yet (Potato's Editor/Upload/Mail
        Window/Events/Find) are added disabled, as an explicit visual
        placeholder per that same checkpoint -- not silently omitted,
        not secretly wired to anything.
        """
        menu_bar = self.menuBar()
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        def add_action(menu, text, slot=None, *, enabled=True):
            action = QAction(text, self)
            if slot is not None:
                action.triggered.connect(slot)
            action.setEnabled(enabled)
            menu.addAction(action)
            return action

        # Menus are kept as attributes, not just locals -- a bare local
        # QMenu can be garbage-collected out from under its own C++
        # object once this method returns (a known PySide6 wrapper-
        # lifetime quirk), which would break later access via e.g.
        # menuBar().actions()[i].menu().
        # -- File ------------------------------------------------------
        self.file_menu = file_menu = menu_bar.addMenu("&File")
        self.connect_action = add_action(
            file_menu, "Connect...", self._show_address_book, enabled=self.address_book is not None
        )
        self.reconnect_action = add_action(file_menu, "Reconnect", self._reconnect)
        self.disconnect_action = add_action(file_menu, "Disconnect", self._disconnect)
        file_menu.addSeparator()
        self.close_action = add_action(file_menu, "Close", self.close)

        toolbar.addAction(self.reconnect_action)
        toolbar.addAction(self.disconnect_action)
        toolbar.addAction(self.close_action)
        toolbar.addSeparator()
        toolbar.addAction(self.connect_action)

        # -- Edit --------------------------------------------------------
        self.edit_menu = edit_menu = menu_bar.addMenu("&Edit")
        self.copy_action = add_action(edit_menu, "Copy", self.scrollback.copy)
        self.find_action = add_action(edit_menu, "Find...", None, enabled=False)

        # -- View --------------------------------------------------------
        self.view_menu = view_menu = menu_bar.addMenu("&View")
        self.theme_menu = theme_menu = view_menu.addMenu("Theme")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.dark_theme_action = QAction("Dark", self)
        self.dark_theme_action.setCheckable(True)
        self.light_theme_action = QAction("Light", self)
        self.light_theme_action.setCheckable(True)
        for action, theme_name in (
            (self.dark_theme_action, "dark"),
            (self.light_theme_action, "light"),
        ):
            theme_group.addAction(action)
            theme_menu.addAction(action)
            action.triggered.connect(lambda checked=False, t=theme_name: self._on_theme_menu_triggered(t))
        (self.dark_theme_action if self._theme == "dark" else self.light_theme_action).setChecked(True)

        # -- Logging -------------------------------------------------------
        self.logging_menu = logging_menu = menu_bar.addMenu("&Logging")
        self.spawn_log_action = add_action(logging_menu, "Spawn Log Window", self.spawn_log_window)
        toolbar.addSeparator()
        toolbar.addAction(self.spawn_log_action)

        # -- Options ---------------------------------------------------
        self.options_menu = options_menu = menu_bar.addMenu("&Options")
        self.settings_action = add_action(
            options_menu,
            "Settings...",
            lambda: self._cmd_settings(""),
            enabled=self.address_book is not None,
        )
        toolbar.addAction(self.settings_action)

        # -- Tools (placeholders; Potato has these, MushTato doesn't yet) --
        self.tools_menu = tools_menu = menu_bar.addMenu("&Tools")
        self.editor_action = add_action(tools_menu, "Editor", None, enabled=False)
        self.upload_action = add_action(tools_menu, "Upload", None, enabled=False)
        self.mail_window_action = add_action(tools_menu, "Mail Window", None, enabled=False)
        self.events_action = add_action(tools_menu, "Events", None, enabled=False)
        toolbar.addSeparator()
        toolbar.addAction(self.editor_action)
        toolbar.addAction(self.upload_action)
        toolbar.addAction(self.mail_window_action)
        toolbar.addAction(self.find_action)

        # -- Help ------------------------------------------------------
        self.help_menu = help_menu = menu_bar.addMenu("&Help")
        self.help_action = add_action(help_menu, "Help", self._show_help)
        self.about_action = add_action(help_menu, "About", self._show_about)
        toolbar.addSeparator()
        toolbar.addAction(self.help_action)
        toolbar.addAction(self.about_action)

        # -- status bar ----------------------------------------------------
        self.status_name_label = QLabel(self._name)
        self.status_addr_label = QLabel(f"{self._host}:{self._port}")
        self.status_duration_label = QLabel("Not connected")
        self.status_time_label = QLabel()
        self.status_state_label = QLabel("Connecting")
        status_bar = self.statusBar()
        status_bar.addWidget(self.status_name_label)
        status_bar.addWidget(self.status_addr_label)
        status_bar.addPermanentWidget(self.status_state_label)
        status_bar.addPermanentWidget(self.status_duration_label)
        status_bar.addPermanentWidget(self.status_time_label)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    # -- built-in commands (Phase 7c) --------------------------------
    # Every command below calls the exact same method its GUI
    # equivalent (button/hotkey/menu) already calls -- never a
    # parallel reimplementation. /connect and /settings are the two
    # that need self.address_book; both degrade to a clear "not
    # available" message rather than erroring when it's None
    # (direct-connect mode has no address book to reach).

    def _register_commands(self) -> None:
        self._commands.register("quit", self._cmd_quit, "Close this window")
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
        self.close()
        return None

    def _cmd_spawnlog(self, args: str) -> Optional[str]:
        del args
        self.spawn_log_window()
        return "Spawned a log window."

    def _cmd_connect(self, args: str) -> Optional[str]:
        if self.address_book is None:
            return "Not available in this session (no address book)."
        name = args.strip()
        if not name:
            return "Usage: /connect <world-name>"
        world = next(
            (w for w in self.address_book.worlds if w.name.lower() == name.lower()), None
        )
        if world is None:
            return f"No saved world named {name!r}."
        self.address_book.connect_to(world)
        return f"Connecting to {name}..."

    def _cmd_settings(self, args: str) -> Optional[str]:
        del args
        if self.address_book is None:
            return "Not available in this session (no address book)."
        self.address_book._open_settings()
        return None

    def _cmd_version(self, args: str) -> Optional[str]:
        del args
        return f"MushTato {mushtato_version()}"

    def _cmd_theme(self, args: str) -> Optional[str]:
        theme = args.strip().lower()
        if theme not in ("dark", "light"):
            return "Usage: /theme <dark|light>"
        return self._set_theme(theme)

    def _cmd_disconnect(self, args: str) -> Optional[str]:
        del args
        self._disconnect()
        return None

    def _cmd_reconnect(self, args: str) -> Optional[str]:
        del args
        self._reconnect()
        return None

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        self.closed.emit()
        self.bridge.stop()
        super().closeEvent(event)
