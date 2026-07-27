"""Asyncio telnet client.

Hand-rolled IAC negotiation (see :mod:`engine.net.telnet`) on top of
plain ``asyncio`` streams, rather than a third-party telnet library.
The negotiation needs for this phase are deliberately minimal (refuse
every option) so a small, fully-owned state machine keeps the
dependency list unchanged and stays trivially testable headless.

Post-Phase-9 addition: TCP keepalive. A silent network drop (e.g. the
client's own power/router loss, as opposed to the server cleanly
closing the connection) never arrives as a FIN/RST -- without
keepalive, a plain ``asyncio.open_connection()`` socket's ``read()``
just waits, potentially for hours, since nothing prompts the OS to
notice the peer is unreachable. This is a real, reported bug (not a
theoretical one): the app never showed "Connection closed" on a tab
whose network had actually died, because nothing ever told it to.
Enabling and tuning keepalive is the direct fix -- once the OS detects
the dead peer, the pending ``read()`` fails with an ``OSError``, which
``gui/windows/telnet_bridge.py``'s ``_run()`` already catches and turns
into the existing ``connectionFailed`` signal; no changes needed on
that side at all.

SSL/TLS support (item 6 of the SSL/proxy/NAWS plan, 2026-07-27): wraps
the raw socket in TLS right after connecting -- "implicit TLS" on a
dedicated port, the same model real Potato uses (verified against its
source; STARTTLS, an in-band upgrade, exists in Potato's code but is
hard-disabled there) -- via asyncio's own built-in ``ssl=`` support on
``open_connection()``, no new dependency. Certificate verification is
trust-on-first-use, mirroring ``engine/net/ssh_client.py``'s
``HostKeyStore``/``HostKeyMismatch`` exactly (same checkpointed
decision as the SSH feature, not Potato's own real choice of no
verification at all -- Potato's code comment there says "the majority
of MUSHes use self-signed certificates," which is also why TLS
verification is disabled at the handshake level here (``check_hostname
= False``, ``verify_mode = ssl.CERT_NONE``) -- otherwise the handshake
itself would reject the self-signed cert before ``CertificateStore``
ever got a chance to make its own trust decision.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import ssl
import sys
from pathlib import Path
from typing import Optional

from .socks4 import socks4_connect
from .telnet import IAC, NOP, TelnetNegotiator

READ_CHUNK_SIZE = 4096

# Tuned for "notice within well under a minute", not the OS defaults
# (Linux's own default TCP_KEEPIDLE is 7200s -- two hours -- before even
# the *first* probe). 10s idle before the first probe, a probe every 5s,
# giving up after 3 missed probes -- roughly 25s worst case to detect a
# genuinely dead connection, safely under the 30s auto-reconnect
# interval (gui/windows/session_tab.py) so a retry attempt isn't wasted
# racing a not-yet-detected-dead old connection.
KEEPALIVE_IDLE_SECONDS = 10
KEEPALIVE_INTERVAL_SECONDS = 5
KEEPALIVE_PROBE_COUNT = 3


def _configure_keepalive(sock: socket.socket) -> None:
    """Enable and tune TCP keepalive on ``sock``, best-effort per
    platform. Always sets ``SO_KEEPALIVE`` (universally supported);
    the finer-grained idle/interval/count tuning uses whichever of
    Linux's ``TCP_KEEPIDLE``/``TCP_KEEPINTVL``/``TCP_KEEPCNT`` or
    macOS's single ``TCP_KEEPALIVE`` constant is actually present --
    verified locally on Linux only (this sandbox has no macOS/Windows
    hardware, per CLAUDE.md); wrapped in a broad ``except`` since a
    platform/kernel that doesn't support a given knob should degrade to
    "just SO_KEEPALIVE with OS default timing", never crash the
    connection attempt.
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        if hasattr(socket, "TCP_KEEPIDLE"):  # Linux
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_IDLE_SECONDS)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVAL_SECONDS)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_PROBE_COUNT)
        elif hasattr(socket, "TCP_KEEPALIVE"):  # macOS: one combined idle-time constant
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, KEEPALIVE_IDLE_SECONDS)
        elif sys.platform == "win32" and hasattr(socket, "SIO_KEEPALIVE_VALS"):
            sock.ioctl(
                socket.SIO_KEEPALIVE_VALS,
                (1, KEEPALIVE_IDLE_SECONDS * 1000, KEEPALIVE_INTERVAL_SECONDS * 1000),
            )
    except OSError:
        # SO_KEEPALIVE itself is already set -- fall back to whatever
        # the OS's own default timing is rather than failing the
        # connection over a tuning knob it doesn't support.
        pass


