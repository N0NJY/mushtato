"""Asyncio telnet client.

Hand-rolled IAC negotiation (see :mod:`engine.net.telnet`) on top of
plain ``asyncio`` streams, rather than a third-party telnet library.
The negotiation needs for this phase are deliberately minimal (refuse
every option) so a small, fully-owned state machine keeps the
dependency list unchanged and stays trivially testable headless.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .telnet import IAC, TelnetNegotiator

READ_CHUNK_SIZE = 4096


class TelnetClient:
    """A single connection to a MUD/MUSH/MOO server."""

    def __init__(self, host: str, port: int, *, encoding: str = "utf-8") -> None:
        self.host = host
        self.port = port
        self.encoding = encoding
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._negotiator = TelnetNegotiator()

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def send_line(self, line: str) -> None:
        """Send one line of user input, terminated with CRLF."""
        if self._writer is None:
            raise RuntimeError("not connected")
        data = line.encode(self.encoding, errors="replace").replace(
            bytes((IAC,)), bytes((IAC, IAC))
        )
        self._writer.write(data + b"\r\n")
        await self._writer.drain()

    async def read(self) -> Optional[str]:
        """Read and decode one chunk of incoming application text.

        Returns ``None`` on connection close (EOF). Returns ``""`` if
        the chunk read was entirely telnet negotiation with no visible
        text -- callers should keep looping, not treat that as a
        disconnect.
        """
        if self._reader is None:
            raise RuntimeError("not connected")
        raw = await self._reader.read(READ_CHUNK_SIZE)
        if not raw:
            return None
        clean, reply = self._negotiator.feed(raw)
        if reply:
            self._writer.write(reply)
            await self._writer.drain()
        return clean.decode(self.encoding, errors="replace")

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except ConnectionError:
                pass
