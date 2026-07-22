"""JSON-file persistence for app-wide settings.

A third sibling alongside address_book.py and script_store.py --
anticipated since Phase 2's scaffolding (CLAUDE.md's repo-structure
comment already named "settings persistence" as one of engine/storage's
three jobs). v1 content is deliberately just hotkeys: nothing else is
configurable yet, so there's nothing else to persist -- add fields when
something actually needs one, not speculatively.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

# Concrete starting keybinding set (Phase 7 checkpoint), mapped to
# actions that already existed from Phases 5/6. Picked to avoid
# colliding with Qt/OS defaults: plain Tab stays normal focus
# traversal, so switching input focus uses Ctrl+Tab instead.
DEFAULT_HOTKEYS: Dict[str, str] = {
    "add_world": "Ctrl+N",
    "connect": "Ctrl+Return",
    "spawn_log_window": "Ctrl+L",
    "switch_input_focus": "Ctrl+Tab",
    "close_window": "Ctrl+W",
}


@dataclass
class Settings:
    hotkeys: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))


def load_settings(path: Path) -> Settings:
    """Load settings from ``path``.

    Returns all-default settings if the file doesn't exist yet. Any
    hotkey action missing from a saved file (e.g. one saved before a
    new configurable action existed) is filled in with its default
    rather than left unbound, so old settings files keep working as
    new actions get added.
    """
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    hotkeys = dict(DEFAULT_HOTKEYS)
    hotkeys.update(data.get("hotkeys", {}))
    return Settings(hotkeys=hotkeys)


def save_settings(path: Path, settings: Settings) -> None:
    """Save ``settings`` to ``path``, atomically (write-then-rename)."""
    data = {"hotkeys": settings.hotkeys}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
