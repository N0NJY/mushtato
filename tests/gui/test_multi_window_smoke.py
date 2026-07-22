"""Smoke tests for the multi-window model: independent MainWindow +
bridge pairs, confirming one window's state/teardown never affects
another's -- the model Phase 5's checkpoint discussion committed to
and Phase 6 actually builds (via the address book's "Connect").
"""

from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def test_multiple_windows_have_independent_bridges(qapp):
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    window_a = MainWindow("a.example.com", 4000, bridge=bridge_a)
    window_b = MainWindow("b.example.com", 5000, bridge=bridge_b)

    assert window_a.bridge is not window_b.bridge
    assert bridge_a.started and bridge_b.started


def test_sending_in_one_window_does_not_affect_another(qapp):
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    window_a = MainWindow("a.example.com", 4000, bridge=bridge_a)
    window_b = MainWindow("b.example.com", 5000, bridge=bridge_b)

    window_a.input_line.setText("look")
    window_a.input_line.returnPressed.emit()

    assert bridge_a.sent == ["look"]
    assert bridge_b.sent == []


def test_incoming_text_in_one_window_does_not_appear_in_another(qapp):
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    window_a = MainWindow("a.example.com", 4000, bridge=bridge_a)
    window_b = MainWindow("b.example.com", 5000, bridge=bridge_b)

    bridge_a.textReceived.emit("only for A\r\n")

    assert "only for A" in window_a.scrollback.toPlainText()
    assert "only for A" not in window_b.scrollback.toPlainText()


def test_closing_one_window_does_not_stop_another_window_s_bridge(qapp):
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    window_a = MainWindow("a.example.com", 4000, bridge=bridge_a)
    window_b = MainWindow("b.example.com", 5000, bridge=bridge_b)

    window_a.close()

    assert bridge_a.stopped is True
    assert bridge_b.stopped is False


def test_three_simultaneous_windows_all_construct_independently(qapp):
    windows = [
        MainWindow(f"world{i}.example.com", 4000 + i, bridge=FakeBridge()) for i in range(3)
    ]
    titles = {w.windowTitle() for w in windows}
    assert len(titles) == 3  # each window's title is genuinely distinct

    windows[1].close()
    assert windows[1].bridge.stopped is True
    assert windows[0].bridge.stopped is False
    assert windows[2].bridge.stopped is False
