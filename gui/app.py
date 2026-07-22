"""Phase 5 GUI entry point: one window, one connection.

Usage:
    python -m gui.app [host] [port]

If host/port aren't given on the command line, prompts for them with a
simple dialog -- no address book yet (that's Phase 6), so this is
intentionally the "hardcoded or prompted" minimum SPEC.md's roadmap
calls for at this phase.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication, QInputDialog

from gui.windows.main_window import MainWindow


def _prompt_for_host_port(app: QApplication) -> tuple[str, int] | None:
    host, ok = QInputDialog.getText(None, "MushTato", "Host:")
    if not ok or not host:
        return None
    port, ok = QInputDialog.getInt(None, "MushTato", "Port:", value=23, minValue=1, maxValue=65535)
    if not ok:
        return None
    return host, port


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help="MUD/MUSH server hostname or IP")
    parser.add_argument("port", nargs="?", type=int, help="server port")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    if args.host and args.port:
        host, port = args.host, args.port
    else:
        prompted = _prompt_for_host_port(app)
        if prompted is None:
            return 0
        host, port = prompted

    window = MainWindow(host, port)
    window.resize(800, 600)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
