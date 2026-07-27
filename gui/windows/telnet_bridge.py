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

from engine.net import CertificateMismatch, CertificateStore, Socks4Error, TelnetClient


class TelnetBridge(QObject):
    connected = Signal()
    textReceived = Signal(str)
    connectionClosed = Signal()
    connectionFailed = Signal(str)

    # Post-Phase-9 addition: an application-level Telnet NOP heartbeat,
    # matching Potato's real "Use NOP Keepalive" option (verified
    # mechanism against potato-telnet.tcl's send_keepalive -- see
    # engine/net/client.py's send_nop() docstring for what wasn't
    # verifiable: Potato's own real scheduling interval). This is
    # this project's own reasonable choice, not a ported value.
    NOP_KEEPALIVE_INTERVAL_SECONDS = 60

    def __init__(
        self,
        host: str,
        port: int,
        parent: Optional[QObject] = None,
        *,
        on_text: Optional[Callable[[str], None]] = None,
        nop_keepalive: bool = False,
        use_ssl: bool = False,
        cert_store: Optional[CertificateStore] = None,
        naws_enabled: bool = False,
        term_enabled: bool = False,
        host2: str = "",
        port2: int = 0,
        use_ssl2: bool = False,
        proxy_host: str = "",
        proxy_port: int = 0,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._on_text = on_text
        self._nop_keepalive = nop_keepalive
        self._use_ssl = use_ssl
        self._cert_store = cert_store
        self._naws_enabled = naws_enabled
        self._term_enabled = term_enabled
        # Item 9 of the SSL/proxy/NAWS plan: a SOCKS4/SOCKS4a proxy,
        # tried only if both are actually set. Applies to *every*
        # candidate (primary and, if configured, the item 8 fallback
        # address) -- matches real Potato's own behavior, which routes
        # every address in its host list through the same proxy setting
        # rather than a per-address proxy choice.
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        # Item 8 of the SSL/proxy/NAWS plan: an optional fallback
        # address, tried only if host2/port2 are both actually set --
        # matches real Potato's own confirmed behavior (verified
        # against its source): primary then secondary, in that fixed
        # order, on *every* connect/reconnect attempt, never "sticky"
        # toward whichever one worked last. Each call to _run() (every
        # start(), including a reconnect's stop()-then-start()) rebuilds
        # this candidate list from scratch and always tries it from the
        # top, which is what gives "no stickiness" for free rather than
        # needing to be implemented as its own special case.
        self._host2 = host2
        self._port2 = port2
        self._use_ssl2 = use_ssl2
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
        candidates = [(self._host, self._port, self._use_ssl)]
        if self._host2 and self._port2:
            candidates.append((self._host2, self._port2, self._use_ssl2))

        client: Optional[TelnetClient] = None
        connect_error: Optional[Exception] = None
        for candidate_host, candidate_port, candidate_ssl in candidates:
            candidate_client = TelnetClient(
                candidate_host,
                candidate_port,
                use_ssl=candidate_ssl,
                cert_store=self._cert_store,
                naws_enabled=self._naws_enabled,
                term_enabled=self._term_enabled,
                proxy_host=self._proxy_host,
                proxy_port=self._proxy_port,
            )
            self._client = candidate_client
            try:
                await candidate_client.connect()
            except asyncio.CancelledError:
                await candidate_client.close()
                raise
            except (CertificateMismatch, OSError, Socks4Error) as exc:
                connect_error = exc
                await candidate_client.close()
                continue
            else:
                client = candidate_client
                connect_error = None
                break

        if client is None:
            self._client = None
            if isinstance(connect_error, CertificateMismatch):
                self.connectionFailed.emit(
                    f"{connect_error}\n"
                    f"If this change is expected (e.g. the server's certificate was "
                    f"reissued), run: /ssl-forget {connect_error.host}:{connect_error.port}  then reconnect."
                )
            else:
                self.connectionFailed.emit(str(connect_error))
            return

        keepalive_task: Optional[asyncio.Task] = None
        try:
            self.connected.emit()
            if self._nop_keepalive:
                keepalive_task = asyncio.create_task(self._send_nop_periodically(client))

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
            if keepalive_task is not None:
                keepalive_task.cancel()
            await client.close()

    async def _send_nop_periodically(self, client: TelnetClient) -> None:
        # A companion task to _run()'s own read loop, cancelled from
        # _run()'s finally block whenever the connection ends (cleanly
        # or not) -- an OSError here just means the connection is
        # already dead, which the read loop's own error handling will
        # discover and report on its own, so this task simply stops
        # rather than emitting a second, redundant failure signal.
        try:
            while True:
                await asyncio.sleep(self.NOP_KEEPALIVE_INTERVAL_SECONDS)
                await client.send_nop()
        except (asyncio.CancelledError, OSError):
            pass
