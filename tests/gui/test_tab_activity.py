"""Headless tests for tab-activity flashing (post-8b addition): a
background tab (not the currently-selected one) that receives new
incoming text gets its tab-bar text colored and blinked, indefinitely,
until the user actually switches to it -- Rick's explicit choice over
a brief-flash-then-settle alternative.
"""

from PySide6.QtGui import QColor

from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def test_activity_in_the_currently_active_tab_does_not_flash(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge = FakeBridge()
    tab = host.open_tab("a.example.com", 4000, bridge=bridge)
    assert host.tab_widget.currentWidget() is tab

    bridge.simulate_incoming("hello\r\n")

    assert tab not in host._tabs_with_activity
    assert host._activity_timer.isActive() is False


def test_activity_in_a_background_tab_marks_it_and_starts_the_timer(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    tab_b = host.open_tab("b.example.com", 5000, bridge=bridge_b)
    assert host.tab_widget.currentWidget() is tab_b  # b is active, a is backgrounded

    bridge_a.simulate_incoming("someone typed something\r\n")

    assert tab_a in host._tabs_with_activity
    assert host._activity_timer.isActive() is True
    index_a = host.tab_widget.indexOf(tab_a)
    assert host.tab_widget.tabBar().tabTextColor(index_a) == MainWindow.ACTIVITY_COLOR


def test_ticking_the_flash_toggles_the_color(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    host.open_tab("b.example.com", 5000, bridge=FakeBridge())

    bridge_a.simulate_incoming("ping\r\n")
    index_a = host.tab_widget.indexOf(tab_a)
    assert host.tab_widget.tabBar().tabTextColor(index_a) == MainWindow.ACTIVITY_COLOR

    host._tick_activity_flash()
    assert host.tab_widget.tabBar().tabTextColor(index_a) == QColor()

    host._tick_activity_flash()
    assert host.tab_widget.tabBar().tabTextColor(index_a) == MainWindow.ACTIVITY_COLOR


def test_switching_to_a_flashing_tab_clears_it(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    host.open_tab("b.example.com", 5000, bridge=FakeBridge())
    bridge_a.simulate_incoming("ping\r\n")
    assert tab_a in host._tabs_with_activity

    host.tab_widget.setCurrentWidget(tab_a)

    assert tab_a not in host._tabs_with_activity
    index_a = host.tab_widget.indexOf(tab_a)
    assert host.tab_widget.tabBar().tabTextColor(index_a) == QColor()


def test_timer_stops_once_the_last_flashing_tab_is_cleared(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    host.open_tab("b.example.com", 5000, bridge=FakeBridge())
    bridge_a.simulate_incoming("ping\r\n")
    assert host._activity_timer.isActive() is True

    host.tab_widget.setCurrentWidget(tab_a)

    assert host._activity_timer.isActive() is False


def test_activity_keeps_flashing_indefinitely_not_just_a_few_ticks(qapp, tmp_path):
    # Rick's explicit choice: no auto-settle after N blinks -- it only
    # stops when the tab is actually viewed.
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    host.open_tab("b.example.com", 5000, bridge=FakeBridge())
    bridge_a.simulate_incoming("ping\r\n")

    for _ in range(20):
        host._tick_activity_flash()

    assert tab_a in host._tabs_with_activity
    assert host._activity_timer.isActive() is True


def test_multiple_background_tabs_flash_independently_tracked_but_together(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    bridge_b = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    tab_b = host.open_tab("b.example.com", 5000, bridge=bridge_b)
    host.open_tab("c.example.com", 6000, bridge=FakeBridge())  # active tab

    bridge_a.simulate_incoming("ping a\r\n")
    bridge_b.simulate_incoming("ping b\r\n")

    assert tab_a in host._tabs_with_activity
    assert tab_b in host._tabs_with_activity

    # Clearing one leaves the other still flashing.
    host.tab_widget.setCurrentWidget(tab_a)
    assert tab_a not in host._tabs_with_activity
    assert tab_b in host._tabs_with_activity
    assert host._activity_timer.isActive() is True


def test_closing_a_flashing_tab_removes_it_from_tracking(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4000, bridge=bridge_a)
    host.open_tab("b.example.com", 5000, bridge=FakeBridge())
    bridge_a.simulate_incoming("ping\r\n")
    assert tab_a in host._tabs_with_activity

    host.close_tab(tab_a)

    assert tab_a not in host._tabs_with_activity
    assert host._activity_timer.isActive() is False
