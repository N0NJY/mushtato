"""Startup splash screen, and the "show it again" mechanism reachable
from the Help window.

Shown for a fixed minimum duration (Rick's explicit choice: 3 seconds)
regardless of how fast real startup actually is -- MushTato's own init
work is fast enough (no heavy assets, no network calls before the main
window appears) that a "close the instant we're ready" splash would
likely flash by unseen.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from .asset_paths import splash_path

SPLASH_MINIMUM_DURATION_MS = 3000

T = TypeVar("T")


def _wait_ms(ms: int) -> None:
    """Blocks for ``ms`` milliseconds without freezing the app -- pumps
    Qt's own event loop the whole time (unlike ``time.sleep()``), so
    the splash stays responsive/repainted and the OS doesn't consider
    the process hung. A no-op for ``ms <= 0`` (real startup already
    took at least the minimum duration on its own).
    """
    if ms <= 0:
        return
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def create_splash() -> QSplashScreen:
    return QSplashScreen(QPixmap(str(splash_path())))


def run_with_splash(
    init_fn: Callable[[], T], *, minimum_ms: int = SPLASH_MINIMUM_DURATION_MS
) -> T:
    """Shows the splash screen, runs ``init_fn`` (the app's real
    startup work), then keeps the splash up until at least
    ``minimum_ms`` has elapsed in total before closing it -- so the
    splash is guaranteed to actually be seen even though MushTato's own
    startup is normally much faster than that. Returns whatever
    ``init_fn`` returned (gui/app.py's real MainWindow instance).
    """
    splash = create_splash()
    splash.show()
    QApplication.processEvents()

    start = time.monotonic()
    result = init_fn()
    elapsed_ms = (time.monotonic() - start) * 1000
    _wait_ms(int(minimum_ms - elapsed_ms))

    splash.close()
    return result


def show_splash_again(*, duration_ms: int = SPLASH_MINIMUM_DURATION_MS) -> None:
    """Re-shows the splash as a standalone popup for ``duration_ms`` --
    used by the Help window's "Show Splash Screen" action. Not part of
    the real startup sequence.
    """
    splash = create_splash()
    splash.show()
    QApplication.processEvents()
    _wait_ms(duration_ms)
    splash.close()
