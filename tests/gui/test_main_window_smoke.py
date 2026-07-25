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


def test_toggle_find_bar_shows_and_hides_it(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    assert tab.find_bar.isHidden() is True

    tab.toggle_find_bar()
    assert tab.find_bar.isHidden() is False

    tab.toggle_find_bar()
    assert tab.find_bar.isHidden() is True


def test_find_bar_can_search_the_tab_s_own_scrollback(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)
    bridge.simulate_incoming("You see a dusty road.\r\n")

    tab.toggle_find_bar()
    tab.find_bar.search_field.setText("dusty")

    assert len(tab.find_bar._matches) == 1


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


def test_line_split_across_two_chunks_is_not_duplicated(qapp):
    # Real, reproduced bug (not hypothetical): a line arriving split
    # across two separate reads -- extremely common over any real
    # network connection -- used to render the finalized line followed
    # by a phantom repeat of its own not-yet-terminated tail, because
    # _insert_finalized_segments unconditionally restored whatever
    # preview was showing before the insert, even when that preview
    # was exactly the pending line that had just been completed.
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.simulate_incoming('You say, "some')
    bridge.simulate_incoming(' words"\r\n')

    text = tab.scrollback.toPlainText()
    assert text.count('You say, "some words"') == 1
    assert not text.rstrip("\n").endswith('You say, "some')


def test_multiple_finalized_lines_plus_trailing_preview_in_one_batch(qapp):
    # A batch with more than one complete line AND a genuine new
    # trailing partial line (e.g. a prompt) must still show that
    # trailing preview once, correctly, at the true end -- the fix for
    # the duplication bug above must not break this case.
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.simulate_incoming("Line1\nLine2\nPartial")

    text = tab.scrollback.toPlainText()
    assert text.endswith("Line1\nLine2\nPartial")
    assert text.count("Partial") == 1


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
