"""Asyncio SSH client (engine/net) -- a genuinely different protocol
from the Telnet client this module's sibling (client.py) implements,
not an extension of it. Built on ``asyncssh`` (a new dependency, added
specifically for this): hand-rolling SSH's own crypto/key-exchange/
authentication would be a real security mistake, unlike Telnet's IAC
negotiation, which has no crypto to get wrong.

Host-key verification is trust-on-first-use (TOFU), matching real
``ssh``'s own ``known_hosts`` behavior -- verified directly against
asyncssh's actual runtime behavior before writing this, not assumed
from its docs: passing ``known_hosts=None`` to ``asyncssh.connect()``
disables host-key checking *entirely* (``SSHClient.
validate_host_public_key`` is never even called), rather than falling
back to a callback. Genuine TOFU needs ``known_hosts=b''`` (an empty
static list, which still populates the internal trusted-keys set and
so still consults the callback) *plus* overriding
``validate_host_public_key()`` on a custom ``SSHClient`` subclass --
confirmed by tracing ``SSHClientConnection._validate_host_key`` in
asyncssh's own source, then proven end-to-end against a real local
throwaway asyncssh test server (first connect trusts + saves; a repeat
connect with the same key succeeds silently; a connect where the key
has changed is rejected with ``HostKeyNotVerifiable``).

MushTato's own known-hosts store (``HostKeyStore``) is a small JSON
file (see ``engine/storage/paths.ssh_known_hosts_path``) completely
separate from the user's real ``~/.ssh/known_hosts`` -- this app never
reads or writes that file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import asyncssh

READ_CHUNK_SIZE = 4096


class HostKeyMismatch(Exception):
    """Raised when a server's host key doesn't match what's already
    saved for this host:port -- distinct from an ordinary connection
    or authentication failure, since the right response (investigate,
    then deliberately ``/ssh-forget`` if the change is expected) is
    completely different advice than "check your password."
    """

    def __init__(self, host: str, port: int, old_fingerprint: str, new_fingerprint: str) -> None:
        self.host = host
        self.port = port
        self.old_fingerprint = old_fingerprint
        self.new_fingerprint = new_fingerprint
        super().__init__(
            f"Host key for {host}:{port} has changed! "
            f"Old: {old_fingerprint}  New: {new_fingerprint}"
        )


class HostKeyStore:
    """MushTato's own trust-on-first-use host-key store: a plain JSON
    file mapping ``"host:port"`` to the server's exported public-key
    text. Deliberately not OpenSSH's own ``known_hosts`` format or file
    -- this never touches the user's real SSH configuration.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        # Set by check() on a rejection, for the caller to build a
        # HostKeyMismatch with -- see this module's docstring for why
        # asyncssh's own validate_host_public_key callback (a plain
        # bool return) can't carry this information back out directly.
        self.last_mismatch: Optional[HostKeyMismatch] = None

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

    def check(self, host: str, port: int, key: "asyncssh.SSHKey") -> bool:
        """True if ``key`` is trusted for ``host``:``port`` -- and, on
        a genuine first-ever connect, saves it as trusted. False if a
        *different* key was already saved (``self.last_mismatch`` is
        set with details for the caller to report); never silently
        trusts a changed key.
        """
        self.last_mismatch = None
        data = self._load()
        entry = self._entry_key(host, port)
        offered = key.export_public_key().decode("ascii")
        if entry not in data:
            data[entry] = offered
            self._save(data)
            return True
        if data[entry] == offered:
            return True
        old_key = asyncssh.import_public_key(data[entry].encode("ascii"))
        self.last_mismatch = HostKeyMismatch(
            host, port, old_key.get_fingerprint(), key.get_fingerprint()
        )
        return False

    def forget(self, host: str, port: int) -> bool:
        """Remove a saved host key so the next connect is treated as
        first-use again. Returns True if an entry actually existed.
        """
        data = self._load()
        entry = self._entry_key(host, port)
        if entry not in data:
            return False
        del data[entry]
        self._save(data)
        return True


class _TofuSSHClient(asyncssh.SSHClient):
    """The thinnest possible adapter between asyncssh's per-connection
    host-key callback and a shared HostKeyStore -- the store makes the
    actual trust decision; this class exists only because asyncssh
    requires an SSHClient subclass to hang validate_host_public_key
    off of.
    """

    def __init__(self, store: HostKeyStore) -> None:
        self._store = store

    def validate_host_public_key(self, host: str, addr: str, port: int, key) -> bool:
        return self._store.check(host, port, key)


class SshClient:
    """A single SSH connection, requesting a real interactive login
    shell (a PTY, no explicit command -- matching plain ``ssh host``
    with nothing else on the command line). Mirrors engine/net/
    client.py's TelnetClient shape (connect/send_line/read/close) so
    gui/windows/ssh_bridge.py can drive it with the same pattern
    telnet_bridge.py already uses for TelnetClient.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        host_key_store: HostKeyStore,
        *,
        encoding: str = "utf-8",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._host_key_store = host_key_store
        self.encoding = encoding
        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self._process: Optional[asyncssh.SSHClientProcess] = None

    async def connect(self) -> None:
        try:
            self._conn = await asyncssh.connect(
                self.host,
                self.port,
                username=self.username,
                password=self.password,
                known_hosts=b"",  # empty static list -- still triggers the TOFU callback below
                client_factory=lambda: _TofuSSHClient(self._host_key_store),
                encoding=None,  # we decode ourselves, matching TelnetClient's own error handling
            )
        except asyncssh.HostKeyNotVerifiable:
            if self._host_key_store.last_mismatch is not None:
                raise self._host_key_store.last_mismatch from None
            raise

        self._process = await self._conn.create_process(
            term_type="xterm",
            term_size=(80, 24),
            encoding=None,
        )

    async def send_line(self, line: str) -> None:
        if self._process is None:
            raise RuntimeError("not connected")
        self._process.stdin.write(line.encode(self.encoding, errors="replace") + b"\r\n")

    async def read(self) -> Optional[str]:
        """Read and decode one chunk of incoming output.

        Returns ``None`` on the remote process/connection closing.
        """
        if self._process is None:
            raise RuntimeError("not connected")
        raw = await self._process.stdout.read(READ_CHUNK_SIZE)
        if not raw:
            return None
        return raw.decode(self.encoding, errors="replace")

    async def close(self) -> None:
        if self._process is not None:
            self._process.stdin.write_eof()
            self._process.terminate()
        if self._conn is not None:
            self._conn.close()
            try:
                await self._conn.wait_closed()
            except (ConnectionError, OSError):
                pass
