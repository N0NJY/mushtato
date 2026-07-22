"""GUI entry point.

Usage:
    python -m gui.app             # opens the address book (Phase 6)
    python -m gui.app host port   # direct-connect, bypassing the
                                  # address book (handy for dev/testing)
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from engine.storage import load_settings, settings_path
from gui.windows.address_book_window import AddressBookWindow
from gui.windows.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help="MUD/MUSH server hostname or IP")
    parser.add_argument("port", nargs="?", type=int, help="server port")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    if args.host and args.port:
        hotkeys = load_settings(settings_path()).hotkeys
        window = MainWindow(args.host, args.port, hotkeys=hotkeys)
        window.resize(800, 600)
        window.show()
    else:
        window = AddressBookWindow()
        window.resize(500, 400)
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
