# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for MushTato (Phase 7).

Invoke from the repo root: `pyinstaller packaging/mushtato.spec`.

Only bundles what gui/app.py's import graph actually reaches today --
engine/scripting (RestrictedPython, google-re2) isn't wired into the
GUI yet (see CLAUDE.md), so PyInstaller's static analysis doesn't
include it in this build. Revisit hiddenimports here once a later
phase wires scripting into the GUI; either of those two dependencies
could plausibly need an explicit hiddenimports entry if PyInstaller's
analysis doesn't follow their dynamic-loading paths automatically.

Icon/splash artwork (post-Phase-12, gui/assets/): `datas` bundles the
whole gui/assets/ directory verbatim so gui/asset_paths.py's frozen-
build branch (sys._MEIPASS/gui/assets) resolves correctly -- the same
relative layout as the source tree, so nothing in gui/asset_paths.py
needs to special-case a frozen path shape. `icon=` is platform-
selected: PyInstaller's EXE(icon=...) only does anything on Windows
(embeds into the .exe) and macOS (embeds into the Mach-O binary/would
feed a real .app bundle's Info.plist); it's silently ignored on Linux,
so `None` there isn't a gap, just accurate. Note this build has no
BUNDLE() step (no real .app bundle is produced on macOS -- COLLECT's
plain onedir folder is just archived with `ditto` in build.yml, same
as every other OS's folder), so the macOS icon's real visible effect
here is limited to the raw executable's own icon resource, not a
Finder-visible .app icon -- a fuller macOS .app bundle is a separate,
more invasive packaging change, not attempted here.

Version display (2026-07-26): `pyproject.toml` is also bundled, at the
frozen bundle's root (matching gui/version.py's sys._MEIPASS/
pyproject.toml lookup) -- a frozen PyInstaller build doesn't carry a
package's own dist-info metadata by default, so
importlib.metadata.version("mushtato") would otherwise always fail in
a packaged build and silently fall back to the "dev" placeholder even
on a real tagged release; bundling the real source of truth directly
is simpler than trying to make PyInstaller preserve install metadata
that was never generated for an app that isn't pip-installed from a
wheel in the first place.
"""

import sys

if sys.platform == "darwin":
    _icon = "../gui/assets/icon.icns"
elif sys.platform == "win32":
    _icon = "../gui/assets/icon.ico"
else:
    _icon = None

a = Analysis(
    ["../gui/app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("../gui/assets", "gui/assets"),
        ("../pyproject.toml", "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MushTato",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MushTato",
)
