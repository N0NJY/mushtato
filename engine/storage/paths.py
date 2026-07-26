"""Cross-platform user-data directory resolution.

Phase 4 deliberately left "where does this file actually live" as a
later decision (storage functions just take an explicit path). Phase 6
is the first phase that needs a real, concrete answer -- the address
book has to persist somewhere real for the GUI to use, not just an
arbitrary path supplied by a test. `platformdirs` gives the OS-idiomatic
location on each platform for *data* (not config) directories --
verified against platformdirs' actual source (Phase 8), not assumed:
``%LOCALAPPDATA%\\MushTato`` on Windows (Local, not Roaming
``%APPDATA%``), ``~/Library/Application Support/MushTato`` on macOS,
``~/.local/share/MushTato`` on Linux (``$XDG_DATA_HOME``, not
``~/.config``, which is ``$XDG_CONFIG_HOME`` -- a different
platformdirs function this project doesn't call) -- rather than a
single hardcoded ``~/.mushtato``-style path.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs

APP_NAME = "MushTato"


def user_data_dir() -> Path:
    # appauthor=False: no separate vendor/company name to nest under --
    # this is a free/open-source project, not a commercial publisher.
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def address_book_path() -> Path:
    return user_data_dir() / "address_book.json"


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def world_script_path(world_name: str) -> Path:
    return user_data_dir() / "scripts" / f"{safe_filename(world_name)}.json"


def logs_dir() -> Path:
    # Shared by spawnlog-save (Phase 11) and the error log (Phase 11) --
    # one real per-OS location, not the ad-hoc ~/.mushtato/logs/-style
    # path an earlier planning doc guessed without checking this module.
    return user_data_dir() / "logs"


def drafts_dir() -> Path:
    # Phase 12's Text Editor default save location -- same correction
    # as logs_dir() above (a planning doc guessed ~/.mushtato/drafts/
    # again, the same recurring mistake, without checking this module).
    return user_data_dir() / "drafts"


def ssh_known_hosts_path() -> Path:
    # MushTato's own trust-on-first-use host-key store -- deliberately
    # separate from the user's real ~/.ssh/known_hosts, never read or
    # written by anything in this app. Plain JSON (host:port -> the
    # server's public key), matching every other storage format here.
    return user_data_dir() / "ssh_known_hosts.json"


def safe_filename(name: str) -> str:
    """Sanitize an arbitrary world name for safe use as a filename."""
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    return cleaned or "unnamed"
