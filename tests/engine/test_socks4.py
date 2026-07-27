"""Headless tests for engine/net/socks4.py -- against a local, real
fake SOCKS4 proxy server, matching this project's established
convention (plain asyncio.run, no live network). Byte layout checked
directly against Potato's own real implementation
(potato-proxy-SOCKS4.tcl), not assumed from general protocol knowledge.
"""

import asyncio

import pytest

from engine.net.socks4 import Socks4Error, socks4_connect


async def _fake_socks4_proxy(reply_status: int, captured: dict):
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        header = await reader.readexactly(8)  # VN CD DSTPORT(2) DSTIP(4)
        captured["header"] = header
        # Read the rest: userid (null-terminated), and -- for SOCKS4a --
        # an optional hostname (also null-terminated) if DSTIP was the
        # 0.0.0.1 placeholder.
        rest = bytearray()
        while True:
            byte = await reader.readexactly(1)
            rest += byte
            if header[4:8] == bytes((0, 0, 0, 1)):
                # SOCKS4a: userid\x00 then hostname\x00 -- two null
                # terminators total.
                if rest.count(b"\x00") >= 2:
                    break
            else:
                if byte == b"\x00":
                    break
        captured["rest"] = bytes(rest)
        writer.write(bytes((0, reply_status, 0, 0, 0, 0, 0, 0)))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    return server, host, port


async def _run_ip_literal_target_granted() -> None:
    captured: dict = {}
    server, host, port = await _fake_socks4_proxy(0x5A, captured)
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        await socks4_connect(reader, writer, "10.0.0.5", 4201)
        writer.close()

    header = captured["header"]
    assert header[0] == 4  # SOCKS version 4
    assert header[1] == 1  # CD = CONNECT
    assert header[2:4] == bytes((4201 // 256, 4201 % 256))
    assert header[4:8] == bytes((10, 0, 0, 5))  # the real IP, not the SOCKS4a placeholder
    assert captured["rest"] == b"\x00"  # empty userid, no hostname suffix


def test_ip_literal_target_uses_classic_socks4_with_the_real_ip():
    asyncio.run(_run_ip_literal_target_granted())


async def _run_hostname_target_granted() -> None:
    captured: dict = {}
    server, host, port = await _fake_socks4_proxy(0x5A, captured)
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        await socks4_connect(reader, writer, "example.com", 4201)
        writer.close()

    header = captured["header"]
    assert header[4:8] == bytes((0, 0, 0, 1))  # SOCKS4a placeholder IP
    assert captured["rest"] == b"\x00example.com\x00"  # empty userid, then the hostname


def test_hostname_target_uses_socks4a_with_a_placeholder_ip_and_appended_hostname():
    asyncio.run(_run_hostname_target_granted())


async def _run_rejected(status: int) -> None:
    captured: dict = {}
    server, host, port = await _fake_socks4_proxy(status, captured)
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        with pytest.raises(Socks4Error) as exc_info:
            await socks4_connect(reader, writer, "example.com", 4201)
        writer.close()
    return exc_info.value


def test_rejected_request_raises_socks4error():
    asyncio.run(_run_rejected(0x5B))


def test_identd_failure_status_raises_a_specific_message():
    async def run():
        captured: dict = {}
        server, host, port = await _fake_socks4_proxy(0x5C, captured)
        async with server:
            reader, writer = await asyncio.open_connection(host, port)
            with pytest.raises(Socks4Error, match="identd"):
                await socks4_connect(reader, writer, "example.com", 4201)
            writer.close()

    asyncio.run(run())


async def _run_proxy_closes_before_replying() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readexactly(8)
        writer.close()  # closes without ever sending the 8-byte reply

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        with pytest.raises(Socks4Error, match="Connection closed"):
            await socks4_connect(reader, writer, "10.0.0.5", 4201)
        writer.close()


def test_proxy_closing_before_a_full_reply_raises_a_clear_error():
    asyncio.run(_run_proxy_closes_before_replying())
