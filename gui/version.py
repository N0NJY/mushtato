"""Single source of truth for the displayed app version.

Split out from main_window.py (Phase 9) so both MainWindow (the host
shell) and SessionTab can import it without creating a circular import
between those two modules.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version


def mushtato_version() -> str:
    try:
        return _pkg_version("mushtato")
    except PackageNotFoundError:
        return "dev"
