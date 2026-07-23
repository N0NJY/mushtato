"""Smoke tests for the multi-connection model (Phase 9: multiple tabs
in one host MainWindow, replacing Phase 5/6's multiple independent
top-level windows) -- confirming one tab's state/teardown never
affects another's.
"""

from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def test_multiple_tabs_have_independent_bridges(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    tab_b = host.open_tab("b.example.com", 5000, bridge=bridge_b)

    assert tab_a.bridge is not tab_b.bridge
    assert bridge_a.started and bridge_b.started


def test_sending_in_one_tab_does_not_affect_another(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    host.open_tab("b.example.com", 5000, bridge=bridge_b)

    tab_a.input_line.setText("look")
    tab_a.input_line.returnPressed.emit()

    assert bridge_a.sent == ["look"]
    assert bridge_b.sent == []


def test_incoming_text_in_one_tab_does_not_appear_in_another(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    tab_b = host.open_tab("b.example.com", 5000, bridge=bridge_b)

    bridge_a.textReceived.emit("only for A\r\n")

    assert "only for A" in tab_a.scrollback.toPlainText()
    assert "only for A" not in tab_b.scrollback.toPlainText()


def test_closing_one_tab_does_not_stop_another_tab_s_bridge(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    host.open_tab("b.example.com", 5000, bridge=bridge_b)

    host.close_tab(tab_a)

    assert bridge_a.stopped is True
    assert bridge_b.stopped is False


def test_three_simultaneous_tabs_all_open_independently(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tabs = [
        host.open_tab(f"world{i}.example.com", 4000 + i, bridge=FakeBridge()) for i in range(3)
    ]
    names = {t.name for t in tabs}
    assert len(names) == 3  # each tab's name is genuinely distinct
    assert host.tab_widget.count() == 3

    host.close_tab(tabs[1])
    assert tabs[1].bridge.stopped is True
    assert tabs[0].bridge.stopped is False
    assert tabs[2].bridge.stopped is False
    assert host.tab_widget.count() == 2


def test_closing_the_last_tab_keeps_the_host_window_open(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    host.show()
    tab = host.open_tab("a.example.com", 4000, bridge=FakeBridge())

    host.close_tab(tab)

    assert host.tab_widget.count() == 0
    assert host.isVisible() is True


def test_connecting_to_the_same_host_and_port_twice_switches_to_the_existing_tab(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    tab = host.open_tab("a.example.com", 4000, bridge=FakeBridge())
    host.open_tab("b.example.com", 5000, bridge=FakeBridge())

    same = host.open_tab("a.example.com", 4000, bridge=FakeBridge())

    assert same is tab
    assert host.tab_widget.count() == 2
    assert host.tab_widget.currentWidget() is tab
