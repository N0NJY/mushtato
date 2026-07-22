"""Qt <-> asyncio bridge for one TelnetClient connection.

Architecture (see CLAUDE.md's Phase 5 discussion for the full
reasoning): the asyncio event loop that engine/net's TelnetClient
needs runs on its own dedicated background thread, never the Qt/GUI
thread. Data crosses back to the GUI thread via Qt signals -- since
this QObject is created on the GUI thread (before its background
thread is started), Qt's default AutoConnection automatically becomes
a QueuedConnection for these signals, safely marshaling delivery
without any manual dispatching. Outbound sends cross the other
direction via ``asyncio.run_coroutine_threadsafe``, the standard
stdlib primitive for scheduling a coroutine onto a loop owned by a
different thread.

This keeps the Qt GUI thread free of anything that could block --
including, notably, engine.scripting's ``run_with_timeout`` watchdog
(Phase 4), which is not wired up yet (Phase 5 is connect/display/send
only) but will be in a later phase: because the read loop already
lives on this background thread rather than the GUI thread, a future
integration's calls into run_with_timeout land here too, by
construction, with no special-casing required to keep the GUI
responsive.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from engine.net import TelnetClient


class TelnetBridge(QObject):
    connected = Signal()
    textReceived = Signal(str)
    connectionClosed = Signal()
    connectionFailed = Signal(str)

    def __init__(self, host: str, port: int, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[TelnetClient] = None
        self._thread: Optional[threading.Thread] = None
        self._main_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Spin up the background thread and begin connecting."""
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def send_line(self, text: str) -> None:
        """Schedule sending ``text`` on the background loop.

        Safe to call from the GUI thread (the only thread this should
        ever be called from) -- ``run_coroutine_threadsafe`` handles
        the cross-thread scheduling.
        """
        if self._loop is None or self._client is None:
            return
        asyncio.run_coroutine_threadsafe(self._client.send_line(text), self._loop)

    def stop(self) -> None:
        """Stop the connection and the background thread.

        Cancels the single running task rather than scheduling a
        separate detached "close" task -- cancellation is delivered at
        whatever await point ``_run()`` is currently suspended on, and
        its ``finally`` block closes the connection as part of the
        same cancellation unwind. That avoids a race between a
        separately-scheduled close() task and the loop being stopped
        out from under it. Deliberately defensive throughout: this runs
        from MainWindow.closeEvent, and a failure here must never
        prevent the window from closing.
        """
        loop = self._loop
        if loop is None:
            return

        if self._main_task is not None:
            try:
                loop.call_soon_threadsafe(self._main_task.cancel)
            except RuntimeError:
                pass  # loop already stopped/closed -- nothing to cancel

        if self._thread is not None:
            self._thread.join(timeout=2)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            self._main_task = loop.create_task(self._run())
            loop.run_until_complete(self._main_task)
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()

    async def _run(self) -> None:
        client = TelnetClient(self._host, self._port)
        self._client = client
        try:
            try:
                await client.connect()
            except OSError as exc:
                self.connectionFailed.emit(str(exc))
                return

            self.connected.emit()

            while True:
                try:
                    chunk = await client.read()
                except OSError as exc:
                    self.connectionFailed.emit(str(exc))
                    return
                if chunk is None:
                    self.connectionClosed.emit()
                    return
                if chunk:
                    self.textReceived.emit(chunk)
        finally:
            await client.close()
