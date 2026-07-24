"""GUI entry point.

Usage:
    python -m gui.app             # opens the main window with no tabs
                                   # open yet -- use File > Address Book
    python -m gui.app host port   # main window with one tab already
                                   # open, connected directly (handy for
                                   # dev/testing)

Phase 7e: MainWindow is now the persistent root/shell (a tabbed
connection host), not one connection itself -- see
gui/windows/main_window.py's module docstring. The address book is a
satellite window opened *from* the main window, not the app's entry
point.

First run (Phase 7b): if no settings file exists yet at
settings_path(), shows the settings dialog in first-run mode (theme +
hotkeys, reusing settings_dialog.py rather than a separate onboarding
flow) before the main window is created. The result is saved
regardless of whether the user clicks OK or Cancel, so this is only
ever shown once -- see engine/storage/settings.py and CLAUDE.md's
Phase 7b notes for the reasoning.

Auto-login on startup (post-8b addition, Rick's own request): any
saved world with its "auto-login" checkbox set *and* a
default_character chosen is opened and logged into automatically, one
at a time, in address-book order -- no confirmation prompt, per Rick's
explicit call ("It doesn't ask me to confirm though. That's not
necessary"). Matches Rick's own described real-Potato behavior (open,
connect, jump to the next tab) rather than waiting for each login to
succeed before starting the next -- a down server shouldn't block the
rest of the list. Only runs on the no-args launch path; a direct
`host port` command-line connect is its own explicit override and
skips this entirely.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QApplication

from engine.storage import (
    Settings,
    WorldProfile,
    address_book_path,
    load_address_book,
    load_settings,
    save_settings,
    settings_path,
)
from gui.dialogs.settings_dialog import SettingsDialog
from gui.theme import apply_theme
from gui.windows.main_window import MainWindow


def ensure_settings(path: Path, *, dialog_factory=SettingsDialog) -> Settings:
    """Return the app's settings, showing the first-run dialog if
    ``path`` doesn't exist yet.

    Always persists a result -- whether the dialog is accepted or
    cancelled -- so first-run is never shown more than once. Split out
    from main() specifically so this logic is unit-testable without
    running the full QApplication/event-loop flow.
    """
    if path.exists():
        return load_settings(path)
    dialog = dialog_factory(settings=Settings(), first_run=True)
    dialog.exec()
    settings = dialog.result_settings()
    save_settings(path, settings)
    return settings


def worlds_to_auto_login(worlds: List[WorldProfile]) -> List[WorldProfile]:
    """Which saved worlds actually auto-login: flagged *and* has a
    default_character -- a checked box with no default character
    chosen is inert, not an error, since there'd be nothing to log in
    as.
    """
    return [w for w in worlds if w.auto_login and w.default_character]


def auto_login_all(window: MainWindow, worlds: List[WorldProfile]) -> None:
    """Open + log into each of ``worlds`` in order, one at a time.

    Split out from main() for the same reason as ensure_settings --
    unit-testable without a real QApplication/event-loop run.
    """
    for world in worlds:
        window.open_tab(world.host, world.port, name=world.name, world=world)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help="MUD/MUSH server hostname or IP")
    parser.add_argument("port", nargs="?", type=int, help="server port")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    settings = ensure_settings(settings_path())
    apply_theme(app, settings.theme)

    window = MainWindow(
        hotkeys=settings.hotkeys,
        theme=settings.theme,
        scrollback_font_family=settings.scrollback_font_family,
        scrollback_font_size=settings.scrollback_font_size,
        input_font_family=settings.input_font_family,
        input_font_size=settings.input_font_size,
        splitter_sizes=settings.splitter_sizes,
    )
    window.resize(900, 700)
    window.show()

    if args.host and args.port:
        window.open_tab(args.host, args.port)
    else:
        worlds = load_address_book(address_book_path())
        auto_login_all(window, worlds_to_auto_login(worlds))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
