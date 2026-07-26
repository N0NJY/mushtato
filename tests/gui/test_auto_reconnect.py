"""Headless tests for automatic reconnection after a dropped connection
(post-Phase-9 addition): a fixed 30-second repeating timer, started
only when the connection drops for a reason the user didn't choose,
stopped by a successful reconnect or an explicit Disconnect -- ticks
call the exact same reconnect_bridge() the manual Reconnect action
already uses.
"""

from PySide6.QtTest import QTest

from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge


def make_tab(**kwargs):
    bridge = kwargs.pop("bridge", None) or FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge, **kwargs)
    return tab, bridge


def test_connection_closed_by_server_starts_auto_reconnect(qapp):
    tab, bridge = make_tab()

    bridge.connectionClosed.emit()

    assert tab._auto_reconnect_timer.isActive() is True
    assert "automatically try to reconnect" in tab.scrollback.toPlainText()


def test_connection_failed_starts_auto_reconnect(qapp):
    tab, bridge = make_tab()

    bridge.connectionFailed.emit("network unreachable")

    assert tab._auto_reconnect_timer.isActive() is True


# -- SSH authentication failures don't auto-reconnect (post-1.0.1 fix) --
# Real, reproduced behavior: retrying every 30s with the same wrong SSH
# password loops forever, since the same credentials will only ever
# fail again -- unlike a genuine dropped network connection, which
# auto-reconnect exists for.


def test_ssh_authentication_failure_does_not_start_auto_reconnect(qapp):
    tab, bridge = make_tab()

    bridge.connectionFailed.emit(
        "PermissionDenied: Permission denied for user someone on host example.com"
    )

    assert tab._auto_reconnect_timer.isActive() is False
    assert "Not retrying automatically" in tab.scrollback.toPlainText()


def test_non_auth_connection_failure_still_auto_reconnects(qapp):
    # A real network-level failure (not shaped like SshBridge's
    # PermissionDenied message) must still retry as before.
    tab, bridge = make_tab()

    bridge.connectionFailed.emit("OSError: Connection refused")

    assert tab._auto_reconnect_timer.isActive() is True


def test_successful_connect_stops_auto_reconnect(qapp):
    tab, bridge = make_tab()
    bridge.connectionClosed.emit()
    assert tab._auto_reconnect_timer.isActive() is True

    bridge.connected.emit()

    assert tab._auto_reconnect_timer.isActive() is False


def test_disconnect_cancels_pending_auto_reconnect(qapp):
    tab, bridge = make_tab()
    bridge.connectionClosed.emit()
    assert tab._auto_reconnect_timer.isActive() is True

    tab.disconnect_bridge()

    assert tab._auto_reconnect_timer.isActive() is False


def test_shutdown_stops_auto_reconnect(qapp):
    tab, bridge = make_tab()
    bridge.connectionClosed.emit()
    assert tab._auto_reconnect_timer.isActive() is True

    tab.shutdown()

    assert tab._auto_reconnect_timer.isActive() is False


def test_starting_auto_reconnect_twice_does_not_duplicate_the_message(qapp):
    tab, bridge = make_tab()

    bridge.connectionClosed.emit()
    bridge.connectionFailed.emit("still down")  # a retry attempt that itself fails again

    assert tab.scrollback.toPlainText().count("automatically try to reconnect") == 1


def test_auto_reconnect_tick_calls_the_same_reconnect_bridge_as_the_manual_action(qapp):
    # Not a parallel implementation -- proven by observing the exact
    # same side effects reconnect_bridge() has (bridge.stop() then a
    # fresh bridge.start(), "Reconnecting to..." in the scrollback).
    tab, bridge = make_tab()
    bridge.connectionClosed.emit()
    bridge.stopped = False  # reset so we can observe the tick's own effect
    bridge.started = False

    tab._auto_reconnect_tick()

    assert bridge.stopped is True
    assert bridge.started is True
    assert "Reconnecting to example.com:4201" in tab.scrollback.toPlainText()


def test_auto_reconnect_actually_fires_after_the_real_interval_elapses(qapp):
    # The strongest proof: a real, running QTimer -- not just calling
    # the tick handler directly -- fires reconnect_bridge() on its own.
    tab, bridge = make_tab()
    tab.AUTO_RECONNECT_INTERVAL_MS = 20  # instance override -- don't wait 30 real seconds
    tab._auto_reconnect_timer.setInterval(20)

    bridge.connectionClosed.emit()
    bridge.stopped = False
    bridge.started = False

    QTest.qWait(200)

    assert bridge.started is True


def test_world_less_tab_still_supports_auto_reconnect(qapp):
    # No world= at all (a direct-connect tab) -- auto-reconnect must
    # not depend on having a saved WorldProfile.
    tab, bridge = make_tab()
    assert tab.world is None

    bridge.connectionClosed.emit()

    assert tab._auto_reconnect_timer.isActive() is True
