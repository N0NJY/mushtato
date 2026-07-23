# Installing MushTato

MushTato is a free, open-source, cross-platform GUI client for MUD/MUSH/MOO
text games (MU*). It combines Potato's point-and-click GUI (address book,
tabbed sessions, dual input, spawn windows, configurable hotkeys) with
TinyFugue's power-user command conventions. No account, license key, or
payment is required — it's free to download and use.

## Where to get it

Every build is published on GitHub Releases:

**https://github.com/N0NJY/mushtato/releases**

Download the archive for your operating system from the latest release:

| OS      | File                     |
|---------|--------------------------|
| Windows | `MushTato-windows.zip`   |
| macOS   | `MushTato-macos.zip`     |
| Linux   | `MushTato-linux.tar.gz`  |

There's no installer — each archive contains a self-contained `MushTato`
folder. Extract it anywhere and run the program inside; there's nothing
separate to "install" beyond extracting the archive.

## Windows

1. Download `MushTato-windows.zip` and extract it (right-click → Extract
   All...).
2. Open the extracted `MushTato` folder and double-click `MushTato.exe`.
3. **Windows SmartScreen may warn you** the first time, saying the app is
   from an "unrecognized publisher." This is expected — MushTato is free/
   open-source and isn't signed with a paid code-signing certificate. Click
   **More info**, then **Run anyway**.
4. To uninstall, just delete the extracted folder — see
   [Removing your data](#removing-your-data-uninstalling) below for saved
   worlds/settings.

## macOS

1. Download `MushTato-macos.zip` and double-click it to extract the
   `MushTato.app` bundle.
2. Move `MushTato.app` wherever you like (e.g. `/Applications`).
3. **macOS Gatekeeper will block the first launch** with a message like
   "MushTato can't be opened because it is from an unidentified developer."
   This is expected — the app is unsigned and not notarized (see
   `SPEC.md` section 8 for why: full macOS QA/notarization is deferred
   until a real Mac-owning beta tester exists to validate the app on).
   To open it anyway: **right-click (or Control-click) `MushTato.app` →
   Open**, then click **Open** again in the dialog that appears. You only
   need to do this once — after that, it opens normally.
4. To uninstall, delete `MushTato.app` — see
   [Removing your data](#removing-your-data-uninstalling) below.

## Linux

1. Download `MushTato-linux.tar.gz` and extract it:
   ```
   tar xzf MushTato-linux.tar.gz
   ```
2. Run it from inside the extracted folder:
   ```
   cd MushTato
   ./MushTato
   ```
3. The build already bundles the Qt/xcb runtime libraries it needs
   (`libxcb-cursor0` and its usual companions) — this was itself a real
   bug found during development (see `CHANGELOG.md`), so it's fixed at
   the build stage, not left as a manual step for you. If you still see
   an error like `could not load the Qt platform plugin "xcb"` on an
   unusually minimal Linux install, install the runtime libraries
   yourself (Debian/Ubuntu and derivatives):
   ```
   sudo apt-get install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
       libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
       libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0
   ```
   Other distributions (Fedora, Arch, etc.) provide equivalent packages
   under different names — search your distro's package manager for
   `libxcb-cursor` if the above `apt` command doesn't apply to you.
4. To uninstall, delete the extracted `MushTato` folder — see
   [Removing your data](#removing-your-data-uninstalling) below.

## First launch

The very first time you run MushTato, it shows a one-time settings dialog
(theme and hotkeys) before opening the main window — after that it's never
shown again. The main window opens with no connections yet; use
**File → Address Book...** to add and connect to a world. See the in-app
**Help** menu for a full walkthrough of every feature.

## Removing your data (uninstalling)

Deleting the extracted folder/`.app` removes the program itself, but
MushTato also saves your address book and settings in your OS's standard
per-user data location (via the `platformdirs` library, not a single
hardcoded path). If you want to remove those too:

| OS      | Location                                          |
|---------|----------------------------------------------------|
| Windows | `%LOCALAPPDATA%\MushTato`                          |
| macOS   | `~/Library/Application Support/MushTato`           |
| Linux   | `~/.local/share/MushTato`                          |

This folder contains `address_book.json` (your saved worlds) and
`settings.json` (your theme/hotkeys) — delete the whole folder to remove
all saved MushTato data.

## Something not working?

See `TROUBLESHOOTING.md` for common issues (connection failures, missing
runtime libraries, Gatekeeper/SmartScreen warnings), or use the in-app
**Help** menu once MushTato is running.
