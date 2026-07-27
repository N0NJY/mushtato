"""Headless tests for TelnetClient's SSL/TLS support (item 6 of the
SSL/proxy/NAWS plan) -- against a local, throwaway self-signed TLS test
server on an OS-assigned ephemeral port. No real network, no real
certificate authority involved at any point.

Plain ``asyncio.run`` throughout, matching test_telnet_client.py's own
established convention (no pytest-asyncio dependency needed). A fresh
self-signed cert/key pair is generated per test via ``cryptography``
(already a transitive dependency via asyncssh) -- written to real temp
files since stdlib ``ssl.SSLContext.load_cert_chain()`` needs file
paths, not in-memory PEM data.
"""

import asyncio
import datetime
import ssl
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from engine.net.client import CertificateMismatch, CertificateStore, TelnetClient


def _generate_self_signed_cert(tmp_path: Path, common_name: str = "127.0.0.1"):
    """Writes a fresh, throwaway self-signed cert+key pair to
    tmp_path, returns (certfile, keyfile) paths.
    """
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


async def _start_tls_echo_server(certfile: Path, keyfile: Path):
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certfile), str(keyfile))

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"Welcome to TestMUD over TLS!\r\n")
        await writer.drain()
        line = await reader.readline()
        if line == b"look\r\n":
            writer.write(b"You see nothing special.\r\n")
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    return server, port


async def _read_text(client: TelnetClient) -> str:
    while True:
        chunk = await client.read()
        assert chunk is not None, "connection closed unexpectedly"
        if chunk:
            return chunk


# -- basic connect / send / receive over TLS -----------------------------


async def _run_connect_and_echo(tmp_path: Path) -> None:
    certfile, keyfile = _generate_self_signed_cert(tmp_path)
    server, port = await _start_tls_echo_server(certfile, keyfile)
    async with server:
        store = CertificateStore(tmp_path / "known_certs.json")
        client = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        await client.connect()

        banner = await _read_text(client)
        assert banner == "Welcome to TestMUD over TLS!\r\n"

        await client.send_line("look")
        response = await _read_text(client)
        assert response == "You see nothing special.\r\n"

        await client.close()


def test_connect_send_and_receive_over_tls(tmp_path: Path):
    asyncio.run(_run_connect_and_echo(tmp_path))


# -- CertificateStore: trust-on-first-use --------------------------------


async def _run_tofu_trust_then_reuse(tmp_path: Path) -> None:
    certfile, keyfile = _generate_self_signed_cert(tmp_path)
    server, port = await _start_tls_echo_server(certfile, keyfile)
    store = CertificateStore(tmp_path / "known_certs.json")

    async with server:
        first = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        await first.connect()  # first-ever connect: trusts and saves
        await first.close()

        assert (tmp_path / "known_certs.json").exists()

        second = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        await second.connect()  # same cert: succeeds silently
        await second.close()


def test_first_connect_trusts_and_saves_the_certificate(tmp_path: Path):
    asyncio.run(_run_tofu_trust_then_reuse(tmp_path))


async def _run_tofu_mismatch(tmp_path: Path) -> None:
    (tmp_path / "server1").mkdir(exist_ok=True)
    certfile1, keyfile1 = _generate_self_signed_cert(tmp_path / "server1")
    server1, port = await _start_tls_echo_server(certfile1, keyfile1)
    store = CertificateStore(tmp_path / "known_certs.json")

    async with server1:
        trusted = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        await trusted.connect()
        await trusted.close()

    # A second server on the SAME port with a DIFFERENT cert -- simulates
    # an impersonation/MITM scenario, or (more innocently) a legitimate
    # server reinstall.
    (tmp_path / "server2").mkdir(exist_ok=True)
    certfile2, keyfile2 = _generate_self_signed_cert(tmp_path / "server2")
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certfile2), str(keyfile2))

    async def handler(reader, writer):
        del reader
        writer.close()

    server2 = await asyncio.start_server(handler, "127.0.0.1", port, ssl=server_context)
    async with server2:
        mismatched = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        with pytest.raises(CertificateMismatch) as exc_info:
            await mismatched.connect()
        assert exc_info.value.old_fingerprint != exc_info.value.new_fingerprint
        assert exc_info.value.host == "127.0.0.1"
        assert exc_info.value.port == port


def test_changed_certificate_is_rejected_not_silently_trusted(tmp_path: Path):
    asyncio.run(_run_tofu_mismatch(tmp_path))


async def _run_forget_then_reconnect(tmp_path: Path) -> None:
    (tmp_path / "server1").mkdir(exist_ok=True)
    certfile1, keyfile1 = _generate_self_signed_cert(tmp_path / "server1")
    server1, port = await _start_tls_echo_server(certfile1, keyfile1)
    store = CertificateStore(tmp_path / "known_certs.json")

    async with server1:
        trusted = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        await trusted.connect()
        await trusted.close()

    (tmp_path / "server2").mkdir(exist_ok=True)
    certfile2, keyfile2 = _generate_self_signed_cert(tmp_path / "server2")
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certfile2), str(keyfile2))

    async def handler(reader, writer):
        del reader
        writer.close()

    server2 = await asyncio.start_server(handler, "127.0.0.1", port, ssl=server_context)
    async with server2:
        rejected = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        with pytest.raises(CertificateMismatch):
            await rejected.connect()

        assert store.forget("127.0.0.1", port) is True

        reconnected = TelnetClient("127.0.0.1", port, use_ssl=True, cert_store=store)
        await reconnected.connect()  # forgotten -- treated as first-use again
        await reconnected.close()


def test_forget_allows_reconnecting_after_a_certificate_change(tmp_path: Path):
    asyncio.run(_run_forget_then_reconnect(tmp_path))


def test_forget_a_host_with_no_saved_entry_returns_false(tmp_path: Path):
    store = CertificateStore(tmp_path / "known_certs.json")
    assert store.forget("nowhere.example.com", 4201) is False


def test_certificate_store_only_writes_the_path_it_was_given(tmp_path: Path):
    custom_path = tmp_path / "totally_isolated.json"
    store = CertificateStore(custom_path)

    assert store.check("example.com", 4201, "deadbeef") is True

    assert custom_path.exists()
    assert list(tmp_path.iterdir()) == [custom_path]


def test_plain_non_ssl_connections_never_touch_the_certificate_store(tmp_path: Path):
    # use_ssl=False (the default) must never call into cert_store at
    # all, even if one happens to be passed -- proven by giving it a
    # store pointed at a path that would fail loudly if written to.
    store = CertificateStore(Path("/nonexistent/should/never/be/created.json"))
    client = TelnetClient("127.0.0.1", 1, cert_store=store)
    assert client.use_ssl is False
