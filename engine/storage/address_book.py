"""JSON-file persistence for the address book: saved world profiles
(name, host, port, notes) a user can browse and connect to.

A sibling to script_store.py rather than an extension of it: address
book entries are a *list* browsed/edited as a whole in one dialog,
while script profiles (script_store.py) are individual per-world
documents loaded independently -- different shape, different access
pattern. Same JSON-plus-atomic-write approach as script_store.py,
just a separate file and separate module, for the same
single-responsibility reasons engine/scripting is split across
triggers.py/aliases.py/world.py/trusted.py rather than one big file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class WorldProfile:
    name: str
    host: str
    port: int
    notes: str = ""


def load_address_book(path: Path) -> List[WorldProfile]:
    """Load saved world profiles from ``path``.

    Returns an empty list if the file doesn't exist yet (first run,
    nothing saved) rather than raising.
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        WorldProfile(
            name=entry["name"],
            host=entry["host"],
            port=entry["port"],
            notes=entry.get("notes", ""),
        )
        for entry in data.get("worlds", [])
    ]


def save_address_book(path: Path, worlds: List[WorldProfile]) -> None:
    """Save ``worlds`` to ``path``, atomically (write-then-rename)."""
    data = {
        "worlds": [
            {"name": w.name, "host": w.host, "port": w.port, "notes": w.notes}
            for w in worlds
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
