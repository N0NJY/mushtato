# CLAUDE.md — Project Guidance for Claude Code

This file is context for Claude Code sessions working on this repo. Read
`SPEC.md` first for the full project vision; this file is about *how* to work
on it session to session.

## Project name

**MushTato** — free, open-source, cross-platform Python GUI client for MUD/MUSH
games, combining Potato's GUI features with TinyFugue-style triggers/macros —
reimagined using sandboxed Python scripting instead of a custom scripting
language.

## Hard rules for every session

1. **One phase at a time.** Check `SPEC.md` section 7 (Roadmap) for the current
   phase. Do not start work on a later phase's features until the current one
   is done and tested. If asked to do a big cross-cutting change, flag that it
   spans phases before proceeding.
2. **Engine and GUI stay separated.** Code under `/engine` must never import
   anything from `/gui` or PySide6. The engine must be fully testable headless.
3. **Scripting is sandboxed by default.** Never wire up raw `exec()`/`eval()`
   of user-provided script text without going through the sandboxing layer
   defined in `/engine/scripting/`. "Trusted mode" (unrestricted execution) is
   an explicit, separate, opt-in code path for a user's own local scripts only
   — never the default for anything that could be shared or imported from
   another user.
4. **Every engine feature needs a headless test** before GUI work touches it.
   Use captured/sample MUD output (ANSI sequences, prompts, etc.) as test
   fixtures rather than requiring a live server connection for tests.
5. **Don't add dependencies casually.** Check `SPEC.md` section 5 (Tech Stack)
   first. If something isn't listed there and seems necessary, propose it and
   explain the trade-off before adding it.

## Repo structure

```
/engine
    /net          - asyncio telnet client, connection handling
    /ansi         - ANSI/xterm-256 color code parsing -> styled text
    /scripting    - sandboxed execution, scripting API, trigger/macro/alias engine
    /storage      - world profiles, saved scripts, settings persistence
/gui
    /windows      - main window, per-world session windows, spawn windows
    /dialogs      - trigger/macro/alias builder, settings, hotkey config
/worlds           - example/default world profile data (not user data)
/tests
    /engine       - headless tests, no GUI/Qt dependency
    /gui          - GUI smoke tests (lower priority, can lag behind engine tests)
SPEC.md
CLAUDE.md
```

## Reference material (design references, not code to transliterate)

- **Potato** (Tcl/Tk MUSH client by Mike Griffiths) — reference for GUI/UX
  behavior: address book, dual input, spawn windows, hotkeys. Source is open;
  use it to clarify exact behavior when the spec is ambiguous, not as code to
  port line-by-line.
- **TinyFugue** (classic Unix MUD client, C) — reference for trigger/macro/gag/
  highlight *semantics* (what a trigger matches, when it fires, precedence
  rules). The goal is to replicate the semantic behavior in Python, not
  reimplement TinyFugue's own scripting language syntax.

## Testing philosophy

- Engine layer: pytest, fully headless, fast, no live server or GUI needed.
  Use fixture files of raw MUD output (with ANSI codes) for parser/trigger tests.
