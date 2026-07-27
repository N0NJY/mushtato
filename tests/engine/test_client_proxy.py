"""Headless tests for TelnetClient's SOCKS4 proxy support (item 9 of
the SSL/proxy/NAWS plan) -- against a real local fake SOCKS4 proxy that
actually relays bytes to a real local fake target server, proving data
genuinely flows client -> proxy -> target and back, not just that the
handshake bytes look right in isolation (already covered by
test_socks4.py). Also covers proxy + SSL together (item 6's TLS wrap
applied *after* the SOCKS4 relay is established), the one real
interaction the original plan flagged between these two items.
"""

import asyncio
import datetime
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from engine.net.client import CertificateStore, TelnetClient


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


async def _relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, ssl.SSLError):
        pass
    finally:
        writer.close()


async def _start_fake_socks4_relay_proxy(target_host: str, target_port: int):
    """A real SOCKS4 proxy: completes the handshake, then actually
    opens its own connection to the real target and relays bytes both
    ways -- not just a handshake-only stub.
    """

    async def handle_client(client_reader, client_writer):
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

        target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
        client_writer.write(bytes((0, 0x5A, 0, 0, 0, 0, 0, 0)))
        await client_writer.drain()

        await asyncio.gather(
            _relay(client_reader, target_writer),
            _relay(target_reader, client_writer),
        )

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    return server, host, port


async def _fake_plain_target_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.write(b"Welcome to TestMUD via proxy!\r\n")
    await writer.drain()
    line = await reader.readline()
    if line == b"look\r\n":
        writer.write(b"You see nothing special.\r\n")
        await writer.drain()
    writer.close()


async def _read_text(client: TelnetClient) -> str:
    while True:
        chunk = await client.read()
        assert chunk is not None, "connection closed unexpectedly"
        if chunk:
            return chunk


async def _run_plain_proxy() -> None:
    target_server = await asyncio.start_server(_fake_plain_target_server, "127.0.0.1", 0)
    target_host, target_port = target_server.sockets[0].getsockname()[:2]

    async with target_server:
        proxy_server, proxy_host, proxy_port = await _start_fake_socks4_relay_proxy(
            target_host, target_port
        )
        async with proxy_server:
            client = TelnetClient(
                target_host, target_port, proxy_host=proxy_host, proxy_port=proxy_port
            )
            await client.connect()

            banner = await _read_text(client)
            assert banner == "Welcome to TestMUD via proxy!\r\n"

            await client.send_line("look")
            response = await _read_text(client)
            assert response == "You see nothing special.\r\n"

            await client.close()


def test_connect_send_and_receive_through_a_socks4_proxy():
    asyncio.run(_run_plain_proxy())


async def _run_proxy_plus_ssl(tmp_path: Path) -> None:
    certfile, keyfile = _generate_self_signed_cert(tmp_path)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certfile), str(keyfile))

    async def tls_handler(reader, writer):
        writer.write(b"Welcome to TestMUD via proxy+TLS!\r\n")
        await writer.drain()
        line = await reader.readline()
        if line == b"look\r\n":
            writer.write(b"You see nothing special.\r\n")
            await writer.drain()
        writer.close()

    target_server = await asyncio.start_server(
        tls_handler, "127.0.0.1", 0, ssl=server_context
    )
    target_host, target_port = target_server.sockets[0].getsockname()[:2]

    async with target_server:
        proxy_server, proxy_host, proxy_port = await _start_fake_socks4_relay_proxy(
            target_host, target_port
        )
        async with proxy_server:
            store = CertificateStore(tmp_path / "known_certs.json")
            client = TelnetClient(
                target_host,
                target_port,
                use_ssl=True,
                cert_store=store,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
            )
            await client.connect()

            banner = await _read_text(client)
            assert banner == "Welcome to TestMUD via proxy+TLS!\r\n"

            await client.send_line("look")
            response = await _read_text(client)
            assert response == "You see nothing special.\r\n"

            await client.close()

            # TOFU actually engaged through the proxy path too, not
            # bypassed -- the cert got saved.
            assert (tmp_path / "known_certs.json").exists()


def test_connect_send_and_receive_through_a_socks4_proxy_with_ssl(tmp_path: Path):
    asyncio.run(_run_proxy_plus_ssl(tmp_path))


async def _run_no_proxy_configured_behaves_as_before() -> None:
    # proxy_host/proxy_port both left at their defaults ("") -- must
    # connect directly, exactly as before this feature existed.
    server = await asyncio.start_server(_fake_plain_target_server, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    async with server:
        client = TelnetClient(host, port)
        await client.connect()
        banner = await _read_text(client)
        assert banner == "Welcome to TestMUD via proxy!\r\n"
        await client.close()


def test_no_proxy_configured_connects_directly():
    asyncio.run(_run_no_proxy_configured_behaves_as_before())
