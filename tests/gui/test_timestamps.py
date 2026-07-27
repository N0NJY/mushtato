"""Headless tests for per-tab timestamps (checkpointed 2026-07-27):
a compact "[HH:mm:ss]" prefix on every new line while enabled, plus a
full-date "[Timestamps enabled/disabled -- ...]" marker line at the
moment of toggling. Per-tab, never persisted, always starts off.
"""

import re

from PySide6.QtGui import QTextCursor

from gui.windows.main_window import MainWindow
from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge

TIME_RE = re.compile(r"\[\d{2}:\d{2}:\d{2}\] ")
FULL_DATE_ON_RE = re.compile(r"\[Timestamps enabled -- \d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2}\]")
FULL_DATE_OFF_RE = re.compile(r"\[Timestamps disabled -- \d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2}\]")


def test_timestamps_are_off_by_default(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    assert tab.show_timestamps is False


def test_incoming_server_line_is_not_timestamped_when_disabled(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.simulate_incoming("You see a dusty road.\r\n")

    assert TIME_RE.search(tab.scrollback.toPlainText()) is None


def test_incoming_server_line_is_timestamped_when_enabled(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)
    tab.set_show_timestamps(True)

    bridge.simulate_incoming("You see a dusty road.\r\n")

    text = tab.scrollback.toPlainText()
    assert TIME_RE.search(text) is not None
    # The prefix comes immediately before the real line, not just
    # somewhere in the document.
    assert re.search(r"\[\d{2}:\d{2}:\d{2}\] You see a dusty road\.", text)


def test_spawn_window_mirror_gets_the_identical_timestamp(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)
    tab.set_show_timestamps(True)
    spawn = tab.spawn_log_window()

    bridge.simulate_incoming("You see a dusty road.\r\n")

    main_line = re.search(r"\[\d{2}:\d{2}:\d{2}\] You see a dusty road\.", tab.scrollback.toPlainText())
    spawn_line = re.search(
        r"\[\d{2}:\d{2}:\d{2}\] You see a dusty road\.", spawn.scrollback.toPlainText()
    )
    assert main_line is not None
    assert spawn_line is not None
    # Not just "both have a timestamp" -- the exact same one, proving
    # they were computed once and shared, not independently recomputed.
    assert main_line.group() == spawn_line.group()


def test_script_echo_output_is_timestamped_when_enabled(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    tab.set_show_timestamps(True)

    tab._on_script_echo_requested("hello from a script", None)

    assert re.search(r"\[\d{2}:\d{2}:\d{2}\] hello from a script", tab.scrollback.toPlainText())


def test_system_notice_is_timestamped_when_enabled_and_leading_blank_line_preserved(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    tab.set_show_timestamps(True)

    tab._append_plain("\n[Connection failed: nope]\n")

    text = tab.scrollback.toPlainText()
    # The leading blank line survives, and the timestamp sits right
    # before the real bracketed message, not swallowing the blank line.
    assert re.search(r"\n\[\d{2}:\d{2}:\d{2}\] \[Connection failed: nope\]\n", text)


def test_system_notice_is_not_timestamped_when_disabled(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    tab._append_plain("[Connection failed: nope]\n")

    text = tab.scrollback.toPlainText()
    assert "[Connection failed: nope]" in text
    assert TIME_RE.search(text) is None


def test_toggling_on_inserts_a_full_date_time_marker_line(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    tab.set_show_timestamps(True)

    assert FULL_DATE_ON_RE.search(tab.scrollback.toPlainText()) is not None


def test_toggling_off_inserts_a_full_date_time_marker_line(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    tab.set_show_timestamps(True)

    tab.set_show_timestamps(False)

    assert FULL_DATE_OFF_RE.search(tab.scrollback.toPlainText()) is not None


def test_toggling_to_the_same_state_is_a_noop(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    before = tab.scrollback.toPlainText()

    tab.set_show_timestamps(False)  # already off -- must not insert a marker

    assert tab.scrollback.toPlainText() == before


def test_toggling_marker_line_itself_is_not_double_timestamped(qapp):
    # The marker line already carries a full date/time inline -- it
    # must not also get the compact per-line prefix stapled on top.
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    tab.set_show_timestamps(True)

    text = tab.scrollback.toPlainText()
    marker_line = next(line for line in text.splitlines() if "Timestamps enabled" in line)
    assert marker_line.count("[") == 1


def test_toggling_does_not_retroactively_relabel_already_shown_lines(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.simulate_incoming("Line before timestamps were on.\r\n")
    tab.set_show_timestamps(True)
    bridge.simulate_incoming("Line after timestamps were on.\r\n")

    text = tab.scrollback.toPlainText()
    before_line = next(line for line in text.splitlines() if "Line before" in line)
    after_line = next(line for line in text.splitlines() if "Line after" in line)
    assert TIME_RE.match(before_line) is None
    assert TIME_RE.match(after_line) is not None


def test_cmd_timestamps_on_and_off(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    tab._commands.process("/timestamps on")
    assert tab.show_timestamps is True

    tab._commands.process("/timestamps off")
    assert tab.show_timestamps is False


def test_cmd_timestamps_rejects_invalid_usage(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    outcome = tab._commands.process("/timestamps sideways")

    assert outcome.text == "Usage: /timestamps [on|off]"
    assert tab.show_timestamps is False


# -- MainWindow chrome: the View menu checkbox --------------------------


def test_view_menu_toggle_calls_set_show_timestamps_on_the_active_tab(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json", scripts_dir=tmp_path / "scripts")
    host.open_tab("example.com", 4201, bridge=FakeBridge())

    host.timestamps_action.trigger()

    tab = host.tab_widget.currentWidget()
    assert tab.show_timestamps is True


def test_switching_tabs_shows_each_tab_s_own_independent_state(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json", scripts_dir=tmp_path / "scripts")
    tab1 = host.open_tab("one.example.com", 4201, bridge=FakeBridge())
    tab1.set_show_timestamps(True)
    tab2 = host.open_tab("two.example.com", 4202, bridge=FakeBridge())
    assert tab2.show_timestamps is False

    # tab2 is current after opening -- checkbox should reflect its (off) state.
    assert host.timestamps_action.isChecked() is False

    host.tab_widget.setCurrentWidget(tab1)
    assert host.timestamps_action.isChecked() is True

    host.tab_widget.setCurrentWidget(tab2)
    assert host.timestamps_action.isChecked() is False


def test_timestamps_action_disabled_with_zero_tabs_open(qapp, tmp_path):
    host = MainWindow(address_book_storage_path=tmp_path / "ab.json", scripts_dir=tmp_path / "scripts")
    assert host.timestamps_action.isEnabled() is False
