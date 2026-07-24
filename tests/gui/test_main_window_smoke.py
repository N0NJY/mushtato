"""Smoke test: a SessionTab constructs correctly and wires up its
widgets/signals -- using an injected fake bridge so this stays fully
offline (no real TelnetClient/network involved), per CLAUDE.md's rule
that engine features (and by extension, GUI smoke tests) shouldn't
need a live server.

FakeBridge lives here because it's imported by many other test files
(Phase 7e renamed MainWindow's old "one connection" role to SessionTab,
but kept this fixture's import path stable rather than force-updating
every importer's path just for a rename).
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette

from gui.theme import DARK_SCROLLBACK_BASE, DARK_SCROLLBACK_TEXT
from gui.windows.session_tab import SessionTab


class FakeBridge(QObject):
    """Same signal shape as TelnetBridge, but start()/send_line()/stop()
    are no-ops -- never touches a real socket or thread.

    Phase 9: also mirrors TelnetBridge's real on_text-then-textReceived
    contract (set_on_text()/simulate_incoming()) and its
    run_in_background() hook, so tests exercise the same wiring
    SessionTab uses against a real bridge. Tests should call
    simulate_incoming() to simulate the server sending text, not emit
    textReceived directly -- that signal alone no longer drives
    anything in SessionTab (see session_tab.py's module docstring);
    only on_text does.
    """

    connected = Signal()
    textReceived = Signal(str)
    connectionClosed = Signal()
    connectionFailed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.sent = []
        self.started = False
        self.stopped = False
        self._on_text = None

    def start(self) -> None:
        self.started = True

    def send_line(self, text: str) -> None:
        self.sent.append(text)

    def stop(self) -> None:
        self.stopped = True

    def set_on_text(self, callback) -> None:
        self._on_text = callback

    def simulate_incoming(self, text: str) -> None:
        if self._on_text is not None:
            self._on_text(text)
        self.textReceived.emit(text)

    def run_in_background(self, func) -> None:
        # No real background thread here -- just run it synchronously,
        # immediately. What matters for a test double is the *effect*
        # (this must never require an event loop or thread to already
        # be pumping), not literally reproducing production's threading.
        func()


def test_tab_constructs_with_expected_widgets(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    assert "example.com:4201" in tab.name
    assert tab.scrollback.isReadOnly() is True
    assert tab.input_line is not None


def test_tab_starts_the_bridge_on_construction(qapp):
    bridge = FakeBridge()
    SessionTab("example.com", 4201, bridge=bridge)
    assert bridge.started is True


def test_typing_and_pressing_enter_echoes_locally_and_sends(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    tab.input_line.setText("look")
    tab.input_line.returnPressed.emit()

    assert bridge.sent == ["look"]
    assert "look" in tab.scrollback.toPlainText()
    assert tab.input_line.text() == ""  # cleared after send


def test_incoming_text_is_rendered_in_scrollback(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.simulate_incoming("You see a dusty road.\r\n")

    assert "You see a dusty road." in tab.scrollback.toPlainText()


def test_connection_closed_disables_input(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.connectionClosed.emit()

    assert tab.input_line.isEnabled() is False
    assert "Connection closed" in tab.scrollback.toPlainText()


def test_connection_failed_disables_input_and_shows_message(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.connectionFailed.emit("Connection refused")

    assert tab.input_line.isEnabled() is False
    assert "Connection refused" in tab.scrollback.toPlainText()


def test_shutdown_stops_the_bridge(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)
    tab.shutdown()
    assert bridge.stopped is True


def test_scrollback_palette_matches_theme_after_construction(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge(), theme="dark")
    palette = tab.scrollback.palette()
    assert palette.color(QPalette.ColorRole.Base) == QColor(DARK_SCROLLBACK_BASE)
    assert palette.color(QPalette.ColorRole.Text) == QColor(DARK_SCROLLBACK_TEXT)
