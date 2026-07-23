# Changelog

MushTato is still pre-1.0 and has not yet had a tagged release — this
changelog is organized by development phase (this project's actual unit
of work, per `CLAUDE.md`/`SPEC.md`'s roadmap) rather than by version
number, reconstructed from `CLAUDE.md`'s phase-by-phase notes and git
history. All dates below are from the actual commit history.

## Phase 8 — Documentation & onboarding (in progress)

- Real in-app Help system (`gui/help/`), replacing the Phase 7c `/help`
  placeholder: a scrollable reference document (menu bar → Help → Help,
  or typing `/help`) covering every feature that actually exists today,
  with a linked table of contents.
- `/help [topic]`, `/help [command]`, and `/help topics` all work from
  the command line, not just the GUI window.
- `INSTALL.md`, `TROUBLESHOOTING.md`, `CREDITS.md`, and this changelog.

## Phase 7e — Tabbed session host window (2026-07-23)

- The main window becomes the persistent root of the app: it opens
  before anything is connected, stays open at zero connections, and
  each connection lives in its own tab instead of its own top-level
  window.
- The address book becomes a satellite picker opened from the main
  window (`File → Address Book...`), rather than the app's entry point.
- `Ctrl+W`/`/quit`/toolbar Close now close the active tab, not the
  whole window; only the window's own close button or `File → Exit`
  exits the program.
- Connecting to an already-open world switches to its existing tab
  instead of duplicating it.
- Hotkey changes now take effect immediately in the same session.

## Post-7d fixes — Theme reliability (2026-07-23)

- Fixed the scrollback pane not honoring the dark/light theme on a real
  desktop (three related issues found via real hardware testing, not
  just headless tests): forcing the Fusion Qt style, palette-application
  ordering relative to the window's chrome, and a `QTextEdit`/viewport
  palette quirk that headless/offscreen testing couldn't reproduce.
- Added a resizable splitter between the scrollback and the command/pose
  input boxes.

## Phase 7c/7d — Built-in commands and GUI chrome (2026-07-23)

- A `/` command system (`engine/commands.py`) informed by a review of
  the real TinyFugue source: `/help`, `/connect`, `/settings`,
  `/version`, `/theme`, `/spawnlog`, `/quit`, `/disconnect`,
  `/reconnect`, plus the `//` literal-text escape convention.
- A menu bar, toolbar, and status bar modeled on a review of Potato's
  real GUI, exposing those same commands as first-class buttons/menu
  items rather than typed-only.

## Phase 7b — Theming and first-run setup (2026-07-22)

- Dark/light theme support (`QPalette`-based), with the dark theme's
  colors matched to Potato's own real shipped defaults.
- A first-run settings dialog shown once, before the main window opens.

## Phase 7 — Polish and packaging (2026-07-22)

- Configurable hotkeys via a Settings dialog.
- Cross-platform packaging via GitHub Actions (Windows/macOS/Linux),
  including a real Linux packaging bug found and fixed (missing
  `libxcb-cursor0` runtime library on the build image).

## Phase 6 — Multi-window Potato features (2026-07-22)

- Address book (add/edit/delete/connect to saved worlds).
- Multiple simultaneous connections (originally as separate top-level
  windows — later replaced by tabs in Phase 7e).
- Spawn windows (log-mirror popups).
- Dual input: a primary command box and a secondary pose/says box that
  always bypasses command processing.

## Phase 5 — Minimal Qt shell (2026-07-22)

- The first real GUI: one window, one connection, ANSI-rendered
  scrollback, single-line input, validated against real MUSH servers.

## Phase 4 — Sandboxed scripting engine (2026-07-22)

- `engine/scripting`: a `RestrictedPython`-sandboxed scripting API
  (`send`, `echo`, `gag`, `highlight`, `set_var`, `get_var`, `timer`,
  `on_trigger`, `on_connect`, `on_alias`), trigger patterns compiled
  against `google-re2` to structurally rule out catastrophic-
  backtracking ReDoS, and JSON-based persistence.
- **Not yet wired into the GUI** — this remains true as of Phase 8; see
  the in-app Help's Scripting topic.

## Phase 3 — Headless engine (2026-07-22)

- `engine/net`: a hand-rolled asyncio telnet client (IAC negotiation).
- `engine/ansi`: ANSI/xterm-256 color parsing into toolkit-agnostic
  styled text.

## Phases 1–2 — Spec and scaffolding (2026-07-22)

- Project spec (`SPEC.md`) and initial repo structure
  (`/engine`, `/gui`, `/worlds`, `/tests`, `CLAUDE.md`).
