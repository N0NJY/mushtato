"""Headless test for TelnetClient against a local loopback fake server
(no live MUD/MUSH server, no external network) -- exercises the full
connect / negotiate / send / receive path together.

Uses plain ``asyncio.run`` rather than a pytest-asyncio plugin, since
pytest is the only test dependency in pyproject.toml (SPEC.md section
5) and this doesn't need anything beyond stdlib asyncio.
"""

import asyncio

from engine.net.client import TelnetClient
from engine.net.telnet import DONT, IAC, WILL


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
