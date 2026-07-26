"""Integration test for SshBridge: a real background thread, a real
asyncio event loop, and a real (local, throwaway) asyncssh server --
not just isolated units. Mirrors test_telnet_bridge_integration.py's
own established pattern exactly, including why it matters (proving the
cross-thread signal bridge actually works end to end, not just against
a fake bridge).
"""

import asyncio
import json
import threading

import asyncssh
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from engine.net import HostKeyStore
from gui.windows.ssh_bridge import SshBridge


def _pump_until(qapp, predicate, timeout_seconds=3.0):
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _FakeServer(asyncssh.SSHServer):
    def begin_auth(self, username):  # noqa: ARG002
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return username == "testuser" and password == "testpass"


async def _fake_shell(process) -> None:
    process.stdout.write("Welcome to TestShell!\r\n")
    async for line in process.stdin:
        text = line.rstrip("\r\n")
        if text == "look":
            process.stdout.write("You see nothing special.\r\n")
    process.exit(0)


def _start_fake_ssh_server_in_background(ready: threading.Event, host_port: dict):
    """Same shutdown-by-task-cancellation pattern as telnet_bridge's own
    integration test helper, adapted for asyncssh.listen().
    """
    loop = asyncio.new_event_loop()
    state: dict = {}

    async def serve():
        key = asyncssh.generate_private_key("ssh-rsa")
        server = await asyncssh.listen(
            "127.0.0.1", 0, server_host_keys=[key],
            process_factory=_fake_shell, server_factory=_FakeServer,
        )
        host, port = server.sockets[0].getsockname()[:2]
        host_port["host"] = host
        host_port["port"] = port
        ready.set()
        async with server:
            await server.wait_closed()

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


def test_bridge_connects_receives_and_sends_against_real_server(qapp, tmp_path):
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_ssh_server_in_background(ready, host_port)
    assert ready.wait(timeout=3), "fake ssh server never started"

    store = HostKeyStore(tmp_path / "known_hosts.json")
    bridge = SshBridge(host_port["host"], host_port["port"], "testuser", "testpass", store)
    received = []
    bridge.textReceived.connect(received.append)
    connected_spy = QSignalSpy(bridge.connected)

    bridge.start()

    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected"
    assert _pump_until(
        qapp, lambda: any("Welcome to TestShell!" in chunk for chunk in received)
    ), f"never received banner, got: {received}"

    bridge.send_line("look")

    assert _pump_until(
        qapp, lambda: any("You see nothing special." in chunk for chunk in received)
    ), f"never received response, got: {received}"

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)


def test_wrong_password_emits_connection_failed(qapp, tmp_path):
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_ssh_server_in_background(ready, host_port)
    assert ready.wait(timeout=3), "fake ssh server never started"

    store = HostKeyStore(tmp_path / "known_hosts.json")
    bridge = SshBridge(host_port["host"], host_port["port"], "testuser", "wrongpass", store)
    failed_spy = QSignalSpy(bridge.connectionFailed)
    connected_spy = QSignalSpy(bridge.connected)

    bridge.start()

    assert _pump_until(qapp, lambda: failed_spy.count() >= 1), "connectionFailed never emitted"
    assert connected_spy.count() == 0

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)


def test_host_key_mismatch_emits_connection_failed_naming_ssh_forget(qapp, tmp_path):
    # Pre-seed the known-hosts store with a WRONG key for this exact
    # host:port -- simulating "we previously trusted a different key
    # here" -- rather than literally standing up two real servers on
    # the same port sequentially (which would race against the first
    # server's socket actually being released before the second binds).
    # engine/net/test_ssh_client.py already proves the underlying
    # HostKeyStore/SshClient mismatch mechanics directly; this test's
    # job is only to prove SshBridge surfaces it correctly as a Qt
    # signal with the right message.
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_ssh_server_in_background(ready, host_port)
    assert ready.wait(timeout=3), "fake ssh server never started"

    known_hosts_path = tmp_path / "known_hosts.json"
    wrong_key = asyncssh.generate_private_key("ssh-rsa").convert_to_public()
    entry = f"{host_port['host']}:{host_port['port']}"
    known_hosts_path.write_text(
        json.dumps({entry: wrong_key.export_public_key().decode("ascii")}), encoding="utf-8"
    )
    store = HostKeyStore(known_hosts_path)

    mismatched = SshBridge(host_port["host"], host_port["port"], "testuser", "testpass", store)
    failed_spy = QSignalSpy(mismatched.connectionFailed)
    connected_spy = QSignalSpy(mismatched.connected)
    mismatched.start()

    assert _pump_until(qapp, lambda: failed_spy.count() >= 1), "connectionFailed never emitted"
    assert connected_spy.count() == 0
    message = failed_spy.at(0)[0]
    assert "/ssh-forget" in message
    assert f"{host_port['host']}:{host_port['port']}" in message

    mismatched.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)
