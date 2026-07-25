"""Headless tests for MainWindow's tray-icon wiring (Phase 12c):
construction gated on QSystemTrayIcon.isSystemTrayAvailable(), the
Restore/Exit menu actions reusing existing methods, and the broader
"activity while the app itself isn't focused" condition that goes
beyond the plain tab-activity-flash tracking.

QSystemTrayIcon.isSystemTrayAvailable() is monkeypatched to True in
most of these tests -- the real offscreen QPA platform this whole
suite runs under always reports no tray available, so without this
override MainWindow's own tray_icon would just be None and none of
this wiring would ever run.
"""

from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def make_host_with_tray(monkeypatch, tmp_path: Path, **kwargs):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    return MainWindow(address_book_storage_path=tmp_path / "ab.json", **kwargs)


def test_tray_icon_is_none_when_the_platform_has_no_tray(qapp, tmp_path: Path):
    # The real, unmocked case -- this offscreen test environment always
    # reports no tray available.
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    assert host._tray_icon is None


def test_tray_icon_is_constructed_when_the_platform_has_a_tray(qapp, tmp_path: Path, monkeypatch):
    host = make_host_with_tray(monkeypatch, tmp_path)
    assert host._tray_icon is not None


def test_restore_action_restores_the_window(qapp, tmp_path: Path, monkeypatch):
    host = make_host_with_tray(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(host, "showNormal", lambda: calls.append("showNormal"))
    monkeypatch.setattr(host, "raise_", lambda: calls.append("raise_"))
    monkeypatch.setattr(host, "activateWindow", lambda: calls.append("activateWindow"))

    host._tray_icon.restore_action.trigger()

    assert calls == ["showNormal", "raise_", "activateWindow"]


def test_exit_action_closes_the_window(qapp, tmp_path: Path, monkeypatch):
    # Reuses the exact same _exit_application MainWindow's File > Exit
    # already calls -- not a parallel shutdown path.
    host = make_host_with_tray(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(host, "close", lambda: calls.append("close"))

    host._tray_icon.exit_action.trigger()

    assert calls == ["close"]


def test_activity_on_a_background_tab_starts_the_tray_blinking(qapp, tmp_path: Path, monkeypatch):
    host = make_host_with_tray(monkeypatch, tmp_path)
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4001, bridge=bridge_a)
    host.open_tab("b.example.com", 4002, bridge=FakeBridge())  # now active

    bridge_a.simulate_incoming("ping\r\n")

    assert host._tray_activity_pending is True
    assert host._tray_icon._blink_timer.isActive() is True


def test_activity_on_the_active_tab_while_app_focused_does_not_start_blinking(
    qapp, tmp_path: Path, monkeypatch
):
    host = make_host_with_tray(monkeypatch, tmp_path)
    bridge = FakeBridge()
    tab = host.open_tab("a.example.com", 4001, bridge=bridge)
    host.show()
    host.activateWindow()
    QApplication.processEvents()
    assert QApplication.activeWindow() is host

    bridge.simulate_incoming("ping\r\n")

    assert host._tray_activity_pending is False
    assert host._tray_icon._blink_timer.isActive() is False


def test_activity_on_the_active_tab_while_app_unfocused_starts_blinking(
    qapp, tmp_path: Path, monkeypatch
):
    # The broader condition beyond plain tab-activity-flash tracking --
    # Rick's explicit checkpoint choice: even sitting on the one tab
    # that got new text, the tray should still notice if the whole app
    # wasn't focused when it arrived. QApplication.activeWindow() is
    # explicitly forced to None here rather than relying on this
    # window simply never having been shown -- real OS/Qt focus state
    # is global and can otherwise leak in from an *earlier* test in the
    # same run that called show()/activateWindow() on a different
    # window and never explicitly deactivated it.
    host = make_host_with_tray(monkeypatch, tmp_path)
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    bridge = FakeBridge()
    tab = host.open_tab("a.example.com", 4001, bridge=bridge)

    bridge.simulate_incoming("ping\r\n")

    assert host._tray_activity_pending is True
    assert host._tray_icon._blink_timer.isActive() is True
    # The narrower tab-label-flash condition is untouched -- the active
    # tab is still never added to _tabs_with_activity.
    assert tab not in host._tabs_with_activity


def test_switching_tabs_clears_tray_pending(qapp, tmp_path: Path, monkeypatch):
    host = make_host_with_tray(monkeypatch, tmp_path)
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4001, bridge=bridge_a)
    tab_b = host.open_tab("b.example.com", 4002, bridge=FakeBridge())
    bridge_a.simulate_incoming("ping\r\n")
    assert host._tray_activity_pending is True

    host.tab_widget.setCurrentWidget(tab_a)

    assert host._tray_activity_pending is False
    assert host._tray_icon._blink_timer.isActive() is False


def test_regaining_focus_clears_tray_pending_even_on_the_same_tab(
    qapp, tmp_path: Path, monkeypatch
):
    # The setup half forces QApplication.activeWindow() to None to
    # deterministically trigger the "unfocused" pending state (see the
    # previous test's comment on why this can't rely on ambient global
    # state). The second half uses the real show()/activateWindow()
    # flow -- changeEvent's own ActivationChange handling checks
    # self.isActiveWindow(), a different, unaffected check, so the
    # QApplication.activeWindow patch above doesn't need undoing first.
    host = make_host_with_tray(monkeypatch, tmp_path)
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    bridge = FakeBridge()
    host.open_tab("a.example.com", 4001, bridge=bridge)
    bridge.simulate_incoming("ping\r\n")  # app unfocused -- sets pending
    assert host._tray_activity_pending is True

    host.show()
    host.activateWindow()
    QApplication.processEvents()

    assert host._tray_activity_pending is False
    assert host._tray_icon._blink_timer.isActive() is False


def test_no_tray_icon_means_activity_tracking_still_works_without_crashing(qapp, tmp_path: Path):
    # The default, real headless case -- _tray_icon is None throughout.
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json")
    bridge_a = FakeBridge()
    tab_a = host.open_tab("a.example.com", 4001, bridge=bridge_a)
    host.open_tab("b.example.com", 4002, bridge=FakeBridge())

    bridge_a.simulate_incoming("ping\r\n")  # must not raise

    assert host._tray_activity_pending is True  # tracked even with no tray to show it
