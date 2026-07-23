"""Headless tests for the spawn-window feature (log-mirror, the
concrete first example -- see CLAUDE.md's Phase 6 notes). Owned by
SessionTab as of Phase 9.
"""

from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge


def test_spawn_log_window_mirrors_incoming_text(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn = tab.spawn_log_window()
    bridge.textReceived.emit("You see a dusty road.\r\n")

    assert "You see a dusty road." in tab.scrollback.toPlainText()
    assert "You see a dusty road." in spawn.scrollback.toPlainText()


def test_spawn_window_does_not_receive_text_from_before_it_was_created(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.textReceived.emit("earlier text\r\n")
    spawn = tab.spawn_log_window()
    bridge.textReceived.emit("later text\r\n")

    assert "earlier text" not in spawn.scrollback.toPlainText()
    assert "later text" in spawn.scrollback.toPlainText()


def test_multiple_spawn_windows_all_receive_the_same_text(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn_a = tab.spawn_log_window()
    spawn_b = tab.spawn_log_window()
    bridge.textReceived.emit("broadcast\r\n")

    assert "broadcast" in spawn_a.scrollback.toPlainText()
    assert "broadcast" in spawn_b.scrollback.toPlainText()


def test_closing_a_spawn_window_removes_it_from_the_owner_s_list(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn = tab.spawn_log_window()
    assert spawn in tab.spawn_windows

    spawn.close()

    assert spawn not in tab.spawn_windows


def test_closing_one_spawn_window_does_not_affect_another(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn_a = tab.spawn_log_window()
    spawn_b = tab.spawn_log_window()

    spawn_a.close()

    assert spawn_a not in tab.spawn_windows
    assert spawn_b in tab.spawn_windows

    bridge.textReceived.emit("still here\r\n")
    assert "still here" in spawn_b.scrollback.toPlainText()


def test_shutdown_closes_all_spawn_windows(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn_a = tab.spawn_log_window()
    spawn_b = tab.spawn_log_window()

    tab.shutdown()

    assert spawn_a.isVisible() is False
    assert spawn_b.isVisible() is False
