"""Cross-platform user-data directory resolution.

Phase 4 deliberately left "where does this file actually live" as a
later decision (storage functions just take an explicit path). Phase 6
is the first phase that needs a real, concrete answer -- the address
book has to persist somewhere real for the GUI to use, not just an
arbitrary path supplied by a test. `platformdirs` gives the OS-idiomatic
location on each platform (``%APPDATA%`` on Windows, ``~/Library/
Application Support`` on macOS, ``~/.config`` on Linux) rather than a
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


def world_script_path(world_name: str) -> Path:
    return user_data_dir() / "scripts" / f"{safe_filename(world_name)}.json"


def safe_filename(name: str) -> str:
    """Sanitize an arbitrary world name for safe use as a filename."""
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    return cleaned or "unnamed"
