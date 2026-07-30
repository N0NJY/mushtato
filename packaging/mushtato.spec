# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for MushTato (Phase 7).

Invoke from the repo root: `pyinstaller packaging/mushtato.spec`.

Bundles what gui/app.py's import graph actually reaches -- as of Phase
9, that includes engine/scripting (RestrictedPython, google-re2), since
SessionTab now builds a ScriptWorld unconditionally for every tab (this
comment previously said scripting wasn't wired in yet -- true before
Phase 9, stale since; corrected 2026-07-29 while investigating build
size, a real staleness bug found on sight rather than the thing being
looked into).

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

Build-size trimming (2026-07-29, extended 2026-07-30): see the comments
around _EXCLUDED_BINARY_KEYWORDS below for what's excluded and why.
Deliberately does NOT touch plugins/generic, plugins/wayland-*,
plugins/egldeviceintegrations, plugins/xcbglintegrations, or
plugins/platformthemes despite their modest combined size (~1.4MB) --
unlike translations/tls (removed based on a plain grep showing zero
usage anywhere in this codebase), whether those are safe to drop
depends on the real display server/window manager/compositor
combination on an actual end-user desktop, which this sandbox's
offscreen-QPA-only environment cannot verify -- and this project has a
documented history of being wrong about exactly that (the
libxcb-cursor0 and theme-palette bugs earlier on). Not worth that risk
for so little size.
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

# Post-Analysis binary trim (2026-07-29, found while investigating a
# real user report that the packaged build is large). PyInstaller's own
# Qt hook table (PyInstaller.utils.hooks.qt._modules_info) associates
# both the "imageformats" and "platforminputcontexts" plugin
# *directories* with QtGui as a whole -- since MushTato genuinely uses
# QtGui, the hook bundles every plugin in both directories
# unconditionally, including two MushTato never touches: "qpdf" (loads
# PDF files as images) and Qt Virtual Keyboard (an on-screen input
# method, irrelevant for a desktop app with a physical keyboard).
# Verified directly against the real built binaries (`ldd`, not
# guessed) that dropping these two is safe: only
# libqtvirtualkeyboardplugin.so depends on the whole Quick/QML/
# VirtualKeyboard shared-library cluster, and only libqpdf.so depends
# on libQt6Pdf.so -- nothing else this build actually uses (Widgets/
# Gui/Core/Network/DBus, or any other retained plugin) references any
# of them, so the plugin files and their now-orphaned private
# dependency libraries can be dropped together. Real, measured saving
# on the Linux build: ~20MB (confirmed via a real rebuild + real
# `gui/app.py` launch under QT_QPA_PLATFORM=offscreen, not assumed safe
# from the dependency analysis alone). Only verified on Linux this
# session (no Windows/macOS build environment available here) -- the
# keyword match below is written to also catch the equivalent .dll/
# .dylib names, but Rick should confirm the Windows/macOS builds still
# launch fine once this ships, same as any other can't-verify-cross-
# platform-locally change in this project.
_EXCLUDED_BINARY_KEYWORDS = (
    "qtvirtualkeyboard",  # plugins/platforminputcontexts/*virtualkeyboard*
    "virtualkeyboard",  # lib/*VirtualKeyboard*
    "qml",  # lib/*Qml*, pulled in only by the virtual keyboard plugin
    "quick",  # lib/*Quick*, pulled in only by the virtual keyboard plugin
    "qpdf",  # plugins/imageformats/*qpdf* (PDF-as-image loading)
    "qt6pdf",  # lib/*Pdf*, pulled in only by the qpdf plugin
    # Second trim pass (2026-07-30), found investigating a further real
    # user report that the packaged build is "huge". Confirmed by
    # grepping engine/ and gui/ for QTranslator/installTranslator (zero
    # hits) and QSsl/QNetworkAccessManager/QNetworkReply (zero hits)
    # before excluding either of these -- MushTato has no i18n
    # framework in use (English-only UI, no QTranslator ever
    # installed), and its own SSL/TLS work (SSL-enabled MU* connections,
    # SSH) goes through Python's stdlib `ssl` module and `asyncssh`
    # directly (engine/net/client.py), never through QtNetwork's own
    # QSslSocket -- so Qt's own TLS backend plugins serve no purpose
    # here either.
    "translations",  # PySide6/Qt/translations/*.qm -- ~6.7MB of Qt's own
    # UI-string translations (Cancel/OK/etc in other languages), dead
    # weight with no QTranslator ever installed.
    "qcertonlybackend",  # plugins/tls/ -- Qt's own TLS backend plugins
    "qopensslbackend",  # for QSslSocket, unused since MushTato's SSL/TLS
    # traffic never goes through QtNetwork.
)
a.binaries = [
    entry
    for entry in a.binaries
    if not any(keyword in entry[0].lower() for keyword in _EXCLUDED_BINARY_KEYWORDS)
]
# The same libraries also show up a second time as separate SYMLINK-
# typecode entries in a.datas (PyInstaller collects a Qt shared
# library's on-disk versioned-symlink chain, e.g. libQt6Qml.so.6, as
# data entries independently of the BINARY entry above) -- found by
# rebuilding and noticing the excluded libraries were still present,
# now as dangling/broken symlinks (confirmed with `file`, not assumed:
# a real symlink pointing at a BINARY path that no longer exists after
# the filter above). Filtering a.datas the same way removes those too,
# so the build has no broken symlinks left behind.
a.datas = [
    entry
    for entry in a.datas
    if not any(keyword in entry[0].lower() for keyword in _EXCLUDED_BINARY_KEYWORDS)
]

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