class CertificateMismatch(Exception):
    """Raised when a server's certificate doesn't match what's already
    saved for this host:port -- distinct from an ordinary connection
    failure, since the right response (investigate, then deliberately
    ``/ssl-forget`` if the change is expected) is completely different
    advice than a generic connection error. Mirrors
    ``engine/net/ssh_client.py``'s ``HostKeyMismatch`` exactly.
    """

    def __init__(self, host: str, port: int, old_fingerprint: str, new_fingerprint: str) -> None:
        self.host = host
        self.port = port
        self.old_fingerprint = old_fingerprint
        self.new_fingerprint = new_fingerprint
        super().__init__(
            f"Certificate for {host}:{port} has changed! "
            f"Old: {old_fingerprint}  New: {new_fingerprint}"
        )


class CertificateStore:
    """MushTato's own trust-on-first-use certificate store: a plain
    JSON file mapping ``"host:port"`` to the server's certificate
    fingerprint (SHA-256 of the DER-encoded certificate, the standard
    way to compactly identify one). Deliberately separate from the
    OS/browser's own certificate trust store -- this never consults or
    modifies that.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        # Set by check() on a rejection, for the caller to build a
        # CertificateMismatch with -- same pattern as HostKeyStore's
        # own last_mismatch, for the same reason: the actual raise
        # happens one level up, once the caller knows the full context.
        self.last_mismatch: Optional[CertificateMismatch] = None

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self._path)

    @staticmethod
    def _entry_key(host: str, port: int) -> str:
        return f"{host}:{port}"

    def check(self, host: str, port: int, fingerprint: str) -> bool:
        """True if ``fingerprint`` is trusted for ``host``:``port`` --
        and, on a genuine first-ever connect, saves it as trusted.
        False if a *different* fingerprint was already saved
        (``self.last_mismatch`` is set with details for the caller to
        report); never silently trusts a changed certificate.
        """
        self.last_mismatch = None
        data = self._load()
        entry = self._entry_key(host, port)
        if entry not in data:
            data[entry] = fingerprint
            self._save(data)
            return True
        if data[entry] == fingerprint:
            return True
        self.last_mismatch = CertificateMismatch(host, port, data[entry], fingerprint)
        return False

    def forget(self, host: str, port: int) -> bool:
        """Remove a saved certificate so the next connect is treated as
        first-use again. Returns True if an entry actually existed.
        """
        data = self._load()
        entry = self._entry_key(host, port)
        if entry not in data:
            return False
        del data[entry]
        self._save(data)
        return True


def _make_tofu_ssl_context() -> ssl.SSLContext:
    # Verification happens ourselves, via CertificateStore, after the
    # handshake -- disabled here so the handshake itself doesn't reject
    # a self-signed certificate before that check ever runs (see this
    # module's own docstring for why, and Potato's real precedent).
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class TelnetClient:
    """A single connection to a MUD/MUSH/MOO server."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        encoding: str = "utf-8",
        use_ssl: bool = False,
        cert_store: Optional[CertificateStore] = None,
        naws_enabled: bool = False,
        term_enabled: bool = False,
        proxy_host: str = "",
        proxy_port: int = 0,
    ) -> None:
        self.host = host
        self.port = port
        self.encoding = encoding
        self.use_ssl = use_ssl
        self._cert_store = cert_store
        # Item 9 of the SSL/proxy/NAWS plan: a SOCKS4/SOCKS4a proxy,
        # tried only if both are actually set (same "both must be
        # present" convention as the item 8 fallback address).
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        # Only ever populated by _connect_via_proxy's TLS-upgrade path
        # -- see its own comment for why this reference has to be kept
        # alive for as long as the connection is in use.
        self._pre_tls_writer: Optional[asyncio.StreamWriter] = None
        self._negotiator = TelnetNegotiator(naws_enabled=naws_enabled, term_enabled=term_enabled)

    async def connect(self) -> None:
        if self.proxy_host and self.proxy_port:
            await self._connect_via_proxy()
        elif self.use_ssl:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port, ssl=_make_tofu_ssl_context()
            )
            self._verify_certificate()
        else:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        raw_socket = self._writer.get_extra_info("socket")
        if raw_socket is not None:
            _configure_keepalive(raw_socket)

    async def _connect_via_proxy(self) -> None:
        # First, a plain (never SSL) connection to the proxy itself --
        # the proxy is a separate hop, and its own connection is never
        # what use_ssl is about (that's the *target* MU*/MUSH server,
        # reached by relaying through the proxy).
        reader, writer = await asyncio.open_connection(self.proxy_host, self.proxy_port)
        await socks4_connect(reader, writer, self.host, self.port)
        if not self.use_ssl:
            self._reader, self._writer = reader, writer
            return
        # Upgrade the already-established (and already SOCKS4-relayed)
        # plain connection to TLS in place -- asyncio.open_connection's
        # own ssl= parameter only applies *while first connecting*, so
        # it can't be used here; loop.start_tls() is the documented,
        # correct primitive for upgrading a connection that already
        # exists (verified directly against its real docstring before
        # relying on it: "Upgrade a transport to TLS... Return a new
        # transport that protocol should start using immediately").
        loop = asyncio.get_running_loop()
        protocol = writer.transport.get_protocol()
        new_transport = await loop.start_tls(
            writer.transport, protocol, _make_tofu_ssl_context(), server_side=False
        )
        self._reader = reader
        self._writer = asyncio.StreamWriter(new_transport, protocol, reader, loop)
        # Real, reproduced bug (not theorized): start_tls() reuses the
        # *same* underlying transport/socket the pre-upgrade `writer`
        # already owned, wrapped by a new SSL layer -- it does not hand
        # out a brand-new independent connection. `writer` itself is a
        # local variable that would otherwise go out of scope the
        # moment this method returns; asyncio.StreamWriter.__del__
        # closes its own transport on garbage collection if not already
        # closing (confirmed directly, not assumed), which tore down
        # the shared underlying socket out from under the new SSL
        # transport almost immediately -- reproduced with a real proxy
        # relaying real TLS bytes, where the connection got a spurious
        # EOF right after the handshake, before the target's own banner
        # ever arrived. Keeping this reference alive for the client's
        # own lifetime (closed explicitly by close() below alongside
        # the real self._writer) is the fix, not a workaround.
        self._pre_tls_writer = writer
        self._verify_certificate()

    def _verify_certificate(self) -> None:
        ssl_object = self._writer.get_extra_info("ssl_object")
        der_cert = ssl_object.getpeercert(binary_form=True)
        fingerprint = hashlib.sha256(der_cert).hexdigest()
        if self._cert_store is None:
            return
        if not self._cert_store.check(self.host, self.port, fingerprint):
            self._writer.close()
            raise self._cert_store.last_mismatch

    async def send_line(self, line: str) -> None:
        """Send one line of user input, terminated with CRLF."""
        if self._writer is None:
            raise RuntimeError("not connected")
        data = line.encode(self.encoding, errors="replace").replace(
            bytes((IAC,)), bytes((IAC, IAC))
        )
        self._writer.write(data + b"\r\n")
        await self._writer.drain()

    async def send_nop(self) -> None:
        """Send a bare Telnet IAC NOP -- a "no operation" byte pair a
        server ignores silently (RFC 854). Application-level keepalive,
        distinct from (and complementary to) the OS-level TCP keepalive
        ``connect()`` already enables -- verified against Potato's real
        source (``potato-telnet.tcl``'s ``send_keepalive``, which sends
        exactly ``$tCmd(IAC)$tCmd(NOP)``) as the mechanism, though not
        against a confirmed real scheduling interval -- Potato's own
        source defines that proc but no call site for it was found in
        the visible .tcl files, so the *interval* MushTato schedules
        this at (see gui/windows/telnet_bridge.py) is this project's
        own reasonable choice, not a verified-from-source Potato value.
        """
        if self._writer is None:
            raise RuntimeError("not connected")
        self._writer.write(bytes((IAC, NOP)))
        await self._writer.drain()

    async def read(self) -> Optional[str]:
        """Read and decode one chunk of incoming application text.

        Returns ``None`` on connection close (EOF). Returns ``""`` if
        the chunk read was entirely telnet negotiation with no visible
        text -- callers should keep looping, not treat that as a
        disconnect.
        """
        if self._reader is None:
            raise RuntimeError("not connected")
        raw = await self._reader.read(READ_CHUNK_SIZE)
        if not raw:
            return None
        clean, reply = self._negotiator.feed(raw)
        if reply:
            self._writer.write(reply)
            await self._writer.drain()
        return clean.decode(self.encoding, errors="replace")

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, ssl.SSLError):
                # ssl.SSLError is a sibling of ConnectionError (both
                # subclass OSError directly, confirmed -- not a subclass
                # relationship), so the pre-existing ConnectionError
                # catch here never covered it. Only became reachable
                # once TLS support existed at all: closing an
                # SSL-wrapped connection whose peer already closed its
                # own raw socket abruptly (never sent a proper
                # close_notify) can raise this during our own graceful-
                # shutdown attempt -- found via a real test using a fake
                # TLS server that does exactly that, not theorized.
                pass
