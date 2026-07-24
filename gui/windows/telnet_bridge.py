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
(Phase 4): because the read loop already lives on this background
thread rather than the GUI thread, Phase 9's trigger-dispatch
integration (``on_text``, below) calls into run_with_timeout here too,
by construction, with no special-casing required to keep the GUI
responsive.

``on_text`` (Phase 9): an optional plain-Python callback, invoked
synchronously on *this* background thread as each raw chunk arrives,
before ``textReceived`` is emitted. Deliberately not a Qt signal for
this one hop -- a Qt signal/slot connection is auto-marshaled onto the
*receiving* QObject's own thread (which is why ``textReceived`` itself
safely reaches the GUI thread despite being emitted from here), so if
the processing that needs to run on this background thread (line-
buffering, ANSI parsing, trigger dispatch -- see
engine/scripting/line_dispatch.py) lived in a GUI-thread QObject's
slot, it would run on the GUI thread instead, defeating the whole
point. A plain callable has no such thread affinity -- it just runs on
whatever thread calls it, which is exactly what's needed here. This
class stays fully unaware of ansi/scripting either way -- it just
invokes whatever opaque callable it's given.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from engine.net import TelnetClient


class TelnetBridge(QObject):
    connected = Signal()
    textReceived = Signal(str)
    connectionClosed = Signal()
    connectionFailed = Signal(str)

    def __init__(
        self,
        host: str,
        port: int,
        parent: Optional[QObject] = None,
        *,
        on_text: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._on_text = on_text
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[TelnetClient] = None
        self._thread: Optional[threading.Thread] = None
        self._main_task: Optional[asyncio.Task] = None

    def set_on_text(self, callback: Optional[Callable[[str], None]]) -> None:
        """Set/replace the ``on_text`` callback after construction.

        SessionTab calls this unconditionally on whatever bridge it
        ends up with (freshly constructed, or injected for tests) so
        the same wiring code works for both -- an injected fake bridge
        only needs to implement this one method (see FakeBridge in
        tests/gui/test_main_window_smoke.py) to correctly participate
        in the real on_text-then-textReceived contract ``_run()``
        follows below.
        """
        self._on_text = callback

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

    def run_in_background(self, func) -> None:
        """Run a blocking, synchronous ``func`` on this connection's
        background loop's executor -- a worker thread, never the GUI
        thread and never the loop's own thread either (so the read
        loop in ``_run()`` keeps running while ``func`` executes).

        Safe to call from the GUI thread (the only thread this should
        ever be called from), mirroring ``send_line``'s existing
        pattern. Used for outbound alias expansion (Phase 9):
        ``AliasEngine.expand()`` can call ``run_with_timeout``, whose
        blocking wait must never land on the GUI thread, the same
        reasoning as incoming trigger dispatch (see ``on_text`` above).
        A no-op if the connection isn't up yet.
        """
        if self._loop is None:
            return

        async def _runner() -> None:
            await self._loop.run_in_executor(None, func)

        asyncio.run_coroutine_threadsafe(_runner(), self._loop)

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
                    if self._on_text is not None:
                        self._on_text(chunk)
                    self.textReceived.emit(chunk)
        finally:
            await client.close()
