"""Headless tests for the system tray icon (Phase 12c) -- modeled on
Potato's real ::potato::flashSystrayIcon (a two-icon-position blink
every 750ms, verified against the actual winico source), not a
multi-frame animation.
"""

from PySide6.QtWidgets import QSystemTrayIcon

from gui.tray_icon import (
    ACTIVITY_COLOR,
    BLINK_INTERVAL_MS,
    RESTING_COLOR,
    TrayIcon,
    generate_activity_icon,
    generate_resting_icon,
)


def test_resting_and_activity_icons_are_not_null(qapp):
    assert generate_resting_icon().isNull() is False
    assert generate_activity_icon().isNull() is False


def test_resting_and_activity_colors_are_distinct():
    assert RESTING_COLOR != ACTIVITY_COLOR


def test_blink_interval_matches_potato_s_real_value():
    assert BLINK_INTERVAL_MS == 750


def test_restore_action_emits_restore_requested(qapp):
    tray = TrayIcon()
    seen = []
    tray.restore_requested.connect(lambda: seen.append(1))

    tray.restore_action.trigger()

    assert seen == [1]


def test_exit_action_emits_exit_requested(qapp):
    tray = TrayIcon()
    seen = []
    tray.exit_requested.connect(lambda: seen.append(1))

    tray.exit_action.trigger()

    assert seen == [1]


def test_left_click_activation_emits_restore_requested(qapp):
    tray = TrayIcon()
    seen = []
    tray.restore_requested.connect(lambda: seen.append(1))

    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)

    assert seen == [1]


def test_double_click_activation_emits_restore_requested(qapp):
    tray = TrayIcon()
    seen = []
    tray.restore_requested.connect(lambda: seen.append(1))

    tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)

    assert seen == [1]


def test_context_menu_activation_does_not_emit_restore_requested(qapp):
    # Right-click's menu is handled automatically by Qt's own
    # setContextMenu() -- must not also trigger a restore.
    tray = TrayIcon()
    seen = []
    tray.restore_requested.connect(lambda: seen.append(1))

    tray._on_activated(QSystemTrayIcon.ActivationReason.Context)

    assert seen == []


def test_start_blinking_switches_to_the_activity_icon_and_starts_the_timer(qapp):
    tray = TrayIcon()

    tray.start_blinking()

    assert tray._blink_timer.isActive() is True
    assert tray._blink_on is True


def test_start_blinking_twice_does_not_restart_the_timer(qapp):
    tray = TrayIcon()
    tray.start_blinking()
    timer_was_active = tray._blink_timer.isActive()

    tray.start_blinking()  # must be a no-op, not double-start

    assert timer_was_active is True
    assert tray._blink_timer.isActive() is True


def test_stop_blinking_resets_to_the_resting_icon_and_stops_the_timer(qapp):
    tray = TrayIcon()
    tray.start_blinking()

    tray.stop_blinking()

    assert tray._blink_timer.isActive() is False
    assert tray._blink_on is False


def test_ticking_toggles_between_icons(qapp):
    tray = TrayIcon()
    tray.start_blinking()
    assert tray._blink_on is True

    tray._tick()
    assert tray._blink_on is False

    tray._tick()
    assert tray._blink_on is True