- Integration smoke test: an optional manual/CI test that connects to a real
  MU* (e.g. Rick's RhostMUSH server) to validate telnet negotiation against a
  live server — not part of the default fast test suite.
- GUI layer: lower test priority initially; focus on engine correctness first.

## Known constraints to keep in mind

- No macOS hardware available locally — macOS builds happen via GitHub Actions
  `macos-latest` runners. Don't assume local macOS testing is possible; note
  in PRs/commits when something needs a Mac-based human check.
- This is free/open-source with no license-key or DRM system — don't add
  licensing gates, paywalls, or telemetry "phone home" logic.
- Scripting security matters even though the project is free, because the
  long-term plan includes a script/plugin sharing community — sandboxing
  decisions should assume scripts may come from strangers.

## Current phase

> Update this section as phases complete.

**Phase 1 (spec) — done. Phase 2 (repo scaffolding) — done. Phase 3
(engine/net + engine/ansi, headless) — done. Phase 4 (engine/scripting,
headless) — done, including Phase 4b (on_alias, see below). Phase 5
(minimal Qt shell) — done, validated against both fake and real
servers (see below). Phase 6 (address book, multi-window, spawn
windows, dual input) — done, see below. Phase 7 (settings/hotkeys,
CI packaging) — done, see below.** Telnet IAC negotiation is
hand-rolled on raw asyncio streams (not telnetlib3)
— see the Phase 3 discussion for reasoning. `scripts/console_client.py`
is a throwaway dev tool for manually testing against a real server
(e.g. Rick's RhostMUSH); it is not part of the shipped product.

Phase 4 decisions (see SPEC.md sections 5/8 for the full reasoning):
sandboxing is RestrictedPython; trigger patterns (`on_trigger()`)
compile against `google-re2` specifically to structurally rule out
catastrophic-backtracking ReDoS; persistence is JSON via
`engine/storage/script_store.py`. Script/callback execution runs under
a best-effort watchdog timeout that does *not* actually interrupt a
true CPU-bound busy loop (GIL limitation, documented in SPEC.md section
8) — that's an accepted, tracked gap, not an oversight. The trusted-
mode escape hatch (`engine/scripting/trusted.py`) is never invoked
automatically anywhere in the engine; it requires a caller to name it
explicitly and pass two redundant confirmation keywords every time.

Phase 4b added `on_alias()` (`engine/scripting/aliases.py`): TinyFugue/
Potato-style outbound command aliases, matched via `fullmatch` (not
`search`, to avoid a pattern like "n" firing on "nonsense") with
first-match-wins dispatch, also on `google-re2` for consistency with
`on_trigger()` and because the ReDoS risk isn't fully zero even for
user-typed input (pasted text, a future speedwalking/batch-send
feature). Reuses the existing sandbox/timeout/script-ownership
machinery unchanged — an alias callback is code of uncertain origin
exactly like a trigger callback, regardless of where the matched text
came from. `send()` is never re-run through alias expansion, by
construction (expand() is only ever meant to be called on raw user
keystrokes, never on send()'s own output) — not a recursion-depth
guard bolted on after the fact. The API surface is now 10 functions:
send/echo/gag/highlight/set_var/get_var/timer/on_trigger/on_connect/
on_alias.

**Phase 5 (minimal Qt shell) — done.** One window
(`gui/windows/main_window.py`), one connection, ANSI-rendered
scrollback, single-line input. `python -m gui.app [host] [port]` is the
entry point (prompts for host/port via a dialog if not given on the
command line — no address book yet, that's Phase 6).

Qt/asyncio architecture decision (see the Phase 5 discussion for the
full reasoning): the asyncio event loop TelnetClient needs runs on its
own background thread per connection (`gui/windows/telnet_bridge.py`,
`TelnetBridge`), never the Qt/GUI thread. Incoming data crosses to the
GUI thread via Qt signals (automatic `QueuedConnection` marshaling,
since the bridge is constructed on the GUI thread before its
background thread starts); outbound sends cross the other way via
`asyncio.run_coroutine_threadsafe`. Rejected qasync (a combined
Qt+asyncio loop on one thread) specifically because it would require a
future scripting integration to remember to wrap
`engine.scripting.sandbox.run_with_timeout` calls in
`loop.run_in_executor(...)` to avoid freezing the GUI on a slow
callback — under the chosen background-thread model, that watchdog's
blocking wait naturally lands on the per-world background thread
instead, by construction, so **no special-casing is needed when
scripting gets wired in later.** No new dependency was needed either
way in the end (background-thread approach uses only stdlib
`threading`/`asyncio` + PySide6's existing signal/slot mechanism).

**Scripting (`engine/scripting`, Phase 4/4b) is deliberately NOT wired
into the GUI yet** — this phase is raw connect/display/send only, no
`ScriptWorld`, no triggers, no aliases touching the GUI. That's an
explicit deferral to a later phase, not an oversight; see the
Qt/asyncio note above for why the current architecture should make
that wiring safe when it happens.

`engine/ansi`'s `StyledSegment` output is converted to Qt formatting in
`gui/windows/styled_text_qt.py` (kept separate from `MainWindow`
specifically because it's the one piece of this phase testable
headless) — engine/ansi itself is reused as-is, no ANSI parsing
duplicated in the GUI layer, per CLAUDE.md rule 2.

The scrollback pane uses a fixed-width font
(`QFontDatabase.SystemFont.FixedFont`), not Qt's default proportional
font — found via manual testing against a real RhostMUSH server (see
below), where the default font broke alignment of ASCII-art banners/
borders that assume a fixed-width terminal.

Validated at two levels, not just one: (1) the automated headless test
suite (`tests/gui/`) includes `test_telnet_bridge_integration.py`,
which drives a real `TelnetBridge` (real background thread, real
asyncio, real Qt signal marshaling) against a local fake asyncio
server — no fakes at the bridge/architecture level, only the "MUD" on
the other end is fake; and (2) beyond that, manual end-to-end
validation against two distinct *real* MUSH servers, which is a
stronger check than most earlier phases got and worth having on
record: `127.0.0.1:4444` (Rick's own local RhostMUSH, running on this
machine) and `silvren.com:4444` (a separate, live third-party RhostMUSH
elsewhere on the internet, *not* owned by Rick — happens to run the
same welcome-banner theme, which is why the two looked identical at
first glance; be considerate about how much automated/repeated testing
hits that one going forward, same courtesy as any other real user's
server). The manual check confirmed real DNS + TCP + telnet
negotiation, real ANSI colors rendering correctly, and a full
interactive round-trip (guest login, `look`, server response) against
both real servers.

**Phase 6 (multi-window Potato features) — done.** Address book
(`gui/windows/address_book_window.py` + `gui/dialogs/world_edit_dialog.py`),
multiple simultaneous connections, a spawn-window feature, and dual
input, all layered on Phase 5's single-window shell without changing
its core architecture.

Storage decisions (checkpoint discussion before code): address book
persistence lives in a **sibling module**,
`engine/storage/address_book.py` (`WorldProfile`, `load_address_book`/
`save_address_book`), not an extension of `script_store.py` — different
data shape/access pattern (a browsed-as-a-whole list vs. independent
per-world documents). Where the file actually lives was also decided
now (Phase 4 had deferred it): `engine/storage/paths.py` uses
`platformdirs` (new dependency) for OS-idiomatic locations
(`%APPDATA%`/`~/Library/Application Support`/`~/.config`) rather than a
single hardcoded path.

Multi-window model: confirmed, not re-decided — each "Connect" from the
address book opens its own independent `MainWindow` + `TelnetBridge`
pair with its own background thread, exactly as Phase 5's checkpoint
discussion already committed to. `AddressBookWindow` just holds
references to the windows it opens (`open_windows`) so Qt doesn't
garbage-collect them, and drops the reference again via each window's
new `closed` signal. Closing the address book itself doesn't close open
sessions — Qt's default `quitOnLastWindowClosed` behavior handles this
correctly as long as nothing ties app-quit to that one window
specifically, which nothing does.

Dual input (`gui/windows/history_line_edit.py`'s `HistoryLineEdit`,
used twice in `MainWindow`): two simultaneously-visible boxes, not a
single toggled/mode-switched one — chosen because "replying while
mid-pose" implies wanting both available at once, which a toggle would
break. `input_line` (primary, "Command...") is where alias expansion
would apply once scripting is wired into the GUI (still deferred, see
below); `secondary_input` ("Pose/says...") is meant to bypass it then,
so a pose starting with a word like "n" is never silently rewritten.
Both currently send identically (`MainWindow._send`'s `apply_aliases`
parameter is a documented no-op hook, not real behavior yet) and each
box keeps its own independent recall history. Both always send to the
same one connection regardless of which box was used.

Spawn windows (`gui/windows/spawn_window.py`): concrete first example
is a **log-mirror window** — `MainWindow.spawn_log_window()` pops a
window that live-mirrors the connection's incoming text from the
moment it's created onward, with no content parsing. A WHO-list- or
channel-specific spawn window was considered and rejected for now: it
would need server-format-specific string heuristics living in the GUI
layer without triggers wired in yet, which is exactly the kind of
fragile special-casing the engine/GUI split exists to avoid. Revisit
once triggers can target a specific pane.

**Scripting (`engine/scripting`) is still deliberately NOT wired into
the GUI** — Phase 6, like Phase 5, is connect/display/send/multi-window
only. This is called out explicitly (again) so it stays a visible,
revisited-every-phase deferral rather than something that quietly never
gets addressed.

Manually validated end-to-end against the real local RhostMUSH
(`127.0.0.1:4444`): address book add/connect, two simultaneous
independent connections to the same server, dual input (both boxes
echoing and sending correctly, confirmed via full-text search after
letting the banner finish arriving — an earlier attempt typed too early
and looked broken until the timing was fixed), and a spawn log window
correctly receiving only text that arrived after it was created.

**Phase 7 (polish + packaging) — done.** Settings dialog
(`gui/dialogs/settings_dialog.py`) for configurable hotkeys, and a
GitHub Actions workflow (`.github/workflows/build.yml`) building
PyInstaller packages for Windows/Linux/macOS.

Settings/hotkey storage: a third sibling in `engine/storage`
(`settings.py`), alongside `address_book.py`/`script_store.py` —
already anticipated since Phase 2's repo-structure comment named
"settings persistence" as one of engine/storage's three jobs, so this
wasn't really a fresh architectural call. v1 content is hotkeys only
(`Settings.hotkeys: Dict[str, str]`); loading merges in defaults for
any action missing from a saved file, so adding a new configurable
action later can't leave it unbound. Concrete starting keybindings:
Add World `Ctrl+N`, Connect `Ctrl+Return` (address book); Spawn Log
Window `Ctrl+L`, Switch Input Focus `Ctrl+Tab` (session window); Close
Window `Ctrl+W` (both). `MainWindow` itself never touches disk for
settings on its own -- it defaults to the plain `DEFAULT_HOTKEYS`
constant if not given a `hotkeys` dict, so tests never depend on
ambient real user-data state; the real disk-loaded settings are passed
in explicitly by `gui/app.py`'s direct-connect path and by
`AddressBookWindow.connect_to`. A settings change applies to
newly-opened windows only, not ones already open -- live-reload across
open windows was judged more machinery than v1 needs.

macOS distribution (checkpoint discussion before code): shipping
**unsigned** for now, not pursuing Apple Developer Program
notarization ($99/year) yet. This isn't a technical call -- SPEC.md
section 3 already non-goals full macOS QA until a real beta tester
with actual Mac hardware exists, and section 8 already listed
notarization as an explicitly open question; paying an ongoing fee to
remove a Gatekeeper warning on a platform nobody's confirmed works well
on yet gets the priority backwards. Revisit once a real macOS user
exists to validate against. Users get the standard right-click-Open
Gatekeeper workaround in the meantime.

CI (`.github/workflows/build.yml`): two triggers -- every push to
`main` builds all three OSes and uploads workflow artifacts only
(catches packaging breakage early); pushing a `v*` tag does the same
build and additionally attaches the artifacts to a GitHub Release.
PyInstaller uses `--onedir` (the checked-in `packaging/mushtato.spec`,
not a bare CLI flag), not `--onefile` -- more reliable Qt-plugin
discovery for PySide6 at the cost of shipping a folder/zip instead of
one exe. Packaging the build output is OS-specific: `ditto` on macOS
(preserves `.app` bundle permissions/symlinks, which a generic zip
would mangle), `7z` on Windows, `tar` on Linux.

A real, separate packaging bug surfaced and got fixed while building
the spec file locally: `pip install -e .` failed outright because
setuptools couldn't auto-discover packages among the repo's multiple
top-level directories (`engine`, `gui`, `tests`, `scripts`, `worlds`).
Fixed via an explicit `[tool.setuptools.packages.find]` `include`
pattern in `pyproject.toml` restricting discovery to `engine*`/`gui*` --
otherwise this would have silently blocked any contributor trying to
install the project for local development.

Verified locally, honestly scoped: built the actual Linux PyInstaller
artifact from the checked-in spec and confirmed it launches and stays
running with no import errors (a real functional check, not just "the
build didn't error") -- this only covers what `gui/app.py`'s import
graph currently reaches (PySide6, engine/net, engine/ansi,
engine/storage); `engine/scripting`'s RestrictedPython/`google-re2`
aren't bundled by this build since nothing in the GUI imports them yet.
Windows and macOS builds, and the GitHub Actions workflow itself, could
not be verified locally -- Rick will check GitHub's Actions tab once
this is pushed.

Still NOT wiring `engine/scripting` into the GUI -- same deferred
decision as every phase since Phase 4b, called out again so it stays
visible rather than quietly dropped.

Next: Phase 8, documentation.
