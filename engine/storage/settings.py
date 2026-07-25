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
from typing import Dict, List

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
    "open_text_editor": "Ctrl+Shift+E",
}

# "dark" is the default (Phase 7b checkpoint): matches engine/ansi's
# xterm-standard palette assumptions and the near-universal MUD/
# terminal convention of a dark background, so it's the safer default
# for typical server content. See gui/theme.py for what each value
# actually renders as.
THEMES = ("dark", "light")
DEFAULT_THEME = "dark"


@dataclass
class Settings:
    hotkeys: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))
    theme: str = DEFAULT_THEME
    # Empty string / 0 are "no override" sentinels, resolved to a real
    # concrete font by gui/fonts.py -- this module can't compute that
    # default itself (it would need QFontDatabase, i.e. PySide6, which
    # /engine is never allowed to import; see CLAUDE.md rule 2).
    scrollback_font_family: str = ""
    scrollback_font_size: int = 0
    input_font_family: str = ""
    input_font_size: int = 0
    # The dual-input splitter's last-dragged QSplitter.sizes() -- one
    # global preference (not per-world), applied as the starting split
    # for every newly-opened tab. Empty list means "no saved preference
    # yet, use the built-in 5:1 stretch-factor default."
    splitter_sizes: List[int] = field(default_factory=list)
    # Phase 12 (Text Editor): a third font category, same "no override"
    # sentinel convention as the two above. Editor windows can be
    # multiple and simultaneous (Rick's checkpoint choice) -- these are
    # the *shared* starting values for every newly-opened one, not
    # per-window state.
    editor_font_family: str = ""
    editor_font_size: int = 0
    editor_line_numbers: bool = True
    editor_word_wrap: bool = True
    # [x, y, width, height] of the most recently moved/resized editor
    # window -- one shared "starting geometry for the next new window"
    # preference, same non-live-updating-already-open-windows reasoning
    # as splitter_sizes above. Empty means "no saved preference yet."
    editor_window_geometry: List[int] = field(default_factory=list)
    # Last directory used in the editor's Open/Save dialogs -- empty
    # means "no saved preference yet, default to drafts_dir()".
    editor_last_dir: str = ""
    # Last directory used in the Upload dialog's file picker -- same
    # "no saved preference yet" empty-string convention as
    # editor_last_dir above.
    upload_last_dir: str = ""


def load_settings(path: Path) -> Settings:
    """Load settings from ``path``.

    Returns all-default settings if the file doesn't exist yet. Any
    hotkey action missing from a saved file (e.g. one saved before a
    new configurable action existed) is filled in with its default
    rather than left unbound, so old settings files keep working as
    new actions get added. Same forward-compatible merge for `theme`:
    an unrecognized or missing value falls back to the default rather
    than raising. Font fields and splitter_sizes default the same way
    (missing -> "no override" sentinel) so a pre-font-settings
    settings.json still loads correctly -- the Phase 12 editor_* fields
    follow the identical pattern for the same reason.
    """
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    hotkeys = dict(DEFAULT_HOTKEYS)
    hotkeys.update(data.get("hotkeys", {}))
    theme = data.get("theme", DEFAULT_THEME)
    if theme not in THEMES:
        theme = DEFAULT_THEME
    return Settings(
        hotkeys=hotkeys,
        theme=theme,
        scrollback_font_family=data.get("scrollback_font_family", ""),
        scrollback_font_size=data.get("scrollback_font_size", 0),
        input_font_family=data.get("input_font_family", ""),
        input_font_size=data.get("input_font_size", 0),
        splitter_sizes=list(data.get("splitter_sizes", [])),
        editor_font_family=data.get("editor_font_family", ""),
        editor_font_size=data.get("editor_font_size", 0),
        editor_line_numbers=data.get("editor_line_numbers", True),
        editor_word_wrap=data.get("editor_word_wrap", True),
        editor_window_geometry=list(data.get("editor_window_geometry", [])),
        editor_last_dir=data.get("editor_last_dir", ""),
        upload_last_dir=data.get("upload_last_dir", ""),
    )


def save_settings(path: Path, settings: Settings) -> None:
    """Save ``settings`` to ``path``, atomically (write-then-rename)."""
    data = {
        "hotkeys": settings.hotkeys,
        "theme": settings.theme,
        "scrollback_font_family": settings.scrollback_font_family,
        "scrollback_font_size": settings.scrollback_font_size,
        "input_font_family": settings.input_font_family,
        "input_font_size": settings.input_font_size,
        "splitter_sizes": settings.splitter_sizes,
        "editor_font_family": settings.editor_font_family,
        "editor_font_size": settings.editor_font_size,
        "editor_line_numbers": settings.editor_line_numbers,
        "editor_word_wrap": settings.editor_word_wrap,
        "editor_window_geometry": settings.editor_window_geometry,
        "editor_last_dir": settings.editor_last_dir,
        "upload_last_dir": settings.upload_last_dir,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
