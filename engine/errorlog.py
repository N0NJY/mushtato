"""Centralized error logging: a crash guard for genuinely *unhandled*
exceptions, not a mirror of errors this app already shows per-tab.

Phase 11 checkpoint scoped this deliberately narrow: script/trigger
errors, connection failures, and alias errors are already surfaced
directly in a tab's scrollback by design (Phase 9) and stay exactly as
they are -- this module only catches exceptions that currently have
nowhere to go at all, via ``sys.excepthook``/``threading.excepthook``.

Qt-free (CLAUDE.md rule 2) so it's headlessly testable without a
QApplication -- the GUI layer's ErrorLogWindow only reads ``.records``
and subscribes via ``add_listener`` for live updates, using its own
signal to marshal delivery onto the GUI thread (a listener can fire
from any thread, including a background connection thread -- see
``install_thread_excepthook``).

Verified empirically before designing around it, not assumed: PySide6
*does* route an exception raised inside a Qt slot (e.g. a QTimer
callback) through ``sys.excepthook`` -- confirmed with a real
QApplication event loop, not just recalled from memory. A background
thread's exception (e.g. inside TelnetBridge's own per-connection
thread) does *not* reach ``sys.excepthook`` at all -- Python routes
those through the separate ``threading.excepthook`` mechanism instead
(also confirmed directly) -- hence both hooks are installed, covering
a real gap the source planning doc's "sys.excepthook only" pseudocode
would have missed for this app's actual threading architecture.

Deliberately does NOT use the stdlib ``logging`` module, despite that
being the source doc's own suggestion -- a real bug, not a style
choice: an earlier draft built this on ``logging.getLogger()`` +
``logging.FileHandler``, and a full-suite test run reproducibly hung
with ``faulthandler``'s own thread dump showing a background thread
stuck *inside* ``logging``'s internal ``makeRecord``/handler-emit
machinery while the main thread waited on ``Thread.join()`` -- ``
logging``'s module-level lock and global logger registry are shared
process-wide by every ``ErrorLog`` instance and every other lingering
background thread in the same test process (idle ``TelnetBridge``
asyncio loops, idle executor workers), a combination this project's
own test suite genuinely exercises at volume. Rewritten on plain file
I/O guarded by one *instance-scoped* ``threading.Lock`` instead --
confirmed via repeated ``faulthandler``-instrumented full-suite runs
that this specific deadlock signature no longer appears. A separate,
pre-existing, already-documented risk remains (SPEC.md section 8):
the full suite can still hang or crash *after* every test has already
passed, during interpreter shutdown, when real background threads from
unrelated tests (``test_telnet_bridge_integration.py``'s live asyncio
loops, ``engine/scripting/sandbox.py``'s worker threads) are still
alive -- confirmed to be the same lingering threads regardless of
whether this module's own tests are even included, i.e. not something
this module introduces or can fix on its own.
"""

from __future__ import annotations

import sys
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from .storage.paths import logs_dir

MAX_IN_MEMORY_ERRORS = 100


@dataclass
class ErrorRecord:
    timestamp: datetime
    level: str
    module: str
    message: str
    traceback_text: str


class ErrorLog:
    """Owns the in-memory ring buffer (last ``MAX_IN_MEMORY_ERRORS``)
    and a real day-rotated log file. Construct one directly with
    ``log_dir=`` in tests (never touches the real per-user data
    directory that way); the real app uses the module-level
    :func:`get_error_log` singleton, since ``sys.excepthook`` is itself
    inherently a single, process-wide hook.

    Thread-safe via one plain ``threading.Lock`` scoped to this
    instance -- not the stdlib ``logging`` module's shared global lock
    (see this module's docstring for the real hang that caused this
    design).
    """

    def __init__(self, *, log_dir: Optional[Path] = None) -> None:
        self._log_dir = log_dir if log_dir is not None else logs_dir()
        self.records: List[ErrorRecord] = []
        self._listeners: List[Callable[[ErrorRecord], None]] = []
        self._lock = threading.Lock()

    def _current_log_file(self) -> Path:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        return self._log_dir / f"error_{datetime.now():%Y%m%d}.log"

    def add_listener(self, callback: Callable[[ErrorRecord], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ErrorRecord], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def log_exception(self, exc_type, exc_value, exc_traceback) -> None:
        traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        record = ErrorRecord(
            timestamp=datetime.now(),
            level="CRITICAL",
            module=getattr(exc_type, "__module__", "") or "unknown",
            message=f"Unhandled exception: {exc_type.__name__}: {exc_value}",
            traceback_text=traceback_text,
        )
        with self._lock:
            line = (
                f"[{record.timestamp:%Y-%m-%d %H:%M:%S}] [{record.level}] "
                f"{record.module}: {record.message}\n{traceback_text}\n"
            )
            with self._current_log_file().open("a", encoding="utf-8") as handle:
                handle.write(line)
            self.records.append(record)
            if len(self.records) > MAX_IN_MEMORY_ERRORS:
                self.records.pop(0)
        for listener in list(self._listeners):
            listener(record)

    def clear(self) -> None:
        """Clears the in-memory list only -- the on-disk file is never
        touched by this, matching the checkpointed Export/Clear split
        (Clear is a display-only reset, Export is the durable copy).
        """
        self.records = []


_singleton: Optional[ErrorLog] = None


def get_error_log() -> ErrorLog:
    global _singleton
    if _singleton is None:
        _singleton = ErrorLog()
    return _singleton


def install_excepthook(error_log: ErrorLog) -> None:
    """Install a ``sys.excepthook`` that logs to ``error_log`` and then
    chains to whatever hook was previously installed (Python's own
    default by default) -- never silently swallows KeyboardInterrupt,
    matching the standard pattern for this kind of hook.
    """
    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_traceback):
        if not issubclass(exc_type, KeyboardInterrupt):
            error_log.log_exception(exc_type, exc_value, exc_traceback)
        previous(exc_type, exc_value, exc_traceback)

    sys.excepthook = _hook


def install_thread_excepthook(error_log: ErrorLog) -> None:
    """Install a ``threading.excepthook`` covering exceptions raised on
    a background thread (e.g. a TelnetBridge connection thread) --
    ``sys.excepthook`` alone does not see these, confirmed directly
    (see this module's docstring) rather than assumed from ``sys.
    excepthook``'s own docs.
    """
    previous = threading.excepthook

    def _hook(args) -> None:
        if not issubclass(args.exc_type, SystemExit):
            error_log.log_exception(args.exc_type, args.exc_value, args.exc_traceback)
        previous(args)

    threading.excepthook = _hook
