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
"""

a = Analysis(
    ["../gui/app.py"],
    pathex=[],
    binaries=[],
    datas=[],
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
