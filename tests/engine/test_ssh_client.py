"""Headless tests for engine/net/ssh_client.py -- SshClient and
HostKeyStore -- against a local, throwaway asyncssh test server on an
OS-assigned ephemeral port. No real network, no real credentials, and
no interaction with the user's actual ``~/.ssh`` files at any point.

Plain ``asyncio.run`` throughout, matching test_telnet_client.py's own
established convention (no pytest-asyncio dependency needed).
"""

import asyncio
from pathlib import Path

import asyncssh
import pytest

from engine.net.ssh_client import HostKeyMismatch, HostKeyStore, SshClient


class _FakeServer(asyncssh.SSHServer):
    def begin_auth(self, username):  # noqa: ARG002 -- asyncssh callback signature
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return username == "testuser" and password == "testpass"


async def _fake_shell(process) -> None:
    process.stdout.write("Welcome to fake shell\r\n$ ")
    async for line in process.stdin:
        text = line.rstrip("\r\n")
        if text == "exit":
            break
        process.stdout.write(f"echo:{text}\r\n$ ")
    process.exit(0)


async def _start_server(host_key):
    server = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_host_keys=[host_key],
        process_factory=_fake_shell,
        server_factory=_FakeServer,
    )
    port = server.sockets[0].getsockname()[1]
    return server, port


async def _read_text(client: SshClient) -> str:
    while True:
        chunk = await client.read()
        assert chunk is not None, "connection closed unexpectedly"
        if chunk:
            return chunk


# -- basic connect / shell round trip --------------------------------


async def _run_connect_and_echo(known_hosts_path: Path) -> None:
    key = asyncssh.generate_private_key("ssh-rsa")
    server, port = await _start_server(key)
    async with server:
        store = HostKeyStore(known_hosts_path)
        client = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        await client.connect()

        banner = await _read_text(client)
        assert "Welcome to fake shell" in banner

        await client.send_line("hello world")
        echoed = await _read_text(client)
        assert "echo:hello world" in echoed

        await client.send_line("exit")
        await client.close()


def test_connect_send_and_receive(tmp_path: Path):
    asyncio.run(_run_connect_and_echo(tmp_path / "known_hosts.json"))


# -- authentication -----------------------------------------------------


async def _run_wrong_password(known_hosts_path: Path) -> None:
    key = asyncssh.generate_private_key("ssh-rsa")
    server, port = await _start_server(key)
    async with server:
        store = HostKeyStore(known_hosts_path)
        client = SshClient("127.0.0.1", port, "testuser", "wrongpass", store)
        with pytest.raises(asyncssh.PermissionDenied):
            await client.connect()


def test_wrong_password_raises_permission_denied(tmp_path: Path):
    asyncio.run(_run_wrong_password(tmp_path / "known_hosts.json"))


# -- HostKeyStore: trust-on-first-use ------------------------------------


async def _run_tofu_trust_then_reuse(known_hosts_path: Path) -> None:
    key = asyncssh.generate_private_key("ssh-rsa")
    server, port = await _start_server(key)
    async with server:
        store = HostKeyStore(known_hosts_path)

        first = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        await first.connect()  # first-ever connect: trusts and saves
        await first.close()

        assert known_hosts_path.exists()

        second = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        await second.connect()  # same key: succeeds silently
        await second.close()


def test_first_connect_trusts_and_saves_the_key(tmp_path: Path):
    asyncio.run(_run_tofu_trust_then_reuse(tmp_path / "known_hosts.json"))


async def _run_tofu_mismatch(known_hosts_path: Path) -> None:
    key1 = asyncssh.generate_private_key("ssh-rsa")
    server1, port = await _start_server(key1)
    store = HostKeyStore(known_hosts_path)

    async with server1:
        trusted = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        await trusted.connect()
        await trusted.close()

    # A second server on the SAME port with a DIFFERENT key -- simulates
    # an impersonation/MITM scenario, or (more innocently) a legitimate
    # server reinstall.
    key2 = asyncssh.generate_private_key("ssh-rsa")
    server2 = await asyncssh.listen(
        "127.0.0.1", port, server_host_keys=[key2],
        process_factory=_fake_shell, server_factory=_FakeServer,
    )
    async with server2:
        mismatched = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        with pytest.raises(HostKeyMismatch) as exc_info:
            await mismatched.connect()
        assert exc_info.value.old_fingerprint != exc_info.value.new_fingerprint
        assert exc_info.value.host == "127.0.0.1"
        assert exc_info.value.port == port


def test_changed_key_is_rejected_not_silently_trusted(tmp_path: Path):
    asyncio.run(_run_tofu_mismatch(tmp_path / "known_hosts.json"))


async def _run_forget_then_reconnect(known_hosts_path: Path) -> None:
    key1 = asyncssh.generate_private_key("ssh-rsa")
    server1, port = await _start_server(key1)
    store = HostKeyStore(known_hosts_path)

    async with server1:
        trusted = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        await trusted.connect()
        await trusted.close()

    key2 = asyncssh.generate_private_key("ssh-rsa")
    server2 = await asyncssh.listen(
        "127.0.0.1", port, server_host_keys=[key2],
        process_factory=_fake_shell, server_factory=_FakeServer,
    )
    async with server2:
        rejected = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        with pytest.raises(HostKeyMismatch):
            await rejected.connect()

        assert store.forget("127.0.0.1", port) is True

        reconnected = SshClient("127.0.0.1", port, "testuser", "testpass", store)
        await reconnected.connect()  # forgotten -- treated as first-use again
        await reconnected.close()


def test_forget_allows_reconnecting_after_a_key_change(tmp_path: Path):
    asyncio.run(_run_forget_then_reconnect(tmp_path / "known_hosts.json"))


def test_forget_a_host_with_no_saved_entry_returns_false(tmp_path: Path):
    store = HostKeyStore(tmp_path / "known_hosts.json")
    assert store.forget("nowhere.example.com", 22) is False


def test_host_key_store_only_writes_the_path_it_was_given(tmp_path: Path):
    # HostKeyStore never assumes or falls back to any other location
    # (e.g. a real ~/.ssh/known_hosts) -- only the exact path passed in
    # at construction is ever touched.
    custom_path = tmp_path / "totally_isolated.json"
    store = HostKeyStore(custom_path)
    key = asyncssh.generate_private_key("ssh-rsa").convert_to_public()

    assert store.check("example.com", 22, key) is True

    assert custom_path.exists()
    assert list(tmp_path.iterdir()) == [custom_path]


# -- connection-level failures -------------------------------------------


async def _run_connection_refused() -> None:
    store = HostKeyStore(Path("/tmp/unused_known_hosts_for_refused_test.json"))
    client = SshClient("127.0.0.1", 1, "testuser", "testpass", store)
    with pytest.raises(OSError):
        await client.connect()


def test_connection_refused_raises_oserror():
    asyncio.run(_run_connection_refused())
