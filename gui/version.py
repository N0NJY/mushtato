"""Single source of truth for the displayed app version.

Split out from main_window.py (Phase 7e) so both MainWindow (the host
shell) and SessionTab can import it without creating a circular import
between those two modules.

Real bug fixed here (2026-07-26): ``importlib.metadata.version()``
only finds a version if the package has real dist-info/egg-info
installed-package metadata -- true for a proper ``pip install`` (incl.
``-e``), but not for source run without that step, and not reliably
true for a PyInstaller-frozen build either (PyInstaller doesn't bundle
a package's own dist-info by default unless something explicitly asks
it to -- a well-known category of gotcha for packages that look up
their own metadata at runtime). Both cases silently fell back to the
"dev" placeholder even on a real tagged release. Fixed by falling back
to reading ``pyproject.toml``'s ``version`` field directly (via
stdlib ``tomllib``, available since Python 3.11 -- this project's own
``requires-python`` floor, so no new dependency) whenever package
metadata isn't found -- resolved via the same dev-vs-frozen-build path
pattern ``gui/asset_paths.py`` already established, and
``packaging/mushtato.spec`` now bundles ``pyproject.toml`` alongside
``gui/assets/`` so this fallback actually has something to read in a
packaged build too.
"""

from __future__ import annotations

import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path


def _pyproject_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "pyproject.toml"
    return Path(__file__).resolve().parent.parent / "pyproject.toml"


def mushtato_version() -> str:
    try:
        return _pkg_version("mushtato")
    except PackageNotFoundError:
        pass
    try:
        data = tomllib.loads(_pyproject_path().read_text(encoding="utf-8"))
        return data["project"]["version"]
    except (FileNotFoundError, KeyError):
        return "dev"
