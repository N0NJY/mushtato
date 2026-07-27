"""Integration test for TelnetBridge's SOCKS4 proxy support (item 9 of
the SSL/proxy/NAWS plan): a real background thread + real asyncio event
loop + a real relaying fake SOCKS4 proxy + a real fake target server,
mirroring test_telnet_bridge_integration.py's own established pattern.
"""

import asyncio
import threading

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from gui.windows.telnet_bridge import TelnetBridge


def _pump_until(qapp, predicate, timeout_seconds=3.0):
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


async def _relay(reader, writer):
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


def _start_target_and_proxy_in_background(ready: threading.Event, host_ports: dict):
    loop = asyncio.new_event_loop()
    state: dict = {}

    async def target_handler(reader, writer):
        writer.write(b"Welcome to TestMUD via a real proxied bridge!\r\n")
        await writer.drain()
        line = await reader.readline()
        if line == b"look\r\n":
            writer.write(b"You see nothing special.\r\n")
            await writer.drain()
        writer.close()

    async def proxy_handler(client_reader, client_writer):
        header = await client_reader.readexactly(8)
        rest = bytearray()
        while True:
            byte = await client_reader.readexactly(1)
            rest += byte
            if header[4:8] == bytes((0, 0, 0, 1)):
                if rest.count(b"\x00") >= 2:
                    break
            elif byte == b"\x00":
                break
        target_reader, target_writer = await asyncio.open_connection(
            host_ports["target_host"], host_ports["target_port"]
        )
        client_writer.write(bytes((0, 0x5A, 0, 0, 0, 0, 0, 0)))
        await client_writer.drain()
        await asyncio.gather(
            _relay(client_reader, target_writer), _relay(target_reader, client_writer)
        )

    async def serve():
        target_server = await asyncio.start_server(target_handler, "127.0.0.1", 0)
        target_host, target_port = target_server.sockets[0].getsockname()[:2]
        host_ports["target_host"] = target_host
        host_ports["target_port"] = target_port

        proxy_server = await asyncio.start_server(proxy_handler, "127.0.0.1", 0)
        proxy_host, proxy_port = proxy_server.sockets[0].getsockname()[:2]
        host_ports["proxy_host"] = proxy_host
        host_ports["proxy_port"] = proxy_port

        ready.set()
        async with target_server, proxy_server:
            await asyncio.gather(target_server.serve_forever(), proxy_server.serve_forever())

    async def main():
        state["task"] = asyncio.current_task()
        try:
            await serve()
        except asyncio.CancelledError:
            pass

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return loop, state


def test_bridge_connects_through_a_real_socks4_proxy(qapp):
    ready = threading.Event()
    host_ports: dict = {}
    server_loop, server_state = _start_target_and_proxy_in_background(ready, host_ports)
    assert ready.wait(timeout=3), "fake target/proxy servers never started"

    bridge = TelnetBridge(
        host_ports["target_host"],
        host_ports["target_port"],
        proxy_host=host_ports["proxy_host"],
        proxy_port=host_ports["proxy_port"],
    )
    received = []
    bridge.textReceived.connect(received.append)
    connected_spy = QSignalSpy(bridge.connected)

    bridge.start()

    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected through proxy"
    assert _pump_until(
        qapp, lambda: any("via a real proxied bridge" in chunk for chunk in received)
    ), f"never received target's banner, got: {received}"

    bridge.send_line("look")
    assert _pump_until(
        qapp, lambda: any("You see nothing special." in chunk for chunk in received)
    ), f"never received response, got: {received}"

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)
