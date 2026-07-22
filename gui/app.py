"""GUI entry point.

Usage:
    python -m gui.app             # opens the address book (Phase 6)
    python -m gui.app host port   # direct-connect, bypassing the
                                  # address book (handy for dev/testing)

First run (Phase 7b): if no settings file exists yet at
settings_path(), shows the settings dialog in first-run mode (theme +
hotkeys, reusing settings_dialog.py rather than a separate onboarding
flow) before either the direct-connect or address-book path. The
result is saved regardless of whether the user clicks OK or Cancel, so
this is only ever shown once -- see engine/storage/settings.py and
CLAUDE.md's Phase 7b notes for the reasoning.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from engine.storage import Settings, load_settings, save_settings, settings_path
from gui.dialogs.settings_dialog import SettingsDialog
from gui.theme import apply_theme
from gui.windows.address_book_window import AddressBookWindow
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help="MUD/MUSH server hostname or IP")
    parser.add_argument("port", nargs="?", type=int, help="server port")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    settings = ensure_settings(settings_path())
    apply_theme(app, settings.theme)

    if args.host and args.port:
        window = MainWindow(
            args.host, args.port, hotkeys=settings.hotkeys, theme=settings.theme
        )
        window.resize(800, 600)
        window.show()
    else:
        window = AddressBookWindow()
        window.resize(500, 400)
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
