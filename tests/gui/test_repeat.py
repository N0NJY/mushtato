"""Headless tests for Item 11 (2026-07-28): /repeat, /repeats, and
/stoprepeat -- a background, cancelable, tab-scoped repeat-process
mechanism.

Real QTimers are used throughout (via QTest.qWait), not mocked --
proving the actual scheduling/cancellation behavior, not just that the
handler functions can be called directly.
"""

from PySide6.QtTest import QTest

from gui.windows.session_tab import SessionTab, parse_repeat_command
from tests.gui.test_main_window_smoke import FakeBridge


def make_tab(**kwargs):
    return SessionTab("example.com", 4201, bridge=FakeBridge(), **kwargs)


def run(tab, command_line: str) -> None:
    tab.input_line.setText(command_line)
    tab.input_line.returnPressed.emit()


# -- parse_repeat_command (standalone, pure) ------------------------------


def test_parse_repeat_minimal():
    assert parse_repeat_command("5 look") == (5, 0.0, "look")


def test_parse_repeat_with_delay():
    assert parse_repeat_command("-d2.5 3 cast fireball") == (3, 2.5, "cast fireball")


def test_parse_repeat_indefinite_count():
    assert parse_repeat_command("i say hello") == (None, 0.0, "say hello")
    assert parse_repeat_command("I say hello") == (None, 0.0, "say hello")


def test_parse_repeat_rejects_zero_count():
    assert parse_repeat_command("0 look") is None
    assert parse_repeat_command("-d1 0 look") is None


def test_parse_repeat_rejects_missing_command():
    assert parse_repeat_command("3") is None
    assert parse_repeat_command("3   ") is None


def test_parse_repeat_rejects_whitespace_only_command():
    assert parse_repeat_command("3    ") is None


# -- /repeat fires immediately and paces subsequent sends -----------------


def test_repeat_fires_immediately_and_the_right_number_of_times(qapp):
    tab = make_tab()
    run(tab, "/repeat 3 look")
    assert tab.bridge.sent == ["look"]  # first firing is synchronous, no delay
    for _ in range(3):
        QTest.qWait(20)
    assert tab.bridge.sent == ["look", "look", "look"]
    assert tab._repeat_processes == {}


def test_repeat_reports_completion(qapp):
    tab = make_tab()
    run(tab, "/repeat 1 look")
    assert "[/repeat #1 finished]" in tab.scrollback.toPlainText()


def test_repeat_paces_sends_with_the_delay_flag(qapp):
    tab = make_tab()
    run(tab, "/repeat -d0.2 3 look")
    assert tab.bridge.sent == ["look"]
    QTest.qWait(50)
    assert tab.bridge.sent == ["look"]  # delay hasn't elapsed yet
    QTest.qWait(600)
    assert tab.bridge.sent == ["look", "look", "look"]


def test_repeat_can_itself_be_a_slash_command(qapp):
    tab = make_tab()
    run(tab, "/repeat 2 /version")
    QTest.qWait(20)
    # /version is handled locally (never sent to the bridge) -- proves
    # each firing goes through the same command-dispatch pipeline as a
    # manually typed line, not straight to the server unconditionally.
    assert tab.bridge.sent == []
    from gui.version import mushtato_version

    assert tab.scrollback.toPlainText().count(mushtato_version()) >= 2


def test_repeat_bad_syntax_reports_usage(qapp):
    tab = make_tab()
    run(tab, "/repeat")
    assert "Usage: /repeat" in tab.scrollback.toPlainText()


# -- /repeats -----------------------------------------------------------


def test_repeats_lists_active_processes(qapp):
    tab = make_tab()
    run(tab, "/repeat -d1 i say hi")
    run(tab, "/repeats")
    text = tab.scrollback.toPlainText()
    assert "#1 -- indefinite remaining, every 1.0s -- say hi" in text


def test_repeats_reports_when_none_are_active(qapp):
    tab = make_tab()
    run(tab, "/repeats")
    assert "No active /repeat processes" in tab.scrollback.toPlainText()


def test_repeats_shows_remaining_out_of_total_for_a_finite_repeat(qapp):
    tab = make_tab()
    run(tab, "/repeat -d5 3 look")
    run(tab, "/repeats")
    assert "2/3 remaining" in tab.scrollback.toPlainText()


# -- /stoprepeat ----------------------------------------------------------


def test_stoprepeat_cancels_an_indefinite_repeat(qapp):
    tab = make_tab()
    run(tab, "/repeat -d0.05 i look")
    QTest.qWait(20)
    assert 1 in tab._repeat_processes
    run(tab, "/stoprepeat 1")
    assert tab._repeat_processes == {}
    sent_count_at_stop = len(tab.bridge.sent)
    QTest.qWait(300)
    # No further sends after cancellation -- proves the timer was
    # actually stopped, not just removed from the tracking dict.
    assert len(tab.bridge.sent) == sent_count_at_stop


def test_stoprepeat_reports_unknown_id():
    tab = make_tab()
    run(tab, "/stoprepeat 99")
    assert "No such /repeat process: #99" in tab.scrollback.toPlainText()


def test_stoprepeat_bad_syntax_reports_usage(qapp):
    tab = make_tab()
    run(tab, "/stoprepeat notanumber")
    assert "Usage: /stoprepeat" in tab.scrollback.toPlainText()


# -- tab-scoping (checkpointed 2026-07-28) ---------------------------------


def test_repeat_processes_are_independent_per_tab(qapp):
    tab1 = make_tab()
    tab2 = make_tab()
    run(tab1, "/repeat -d5 i look")
    run(tab1, "/repeats")
    run(tab2, "/repeats")
    assert "#1" in tab1.scrollback.toPlainText()
    assert "No active /repeat processes" in tab2.scrollback.toPlainText()


# -- auto-cancel on close/disconnect (checkpointed 2026-07-28) ------------


def test_disconnect_cancels_active_repeats(qapp):
    tab = make_tab()
    run(tab, "/repeat -d5 i look")
    assert tab._repeat_processes
    tab.disconnect_bridge()
    assert tab._repeat_processes == {}


def test_connection_closed_cancels_active_repeats(qapp):
    tab = make_tab()
    run(tab, "/repeat -d5 i look")
    assert tab._repeat_processes
    tab._on_connection_closed()
    assert tab._repeat_processes == {}


def test_connection_failed_cancels_active_repeats(qapp):
    tab = make_tab()
    run(tab, "/repeat -d5 i look")
    assert tab._repeat_processes
    tab._on_connection_failed("OSError: Connection refused")
    assert tab._repeat_processes == {}


def test_shutdown_cancels_active_repeats(qapp):
    tab = make_tab()
    run(tab, "/repeat -d5 i look")
    assert tab._repeat_processes
    tab.shutdown()
    assert tab._repeat_processes == {}


def test_stopped_repeat_does_not_error_if_it_would_have_fired_anyway(qapp):
    # Regression guard: _fire_repeat looks the id up in the dict every
    # time it runs -- stopping (or cancelling) a repeat between when its
    # timer was scheduled and when it would have fired must be a silent
    # no-op, not a KeyError.
    tab = make_tab()
    run(tab, "/repeat -d0.05 i look")
    tab._cancel_all_repeats()
    tab._fire_repeat(1)  # simulates a timer tick that was already stopped
    assert tab.bridge.sent == ["look"]  # only the immediate first firing
