"""JSON-file persistence for the address book: saved world profiles
a user can browse and connect to, each with its own saved characters,
connect-time auto-sends, and notes (Phase 8b: Potato-parity depth).

A sibling to script_store.py rather than an extension of it: address
book entries are a *list* browsed/edited as a whole in one dialog,
while script profiles (script_store.py) are individual per-world
documents loaded independently -- different shape, different access
pattern. Same JSON-plus-atomic-write approach as script_store.py,
just a separate file and separate module, for the same
single-responsibility reasons engine/scripting is split across
triggers.py/aliases.py/world.py/trusted.py rather than one big file.

Phase 8b's shape was verified against the real Potato source
(~/git/potato/potato.vfs), not assumed: a "Character" there is only
ever a (name, password) pair -- no per-character notes, auto-sends, or
connection overrides exist anywhere in Potato's own source, despite an
initial assumption otherwise. Auto-sends/notes/login format are all
World-level, matched here for strict parity (confirmed, not just
accepted as a correction: two different worlds can have a character of
the same name with a different password, since characters are scoped
to their own world's list, never a global namespace).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# A saved world is a Telnet MU* connection unless explicitly marked
# otherwise -- "telnet" stays the default so every pre-SSH-feature
# saved world keeps behaving exactly as before with no migration step.
PROTOCOLS = ("telnet", "ssh")
DEFAULT_PROTOCOL = "telnet"


@dataclass
class CharacterProfile:
    """Just a (name, password) pair -- verified against Potato's real
    source (configureWorldCharsFinish's ``list $newChar $newPw``), not
    assumed to carry anything richer.
    """

    name: str
    password: str = ""


@dataclass
class WorldProfile:
    name: str
    host: str
    port: int
    notes: str = ""
    characters: List[CharacterProfile] = field(default_factory=list)
    default_character: str = ""
    # Potato's real default ("connect %s %s", positional) is replaced
    # here with named placeholders -- clearer than positional "which
    # %s is which", and this is MushTato's own reimplementation, not
    # literal Potato code to reproduce verbatim.
    login_format: str = "connect {name} {password}"
    login_delay: float = 1.5
    autosend_firstconnect: str = ""
    autosend_connect: str = ""
    autosend_login: str = ""
    # Persisted (not just in-memory) so "first connect ever" auto-sends
    # correctly never fire again after the first real connection,
    # verified against Potato's own sendLoginInfoSub: it checks
    # conn($c,numConnects) == 1, a counter that survives restarts.
    connect_count: int = 0
    # Per-world "connect me automatically on app startup" flag (post-8b
    # addition, Rick's own request -- no Potato equivalent researched
    # or claimed here). Only actually acted on at startup if a
    # default_character is also set, since auto-login has nothing to
    # log in as otherwise.
    auto_login: bool = False
    # Application-level Telnet NOP heartbeat (post-Phase-9 addition),
    # matching Potato's real "Use NOP Keepalive" per-world checkbox
    # (verified against potato-telnet.tcl -- see
    # gui/windows/telnet_bridge.py's own docstring for what wasn't
    # verifiable, namely Potato's real scheduling interval). Off by
    # default -- most connections don't need it; this is a targeted
    # opt-in for a world known to idle-kick quiet connections.
    nop_keepalive: bool = False
    # Phase 12b (Mail Window): verified against Potato's real source
    # (potato.tcl's mailWindow/mailWindowSend, potato-config.tcl's
    # gameMail array) -- Format/Custom-template/Convert-Returns are
    # per-world settings there too, edited only from the compose
    # window itself (no separate settings page), matched here exactly.
    mail_format: str = "MUSH @mail"
    mail_format_custom: str = "writeto %to% %cc% %bcc% about %subject% ;; write %body% ;; send"
    mail_convert_returns: bool = True
    mail_convert_returns_to: str = "%r"
    # SSH support (post-13 addition): "telnet" (default, every existing
    # world) or "ssh". ssh_username is saved like any other field, but
    # the SSH *password* is deliberately never persisted here -- Rick's
    # explicit call, since a real shell account's password is a higher-
    # stakes secret than a MU* character's; it's prompted fresh at
    # every connect instead (see gui/dialogs -- the Connect flow for an
    # ssh-protocol world always asks).
    protocol: str = DEFAULT_PROTOCOL
    ssh_username: str = ""
    # Post-1.1.0 addition: the dual-input splitter's last-dragged size
    # for this world specifically, reversing the earlier post-8b
    # decision to keep it a single app-wide preference (see
    # MainWindow.record_splitter_sizes's docstring) -- Rick's own
    # later request. Empty means "no saved size for this world yet";
    # a world-less tab (blank tab / raw /connect host port) has no
    # WorldProfile to store this on at all, so it keeps using the
    # original global Settings.splitter_sizes mechanism unchanged.
    splitter_sizes: List[int] = field(default_factory=list)


def load_address_book(path: Path) -> List[WorldProfile]:
    """Load saved world profiles from ``path``.

    Returns an empty list if the file doesn't exist yet (first run,
    nothing saved) rather than raising. Every Phase 8b field is
    defaulted when missing, so a Phase 6-shape ``address_book.json``
    (no characters/auto-sends/login fields at all) still loads
    correctly -- see test_address_book.py's old-format migration test.
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    worlds = []
    for entry in data.get("worlds", []):
        characters = [
            CharacterProfile(name=c["name"], password=c.get("password", ""))
            for c in entry.get("characters", [])
        ]
        worlds.append(
            WorldProfile(
                name=entry["name"],
                host=entry["host"],
                port=entry["port"],
                notes=entry.get("notes", ""),
                characters=characters,
                default_character=entry.get("default_character", ""),
                login_format=entry.get("login_format", "connect {name} {password}"),
                login_delay=entry.get("login_delay", 1.5),
                autosend_firstconnect=entry.get("autosend_firstconnect", ""),
                autosend_connect=entry.get("autosend_connect", ""),
                autosend_login=entry.get("autosend_login", ""),
                connect_count=entry.get("connect_count", 0),
                auto_login=entry.get("auto_login", False),
                nop_keepalive=entry.get("nop_keepalive", False),
                mail_format=entry.get("mail_format", "MUSH @mail"),
                mail_format_custom=entry.get(
                    "mail_format_custom",
                    "writeto %to% %cc% %bcc% about %subject% ;; write %body% ;; send",
                ),
                mail_convert_returns=entry.get("mail_convert_returns", True),
                mail_convert_returns_to=entry.get("mail_convert_returns_to", "%r"),
                protocol=entry.get("protocol", DEFAULT_PROTOCOL),
                ssh_username=entry.get("ssh_username", ""),
                splitter_sizes=list(entry.get("splitter_sizes", [])),
            )
        )
    return worlds


def save_address_book(path: Path, worlds: List[WorldProfile]) -> None:
    """Save ``worlds`` to ``path``, atomically (write-then-rename)."""
    data = {
        "worlds": [
            {
                "name": w.name,
                "host": w.host,
                "port": w.port,
                "notes": w.notes,
                "characters": [
                    {"name": c.name, "password": c.password} for c in w.characters
                ],
                "default_character": w.default_character,
                "login_format": w.login_format,
                "login_delay": w.login_delay,
                "autosend_firstconnect": w.autosend_firstconnect,
                "autosend_connect": w.autosend_connect,
                "autosend_login": w.autosend_login,
                "connect_count": w.connect_count,
                "auto_login": w.auto_login,
                "nop_keepalive": w.nop_keepalive,
                "mail_format": w.mail_format,
                "mail_format_custom": w.mail_format_custom,
                "mail_convert_returns": w.mail_convert_returns,
                "mail_convert_returns_to": w.mail_convert_returns_to,
                "protocol": w.protocol,
                "ssh_username": w.ssh_username,
                "splitter_sizes": w.splitter_sizes,
            }
            for w in worlds
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
