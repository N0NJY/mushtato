"""Qt <-> asyncio bridge for one SshClient connection.

Deliberately mirrors telnet_bridge.py's architecture exactly (see its
own module docstring for the full reasoning): a dedicated background
thread/asyncio loop per connection, Qt signals to cross back to the
GUI thread, ``asyncio.run_coroutine_threadsafe`` to cross the other
way. This is not an accident of convenience -- implementing the
*same* ``start()``/``send_line()``/``stop()``/``set_on_text()`` +
``connected``/``connectionClosed``/``connectionFailed`` contract means
``SessionTab`` (and everything downstream of it -- line dispatch,
scripting, the scrollback) needs no changes at all to host an SSH
session instead of a Telnet one; it already only depends on that
contract, never on ``TelnetBridge`` by name.

Host-key mismatches (see engine/net/ssh_client.py's HostKeyMismatch)
are surfaced through the *same* ``connectionFailed`` signal as any
other connection failure, not a new one -- SessionTab doesn't need to
know this is a different kind of failure to display it usefully; the
message text itself carries the old/new fingerprints and names the
exact ``/ssh-forget`` command to run if the change is expected.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from engine.net import HostKeyMismatch, HostKeyStore, SshClient


class SshBridge(QObject):
    connected = Signal()
    textReceived = Signal(str)
    connectionClosed = Signal()
    connectionFailed = Signal(str)

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        host_key_store: HostKeyStore,
        parent: Optional[QObject] = None,
        *,
        on_text: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._host_key_store = host_key_store
        self._on_text = on_text
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[SshClient] = None
        self._thread: Optional[threading.Thread] = None
        self._main_task: Optional[asyncio.Task] = None

    def set_on_text(self, callback: Optional[Callable[[str], None]]) -> None:
        self._on_text = callback

    def start(self) -> None:
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def send_line(self, text: str) -> None:
        if self._loop is None or self._client is None:
            return
        asyncio.run_coroutine_threadsafe(self._client.send_line(text), self._loop)

    def run_in_background(self, func) -> None:
        """Same contract as TelnetBridge.run_in_background -- see its
        docstring. Kept here even though SSH sessions don't use alias
        expansion themselves, so any future code path that just calls
        ``bridge.run_in_background(...)`` generically keeps working
        regardless of which bridge type it was actually handed.
        """
        if self._loop is None:
            return

        async def _runner() -> None:
            await self._loop.run_in_executor(None, func)

        asyncio.run_coroutine_threadsafe(_runner(), self._loop)

    def stop(self) -> None:
        loop = self._loop
        if loop is None:
            return

        if self._main_task is not None:
            try:
                loop.call_soon_threadsafe(self._main_task.cancel)
            except RuntimeError:
                pass

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
        client = SshClient(
            self._host, self._port, self._username, self._password, self._host_key_store
        )
        self._client = client
        try:
            try:
                await client.connect()
            except HostKeyMismatch as exc:
                self.connectionFailed.emit(
                    f"{exc}\n"
                    f"If this change is expected (e.g. the server was reinstalled), "
                    f"run: /ssh-forget {exc.host}:{exc.port}  then reconnect."
                )
                return
            except Exception as exc:  # noqa: BLE001 -- surfaced to the user, never crashes the tab
                self.connectionFailed.emit(f"{type(exc).__name__}: {exc}")
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
