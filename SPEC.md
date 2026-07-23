# Project Spec: MushTato — A Modern Python MUD/MUSH Client

*(Name: MUSH + Potato — a nod to the MU* protocol family and the Potato client,
with TinyFugue's scripting spirit built in under the hood.)*

## 1. What this is

MushTato is a free, open-source, cross-platform (Windows/Linux/macOS) GUI client for connecting
to any MUD/MUSH/MOO-type text game (MU*). It combines:

- **Potato's** GUI strengths: address book of saved worlds, multiple simultaneous
  connections, spawn windows, dual input, ANSI/xterm color rendering, configurable
  hotkeys.
- **TinyFugue's** power-user strengths: triggers, macros, gags, highlights,
  speedwalking — but reimagined with **full Python scripting** instead of TinyFugue's
  own custom scripting language.

Target users: both newbies who want a point-and-click client with zero coding, and
expert users/scripters who want TinyFugue-level (or greater) programmability.

## 2. Goals

- One unified underlying system: GUI-built triggers/macros and hand-written Python
  scripts are the *same* object internally. The dialog builder just authors scripts;
  it isn't a separate "lite" system that drifts from the "real" one.
- A bounded, sandboxed scripting API (not raw `exec()` of arbitrary Python) so that
  shared/downloaded community scripts can't do arbitrary damage to a user's machine.
- Cross-platform packaging via CI (GitHub Actions), including macOS builds despite
  no local Mac hardware.
- Free and open-source. Monetization via GitHub Sponsors / donation links only —
  no license keys, no DRM, no paid tiers.
- Eventually: a community script/plugin sharing ecosystem (repo of shareable
  trigger packs, similar in spirit to TinyFugue's community `.tf` files).

## 3. Non-goals (for now)

- No paid features, license enforcement, or commercial licensing concerns.
- No custom scripting language (no TinyFugue-syntax reimplementation) — Python
  is the scripting language, full stop.
- No mobile client.
- Full macOS QA is out of scope until a human beta tester with real Mac hardware
  is found; CI builds only guarantee it *compiles* and *launches*, not full UX
  polish on macOS.

## 4. Architecture

Two cleanly separated layers:

### Engine (UI-agnostic, testable headless)
- Async networking (asyncio), telnet protocol handling (IAC negotiation, MCCP/GMCP
  as stretch goals)
- ANSI/xterm-256 color code parser → structured "styled text" representation
  (not tied to any GUI toolkit)
- Trigger/macro/alias engine: pattern matching (regex) → action dispatch
- Scripting API: a defined set of safe functions (`send()`, `echo()`, `gag()`,
  `highlight()`, `set_var()`, `get_var()`, `timer()`, `on_trigger()`, `on_connect()`,
  etc.) exposed to user scripts
- Sandboxed execution: restricted Python execution (e.g. via `RestrictedPython`
  or a hand-rolled AST whitelist) blocking `import os`, `subprocess`, raw `socket`,
  `eval`/`exec`, arbitrary file I/O — unless a script is explicitly marked "trusted"
  by the user (for their own personal, non-shared scripts only)
- World/profile persistence (JSON or SQLite): saved connections, saved scripts,
  saved settings

### GUI (PySide6)
- Main window: connection manager / address book
- Per-world session windows: scrollback pane (ANSI-rendered), input line, dual
  input mode
- Spawn windows: pop any channel/log/who-list into its own pane
- Trigger/macro/alias builder dialogs (generates scripts against the same
  scripting API used by hand-written scripts)
- "View generated script" option so GUI-built triggers are visible/editable as
  real code — the on-ramp from newbie to power user
- Settings/preferences, hotkey configuration

## 5. Tech stack

- **Language:** Python 3.11+
- **GUI:** PySide6 (Qt for Python; permissive LGPL, no longer a hard commercial
  constraint now that this is open-source, but still the more permissive default)
- **Networking:** asyncio + a telnet-aware layer (evaluate `telnetlib3` vs
  hand-rolled)
- **Sandboxing:** `RestrictedPython` (decided, Phase 4) — see section 8 history
- **Trigger pattern matching:** `google-re2` (decided, Phase 4) — trigger
  patterns (`on_trigger()`) compile against RE2 rather than stdlib `re`,
  which structurally rules out catastrophic-backtracking ReDoS for the one
  place in the codebase where untrusted-origin patterns are matched against
  untrusted-origin text. Other regex use in the codebase (e.g. the ANSI
  parser's fixed, developer-authored patterns) has no such exposure and
  stays on stdlib `re`.
- **Persistence:** JSON files (decided, Phase 4) — script source (+ a
  `trusted` flag) and per-world variables; simple enough a schema that
  SQLite's extra structure wasn't worth it, and JSON fits the eventual
  shareable-script-pack goal (section 2) better than a DB blob.
- **Packaging:** PyInstaller, built via GitHub Actions matrix (windows-latest,
  ubuntu-latest, macos-latest)
- **Testing:** pytest, with the engine layer fully testable headless (no GUI
  dependency needed for engine tests)

## 6. Feature checklist by origin

**From Potato:**
- [ ] Address book / saved world list
- [ ] Multiple simultaneous connections (multi-window)
- [ ] Dual input windows
- [ ] ANSI + xterm-256 color rendering
- [ ] Spawn windows
- [ ] Configurable hotkeys

**From TinyFugue (reimagined in Python):**
- [ ] Triggers (regex → Python callback)
- [ ] Macros / user-defined commands
- [ ] Gags
- [ ] Highlights
- [ ] Speedwalking
- [ ] Variables / persistent state per world

**New/unique to this project:**
- [ ] Sandboxed Python scripting API (not present in either original)
- [ ] "View generated script" bridge between GUI builder and raw code
- [ ] Script/plugin sharing format + (eventually) a community repo

## 7. Roadmap (phased; one phase per Claude Code focus session)

1. **Pin down the spec** — this document; refine as needed before coding starts.
2. **Scaffold the repo** — `/engine`, `/gui`, `/worlds`, `/tests`, `CLAUDE.md`.
3. **Build the engine headless** — asyncio telnet client, ANSI parsing, tested
   against Rick's own RhostMUSH server, console output only, no GUI.
4. **Add the trigger/macro/scripting layer** — sandboxed script execution,
   the scripting API, tested headless against captured MUD output.
5. **Build the minimal Qt shell** — one window, one connection, scrollback +
   input, wired to the validated engine.
6. **Layer in Potato's multi-window features** — address book, multi-connection,
   spawn windows, dual input.
7. **Polish** — hotkeys, settings dialog, packaging via CI for all three OSes.
7b. **Theme support (light/dark) and first-run settings dialog** — QPalette-based
    light/dark theming covering both chrome (address book, dialogs) and session
    windows (scrollback + input boxes) consistently; a first-run settings
    dialog (reusing settings_dialog.py) shown when no settings file exists yet.
7c. **Built-in client command system** (`/help`, `/connect`, and similar),
    informed by a review of the real TinyFugue source.
7d. **Menu bar, toolbar, and status bar chrome**, modeled on a review of
    Potato's real GUI (screenshot), exposing the built-in commands/handlers
    from Phase 7c as first-class menu/toolbar items rather than typed-only.
7e. **Tabbed session host window** — MainWindow becomes the persistent
    root shell (a QTabWidget of connections plus the Phase 7d chrome),
    replacing the one-window-per-connection model from Phase 5/6. The
    address book becomes a satellite picker spawned from the host rather
    than the app's entry point.
8. **Documentation & onboarding** — INSTALL.md (novice-friendly: what
   MushTato is, where to download it, OS-specific install steps including
   Gatekeeper/SmartScreen unsigned-binary workarounds, uninstall
   instructions), an in-app Help system (accessible via menu and a
   client-side command, content covering the client's features end to
   end), troubleshooting/FAQ, credits/attribution to Potato and
   TinyFugue, and a CHANGELOG.md.
8b. **Address book / World Properties overhaul** (Potato parity:
    characters, auto-sends, notes, connection specifics) + corresponding
    Help content update.
9. **(Post-1.0) Script-sharing ecosystem** — define a shareable script package
   format, decide on a distribution point (repo, in-app browser, or both).

## 8. Open questions to revisit

- ~~SQLite vs JSON for world/script storage.~~ **Decided (Phase 4): JSON.**
  See section 5.
- ~~Exact sandboxing library/approach (RestrictedPython vs custom AST
  whitelist).~~ **Decided (Phase 4): RestrictedPython.** Mature,
  purpose-built for running semi-trusted code inside a larger app (used by
  Zope/Plone for this exact purpose for ~2 decades); a hand-rolled AST
  whitelist would have to independently rediscover known sandbox-escape
  techniques (dunder-attribute traversal, format-string tricks, etc.) that
  RestrictedPython's guarded attribute/item access and maintained
  safe-builtins baseline already close off. Relevant given this project
  expects scripts from strangers once script-sharing exists (section 2).
- **Known gap: runaway script execution isn't fully bounded (Phase 4).**
  Script execution runs under a best-effort watchdog timeout, but a true
  CPU-bound busy loop in restricted Python (e.g. `while True: pass`) is
  *not* actually interrupted by that timeout — Python's GIL means a thread
  running pure-Python CPU-bound code can't be preempted from outside it, so
  the watchdog only protects against I/O-style stalls, not a genuine
  infinite loop. (Catastrophic-backtracking ReDoS in trigger patterns is
  separately closed off structurally by RE2 — see section 5 — rather than
  relying on this timeout.) The real fix for the busy-loop gap is running
  script execution in an isolated subprocess with a hard kill, which is
  more scope than a single phase; revisit as a hardening pass once the
  scripting layer sees real use, and especially before any script-sharing
  feature (section 7, phase 9) ships.
- ~~macOS notarization: pursue Apple Developer Program membership, or ship
  unsigned with a documented Gatekeeper workaround?~~ **Decided (Phase 7):
  ship unsigned for now.** Not a technical call — section 3 already
  non-goals full macOS QA until a real beta tester with actual Mac
  hardware exists, so paying $99/year on an ongoing basis to remove a
  Gatekeeper warning on a platform nobody's confirmed works well on yet
  gets the priority backwards. Users get the standard right-click-Open
  workaround in the meantime. Revisit once a real macOS user exists to
  validate against.
- Format/venue for the eventual script-sharing community.
