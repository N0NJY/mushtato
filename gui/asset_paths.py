"""Resolves gui/assets/ (icon + splash artwork) correctly whether
running from source or from a frozen PyInstaller build.

PyInstaller's bootloader sets ``sys.frozen`` and ``sys._MEIPASS`` for
both ``--onedir`` and ``--onefile`` builds (onedir's ``_MEIPASS`` just
points at the app's own installation directory rather than a temp-
extracted one) -- this is the standard, documented way to resolve
bundled data files regardless of which build mode
packaging/mushtato.spec uses. Kept as its own small module (like
gui/version.py) rather than folded into gui/app.py, so gui/tray_icon.py
and gui/help/help_window.py can import it too without a circular
import.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The standard sizes icon/ is pre-rendered at -- single source of truth
# so gui/app.py (building a multi-resolution QIcon) and the test suite
# (checking every size actually exists) can't silently drift apart.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "gui" / "assets"
    return Path(__file__).parent / "assets"


def icon_png_path(size: int) -> Path:
    """Path to the pre-rendered icon PNG at exactly ``size`` pixels
    (16/24/32/48/64/128/256/512/1024) -- crisper than scaling the
    1024px master at runtime for a smaller target size.
    """
    return assets_dir() / "icon" / f"{size}.png"


def icon_master_path() -> Path:
    """The 1024px master icon (real alpha transparency, fixed
    2026-07-26 -- see gui/assets/README.md).
    """
    return assets_dir() / "icon.png"


def splash_path() -> Path:
    return assets_dir() / "splash.png"
