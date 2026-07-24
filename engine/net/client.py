"""Asyncio telnet client.

Hand-rolled IAC negotiation (see :mod:`engine.net.telnet`) on top of
plain ``asyncio`` streams, rather than a third-party telnet library.
The negotiation needs for this phase are deliberately minimal (refuse
every option) so a small, fully-owned state machine keeps the
dependency list unchanged and stays trivially testable headless.

Post-Phase-9 addition: TCP keepalive. A silent network drop (e.g. the
client's own power/router loss, as opposed to the server cleanly
closing the connection) never arrives as a FIN/RST -- without
keepalive, a plain ``asyncio.open_connection()`` socket's ``read()``
just waits, potentially for hours, since nothing prompts the OS to
notice the peer is unreachable. This is a real, reported bug (not a
theoretical one): the app never showed "Connection closed" on a tab
whose network had actually died, because nothing ever told it to.
Enabling and tuning keepalive is the direct fix -- once the OS detects
the dead peer, the pending ``read()`` fails with an ``OSError``, which
``gui/windows/telnet_bridge.py``'s ``_run()`` already catches and turns
into the existing ``connectionFailed`` signal; no changes needed on
that side at all.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from typing import Optional

from .telnet import IAC, NOP, TelnetNegotiator

READ_CHUNK_SIZE = 4096

# Tuned for "notice within well under a minute", not the OS defaults
# (Linux's own default TCP_KEEPIDLE is 7200s -- two hours -- before even
# the *first* probe). 10s idle before the first probe, a probe every 5s,
# giving up after 3 missed probes -- roughly 25s worst case to detect a
# genuinely dead connection, safely under the 30s auto-reconnect
# interval (gui/windows/session_tab.py) so a retry attempt isn't wasted
# racing a not-yet-detected-dead old connection.
KEEPALIVE_IDLE_SECONDS = 10
KEEPALIVE_INTERVAL_SECONDS = 5
KEEPALIVE_PROBE_COUNT = 3


def _configure_keepalive(sock: socket.socket) -> None:
    """Enable and tune TCP keepalive on ``sock``, best-effort per
    platform. Always sets ``SO_KEEPALIVE`` (universally supported);
    the finer-grained idle/interval/count tuning uses whichever of
    Linux's ``TCP_KEEPIDLE``/``TCP_KEEPINTVL``/``TCP_KEEPCNT`` or
    macOS's single ``TCP_KEEPALIVE`` constant is actually present --
    verified locally on Linux only (this sandbox has no macOS/Windows
    hardware, per CLAUDE.md); wrapped in a broad ``except`` since a
    platform/kernel that doesn't support a given knob should degrade to
    "just SO_KEEPALIVE with OS default timing", never crash the
    connection attempt.
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        if hasattr(socket, "TCP_KEEPIDLE"):  # Linux
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_IDLE_SECONDS)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVAL_SECONDS)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_PROBE_COUNT)
        elif hasattr(socket, "TCP_KEEPALIVE"):  # macOS: one combined idle-time constant
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, KEEPALIVE_IDLE_SECONDS)
        elif sys.platform == "win32" and hasattr(socket, "SIO_KEEPALIVE_VALS"):
            sock.ioctl(
                socket.SIO_KEEPALIVE_VALS,
                (1, KEEPALIVE_IDLE_SECONDS * 1000, KEEPALIVE_INTERVAL_SECONDS * 1000),
            )
    except OSError:
        # SO_KEEPALIVE itself is already set -- fall back to whatever
        # the OS's own default timing is rather than failing the
        # connection over a tuning knob it doesn't support.
        pass


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
        raw_socket = self._writer.get_extra_info("socket")
        if raw_socket is not None:
            _configure_keepalive(raw_socket)

    async def send_line(self, line: str) -> None:
        """Send one line of user input, terminated with CRLF."""
        if self._writer is None:
            raise RuntimeError("not connected")
        data = line.encode(self.encoding, errors="replace").replace(
            bytes((IAC,)), bytes((IAC, IAC))
        )
        self._writer.write(data + b"\r\n")
        await self._writer.drain()

    async def send_nop(self) -> None:
        """Send a bare Telnet IAC NOP -- a "no operation" byte pair a
        server ignores silently (RFC 854). Application-level keepalive,
        distinct from (and complementary to) the OS-level TCP keepalive
        ``connect()`` already enables -- verified against Potato's real
        source (``potato-telnet.tcl``'s ``send_keepalive``, which sends
        exactly ``$tCmd(IAC)$tCmd(NOP)``) as the mechanism, though not
        against a confirmed real scheduling interval -- Potato's own
        source defines that proc but no call site for it was found in
        the visible .tcl files, so the *interval* MushTato schedules
        this at (see gui/windows/telnet_bridge.py) is this project's
        own reasonable choice, not a verified-from-source Potato value.
        """
        if self._writer is None:
            raise RuntimeError("not connected")
        self._writer.write(bytes((IAC, NOP)))
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
