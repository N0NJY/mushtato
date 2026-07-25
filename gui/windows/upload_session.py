"""Drives an in-flight Upload (Tools > Upload / /upload) end to end:
paces sends via a ``QTimer`` over an ``engine.upload_format.
UploadStepper``, shows/updates an ``UploadProgressWindow``, and
reports completion/cancellation back to ``SessionTab`` via a Qt
signal. Modeled on Potato's real ``uploadBegin``/``uploadEnd``
(potato.tcl ~1197-1401) -- Potato's recursive ``after $delay [list
uploadBegin $c]`` self-rescheduling becomes a single-shot ``QTimer``
restarted after every step here.

Only one ``UploadSession`` exists per tab at a time
(``SessionTab.upload_session``), matching Potato's own real
``uploadWindow`` dispatcher (opening Upload again while one's already
running shows the progress window instead of a new file picker,
rather than starting a second upload).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from engine.upload_format import UploadOptions, UploadStepper, delay_ms

from .upload_progress_window import UploadProgressWindow


class UploadSession(QObject):
    # True = ran to completion, False = cancelled by the user.
    finished = Signal(bool)

    def __init__(
        self,
        file_path: str,
        lines: List[str],
        options: UploadOptions,
        *,
        send_line: Callable[[str], None],
        add_to_history: Optional[Callable[[str], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.options = options
        self._send_line = send_line
        self._add_to_history = add_to_history
        self.stepper = UploadStepper(lines, options)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._run_step)
        self.progress_window: Optional[UploadProgressWindow] = None
        self._cancelled = False

    def start(self) -> None:
        self._run_step()

    def show_progress_window(self) -> UploadProgressWindow:
        if self.progress_window is None:
            self.progress_window = UploadProgressWindow(
                Path(self.file_path).name, self.stepper.total_bytes
            )
            self.progress_window.cancel_requested.connect(self.cancel)
            self.progress_window.set_progress(self.stepper.bytes_consumed, self.stepper.total_bytes)
        self.progress_window.show()
        self.progress_window.raise_()
        self.progress_window.activateWindow()
        return self.progress_window

    def cancel(self) -> None:
        if self._cancelled or self.stepper.done:
            return
        self._cancelled = True
        self._timer.stop()
        if self.progress_window is not None:
            self.progress_window.close()
        self.finished.emit(False)

    def _run_step(self) -> None:
        if self._cancelled:
            return
        step = self.stepper.step()
        if step.send_text is not None:
            self._send_line(step.send_text)
            if self.options.add_to_history and self._add_to_history is not None:
                self._add_to_history(step.send_text)
        if self.progress_window is not None:
            self.progress_window.set_progress(self.stepper.bytes_consumed, self.stepper.total_bytes)
        if step.done:
            if self.progress_window is not None:
                self.progress_window.close()
            self.finished.emit(True)
            return
        wait_ms = delay_ms(self.options.delay_seconds) if step.send_text is not None else 0
        self._timer.start(wait_ms)
