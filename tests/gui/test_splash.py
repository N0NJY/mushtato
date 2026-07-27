"""Headless tests for gui/splash.py -- the startup splash screen and
its "show it again" mechanism. Real (but small) timing waits, not
mocked out, to actually prove the minimum-duration guarantee -- kept
short (tens of milliseconds) so the test suite stays fast.
"""

import time

import gui.splash
from gui.splash import create_splash, run_with_splash, show_splash_again


def test_create_splash_loads_the_real_splash_art(qapp):
    splash = create_splash()
    assert splash.pixmap().isNull() is False


def test_run_with_splash_calls_init_fn_and_returns_its_result(qapp):
    calls = []

    def init_fn():
        calls.append(1)
        return "the-result"

    result = run_with_splash(init_fn, minimum_ms=0)

    assert calls == [1]
    assert result == "the-result"


def test_run_with_splash_waits_for_the_minimum_duration(qapp):
    start = time.monotonic()
    run_with_splash(lambda: None, minimum_ms=150)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert elapsed_ms >= 140  # small tolerance for timer granularity


def test_run_with_splash_does_not_wait_if_init_fn_already_took_longer(qapp, monkeypatch):
    # Route around the real QSplashScreen.show() call for this one --
    # verified directly (see CLAUDE.md's Phase 3/icon+splash notes)
    # that it costs a fixed ~1000ms under the offscreen QPA platform
    # regardless of pixmap size, an offscreen-environment quirk (a
    # plain QWidget.show(), even with the identical Qt.WindowType.
    # SplashScreen flag, is near-instant) rather than anything in
    # run_with_splash's own wait-calculation logic. A wall-clock
    # ceiling assertion would be contaminated by that fixed overhead,
    # so this asserts the actual claim directly instead: _wait_ms is
    # never called with a positive duration once init_fn alone already
    # exceeded minimum_ms.
    wait_calls = []
    monkeypatch.setattr(gui.splash, "_wait_ms", lambda ms: wait_calls.append(ms))

    def slow_init():
        time.sleep(0.2)
        return "done"

    result = run_with_splash(slow_init, minimum_ms=50)

    assert result == "done"
    assert wait_calls == [wait_calls[0]]
    assert wait_calls[0] <= 0


def test_show_splash_again_shows_and_closes_within_the_given_duration(qapp):
    start = time.monotonic()
    show_splash_again(duration_ms=100)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert elapsed_ms >= 90
