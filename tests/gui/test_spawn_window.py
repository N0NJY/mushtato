"""Headless tests for the spawn-window feature (log-mirror, the
concrete first example -- see CLAUDE.md's Phase 6 notes). Owned by
SessionTab as of Phase 7e.
"""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.windows.session_tab import SessionTab
from gui.windows.spawn_window import SpawnWindow
from tests.gui.test_main_window_smoke import FakeBridge


def test_spawn_log_window_mirrors_incoming_text(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn = tab.spawn_log_window()
    bridge.simulate_incoming("You see a dusty road.\r\n")

    assert "You see a dusty road." in tab.scrollback.toPlainText()
    assert "You see a dusty road." in spawn.scrollback.toPlainText()


# -- Save Spawnlog (Phase 11) -------------------------------------------


def test_save_spawnlog_defaults_to_logs_dir_and_timestamped_filename(qapp, monkeypatch, tmp_path):
    # logs_dir_override so this never touches the real per-user logs
    # directory -- same leak class Phase 9 already hit once with
    # world_script_path.
    override_dir = tmp_path / "logsdir"
    window = SpawnWindow("Test Log", logs_dir_override=override_dir)
    captured = {}

    def fake_get_save_file_name(parent, caption, start, filter_):
        captured["start"] = start
        return str(tmp_path / "chosen.txt"), filter_

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_get_save_file_name))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    window.save_spawnlog()

    assert str(override_dir) in captured["start"]
    assert Path(captured["start"]).name.startswith("spawnlog_")
    assert captured["start"].endswith(".txt")


def test_save_spawnlog_writes_header_and_scrollback_text(qapp, monkeypatch, tmp_path):
    from gui.windows.styled_text_qt import append_styled_segments
    from engine.ansi import Style, StyledSegment

    window = SpawnWindow("Test Log", logs_dir_override=tmp_path / "logsdir")
    append_styled_segments(window.scrollback, [StyledSegment("You see a dusty road.\n", Style())])

    target = tmp_path / "saved.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "Text files (*.txt)"))
    )
    shown = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda parent, title, text: shown.append(text))
    )

    window.save_spawnlog()

    content = target.read_text(encoding="utf-8")
    assert "Spawnlog saved:" in content
    assert "You see a dusty road." in content
    assert str(target) in shown[0]


def test_save_spawnlog_cancelled_dialog_writes_nothing(qapp, monkeypatch, tmp_path):
    # The default logs_dir itself still gets created (matching a real
    # file dialog's own default-directory behavior), but no file should
    # be written when the user cancels.
    window = SpawnWindow("Test Log", logs_dir_override=tmp_path / "logsdir")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    window.save_spawnlog()
    assert list((tmp_path / "logsdir").iterdir()) == []


def test_spawn_window_does_not_receive_text_from_before_it_was_created(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.simulate_incoming("earlier text\r\n")
    spawn = tab.spawn_log_window()
    bridge.simulate_incoming("later text\r\n")

    assert "earlier text" not in spawn.scrollback.toPlainText()
    assert "later text" in spawn.scrollback.toPlainText()


def test_multiple_spawn_windows_all_receive_the_same_text(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn_a = tab.spawn_log_window()
    spawn_b = tab.spawn_log_window()
    bridge.simulate_incoming("broadcast\r\n")

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

    bridge.simulate_incoming("still here\r\n")
    assert "still here" in spawn_b.scrollback.toPlainText()


def test_shutdown_closes_all_spawn_windows(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    spawn_a = tab.spawn_log_window()
    spawn_b = tab.spawn_log_window()

    tab.shutdown()

    assert spawn_a.isVisible() is False
    assert spawn_b.isVisible() is False
