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


def test_on_text_callback_fires_synchronously_on_the_background_thread_not_the_gui_thread(qapp):
    # This is the actual claim Phase 9's checkpoint needed verified,
    # not just asserted: the on_text callback -- where line-buffering/
    # trigger dispatch will run -- must execute on TelnetBridge's own
    # background thread, never the GUI thread, since that's what keeps
    # a slow/hung trigger's run_with_timeout wait off the UI.
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_server_in_background(ready, host_port)
    assert ready.wait(timeout=3), "fake server never started"

    gui_thread = threading.current_thread()
    callback_threads = []
    received_chunks = []

    def on_text(chunk):
        callback_threads.append(threading.current_thread())
        received_chunks.append(chunk)

    bridge = TelnetBridge(host_port["host"], host_port["port"], on_text=on_text)
    bridge.start()

    assert _pump_until(
        qapp, lambda: any("Welcome to TestMUD!" in c for c in received_chunks)
    ), f"on_text never fired, got: {received_chunks}"

    assert callback_threads, "on_text was never called"
    assert all(t is not gui_thread for t in callback_threads)

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)


def test_run_in_background_executes_off_the_gui_thread(qapp):
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_server_in_background(ready, host_port)
    assert ready.wait(timeout=3), "fake server never started"

    bridge = TelnetBridge(host_port["host"], host_port["port"])
    connected_spy = QSignalSpy(bridge.connected)
    bridge.start()
    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected"

    gui_thread = threading.current_thread()
    result = {}

    def blocking_work():
        result["thread"] = threading.current_thread()
        result["done"] = True

    bridge.run_in_background(blocking_work)

    assert _pump_until(qapp, lambda: result.get("done")), "run_in_background never ran"
    assert result["thread"] is not gui_thread

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)


def test_on_text_callback_fires_before_the_equivalent_textReceived_signal(qapp):
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_server_in_background(ready, host_port)
    assert ready.wait(timeout=3), "fake server never started"

    order = []
    bridge = TelnetBridge(
        host_port["host"], host_port["port"], on_text=lambda chunk: order.append("on_text")
    )
    bridge.textReceived.connect(lambda chunk: order.append("textReceived"))
    bridge.start()

    assert _pump_until(qapp, lambda: len(order) >= 2), f"never got both, got: {order}"
    assert order[:2] == ["on_text", "textReceived"]

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)


def _start_byte_recording_server_in_background(ready: threading.Event, host_port: dict, received: list):
    """Like _start_fake_server_in_background, but the server just
    records every byte it receives (rather than scripting a specific
    banner/response exchange) -- used to prove the NOP keepalive
    heartbeat actually reaches the wire.
    """
    loop = asyncio.new_event_loop()
    state: dict = {}

    async def record(reader, writer):
        del writer
        while True:
            chunk = await reader.read(64)
            if not chunk:
                return
            received.extend(chunk)

    async def serve():
        server = await asyncio.start_server(record, "127.0.0.1", 0)
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


def test_nop_keepalive_sends_iac_nop_periodically_when_enabled(qapp):
    from engine.net.telnet import IAC, NOP

    ready = threading.Event()
    host_port: dict = {}
    received: list = []
    server_loop, server_state = _start_byte_recording_server_in_background(ready, host_port, received)
    assert ready.wait(timeout=3), "fake server never started"

    bridge = TelnetBridge(host_port["host"], host_port["port"], nop_keepalive=True)
    bridge.NOP_KEEPALIVE_INTERVAL_SECONDS = 0.05  # instance override -- don't wait 60 real seconds
    connected_spy = QSignalSpy(bridge.connected)
    bridge.start()

    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected"
    assert _pump_until(
        qapp, lambda: received.count(IAC) >= 2, timeout_seconds=3.0
    ), f"never received repeated NOPs, got: {received}"
    assert received[:2] == [IAC, NOP]

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)


def test_no_nop_keepalive_sent_when_disabled(qapp):
    ready = threading.Event()
    host_port: dict = {}
    received: list = []
    server_loop, server_state = _start_byte_recording_server_in_background(ready, host_port, received)
    assert ready.wait(timeout=3), "fake server never started"

    bridge = TelnetBridge(host_port["host"], host_port["port"])  # nop_keepalive defaults to False
    connected_spy = QSignalSpy(bridge.connected)
    bridge.start()
    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected"

    _pump_until(qapp, lambda: False, timeout_seconds=0.3)  # let a moment pass
    assert received == []

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)
