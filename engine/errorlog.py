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
"""

from __future__ import annotations

import logging
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


class _InMemoryHandler(logging.Handler):
    """Turns a stdlib LogRecord into an ErrorRecord and hands it to a
    plain callback -- kept separate from ErrorLog so ErrorLog doesn't
    need to know anything about the logging module's own record shape.
    """

    def __init__(self, on_record: Callable[[ErrorRecord], None]) -> None:
        super().__init__()
        self._on_record = on_record

    def emit(self, record: logging.LogRecord) -> None:
        tb_text = ""
        if record.exc_info:
            tb_text = "".join(traceback.format_exception(*record.exc_info))
        self._on_record(
            ErrorRecord(
                timestamp=datetime.fromtimestamp(record.created),
                level=record.levelname,
                module=record.name,
                message=record.getMessage(),
                traceback_text=tb_text,
            )
        )


class ErrorLog:
    """Owns the in-memory ring buffer (last ``MAX_IN_MEMORY_ERRORS``)
    and a real day-rotated log file. Construct one directly with
    ``log_dir=`` in tests (never touches the real per-user data
    directory that way); the real app uses the module-level
    :func:`get_error_log` singleton, since ``sys.excepthook`` is itself
    inherently a single, process-wide hook.
    """

    def __init__(self, *, log_dir: Optional[Path] = None) -> None:
        self._log_dir = log_dir if log_dir is not None else logs_dir()
        self.records: List[ErrorRecord] = []
        self._listeners: List[Callable[[ErrorRecord], None]] = []
        self._logger = logging.getLogger(f"mushtato.errors.{id(self)}")
        self._logger.setLevel(logging.WARNING)
        self._logger.propagate = False
        self._logger.addHandler(_InMemoryHandler(self._add_record))
        self._file_handler: Optional[logging.FileHandler] = None
        self._file_handler_day: Optional[str] = None

    def _ensure_file_handler(self) -> None:
        day = datetime.now().strftime("%Y%m%d")
        if self._file_handler is not None and self._file_handler_day == day:
            return
        if self._file_handler is not None:
            self._logger.removeHandler(self._file_handler)
            self._file_handler.close()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(self._log_dir / f"error_{day}.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"))
        self._logger.addHandler(handler)
        self._file_handler = handler
        self._file_handler_day = day

    def _add_record(self, record: ErrorRecord) -> None:
        self.records.append(record)
        if len(self.records) > MAX_IN_MEMORY_ERRORS:
            self.records.pop(0)
        for listener in list(self._listeners):
            listener(record)

    def add_listener(self, callback: Callable[[ErrorRecord], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ErrorRecord], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def log_exception(self, exc_type, exc_value, exc_traceback) -> None:
        self._ensure_file_handler()
        self._logger.critical(
            f"Unhandled exception: {exc_type.__name__}: {exc_value}",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

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
