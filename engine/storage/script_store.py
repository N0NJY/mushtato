"""JSON-file persistence for a world's saved scripts and variables.

Deliberately minimal: per SPEC.md section 2, GUI-built triggers and
hand-written scripts are meant to be the *same* object internally, so
there's no separate "trigger" table to persist here -- just script
source text (+ a ``trusted`` flag, which the engine never acts on by
itself -- see engine/scripting/trusted.py) and a per-world variables
dict. Where this file actually lives (a platform user-data directory,
a ``--data-dir`` flag, etc.) is a later, GUI-integration-phase
decision; these functions just take an explicit path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ScriptRecord:
    name: str
    source: str
    trusted: bool = False
    enabled: bool = True


@dataclass
class WorldScriptProfile:
    scripts: List[ScriptRecord] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)


def load_world_scripts(path: Path) -> WorldScriptProfile:
    """Load a world's saved scripts/variables from ``path``.

    Returns an empty profile if the file doesn't exist yet (a brand
    new world with nothing saved) rather than raising.
    """
    if not path.exists():
        return WorldScriptProfile()
    data = json.loads(path.read_text(encoding="utf-8"))
    scripts = [
        ScriptRecord(
            name=entry["name"],
            source=entry["source"],
            trusted=entry.get("trusted", False),
            enabled=entry.get("enabled", True),
        )
        for entry in data.get("scripts", [])
    ]
    return WorldScriptProfile(scripts=scripts, variables=data.get("variables", {}))


def save_world_scripts(path: Path, profile: WorldScriptProfile) -> None:
    """Save ``profile`` to ``path``, atomically.

    Writes to a temp file in the same directory and renames it over
    the target, so a crash mid-write can't leave a corrupted/partial
    save behind.
    """
    data = {
        "scripts": [
            {
                "name": script.name,
                "source": script.source,
                "trusted": script.trusted,
                "enabled": script.enabled,
            }
            for script in profile.scripts
        ],
        "variables": profile.variables,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
