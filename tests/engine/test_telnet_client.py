"""Headless test for TelnetClient against a local loopback fake server
(no live MUD/MUSH server, no external network) -- exercises the full
connect / negotiate / send / receive path together.

Uses plain ``asyncio.run`` rather than a pytest-asyncio plugin, since
pytest is the only test dependency in pyproject.toml (SPEC.md section
5) and this doesn't need anything beyond stdlib asyncio.
"""

import asyncio
import socket

from engine.net.client import TelnetClient, _configure_keepalive
from engine.net.telnet import DONT, IAC, NOP, WILL


async def _fake_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    # Offer an option the client should refuse, then send a banner line.
    writer.write(bytes((IAC, WILL, 1)))  # WILL ECHO
    await writer.drain()

    reply = await reader.readexactly(3)
    assert reply == bytes((IAC, DONT, 1))

    writer.write(b"Welcome to TestMUD!\r\n")
    await writer.drain()

    line = await reader.readline()
    assert line == b"look\r\n"

    writer.write(b"You see nothing special.\r\n")
    await writer.drain()
    writer.close()


async def _read_text(client: TelnetClient) -> str:
    """Read chunks until one carries actual text.

    A single ``client.read()`` call may consume nothing but a telnet
    negotiation reply and return ``""`` (per its documented contract),
    so callers loop past those rather than treating them as the
    awaited application text.
    """
    while True:
        chunk = await client.read()
        assert chunk is not None, "connection closed unexpectedly"
        if chunk:
            return chunk


async def _run() -> None:
    server = await asyncio.start_server(_fake_server, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]

    async with server:
        client = TelnetClient(host, port)
        await client.connect()

        banner = await _read_text(client)
        assert banner == "Welcome to TestMUD!\r\n"

        await client.send_line("look")

        response = await _read_text(client)
        assert response == "You see nothing special.\r\n"

        await client.close()


def test_connect_negotiate_send_and_receive():
    asyncio.run(_run())


# -- Keepalive (real, reported bug fix: a silent network drop was --
# -- never detected because nothing enabled TCP keepalive) ----------


def test_configure_keepalive_enables_so_keepalive_on_a_real_socket():
    a, b = socket.socketpair()
    try:
        assert a.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) == 0
        _configure_keepalive(a)
        assert a.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
    finally:
        a.close()
        b.close()


def test_configure_keepalive_tunes_linux_specific_options_when_available():
    if not hasattr(socket, "TCP_KEEPIDLE"):
        return  # not Linux -- nothing further to check here
    # AF_UNIX sockets (used by the SO_KEEPALIVE test above) don't
    # support IPPROTO_TCP options -- a real AF_INET pair is needed for
    # the TCP-specific setsockopt calls to actually apply.
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client_sock = socket.create_connection(server.getsockname())
    try:
        from engine.net.client import (
            KEEPALIVE_IDLE_SECONDS,
            KEEPALIVE_INTERVAL_SECONDS,
            KEEPALIVE_PROBE_COUNT,
        )

        _configure_keepalive(client_sock)
        assert client_sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE) == (
            KEEPALIVE_IDLE_SECONDS
        )
        assert client_sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL) == (
            KEEPALIVE_INTERVAL_SECONDS
        )
        assert client_sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT) == (
            KEEPALIVE_PROBE_COUNT
        )
    finally:
        client_sock.close()
        server.close()


def test_configure_keepalive_never_raises_even_if_a_knob_is_unsupported():
    # A socket type keepalive tuning genuinely can't apply to (AF_UNIX)
    # must not crash connect() -- SO_KEEPALIVE alone still gets set.
    a, b = socket.socketpair()
    try:
        _configure_keepalive(a)  # must not raise
    finally:
        a.close()
        b.close()


async def _run_real_connection_has_keepalive_enabled() -> None:
    async def fake_server(reader, writer):
        del reader
        writer.close()  # a handler that never closes its side hangs server.wait_closed()

    server = await asyncio.start_server(fake_server, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    async with server:
        client = TelnetClient(host, port)
        await client.connect()
        raw_socket = client._writer.get_extra_info("socket")
        assert raw_socket.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
        await client.close()


def test_a_real_connect_call_actually_enables_keepalive_on_the_socket():
    # Proves the wiring, not just the helper function in isolation --
    # TelnetClient.connect() must actually call _configure_keepalive.
    asyncio.run(_run_real_connection_has_keepalive_enabled())


async def _run_send_nop() -> None:
    received = {}

    async def fake_server(reader, writer):
        received["bytes"] = await reader.readexactly(2)
        writer.close()

    server = await asyncio.start_server(fake_server, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    async with server:
        client = TelnetClient(host, port)
        await client.connect()
        await client.send_nop()
        await asyncio.sleep(0.1)  # let the fake server's read complete
        await client.close()

    assert received["bytes"] == bytes((IAC, NOP))


def test_send_nop_sends_exactly_iac_nop():
    asyncio.run(_run_send_nop())
