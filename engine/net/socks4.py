"""Hand-rolled SOCKS4/SOCKS4a client handshake (item 9 of the SSL/
proxy/NAWS plan) -- verified directly against real Potato's own
implementation (``~/git/potato/potato.vfs/lib/potato-proxy-SOCKS4.tcl``)
before writing this, not assumed from general protocol knowledge alone.
A small, self-contained protocol -- simpler than the Telnet IAC
negotiator this project already hand-rolls -- matching this project's
existing philosophy of owning well-understood protocols directly
rather than adding a dependency for one this size.

Real finding from that verification, correcting an assumption made
before reading the source closely: Potato's real SOCKS4 support already
includes the SOCKS4a hostname extension -- given a literal dotted-IPv4
address, it sends the address directly (classic SOCKS4); given a
hostname, it uses SOCKS4a's placeholder address (0.0.0.1) plus the
hostname appended after the user-ID field, letting the *proxy* resolve
DNS rather than doing it client-side. Replicated here exactly, not the
also-valid-but-not-what-Potato-does alternative of resolving the
hostname ourselves before ever talking to the proxy.
"""

from __future__ import annotations

import asyncio
import re

_SOCKS4_VERSION = 4
_CMD_CONNECT = 1
_REPLY_GRANTED = 0x5A
_IDENTD_FAILURE_CODES = (0x5C, 0x5D)

_IPV4_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


class Socks4Error(Exception):
    """Raised when the proxy rejects (or never properly answers) a
    SOCKS4/SOCKS4a CONNECT request.
    """


def _encode_request(dest_host: str, dest_port: int) -> bytes:
    port_bytes = bytes((dest_port // 256, dest_port % 256))
    user_id = b"\x00"  # no username offered, matching Potato's own real choice
    if _IPV4_RE.match(dest_host):
        ip_bytes = bytes(int(part) for part in dest_host.split("."))
        host_suffix = b""
    else:
        ip_bytes = bytes((0, 0, 0, 1))  # SOCKS4a placeholder
        host_suffix = dest_host.encode("ascii") + b"\x00"
    return bytes((_SOCKS4_VERSION, _CMD_CONNECT)) + port_bytes + ip_bytes + user_id + host_suffix


async def socks4_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    dest_host: str,
    dest_port: int,
) -> None:
    """Performs the SOCKS4/SOCKS4a CONNECT handshake on an already-open
    connection to the proxy itself (``reader``/``writer``), asking it
    to relay to ``dest_host``:``dest_port``. Raises ``Socks4Error`` if
    the proxy rejects the request or closes the connection before
    replying in full; returns normally (nothing) on success, at which
    point ``reader``/``writer`` are ready to carry the actual relayed
    traffic.
    """
    writer.write(_encode_request(dest_host, dest_port))
    await writer.drain()

    try:
        reply = await reader.readexactly(8)
    except asyncio.IncompleteReadError:
        raise Socks4Error("Connection closed by proxy server.") from None

    status = reply[1]
    if status == _REPLY_GRANTED:
        return
    if status in _IDENTD_FAILURE_CODES:
        raise Socks4Error("identd not running / user ID could not be verified")
    raise Socks4Error(
        f"Proxy server rejected request for {dest_host}:{dest_port} (status {status:#x})"
    )
