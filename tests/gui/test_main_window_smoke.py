"""Smoke test: the main window constructs correctly and wires up its
widgets/signals -- using an injected fake bridge so this stays fully
offline (no real TelnetClient/network involved), per CLAUDE.md's rule
that engine features (and by extension, GUI smoke tests) shouldn't
need a live server.
"""

from PySide6.QtCore import QObject, Signal

from gui.windows.main_window import MainWindow


class FakeBridge(QObject):
    """Same signal shape as TelnetBridge, but start()/send_line()/stop()
    are no-ops -- never touches a real socket or thread.
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

    def start(self) -> None:
        self.started = True

    def send_line(self, text: str) -> None:
        self.sent.append(text)

    def stop(self) -> None:
        self.stopped = True


def test_window_constructs_with_expected_widgets(qapp):
    window = MainWindow("example.com", 4201, bridge=FakeBridge())
    assert "example.com:4201" in window.windowTitle()
    assert window.scrollback.isReadOnly() is True
    assert window.input_line is not None


def test_window_starts_the_bridge_on_construction(qapp):
    bridge = FakeBridge()
    MainWindow("example.com", 4201, bridge=bridge)
    assert bridge.started is True


def test_typing_and_pressing_enter_echoes_locally_and_sends(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)

    window.input_line.setText("look")
    window.input_line.returnPressed.emit()

    assert bridge.sent == ["look"]
    assert "look" in window.scrollback.toPlainText()
    assert window.input_line.text() == ""  # cleared after send


def test_incoming_text_is_rendered_in_scrollback(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)

    bridge.textReceived.emit("You see a dusty road.\r\n")

    assert "You see a dusty road." in window.scrollback.toPlainText()


def test_connection_closed_disables_input(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)

    bridge.connectionClosed.emit()

    assert window.input_line.isEnabled() is False
    assert "Connection closed" in window.scrollback.toPlainText()


def test_connection_failed_disables_input_and_shows_message(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)

    bridge.connectionFailed.emit("Connection refused")

    assert window.input_line.isEnabled() is False
    assert "Connection refused" in window.scrollback.toPlainText()


def test_close_event_stops_the_bridge(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)
    window.close()
    assert bridge.stopped is True
