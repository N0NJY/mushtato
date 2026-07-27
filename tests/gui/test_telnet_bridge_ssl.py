"""Integration test for TelnetBridge's SSL/TLS support (item 6 of the
SSL/proxy/NAWS plan): a real background thread + real asyncio event
loop + a real local self-signed TLS server, mirroring
test_telnet_bridge_integration.py's own established pattern exactly --
not just a fake bridge, the same real cross-thread signal delivery.
"""

import asyncio
import datetime
import ssl
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from engine.net.client import CertificateStore
from gui.windows.telnet_bridge import TelnetBridge


def _generate_self_signed_cert(tmp_path: Path, common_name: str = "127.0.0.1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    certfile = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return certfile, keyfile


def _pump_until(qapp, predicate, timeout_seconds=3.0):
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


async def _fake_tls_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.write(b"Welcome to TestMUD over TLS!\r\n")
    await writer.drain()
    line = await reader.readline()
    assert line == b"look\r\n"
    writer.write(b"You see nothing special.\r\n")
    await writer.drain()
    writer.close()


def _start_fake_tls_server_in_background(
    ready: threading.Event, host_port: dict, certfile: Path, keyfile: Path
):
    loop = asyncio.new_event_loop()
    state: dict = {}

    async def serve():
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(certfile), str(keyfile))
        server = await asyncio.start_server(_fake_tls_server, "127.0.0.1", 0, ssl=server_context)
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


def test_bridge_connects_receives_and_sends_over_tls(qapp, tmp_path):
    certfile, keyfile = _generate_self_signed_cert(tmp_path)
    ready = threading.Event()
    host_port: dict = {}
    server_loop, server_state = _start_fake_tls_server_in_background(
        ready, host_port, certfile, keyfile
    )
    assert ready.wait(timeout=3), "fake TLS server never started"

    store = CertificateStore(tmp_path / "known_certs.json")
    bridge = TelnetBridge(
        host_port["host"], host_port["port"], use_ssl=True, cert_store=store
    )
    received = []
    bridge.textReceived.connect(received.append)
    connected_spy = QSignalSpy(bridge.connected)

    bridge.start()

    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "never connected"
    assert _pump_until(
        qapp, lambda: any("Welcome to TestMUD over TLS!" in chunk for chunk in received)
    ), f"never received banner, got: {received}"

    bridge.send_line("look")

    assert _pump_until(
        qapp, lambda: any("You see nothing special." in chunk for chunk in received)
    ), f"never received response, got: {received}"

    bridge.stop()
    server_loop.call_soon_threadsafe(server_state["task"].cancel)


def test_certificate_mismatch_surfaces_via_connection_failed_naming_ssl_forget(qapp, tmp_path):
    # First connect with server1's cert trusts + saves it -- then a
    # second server on the SAME port with a DIFFERENT cert must be
    # rejected via the real connectionFailed signal, not silently
    # trusted, with a message naming the real /ssl-forget command.
    (tmp_path / "server1").mkdir()
    certfile1, keyfile1 = _generate_self_signed_cert(tmp_path / "server1")
    ready1 = threading.Event()
    host_port: dict = {}
    server1_loop, server1_state = _start_fake_tls_server_in_background(
        ready1, host_port, certfile1, keyfile1
    )
    assert ready1.wait(timeout=3), "fake TLS server 1 never started"

    store = CertificateStore(tmp_path / "known_certs.json")
    first_bridge = TelnetBridge(
        host_port["host"], host_port["port"], use_ssl=True, cert_store=store
    )
    connected_spy = QSignalSpy(first_bridge.connected)
    first_bridge.start()
    assert _pump_until(qapp, lambda: connected_spy.count() >= 1), "first connect never succeeded"
    first_bridge.stop()
    server1_loop.call_soon_threadsafe(server1_state["task"].cancel)

    # A second, independent TLS server bound to the SAME port with a
    # different cert -- start_server on the same fixed port only works
    # once the first server has actually released it, so wait briefly.
    import time

    time.sleep(0.2)

    (tmp_path / "server2").mkdir()
    certfile2, keyfile2 = _generate_self_signed_cert(tmp_path / "server2")
    ready2 = threading.Event()
    host_port2: dict = {"port": host_port["port"]}

    loop2 = asyncio.new_event_loop()
    state2: dict = {}

    async def serve2():
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(certfile2), str(keyfile2))
        server = await asyncio.start_server(
            _fake_tls_server, "127.0.0.1", host_port["port"], ssl=server_context
        )
        ready2.set()
        async with server:
            await server.serve_forever()

    async def main2():
        state2["task"] = asyncio.current_task()
        try:
            await serve2()
        except asyncio.CancelledError:
            pass

    def run2():
        asyncio.set_event_loop(loop2)
        loop2.run_until_complete(main2())

    thread2 = threading.Thread(target=run2, daemon=True)
    thread2.start()
    assert ready2.wait(timeout=3), "fake TLS server 2 never started"

    second_bridge = TelnetBridge(
        host_port["host"], host_port2["port"], use_ssl=True, cert_store=store
    )
    failures = []
    second_bridge.connectionFailed.connect(failures.append)
    second_bridge.start()

    assert _pump_until(qapp, lambda: len(failures) >= 1), "certificate mismatch never surfaced"
    assert "Certificate for" in failures[0]
    assert "/ssl-forget" in failures[0]

    second_bridge.stop()
    loop2.call_soon_threadsafe(state2["task"].cancel)
