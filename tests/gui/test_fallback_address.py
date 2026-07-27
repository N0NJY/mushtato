"""Integration tests for TelnetBridge's fallback second address (item 8
of the SSL/proxy/NAWS plan): a real background thread + real asyncio
event loop + real local fake servers, mirroring
test_telnet_bridge_integration.py's own established pattern -- proving
the actual claims (a failed primary really does fall through to a
working secondary; a later attempt tries primary first again, not
"sticky" toward whichever one worked last), not just that the code
takes the intended branch.
"""

import asyncio
import socket
import threading

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from gui.windows.telnet_bridge import TelnetBridge


def _reserve_and_release_a_port() -> int:
    """Binds a real socket to an OS-assigned port, then closes it
    immediately -- reliably produces a port nothing is listening on
    (a genuine "connection refused"), rather than guessing at an
    arbitrary fixed port that might collide with something real on the
    test machine.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _pump_until(qapp, predicate, timeout_seconds=3.0):
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _start_fake_server_in_background(banner: bytes, ready: threading.Event, host_port: dict):
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        del reader
        writer.write(banner)
        await writer.drain()

    loop = asyncio.new_event_loop()
    state: dict = {}

    async def serve():
        server = await asyncio.start_server(handler, "127.0.0.1", 0)
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


def test_a_failed_primary_falls_through_to_a_working_secondary(qapp):
    dead_port = _reserve_and_release_a_port()  # nothing listens here -- refused

    ready = threading.Event()
    secondary_host_port: dict = {}
    secondary_loop, secondary_state = _start_fake_server_in_background(
        b"Welcome to the SECONDARY server!\r\n", ready, secondary_host_port
    )
    assert ready.wait(timeout=3), "secondary server never started"

    bridge = TelnetBridge(
        "127.0.0.1",
        dead_port,
        host2=secondary_host_port["host"],
        port2=secondary_host_port["port"],
    )
    received = []
    bridge.textReceived.connect(received.append)
    connected_spy = QSignalSpy(bridge.connected)
    failed_spy = QSignalSpy(bridge.connectionFailed)

    bridge.start()

    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected via fallback"
    assert _pump_until(
        qapp, lambda: any("SECONDARY" in chunk for chunk in received)
    ), f"never received secondary's banner, got: {received}"
    assert failed_spy.count() == 0  # the primary's own failure must never surface as a user-facing error

    bridge.stop()
    secondary_loop.call_soon_threadsafe(secondary_state["task"].cancel)


def test_both_addresses_failing_reports_the_secondary_s_own_failure(qapp):
    dead_port1 = _reserve_and_release_a_port()
    dead_port2 = _reserve_and_release_a_port()

    bridge = TelnetBridge("127.0.0.1", dead_port1, host2="127.0.0.1", port2=dead_port2)
    failed_spy = QSignalSpy(bridge.connectionFailed)

    bridge.start()

    assert _pump_until(qapp, lambda: failed_spy.count() >= 1), "connectionFailed never fired"
    bridge.stop()


def test_a_later_reconnect_tries_the_primary_first_again_not_sticky(qapp):
    # First attempt: primary dead, secondary alive -- connects via
    # fallback exactly like the test above. Then the primary is made
    # reachable too, and a fresh connect attempt (a real reconnect, via
    # stop()+start() on the same bridge) must try *primary* first again,
    # not silently keep using the secondary that worked last time.
    primary_port = _reserve_and_release_a_port()  # dead for the first attempt only

    ready_secondary = threading.Event()
    secondary_host_port: dict = {}
    secondary_loop, secondary_state = _start_fake_server_in_background(
        b"Welcome to the SECONDARY server!\r\n", ready_secondary, secondary_host_port
    )
    assert ready_secondary.wait(timeout=3), "secondary server never started"

    bridge = TelnetBridge(
        "127.0.0.1",
        primary_port,
        host2=secondary_host_port["host"],
        port2=secondary_host_port["port"],
    )
    received = []
    bridge.textReceived.connect(received.append)
    connected_spy = QSignalSpy(bridge.connected)

    bridge.start()
    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected via fallback"
    assert _pump_until(qapp, lambda: any("SECONDARY" in chunk for chunk in received))

    bridge.stop()

    # Now make the primary reachable too, using the exact same port.
    ready_primary = threading.Event()
    primary_host_port: dict = {"port": primary_port}

    async def primary_handler(reader, writer):
        del reader
        writer.write(b"Welcome to the PRIMARY server!\r\n")
        await writer.drain()

    primary_loop = asyncio.new_event_loop()
    primary_state: dict = {}

    async def serve_primary():
        server = await asyncio.start_server(primary_handler, "127.0.0.1", primary_port)
        ready_primary.set()
        async with server:
            await server.serve_forever()

    async def primary_main():
        primary_state["task"] = asyncio.current_task()
        try:
            await serve_primary()
        except asyncio.CancelledError:
            pass

    def run_primary():
        asyncio.set_event_loop(primary_loop)
        primary_loop.run_until_complete(primary_main())

    thread = threading.Thread(target=run_primary, daemon=True)
    thread.start()
    assert ready_primary.wait(timeout=3), "primary server never started"

    received.clear()
    connected_spy2 = QSignalSpy(bridge.connected)
    bridge.start()

    assert _pump_until(qapp, lambda: connected_spy2.count() >= 1), "never reconnected"
    assert _pump_until(
        qapp, lambda: any("PRIMARY" in chunk for chunk in received)
    ), f"did not try primary first on reconnect, got: {received}"

    bridge.stop()
    secondary_loop.call_soon_threadsafe(secondary_state["task"].cancel)
    primary_loop.call_soon_threadsafe(primary_state["task"].cancel)


def test_no_fallback_configured_behaves_exactly_as_before(qapp):
    dead_port = _reserve_and_release_a_port()

    bridge = TelnetBridge("127.0.0.1", dead_port)  # host2/port2 both left at their defaults
    failed_spy = QSignalSpy(bridge.connectionFailed)

    bridge.start()

    assert _pump_until(qapp, lambda: failed_spy.count() >= 1), "connectionFailed never fired"
    bridge.stop()
