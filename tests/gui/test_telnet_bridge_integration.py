"""Integration test for the actual Phase 5 architecture decision: a
real TelnetBridge (real background thread, real asyncio event loop)
talking to a local loopback fake server, with data crossing back to
the Qt/GUI thread via real signal emission -- not just isolated units.

Not explicitly requested by the phase's test scope, but added because
this is the one thing the whole checkpoint discussion was about; it's
worth proving the cross-thread signal bridge actually works end to end
rather than only testing MainWindow against a fake bridge. Stays
headless/local (asyncio.start_server on 127.0.0.1) -- no live MUD
server, matching CLAUDE.md's testing philosophy.
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


async def _fake_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.write(b"Welcome to TestMUD!\r\n")
    await writer.drain()

    line = await reader.readline()
    assert line == b"look\r\n"

    writer.write(b"You see nothing special.\r\n")
    await writer.drain()
    writer.close()


def _start_fake_server_in_background(ready: threading.Event, host_port: dict):
    """Returns (loop, state). Shut down via
    ``loop.call_soon_threadsafe(state["task"].cancel)`` rather than
    ``loop.stop()`` directly -- stopping a loop while
    run_until_complete is still waiting on its future raises
    "Event loop stopped before Future completed"; cancelling the task
    and letting it be caught inside lets run_until_complete return
    normally instead.
    """
    loop = asyncio.new_event_loop()
    state: dict = {}

    async def serve():
        server = await asyncio.start_server(_fake_server, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        host_port["host"] = host
        host_port["port"] = port
        ready.set()
        async with server:
            await server.serve_forever()

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


def test_bridge_connects_receives_and_sends_against_real_server(qapp):
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_server_in_background(ready, host_port)
    assert ready.wait(timeout=3), "fake server never started"

    bridge = TelnetBridge(host_port["host"], host_port["port"])
    received = []
    bridge.textReceived.connect(received.append)
    connected_spy = QSignalSpy(bridge.connected)

    bridge.start()

    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected"
    assert _pump_until(
        qapp, lambda: any("Welcome to TestMUD!" in chunk for chunk in received)
    ), f"never received banner, got: {received}"

    bridge.send_line("look")

    assert _pump_until(
        qapp, lambda: any("You see nothing special." in chunk for chunk in received)
    ), f"never received response, got: {received}"

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)
