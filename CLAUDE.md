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
CI packaging) — done, see below. Phase 7b (theme support, first-run
settings dialog) — done, see below. Phase 7c (built-in client command
system) — done, see below. Phase 7d (menu bar, toolbar, status bar
chrome) — done, see below. Phase 7e (tabbed session host window) —
done, see below. Phase 8 (documentation & onboarding) — done, see
below. Phase 8b (address book / World Properties overhaul) — done,
see below. Phase 9 (GUI-scripting integration: engine/scripting wired
into the tabbed session GUI for real) — done, see below. Phase 10
(quick-win polish: About credits, Edit menu) — done, see below. Phase
11 (movable tabs, spawnlog save, error log, find/search) — done, see
below.** See `PHASE10-12_PLAN.md` (repo root) for the full Phase 10-12
plan and the checkpoint that renumbered script-sharing from Phase 10 to
Phase 13. Telnet IAC negotiation is
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

A real bug in that "verified locally" claim surfaced once Rick actually
ran the CI-built Linux artifact on a real desktop: it aborted on launch
with "no Qt platform plugin could be initialized" -- since Qt 6.5, the
xcb platform plugin requires `libxcb-cursor0` to load at all, and
`ubuntu-latest` doesn't have it (or its usual xcb companions)
pre-installed. The local build in this repo's dev sandbox had actually
already warned about exactly this (`Library not found: could not
resolve 'libxcb-cursor.so.0'`) during the PyInstaller build step, but
local verification used `QT_QPA_PLATFORM=offscreen`, which bypasses the
xcb platform entirely -- so the one thing that warning was about was
never actually exercised before calling the build "verified." Fixed by
installing `libxcb-cursor0` plus its standard xcb companions
(`libxkbcommon-x11-0`, `libxcb-icccm4`, `libxcb-image0`,
`libxcb-keysyms1`, `libxcb-randr0`, `libxcb-render-util0`,
`libxcb-shape0`, `libxcb-xfixes0`, `libxcb-xinerama0`) on the CI runner
*before* the PyInstaller build step, so they get bundled into the
artifact itself rather than documented as a user-side `apt install`
requirement -- PyInstaller can only bundle a shared library that's
present on the machine doing the building. Lesson for future sessions:
"offscreen" is fine for automated headless tests, but it is not a
substitute for exercising the real platform plugin path when verifying
a packaged GUI build.

Still NOT wiring `engine/scripting` into the GUI -- same deferred
decision as every phase since Phase 4b, called out again so it stays
visible rather than quietly dropped.

**Phase 7b (theme support, first-run settings dialog) — done.**
Extended `Settings` (`engine/storage/settings.py`) with a `theme`
field (`"dark"`/`"light"`, default-merged like hotkeys so old settings
files keep working), a new `gui/theme.py`, and a first-run flow in
`gui/app.py`.

Theme approach (checkpoint discussion before code): `QPalette` via
`QApplication.setPalette()`, not Qt Style Sheets or a third-party theme
library -- no new dependency, and it reaches chrome, dialogs, input
boxes, *and* the scrollback for free, since nothing in this codebase
had ever set an explicit palette/stylesheet override before this
phase.

The dark theme's scrollback/input colors are **Rick's own real Potato
client's actual shipped defaults**, not invented -- pulled directly
from `potato.vfs/lib/potato-config.tcl` on his machine: output pane
`#000000` background / `#aeaeae` dimmed text, input box `#000000`
background / `#ffffff` brighter text (Potato deliberately makes typed
input brighter than server output). Chrome colors (dialogs/buttons/
list) have no authentic Potato reference -- Potato's own skin system is
about native ttk widget styles (xpnative/aqua), not a custom dark
scheme for its own dialogs -- so those are this project's own design,
called out as such in `gui/theme.py`'s docstring rather than presented
as more "authentic" than they are. The light theme has no Potato
precedent at all (Potato's own defaults are black-background); it's
this project's own reasonable choice.

**ANSI black-on-black checkpoint, explicitly declined:** Potato's own
answer to the light/dark ANSI-legibility risk flagged before code was
proposed -- its "black" ANSI color is `#222222`, not pure black,
specifically so it isn't invisible against its own black output pane.
Adopting the equivalent fix in `engine/ansi/palette.py`
(`basic_color(0)`, currently pure `(0, 0, 0)`) was proposed and
**declined** -- that file is Phase 3, a different layer than this
phase's actual scope, and Rick chose to leave it untouched. The
mitigation that *did* ship is scoped to the GUI/theme layer only: the
dark theme's own background choice (Potato's `#000000`) is what keeps
things legible for the overwhelmingly common case, not a change to the
engine's color mapping. The broader risk (a server sending explicit
light ANSI foreground colors against the light theme) remains an
accepted, documented gap, same pattern as the GIL busy-loop timeout gap
-- a full theme-aware ANSI remap was raised and explicitly scoped out
as bigger than "a small addition."

Live-reload, verified empirically rather than assumed: calling
`apply_theme(app, new_theme)` again after startup **does** update
already-open windows' chrome and input boxes (they just inherit the
app-wide `QPalette`, and Qt's own event loop propagates the change) --
confirmed both programmatically and with a real screenshot showing an
already-open session window's input boxes and button switching from
dark to light live. The scrollback's own dimmer Base/Text override
(`gui/theme.scrollback_palette`, applied once per-widget at
construction to get Potato's distinct output-vs-input colors) does
**not** live-update on already-open windows -- confirmed by the same
screenshot, which shows the scrollback still black after the app
switched to light. Only newly-opened windows pick up a changed theme's
scrollback colors, same limitation pattern as hotkeys from Phase 7.

First-run detection: `not settings_path().exists()`, checked once in
`gui/app.py` via a new `ensure_settings()` helper (split out from
`main()` specifically so it's unit-testable without a real
QApplication/event-loop run) -- applies before either the direct-
connect or address-book path, so it's independent of which entry mode
is used. Reuses `settings_dialog.py` as-is (a `first_run: bool` flag
just adds one intro `QLabel`), not a separate onboarding dialog; a
fuller "welcome tour" belongs to Phase 8 (documentation & onboarding),
not this phase. Per Rick's choice, the dialog's result is saved
whether OK or Cancel is clicked, so it's shown at most once ever, never
nagging on a later launch.

Manually validated end-to-end against the real local RhostMUSH
(`127.0.0.1:4444`): dark theme applied at startup renders exactly like
Potato's real client (black scrollback, dimmed output text, brighter
input text); switching to light via the settings dialog updated the
address book and an already-open session window's chrome/inputs live,
while that window's scrollback correctly stayed on its
construction-time theme, matching the verified/documented limitation
precisely.

**Phase 7c (built-in client command system) — done.** New
`engine/commands.py` (`CommandTable`/`CommandOutcome`) plus command
registrations in `gui/windows/main_window.py`.

**The real TinyFugue source (`/home/rick/git/tinyfugue`) was consulted
before any design or code** — reference-only, same approach CLAUDE.md
already establishes for Potato, not code to port. Concretely useful
findings, verified in the actual C source rather than assumed from
memory:
- Prefix/collision convention (`src/expand.c`'s `statement()`): no
  leading `/` sends the line to the MUD verbatim; a single leading `/`
  is a command (stripped, rest is `name args`); a leading `//` is the
  escape hatch -- one `/` is stripped and the remainder (still
  starting with a `/`) is sent as literal data. TF's actual,
  decades-old answer to "the MUD server also uses this prefix" —
  adopted exactly in `engine/commands.py`.
- Command lookup (`src/command.c`'s `find_builtin_cmd`): exact,
  case-insensitive name match via binary search over an alphabetically
  sorted table -- **no abbreviation support**, contrary to a
  half-remembered assumption going in. An unrecognized `/word` is an
  error ("no such command or macro"), never silently forwarded as
  plain text. Both behaviors adopted exactly.
- Argument parsing: no single uniform scheme in TF -- each command
  handler gets the raw remainder-of-line string and parses its own
  arguments however it needs. `engine/commands.py`'s handlers follow
  the same flexibility rather than forcing one universal
  split-by-whitespace convention.
- Help system (`src/help.c`): an external indexed help-text file with
  major/minor topic markup and its own index-builder tool -- real
  precedent for Phase 8's Help system, deliberately not built now (see
  below).
- Command set (`src/cmdlist.h`, ~60 entries): TF's own scripting-
  language directives (`DEF`/`EVAL`/`LET`/`SHIFT`/`REPEAT`) and
  process-management commands (`KILL`/`PS`/`SH`) don't apply here --
  Python is the scripting language (SPEC.md non-goals) and this
  sandboxing model doesn't spawn subprocesses. Confirms *not* porting
  TF's command set wholesale was the right call, not just a
  simplification for convenience.

**Design principle applied throughout, not just noted once (Rick's
explicit correction after the first proposal missed it in two
places):** every built-in command must call the *exact same handler*
its GUI equivalent (button/hotkey) already calls -- never a parallel
reimplementation. This actually changed the v1 list during review, not
just after it:
- `/quit` -> `self.close()` (same as the Ctrl+W hotkey and the
  window's own close button) and `/spawnlog` -> `self.spawn_log_window()`
  (same as the button and Ctrl+L) were solid matches from the start.
- `/connect` and `/settings`'s real GUI equivalents
  (`AddressBookWindow.connect_to()` / `._open_settings()`) live on a
  *different window* than the one commands are typed into. Fixed by
  adding an optional `MainWindow(..., address_book=None)` reference --
  set by `AddressBookWindow.connect_to()` when it opens a session
  window, `None` in direct-connect mode (`gui/app.py host port`, which
  has no address book at all). Both commands check for `None` and
  report "not available in this session" rather than erroring, instead
  of pretending the capability exists where it doesn't.
- `/help` has no GUI equivalent yet, by design: SPEC.md's own Phase 8
  entry already pairs a menu-accessible Help system with the client-
  side command as *that* phase's joint deliverable. Building the menu
  now would be scope creep into Phase 8, so `/help` ships as an
  explicit, acknowledged command-only exception for this phase --
  currently just a placeholder listing registered commands, per the
  explicit instruction that rich help content is Phase 8's job.
- `/version` had no GUI equivalent either -- fixed by adding a small
  "About" button (next to "Spawn Log Window") that shares a single
  `mushtato_version()` helper (reads `pyproject.toml`'s version via
  `importlib.metadata`, not a second hardcoded copy that could drift)
  with the command handler, rather than adding the button as an
  afterthought disconnected from the command.
- `/theme <dark|light>` has no single dedicated button, but calls the
  identical `Settings`/`save_settings`/`apply_theme` chain the settings
  dialog's OK button already triggers -- judged "the same handler, a
  faster route to it" rather than a parallel implementation, and kept
  on that basis.

Dual input wiring: only the primary (`input_line`) checks for `/`
commands; the secondary (`secondary_input`, poses/says) always
bypasses command processing entirely, for the identical reason it's
already meant to bypass alias expansion once that's wired in -- a pose
starting with `/` must never be silently reinterpreted. Verified with
a test that types `/quit` into the secondary box and confirms it's
sent to the MUD literally, not executed.

Manually validated end-to-end against the real local RhostMUSH: `/help`,
`/version`, `/spawnlog`, `/theme light`, and the `//` escape hatch (sent
`/notacommand` literally, visible in the scrollback) all worked
correctly; `/connect` from a session window opened a second window via
the address book's real `connect_to()` (confirmed by the address
book's own open-window count); and switching theme via `/theme`
propagated live to the address book window exactly as Phase 7b's
verified live-reload behavior predicts, not a new/different code path.

Still NOT wiring `engine/scripting` into the GUI -- same deferred
decision as every phase since Phase 4b, called out again so it stays
visible rather than quietly dropped.

**Phase 7d (menu bar, toolbar, status bar chrome) — done.** Extended
`gui/windows/main_window.py` (`MainWindow._build_chrome()`) and
`gui/windows/address_book_window.py` (`AddressBookWindow._build_menu()`).

Triggered by Rick sharing a real screenshot of Potato's actual GUI
(menu bar: File/Edit/View/Logging/Options/Tools/Help; a grouped
toolbar; a tab bar for multiple worlds; a status bar) and asking for
something "similar" -- a menu bar plus buttons exposing MushTato's
internal commands, not just typed `/commands`. Two checkpoint questions
before code, both resolved by Rick directly rather than needing the
full multi-choice tool: (1) Potato's tab bar implies multiple worlds
live in *one* window, which conflicts with MushTato's Phase 5 decision
(separate top-level window per connection) -- Rick clarified that in
Potato itself, each toolbar button (Conf, Events, Log, Upload, Editor,
Mail Window, Find, Help) already opens its own separate window, so
there's no real conflict: MushTato keeps one-window-per-connection,
and the tab bar simply isn't replicated -- confirmed as correct rather
than needing to reopen the Phase 5 decision. (2) which of Potato's
toolbar/menu actions get built for real this phase, chosen via
AskUserQuestion: grayed-out disabled placeholders for the ones with no
backing MushTato feature yet (Editor, Upload, Mail Window, Events,
Find), rather than leaving them out of the chrome entirely -- so the
menu visually previews Potato's fuller feature set for later phases to
enable, without pretending they work now.

Same "same handler, not parallel implementation" principle as Phase 7c,
applied throughout: every enabled menu/toolbar `QAction` calls the
exact same method its typed `/` command (or existing button/hotkey)
already calls. This extended the command set, not just the GUI --
`/disconnect` and `/reconnect` are new built-in commands added
specifically so the new Reconnect/Disconnect actions have a single
shared handler (`MainWindow._disconnect()`/`_reconnect()`) rather than
the GUI action being the only path to that behavior. `_reconnect()`
calls `stop()` then `start()` on the *same* `TelnetBridge` instance
(rather than constructing a new one) since `TelnetBridge.start()`
already spins up a fresh background thread/loop/client each call (see
`telnet_bridge.py`'s `_thread_main`) -- reusing the instance means the
signal connections made once in the constructor never need redoing.
`/theme`'s logic was extracted into a shared `_set_theme()` helper so
both the text command and the new View > Theme > Dark/Light checkable
menu actions (a `QActionGroup`, mutually exclusive) go through one
code path; this also fixed a latent gap where `_cmd_theme` previously
never updated `self._theme`, so a spawn-log window opened after a
`/theme` change would have inherited the session's original theme
instead of the current one.

The old Phase 7c button row (`spawn_log_button`, `about_button`) was
removed, not kept alongside the new toolbar -- keeping both would have
meant two separate widgets triggering the same action, which is exactly
the kind of redundant chrome this phase exists to replace with a single
coherent set of entry points.

New status bar (`MainWindow`): world name, host:port, connection state
(Connecting/Connected/Disconnected, updated by the same bridge signal
handlers that already drove scrollback messages), a live "Connected
For: Xh Ym" duration counter, and a clock -- both ticked by one
`QTimer` (`_update_clock`, 1s interval), mirroring Potato's real status
bar layout from the reviewed screenshot.

`AddressBookWindow` also gained a menu bar (File: Add/Edit/Delete
World, Connect, Settings, Close; Help: About) -- no new toolbar there,
since Phase 6 already gave it a button row for the same actions, so
"buttons for the internal commands" was already satisfied on that
window; only the menu bar was new.

A real PySide6/shiboken wrapper-lifetime quirk surfaced writing this
phase's tests: a `QMenu` or `QAction` returned by `addMenu()`/
`addAction()` and kept only as a bare local variable can have its
underlying C++ object garbage-collected once the enclosing method
returns, causing `RuntimeError: Internal C++ object already deleted`
on a later `menuBar().actions()[i].menu()`-style lookup -- reproduced
directly, not assumed. Fixed by keeping every menu and action as a
named `self.*` attribute in both `MainWindow` and `AddressBookWindow`
(e.g. `self.file_menu`, `self.connect_menu_action`), and writing tests
to reach them via those attributes directly rather than by walking
`menuBar().actions()`.

Manually validated end-to-end against the real local RhostMUSH
(`127.0.0.1:4444`), including a real disconnect/reconnect cycle (not
just a fake-bridge test): menu bar and toolbar populated correctly with
placeholders visibly grayed out, status bar showed live host/state/
duration/clock, About and Help both showed correct content, Disconnect
followed by Reconnect via the toolbar actually dropped and
re-established the live telnet connection (visible in the scrollback:
"[Disconnected]" then a fresh "Welcome to..." banner replay), and
switching theme via the View menu applied live -- screenshotted for the
record (session window: menu bar, toolbar with grayed placeholders,
status bar, and the disconnect/reconnect transcript all visible in one
capture).

Still NOT wiring `engine/scripting` into the GUI -- same deferred
decision as every phase since Phase 4b, called out again so it stays
visible rather than quietly dropped.

**Post-7d fix: scrollback ignored the theme on a real desktop.** Rick
downloaded and ran the actual packaged build and reported that the
theme reached the window chrome but not "the actual terminal" (the
scrollback pane stayed on default light colors instead of Potato's
dark/dimmed output colors) -- a real bug this session's own headless
tests and offscreen-platform screenshots never caught, because Qt's
`offscreen` QPA platform doesn't load a real platform theme plugin at
all, so it can't reproduce this. Same category of gap as the Phase 7
`libxcb-cursor0` packaging bug: verification that only ever exercised
`offscreen` isn't a substitute for a real desktop's platform
integration. Root cause: on several real Linux desktops (KDE/qt6ct-
style platform theme integration in particular), Qt's native style
pulls its own palette from the system theme and can silently override
an app's own `QApplication.setPalette()` for individual widgets --
Fusion is the one built-in Qt style that reliably honors an explicitly
-set palette everywhere. Fixed in `gui/theme.py`'s `apply_theme()` by
calling `app.setStyle(QStyleFactory.create("Fusion"))` before
`setPalette()` (order matters: Qt resets to a new style's own default
palette on a style change, so setting the palette first would just get
overwritten). No new dependency -- `QStyleFactory` is stdlib PySide6.
Two new headless tests assert the style is actually forced to Fusion
and that the palette is set after (not before) that style change;
neither test can prove the real-desktop rendering is fixed, only that
the code takes the documented order-dependent path -- Rick will
re-verify this against a fresh download, same as any other
can't-verify-headless GUI change in this project.

**Post-7d fix #2: the Fusion fix alone wasn't enough for MainWindow's
own scrollback.** Rick re-tested the fresh build with fix #1 above and
reported real progress but a narrower remaining gap: the address book
window and a spawned log window both themed correctly, but MainWindow's
own scrollback (the actual session/"terminal" pane) still didn't. The
one structural difference between those two working windows and the
non-working one: `AddressBookWindow`/`SpawnWindow` are plain
`QMainWindow`s with no toolbar, while `MainWindow` (as of Phase 7d) has
a menu bar, toolbar, and status bar. `MainWindow.scrollback`'s palette
override was being set early in `__init__`, before `_build_chrome()`
added that chrome -- moved to run immediately after `_build_chrome()`
instead, on the theory that QMainWindow's toolbar/dock-area layout
machinery re-polishes the central widget subtree once a toolbar is
added, which can discard an explicit palette override set beforehand.
Same honesty caveat as fix #1: this can't be proven in the offscreen
headless sandbox (a new regression test only guards the ordering, it
can't reproduce the real-desktop symptom), so this is a
best-reasoned-from-the-evidence fix, not a confirmed root cause --
Rick will re-verify against another fresh build.

**Post-7d fix #3: the real root cause, found by pixel-sampling, not
eyeballing.** Rick sent two more screenshots after fix #2 and reported
the scrollback still wasn't dark. A first visual read of the
screenshots looked correctly dark -- wrong; sampling actual pixel RGB
values with PIL (`im.getpixel(...)`) at multiple empty-scrollback
coordinates showed pure white (`255,255,255`) throughout the scrollback
viewport, while the input box sampled genuinely black (`0,0,0`) --
Rick's report was correct and the earlier "looks dark to me" read was
not a substitute for actually checking. Real root cause: `QTextEdit` is
a `QAbstractScrollArea`, and its visible background is painted by a
separate child widget, `viewport()` -- calling `.setPalette()` on the
`QTextEdit` itself doesn't reliably propagate to the viewport on every
platform/style combination, so fixes #1 and #2 (style + ordering) never
addressed the actual cause. Fixed with a new
`gui/theme.apply_scrollback_theme(text_edit, theme)` helper that sets
the palette AND `autoFillBackground(True)` on **both** the widget and
`.viewport()` -- used by `MainWindow` and `SpawnWindow` alike (both had
the same latent bug; `SpawnWindow` happening to look fine in Rick's
first test was inconclusive, not evidence it was actually correct).
Also added a `showEvent()` override on both windows that reapplies the
same theme every time the window becomes visible, as a second guard
against whatever real-desktop style/theme integration might reset a
widget's palette around show time. This time verified with actual pixel
sampling in this sandbox too (not just re-asserting the same
screenshot-eyeballing that was wrong last time): background samples at
multiple empty-scrollback coordinates in a fresh local-RhostMUSH smoke
test came back pure `(0, 0, 0)` in both `MainWindow` and a spawned
`SpawnWindow`. Real-desktop confirmation is still Rick's to do, per the
same pattern as fixes #1/#2, but this round's own verification step was
substantively stronger than before.

**Resizable input area, added alongside the fix #3 work.** Rick also
asked to be able to resize the command input box. `HistoryLineEdit` is
a plain `QLineEdit`, whose default vertical size policy is `Fixed` --
a `QVBoxLayout` alone can't give the user any control over the split
between scrollback and input. `MainWindow` now wraps `input_line` +
`secondary_input` in a container widget and puts that container and
`scrollback` into a `QSplitter` (`self.splitter`, vertical orientation,
5:1 stretch favoring the scrollback initially) -- both line edits' size
policies were switched to `Expanding` so dragging the splitter handle
actually changes their visible height, not just invisible layout
padding around a fixed-size box. `input_line`/`secondary_input` remain
the same objects at the same attribute names, so no existing test or
GUI-wiring code needed to change.

**Phase 7e (tabbed session host window) — done.** New
`gui/windows/session_tab.py` (`SessionTab`), rewritten
`gui/windows/main_window.py` (`MainWindow`) and
`gui/windows/address_book_window.py` (`AddressBookWindow`), new
`gui/version.py`.

Triggered by Rick asking to examine whether connections could be tabs
instead of separate windows -- flagged up front (per this file's rule
1) that it's a cross-cutting change spanning every GUI phase since 5,
then resolved via a checkpoint before any code: Rick's answer reframed
the whole model, not just "tabs vs. windows" -- **the main connection
window is the persistent root of the app**, opened at launch whether
or not anything is connected yet; the address book is a satellite
picker spawned *from* it (`File > Address Book...`), not the app's
entry point; closing the last tab leaves the (now empty) host window
open, ready for a new connection -- only the window's own X button or
`File > Exit` actually quits the program; a spawned log window stays
bound to the one tab it was opened from, unaffected by tab-switching
afterward. This is the reverse of every prior phase's model (Phase 5's
MainWindow was one connection; AddressBookWindow was the thing you
started from) -- confirmed as an intentional, explicit reversal, not
scope creep.

Architecture split, following from that: `MainWindow` used to be both
"one connection" and "the window chrome" in the same class. Phase 7e
splits those: **`SessionTab`** (`QWidget`, not a window) now owns
exactly what MainWindow used to own per-connection -- scrollback, dual
input + splitter, `TelnetBridge`, `CommandTable`, spawn windows, own
theme captured at construction. **`MainWindow`** now owns exactly one
`QTabWidget` of `SessionTab`s plus the Phase 7d chrome (menu bar,
toolbar, status bar), all of which now act on *whichever tab is
currently active* (`tab_widget.currentWidget()`) rather than on "this
one connection." `SessionTab` is constructible with `host_window=None`
for standalone headless tests (mirroring the `address_book=None`
pattern Phase 7c already used) -- `/connect`, `/settings`, `/theme`
degrade to "not available" in that case, which only happens in tests;
the real app always supplies a host.

Close semantics, precisely per Rick's answer: `Ctrl+W`/toolbar
"Close"/`/quit` now close the *active tab* (`MainWindow.close_tab`),
never the host window itself, even when it's the last tab
(`close_current_tab` just leaves `tab_widget` at zero tabs, host stays
visible -- covered by
`test_multi_window_smoke.test_closing_the_last_tab_keeps_the_host_window_open`).
The host window's own `closeEvent` is the one place a real "exit"
happens: it explicitly shuts down every open tab's bridge and calls
`QApplication.quit()` directly, rather than relying on Qt's
`quitOnLastWindowClosed` default -- the address book or a spawn window
might still be open when the root window closes, and Rick's answer was
explicit that closing the root should exit "completely" regardless.

Connecting to an already-open world switches to the existing tab
instead of opening a duplicate (`MainWindow.open_tab` checks
`tab_widget` for a matching host:port first) -- not explicitly
requested, but a small, obviously-correct addition once tabs made
"the same world twice" a real possibility that didn't exist under the
one-window-per-connection model.

Settings/About moved to be host-only, not duplicated on the address
book: since the host now always exists, `AddressBookWindow` no longer
loads/saves `Settings` at all (`MainWindow.open_settings()` is the one
implementation, reused by the `Options` menu action and the `/settings`
command alike) and lost its own `Help > About` menu entirely --
matches Rick's own framing ("I'd like everything to reside in the
connection window unless we spawn something like log, editor, etc").
`AddressBookWindow` is now a lean picker: browse/add/edit/delete saved
worlds, `Connect` delegates to `host_window.open_tab(...)`, nothing
else.

Hotkeys consolidated to one owner for the same reason: previously each
per-connection `MainWindow` built its own `QShortcut`s at construction,
so a `Settings` change only ever reached the *next* window opened
(documented as an accepted limitation in Phase 7's notes). With exactly
one host window now, `MainWindow._apply_hotkeys()` tears down and
rebuilds its `QShortcut`s on every `open_settings()` save, so a hotkey
change takes effect immediately in the same running session -- a real
improvement made possible by the architecture simplification, not a
deliberate goal going in.

Test impact was as large as flagged up front: roughly 60 of the ~105
GUI tests directly instantiated the old per-connection `MainWindow`.
Rewrote `test_main_window_smoke.py`/`test_dual_input.py`/
`test_spawn_window.py`/`test_commands_wiring.py` against `SessionTab`
directly (`FakeBridge` kept in `test_main_window_smoke.py` at its
original import path so other files' imports didn't need touching);
`test_multi_window_smoke.py` rewritten around one host with multiple
tabs; `test_hotkeys.py`/`test_chrome.py` rewritten for host-level
chrome acting on the active tab; `test_address_book_window.py` now
uses a `FakeHostWindow` recording `open_tab()` calls instead of a fake
session-window factory; four `test_settings_dialog.py` tests that
exercised `AddressBookWindow`'s now-removed settings ownership were
deleted outright rather than adapted, since that capability no longer
exists there by design. New `test_host_window.py` covers the host-only
behaviors that have no Phase-7d equivalent: closing the host stops
every tab's bridge and force-quits the app, and a settings save live-
reloads hotkeys. Full suite: 224 passing (up from 219 pre-Phase-9,
net new coverage despite the large rewrite).

Manually validated end-to-end against the real local RhostMUSH
(`127.0.0.1:4444`) and a second real connection to `silvren.com:4444`
in a second tab, in the same run: host starts with zero tabs; opening
the address book and connecting added a labeled tab and updated the
status bar; connecting to the same host:port again switched to the
existing tab rather than duplicating it (confirmed by tab count
staying at 1); opening a second, different world added a second tab;
switching tabs updated the status bar to match; a spawned log window
bound correctly to whichever tab was active when it was spawned;
`/quit` closed just that one tab; Disconnect/Reconnect via the toolbar
actually dropped and re-established the live connection on whichever
tab was then active; switching theme applied live; closing every tab
one at a time via the Close action left the host window open and
visible throughout, with the status bar correctly falling back to "No
connection" at zero tabs -- screenshotted for the record.

Still NOT wiring `engine/scripting` into the GUI -- same deferred
decision as every phase since Phase 4b, called out again so it stays
visible rather than quietly dropped.

**Phase 8 (documentation & onboarding) — done.** New `gui/help/`
package (`topics.py`, `markdown_tools.py`, `help_window.py`), new
`INSTALL.md`/`TROUBLESHOOTING.md`/`CREDITS.md`/`CHANGELOG.md`, small
additions to `engine/commands.py` and `gui/windows/session_tab.py`/
`main_window.py`.

Two checkpoints before code, per this file's own standing rules (added
partway through this same session, immediately put to use). First
checkpoint: content architecture. Resolved: (1) current reality only --
Rick's own prompt said "multi-window sessions," caught and corrected to
document Phase 7e's actual tabbed model instead of stale wording, per
his confirmation; (2) a new Menus & Toolbar topic added beyond the
original list, since a novice clicking a disabled placeholder button
(Editor/Upload/Mail Window/Find) and getting nothing is exactly the
confusion this phase exists to prevent; (3) one scrolling `QTextBrowser`
document with a linked table of contents, not a ~10-tab `QTabWidget` or
a sidebar-list split -- ties back to Phase 7c's own TinyFugue research
(`src/help.c`: an indexed text file read top-to-bottom with jump
targets), and scales better as sections are added later than more tabs
would; (4) static content as Markdown-formatted **Python string
constants** in `gui/help/topics.py`, not loose `.md` files -- deliberately
avoiding a second "works locally, breaks in the real packaged build" gap
(`packaging/mushtato.spec`'s `datas=[]` is empty; bundling loose files
would need real spec changes plus frozen-vs-source path resolution,
unverifiable without an actual PyInstaller build, exactly the shape of
the libxcb-cursor0 and theme-palette bugs already hit this session) --
a `.py` module needs none of that, it's bundled automatically via the
normal import graph. The command list and hotkey list are generated
from live data (`COMMAND_HELP`, `HelpContext`), not hand-copied, for the
same reason the Phase 7c `/help` placeholder already generated its text
live.

Second checkpoint, after Rick added a new requirement mid-review (every
Help feature must also be reachable from the command line): resolved
into `/help` (bare, opens the window and prints a short pointer),
`/help topics` (a reserved keyword listing topic slugs, Rick's own
explicit ask), `/help <topic-slug>` (prints that topic's content to the
scrollback), and `/help <command-name>` (unchanged -- still prints that
command's one-line help). Topic slugs were chosen up front to never
collide with real command names (`themes` vs. `theme`, `commands` vs.
no command literally named that) -- confirmed with a test
(`test_topic_slugs_never_collide_with_command_names`), not just asserted
by construction. Markdown syntax is lightly stripped
(`gui/help/markdown_tools.strip_markdown`) before printing a topic to
the scrollback -- a small regex pass (header/emphasis markers only,
list bullets left alone), not a full Markdown-to-text engine, agreed as
the right amount of polish for this feature.

Single source of truth, enforced structurally, not just by convention:
`gui/help/topics.py`'s `COMMAND_HELP` list is what
`SessionTab._register_commands()` actually iterates to register every
command (refactored from eight explicit `.register()` calls into one
data-driven loop) -- the registered set and the documented set cannot
diverge, and a test (`test_command_help_matches_what_session_tab_actually_registers`)
checks this against a real, live `CommandTable`, not just re-asserting
the same list back at itself. `/help` itself is re-registered by
`SessionTab` (overriding `engine/commands.py`'s auto-registered default),
the same established pattern `/connect`/`/settings`/`/theme` already use
to reach the host shell without the engine layer ever importing Qt
(rule 2) -- confirmed before writing any code that this was the right
reuse, not a one-off.

`MainWindow._show_help()` (the Phase 7c placeholder: required an active
tab, showed a `QMessageBox`) is gone, replaced by `MainWindow.show_help()`
-- the real Help window is static app documentation and must be reachable
with zero tabs open, which the placeholder's design couldn't do. The
Help window is a lazily-constructed singleton satellite (same pattern
as `AddressBookWindow`), but its content is rebuilt on every open
(`HelpWindow.refresh()`) rather than left stale, since hotkeys/theme can
change between opens and there's now exactly one long-lived instance to
go stale.

**A real Markdown-rendering bug, found by actually rendering the
content, not by reading the source and assuming it was fine:** command
help text originally used angle-bracket placeholders (`/connect <name>`,
`/theme <dark|light>`), matching how the rest of the app's plain-text
usage strings already looked. Rendering the assembled "Built-in
Commands" topic through `QTextBrowser.setMarkdown()` silently corrupted
everything after the first `<...>` -- Qt's Markdown parser treats
`<name>` as an (invalid) inline HTML tag and swallows subsequent content
trying to resolve it. Confirmed by isolating the exact rendered output,
not guessed at from the visual glitch alone. Fixed by switching every
placeholder to square brackets (`/connect [name]`, `/theme [dark|light]`)
project-wide, in both the Markdown content and the plain-text command
usage strings, for one consistent convention -- with a regression test
(`test_markdown_rendering_does_not_swallow_content_after_a_placeholder`)
that renders the real content through the real widget and checks every
command's description survived, not just that the source text looks
right.

A second, smaller real rendering bug from the same "verify by actually
rendering it" pass: consecutive `cursor.insertMarkdown()` calls (TOC,
then each section) left the cursor "inside" the prior bullet list's
context, so the next section's `# Heading` got absorbed as plain text
into the previous list item instead of starting a real heading block --
visible as sections running into each other with no line break. Fixed
by inserting a freshly-reset `QTextBlockFormat()` block before each
section. Table-of-contents navigation itself was verified empirically
rather than assumed to "just work" from Markdown: Qt's `setMarkdown()`
does not generate `id`/`name` anchors on headings (confirmed by
inspecting the actual generated HTML), so `QTextBrowser.scrollToAnchor()`
would silently do nothing -- navigation instead tracks each section's
starting `QTextCursor` position during assembly and jumps there
directly on `anchorClicked` (with `setOpenLinks(False)` so Qt doesn't try
to resolve the anchor itself), which depends only on documented,
guaranteed `QTextCursor` behavior.

The Help window's content pane reuses the same "set the palette on both
the widget and its `viewport()`" fix already found for the scrollback
(`gui/theme.py`, generalized this phase into
`apply_widget_and_viewport_palette()`, with `apply_scrollback_theme()`
now a thin wrapper over it) -- `QTextBrowser` is a `QTextEdit` subclass
and was flagged as a likely carrier of the identical bug before it was
ever reported, then actually confirmed via the same pixel-sampling
discipline used for the scrollback fix, not assumed safe by similarity.
Uses the window's own inherited app-wide palette, not the scrollback's
dimmed output-pane colors -- a reference document isn't MUD output and
has no reason to use Potato's dimmer text.

A real, verified documentation-accuracy fix surfaced while writing
`INSTALL.md`'s uninstall section: `engine/storage/paths.py`'s own
comment claimed `~/.config` on Linux and `%APPDATA%` on Windows --
checking `platformdirs`' actual source (not the comment) found both
wrong. `user_data_dir` (not `user_config_dir`, a different function this
project doesn't call) resolves to `~/.local/share/MushTato` on Linux
(`$XDG_DATA_HOME`) and `%LOCALAPPDATA%\MushTato` on Windows (Local, not
Roaming) -- macOS's `~/Library/Application Support/MushTato` was already
correct. Fixed the stale comment in the same pass rather than
documenting the wrong path in `INSTALL.md` to match it.

`TROUBLESHOOTING.md` and the in-app FAQ/Troubleshooting topic are the
same content in two places, per the scope's own "a matching in-app FAQ
section" requirement -- not the single-source-of-truth-in-Python
approach used for the command list, since this content doesn't need to
stay mechanically in sync with live app state the way command
registrations do; both copies just need a human to keep them aligned on
future edits, same as `CREDITS.md`.

Testing, explicit about verification level per this file's own standing
rules: the Help *mechanism* is unit-tested headlessly (topic resolution,
command/topic namespace non-collision, Markdown stripping, TOC
navigation actually moving the cursor, the command-list single-source-
of-truth claim checked against a live `CommandTable`) -- 135 GUI tests
passing (up from 135... from 133 pre-Phase-8, +14 new). Content
*accuracy* was explicitly out of scope for testing (Rick's own call in
the original ask) -- reviewed by rendering it for real and reading it,
not asserted correct by a test. Full suite: 249 passing (114 engine +
135 GUI, up from 224 total at the end of Phase 7e). Manually verified end-to-end against
the real local RhostMUSH: opened the Help window from the menu and via
`/help`, clicked through TOC navigation to a far section, ran
`/help topics`, `/help hotkeys`, `/help theme`, and `/help bogus` from a
live tab and confirmed each printed the right thing to the real
scrollback -- screenshotted for the record, including the specific
before/after screenshots that caught the two rendering bugs above (a
visual read alone caught the block-separation bug; the angle-bracket
corruption needed isolating the actual rendered text to catch at all,
since the visual glitch by itself didn't point at the cause).

Still NOT wiring `engine/scripting` into the GUI -- same deferred
decision as every phase since Phase 4b, called out again so it stays
visible rather than quietly dropped, and now has its own in-app Help
topic saying exactly that.

**Phase 8b (address book / World Properties overhaul) — done.**
Extended `engine/storage/address_book.py` (`WorldProfile`, new
`CharacterProfile`), new `gui/dialogs/world_properties_dialog.py`
(`WorldPropertiesDialog`), extended `gui/windows/session_tab.py` (auto-
sends/character login) and `gui/windows/main_window.py`
(`record_world_connected`), fixed a real data-loss bug in
`gui/dialogs/world_edit_dialog.py`, updated `gui/help/topics.py`'s
Address Book section.

Two checkpoints before code (this file's standing rules again put to
immediate use). First: research. `~/git/potato/potato.vfs` (the real,
canonical `potatomushclient/potato` repo, confirmed via its own
`README.md`/git log, not a stub) was read before any design was
proposed -- and it directly overturned part of Rick's own initial
framing, surfaced explicitly rather than silently followed: a Potato
"Character" is verified (via `configureWorldCharsFinish`'s `list
$newChar $newPw`) to be *only* a name+password pair -- auto-sends,
notes, and login format are all World-level in the real source, not
per-Character as first described. Rick confirmed strict parity on
review, with a concrete reason: two different worlds can each have a
Character named the same thing with a different password, which only
works cleanly under per-world scoping. Also found only after
discovering `grep` was silently treating `potato.tcl` as binary (a
stray non-UTF8 byte; `-a` fixed it): the real dispatch order and timing
in `sendLoginInfoSub` -- after a world's `loginDelay`, firstconnect
(only if `numConnects == 1`, a persisted counter) -> connect -> the
formatted Character login line -> login. And the real World Properties
window's shape: a `ttk::panedwindow` with a category `treeview` on the
left and a swappable canvas on the right (13 real sections in Potato;
scoped to 5 here -- Basic/Characters/Connection/Auto-Sends/Notes -- the
rest either duplicate MushTato's own theme/hotkey system or need real
`engine/net` work out of scope this phase).

Second checkpoint, informed by that research: data model (strict
parity, approved), auto-send mechanism (reuse
`SessionTab.bridge.send_line()` directly via `QTimer.singleShot`, no
`engine/scripting` involvement since this is fixed saved text, not
user-provided code to sandbox), UI shape (`WorldPropertiesDialog`, a
`QListWidget` category list + `QStackedWidget` pages -- the direct Qt
equivalent of Potato's real tree+canvas split -- reached via a new
"Properties..." button on `AddressBookWindow`, additive to the existing
quick `WorldEditDialog`), and storage (kept the existing single-list
`address_book.json`/`address_book.py`, just extended `WorldProfile`'s
shape -- Potato's own real on-disk shape, one `.wld` file per world
under `~/.potato/worlds/`, checked for filenames/structure only, per
Rick's explicit instruction never to read or reproduce actual saved-
world content -- doesn't override the original Phase 6 reasoning that
the address book is browsed as one list).

Deliberate deviation from Potato, called out explicitly rather than
silently copied: Potato's own `send_to` (used for autosends) routes
through `process_input`, which also parses for Potato's own slash
commands -- MushTato's autosends are sent as literal raw text via
`_send_to_bridge(..., apply_aliases=False)` instead, *never* through
`CommandTable`, for the same reason the secondary pose/says input box
already bypasses command processing: a saved autosend line that happens
to start with `/quit` must reach the server literally, not silently
close the tab. Covered by a test
(`test_autosend_lines_bypass_slash_command_processing`) using exactly
that `/quit` scenario, not just asserted safe by design.

Also a deliberate small implementation choice, not a design fork
needing its own checkpoint: `login_format` uses named `{name}`/
`{password}` placeholders (e.g. `connect {name} {password}`) rather
than Potato's real positional `%s %s` -- clearer, and this is
MushTato's own reimplementation rather than literal ported code. The
masked-password echo (`●` repeated to the password's length) *is*
lifted directly from Potato's own real behavior in `sendLoginInfoSub`,
not invented.

A real data-loss bug found while extending the model, not before
shipping it: `WorldEditDialog` (the quick name/host/port/notes dialog)
used to always build a brand new `WorldProfile` from just its 4 visible
fields on save -- meaning using quick Edit on a world that already had
Characters/auto-sends set up via the new Properties dialog would
silently wipe all of it out. Fixed with `dataclasses.replace()` against
the original profile so only the 4 shown fields actually change; a
regression test
(`test_editing_preserves_characters_and_autosends_not_shown_in_this_dialog`)
proves the fix, not just describes the fix.

Migration is genuinely additive, proven with a test that writes a
real Phase-6-shape JSON file (no Phase 8b fields at all) and loads it
under the extended model
(`test_old_phase6_format_json_still_loads_with_new_fields_defaulted`) --
not just a description of intended behavior. Full suite: 283 passing
(120 engine + 163 GUI, up from 249 at the end of Phase 8).

Manually validated end-to-end against the real local RhostMUSH
(`127.0.0.1:4444`): added a "guest"/"guest" Character via the real
Properties dialog UI, set it as default, set `look` (connect) and `who`
(login) auto-sends, saved, then connected via the real Address-Book-
driven path -- confirmed in the actual scrollback: the banner arrived,
then the masked login line (`connect guest ●●●●●`, password never in
plaintext), then `look`'s room description, then `who`'s player list,
in exactly that order. Disconnect/Reconnect via the toolbar fired the
same sequence again and `connect_count` persisted correctly across it
(1 -> 2, confirmed by re-reading the actual saved JSON file, not just
the in-memory object) -- screenshotted for the record (session window,
and the Properties dialog's Characters and Auto-Sends pages).

Still NOT wiring `engine/scripting` into the GUI -- same deferred
decision as every phase since Phase 4b, called out again so it stays
visible rather than quietly dropped.

**Post-8b fixes: two real issues Rick found testing the actual build.**

1. **Address book buttons silently no-op'd with nothing selected.** A
   freshly-opened `QListWidget` starts with `currentRow() == -1` even
   when worlds already exist -- clicking Properties/Edit/Delete/Connect
   before ever clicking a row did nothing, with zero feedback. Rick's
   report ("Properties... showed nothing until I'd already connected
   to something") traced directly to this: double-clicking to connect
   also happens to select the row, which is why it "started working"
   only after that. Fixed by disabling those four buttons whenever
   nothing is selected (`AddressBookWindow._refresh_selection_dependent_buttons`,
   wired to `list_widget.currentRowChanged` and re-run after every list
   rebuild) -- makes the requirement visible instead of silent, the
   same principle Phase 7e's chrome already uses for actions that need
   an active tab.

2. **Adding a Character didn't do anything on connect by itself.** Not
   a bug -- confirmed against the code and the original checkpoint --
   but a real UX gap: `default_character` is a separate field set on
   the *Basic* page, a different page from where you *add* a Character
   on the *Characters* page. Rick added one and reasonably expected it
   to just be used; nothing fired until he manually duplicated the
   login line into the Auto-Sends "connect" box himself. Resolved via
   a quick follow-up checkpoint (not silently picked): auto-default the
   *first* Character added to a world with no default set yet
   (`_CharactersPage.characterAdded` signal ->
   `WorldPropertiesDialog._on_character_added`) -- adding a second
   Character later never overrides an existing default, that stays an
   explicit choice on the Basic page.

Both re-verified against the real local RhostMUSH, not just the
headless tests: Properties correctly stays disabled until a world row
is actually clicked, and connecting with only a freshly-added "guest"
Character (zero manually-typed Auto-Sends text) still sent the masked
`connect guest ●●●●●` login line automatically. 289 tests passing (120
engine + 169 GUI, up from 283).

**Post-8b addition: a Character picker in the Address Book.** Rick
asked for a way to pick a saved Character (from a world's list) and log
in as that one specifically, right from the Address Book, rather than
only via the single `default_character` set on the Properties Basic
page. Checked Potato's own real source first (`~/git/potato/potato.vfs`)
rather than assuming: its Manage Worlds window's "Char" column and
Connect button only ever read `charDefault` -- no right-click/double-
click character-choice binding exists anywhere, and `newConnection`'s
optional `character` argument is only ever called with a real value
from `newConnectionDefault`. So this is confirmed as a genuine MushTato
addition beyond Potato, not a parity port, called out as such rather
than presented as more "authentic" than it is.

Three real forks, checkpointed rather than picked silently: (1) picking
a Character here is **one-time only** -- it never overwrites the
world's stored `default_character`, avoiding a surprising side effect
from what's meant to be a quick action; (2) Log In **always opens a new
tab**, even if that world's host:port already has one open elsewhere --
`MainWindow.open_tab()` now skips its existing-tab dedup check whenever
an explicit `character` argument is given, since logging in as a
different Character is a genuinely different session server-side (e.g.
a main character and an alt on the same MUD at once), not a duplicate
of an existing connection; plain Connect keeps the original dedup
behavior unchanged; (3) a second `QListWidget` (not a dropdown) next to
the world list, for visibility/consistency with how Characters are
already shown in Properties.

Mechanically: `SessionTab` gained an `_explicit_character` (renamed
`_resolve_default_character` to `_resolve_login_character`, which now
checks the explicit choice first and only falls back to
`world.default_character` when none was given); `MainWindow.open_tab()`
and `AddressBookWindow` both thread an optional `character` parameter
through to it, reusing the exact same `open_tab()` -> `SessionTab` ->
auto-send/login-dispatch path Connect already uses -- Log In is not a
parallel implementation, just a different set of arguments into the
same machinery. `AddressBookWindow.log_in_as(world, character)` is a
public method for this, separate from the private
`_log_in_as_selected_character()` that reads the two list widgets'
current selections. Updated `gui/help/topics.py`'s Address Book section
to document the picker and its one-time/new-tab semantics.

Manually verified end-to-end against the real local RhostMUSH with two
saved Characters (GuestA default, GuestB not): Log In button correctly
stayed disabled until a Character was actually picked; logging in as
GuestB (not the default) sent `connect GuestB ●●●●●`; logging in as
GuestA afterward opened a genuine second tab (`tab1 is tab2` false, tab
count 2) rather than reusing the first; a subsequent plain Connect
still correctly reused/deduped against an existing tab; and
`default_character` was confirmed unchanged (`GuestA`) in the actual
saved JSON after all of this -- screenshotted for the record. 296 tests
passing (120 engine + 176 GUI, up from 289).

**Post-8b addition: auto-login on startup + address book sorting.**
Rick asked for two things together: (1) a per-world "auto-login"
checkbox so flagged worlds connect and log in automatically when
MushTato starts, and (2) a way to sort/reorder the Worlds list
(alphabetical, reverse-alphabetical, or a manually chosen order).

Checkpointed two real forks before writing code. On timing/sequencing:
Rick described Potato's own real behavior from memory (open, connect,
jump to the next tab, one at a time -- not waiting on login success
first, "because occasionally a site might be down") and, when asked,
said explicitly **no confirmation prompt is needed** ("It doesn't ask
me to confirm though. That's not necessary") -- a real change from the
original request's "might ask 'Do you wish Auto-Login?'" wording,
caught only by asking rather than building the first draft literally.
On manual reordering: Rick chose **drag-and-drop** over Move Up/Down
buttons, despite Move Up/Down being the recommended (lower-risk) option.

`WorldProfile` gained `auto_login: bool = False`
(`engine/storage/address_book.py`), additive-migration-safe like every
other Phase 8b field. `AddressBookWindow`'s Worlds list
(`gui/windows/address_book_window.py`) now builds `QListWidgetItem`s
with a checkbox **only when a world has a `default_character` set** --
a world without one shows no checkbox at all, not a disabled one. This
was a real correction mid-build, not the first design: a disabled
checkbox requires clearing `Qt.ItemFlag.ItemIsEnabled` on the whole
item, which also would have made the *entire row* unselectable --
silently breaking Edit/Delete/Connect/Properties for any world without
a default Character (i.e. most newly-added worlds). Toggling the
checkbox persists immediately via `itemChanged`, guarded by
`blockSignals()` during `_refresh_list()`'s own repopulation so a
routine refresh doesn't re-fire it. Each item's world object is stored
via `Qt.ItemDataRole.UserRole` and used directly (not re-looked-up by
index), so persistence is correct regardless of list order.

Sort A-Z / Sort Z-A are one-shot re-sorts of `self.worlds` (by
`.name.lower()`), not a persistent "mode" -- a newly added world just
appends to the end until Sort is clicked again, per Rick's own request
("sort... or choose the order"). Drag-and-drop reordering uses
`QAbstractItemView.DragDropMode.InternalMove`; the actual persistence
hook is the model's `rowsMoved` signal (`_on_worlds_reordered`), which
rebuilds `self.worlds` from each item's stored `UserRole` data in the
list's current visual order -- proven in a test that calls
`model().moveRow()` directly (the same primitive a real internal-move
drop performs), not just simulated by clearing and re-adding items.

Startup wiring (`gui/app.py`): `worlds_to_auto_login()` filters the
loaded address book to worlds with both `auto_login` and a
`default_character` set (a checked box with no default is inert, not
an error); `auto_login_all()` then calls the *exact same*
`MainWindow.open_tab()` every other connect path already uses, once
per flagged world, in address-book order -- no parallel connect
mechanism, no artificial delay between opens (each tab's connection
already runs on its own independent background thread per the
Phase 5 architecture, so "one at a time" just describes iteration
order, matching what Rick described). Only runs on the no-args launch
path; a direct `host port` CLI connect skips it entirely, same as it
already skips first-run settings.

Verified at multiple levels, distinguished honestly: the full
automated suite (296 tests defined; 248 of them -- everything outside
`engine/scripting`'s RestrictedPython/`google-re2` dependency, which
this particular sandbox doesn't have installed, an environment gap
unrelated to this feature -- collected and passing, including 10 new
tests for the checkbox/sort/reorder behavior and 4 for the
`worlds_to_auto_login`/`auto_login_all` startup logic); a headless
screenshot smoke test confirming the checkbox/no-checkbox rendering
and Sort Z-A visually; and a genuine live end-to-end run against the
real local RhostMUSH (`127.0.0.1:4444`) driving `gui/app.py`'s actual
`app.exec()` event loop (not just `QTest.qWait`, which didn't
reproduce real cross-thread signal delivery correctly in an ad hoc
script) -- confirmed the flagged world's tab opened, connected, sent
the masked login line, and received real room content back.
Updated `gui/help/topics.py`'s Address Book section to document both
features.

**Post-8b addition: tab-activity flashing.** Rick asked for some way
to notice when a background tab (not the one currently in view)
receives new text -- explored as an exploratory question first (per
this file's own guidance for "what do you think?"-style asks), landing
on a two-part answer: a color change on the tab label, plus actual
blinking, not just a static color. One more checkpoint on the
remaining real fork -- whether the blink settles into a steady color
after a few seconds (calmer, Slack/Discord-style) or keeps blinking
indefinitely until viewed -- and Rick chose **indefinite**, explicitly
over the recommended calmer option.

`SessionTab` (`gui/windows/session_tab.py`) gained a new `activity`
signal, emitted from `_on_text_received()` whenever real segments
arrive (same guard already used for the scrollback-append/spawn-window
mirroring, so this doesn't fire for a completely empty chunk).
`SessionTab` deliberately doesn't know or care whether it's the
*currently active* tab -- exactly the same separation of concerns as
`connectionStateChanged`, where the host shell (which actually owns
tab selection) makes that call, not the tab itself.

`MainWindow` (`gui/windows/main_window.py`) does the rest: a single
shared `QTimer` (`_activity_timer`, 500ms) flashes every tab currently
tracked in `_tabs_with_activity` together, rather than one timer per
tab -- simpler, and keeps multiple flashing tabs blinking in sync
rather than independently drifting. Tracked by **tab object**, not
index -- indices shift as tabs open/close, so each tick looks up a
tab's *current* index via `indexOf()` rather than trusting a stashed
one. `QTabBar.setTabTextColor(index, QColor())` (an invalid color) is
the reset path back to the tab bar's own default text color, rather
than this code trying to compute/track what that default is per-theme.
The activity color itself (`MainWindow.ACTIVITY_COLOR`, orange) is a
single fixed choice for both dark/light themes -- this is tab-bar
chrome, not scrollback content, so the dark/light legibility concerns
that drove `gui/theme.py`'s and `engine/ansi`'s own color choices don't
carry over the same way; revisit if orange turns out to read poorly on
one theme in practice. `_on_current_tab_changed()` (already existed,
wired to `tab_widget.currentChanged`) is where clearing happens --
switching to a flashing tab clears and un-tracks it immediately,
regardless of scroll position within that tab. `close_tab()` also
untracks a closed tab so `_tabs_with_activity` never holds a stale
reference. The timer only runs while at least one tab actually has
unseen activity, stopping itself once the last one is cleared.

Verified with 8 new headless tests (`tests/gui/test_tab_activity.py`):
activity in the *currently active* tab never marks/flashes it; a
background tab's activity marks it, starts the timer, and colors its
tab immediately; manually ticking the flash toggles the color between
`ACTIVITY_COLOR` and the reset color; switching to a flashing tab
clears it and resets its color; the timer stops once the last flashing
tab is cleared; the flash keeps going through 20+ ticks with no
auto-settle (Rick's "indefinite" choice, proven, not just asserted);
multiple background tabs flash independently-tracked but in sync, and
clearing one leaves the other still flashing; closing a flashing tab
untracks it. Full suite: 256 passing (up from 248, everything outside
`engine/scripting`'s `google-re2`/RestrictedPython dependency, which
this sandbox still doesn't have installed -- an unrelated, pre-existing
environment gap). Also visually confirmed via a headless screenshot
smoke test showing two background tabs' labels rendering in orange
while the active tab stays normal, and the color correctly toggling
off on the next simulated tick. Updated the "Sessions & Tabs" Help
topic to document the behavior.

**Post-8b addition: remembered input-pane size + configurable fonts.**
Rick asked for two things together: (1) the dual-input splitter to
remember whatever height he last dragged it to, across restarts, and
(2) a Settings option to change the font used in the scrollback/
terminal pane and in the input boxes.

Checkpointed two real forks before writing code (both times, Rick chose
the option this file's own convention would call "Recommended," but
they were genuine forks, not rubber-stamps): (1) splitter-size scope --
**one global preference** applied as the starting split for every
newly-opened tab, not saved per-world (per-world would need a
`WorldProfile` schema change for a fairly small visual preference); (2)
font scope -- **two independent pickers** (Terminal Font, Input Font),
matching Rick's own phrasing ("both the display terminal window as
well as the input windows") rather than one shared font+size for both.

`engine/storage/settings.py`'s `Settings` gained
`scrollback_font_family`/`scrollback_font_size`/`input_font_family`/
`input_font_size` (empty string / `0` = "no override" sentinels) and
`splitter_sizes` (empty list = "no saved preference yet") -- additive-
migration-safe like every other Settings field. The empty-sentinel
design exists specifically because `/engine` can never import PySide6
(rule 2): `engine/storage` can't compute a real font default itself
(that needs `QFontDatabase`), so it stores "unset" and leaves resolving
that to the GUI layer.

New `gui/fonts.py` (`resolve_scrollback_font`/`resolve_input_font`/
`default_scrollback_font`) is the one place those sentinels get
resolved into a real `QFont` -- reused identically by `SessionTab` (at
construction and in a new `apply_fonts()` live-reload method) and by
`SettingsDialog` (to pre-populate the pickers with the *actual*
effective font, not a blank field, when nothing's been saved yet).

`SettingsDialog` gained two `QFontComboBox` + `QSpinBox` pairs. The
Terminal Font combo is filtered to `QFontComboBox.FontFilter.
MonospacedFonts` specifically -- MUD output (banners, tables, ASCII-art
borders) assumes a fixed-width terminal, the exact real alignment bug
Phase 5 found and fixed by defaulting to a fixed-width font in the
first place; letting the terminal font drift to a proportional face
would silently reintroduce that. The Input Font combo is unfiltered,
since the input boxes have no such constraint. `splitter_sizes` has no
UI in this dialog at all -- it's set only by dragging, so
`result_settings()` just passes whatever value the dialog was
constructed with straight through unchanged, never resetting it.

Live-reload semantics deliberately differ between fonts and splitter
size, and this was a real design distinction, not an oversight:
**fonts** propagate to every already-open tab immediately when Settings
is saved (`MainWindow._refont_open_tabs()`, the same treatment
`_retheme_open_tabs()` already gives Theme) -- a font change made
through Settings is a deliberate preference change. **Splitter size**
does *not* propagate to already-open tabs -- dragging one tab's split
is an in-the-moment layout tweak on that one tab, not a Settings-dialog
preference; silently resizing every other open tab to match would be
surprising mid-session. It only becomes the starting point for tabs
opened *after* the drag (this session or a future launch).

A real latent bug fixed along the way, found by re-reading the existing
code rather than by a bug report: `MainWindow.open_settings()` and
`set_theme()` used to each build a `Settings(hotkeys=..., theme=...)`
object from only two fields and save *that* -- meaning saving hotkeys or
switching theme would have silently wiped out any saved font/splitter
preferences the next time either ran. Fixed by a new
`MainWindow._current_settings()` that always builds the *complete*
current settings from every tracked field, with `open_settings()`/
`set_theme()`/`record_splitter_sizes()` all funneling through one
`_save_settings_to_disk()` -- a single save path that can't accidentally
go out of sync with what MainWindow actually knows, instead of several
independent partial-Settings constructions that could each drift.
Covered by a regression test
(`test_setting_theme_does_not_clobber_previously_saved_fonts`) proving
the specific failure mode, not just describing it.

Splitter-size persistence is debounced (400ms, `MainWindow.
_splitter_save_timer`, a single-shot `QTimer` restarted on every
`record_splitter_sizes()` call): `QSplitter.splitterMoved` fires on
every pixel of a drag, so writing the whole `settings.json` file
synchronously on each one would hit disk dozens of times per drag --
this coalesces a fast drag into one write shortly after it actually
stops. Proven with a test that calls `record_splitter_sizes()` ten
times in a row and confirms only the *last* value ends up on disk.

A real test-writing lesson from this round, not a product bug: an
unshown/unresized `QWidget` in the headless offscreen test environment
has ~0 real geometry, so `QSplitter.setSizes()` at construction has
nothing to actually distribute against until the widget (or, for a
`SessionTab` embedded in `MainWindow.tab_widget`, the *host* window) is
given a real size via `resize()` + `show()` + `QApplication.
processEvents()`. A second lesson: hardcoding specific font names like
"Courier New"/"Arial" in tests is flaky by environment -- they aren't
guaranteed installed on every OS/CI runner, and Qt silently substitutes
the nearest match for a missing font (and resolves generic fontconfig
aliases like `"monospace"` to a concrete family name via `QFontInfo`
rather than returning the alias itself). Fixed by pulling actually-
installed font names from the dialog's own populated combo list rather
than assuming specific fonts exist.

Verified at three levels: 281 tests passing (up from 256; everything
outside `engine/scripting`'s `google-re2`/RestrictedPython dependency,
the same pre-existing, unrelated environment gap noted in every recent
phase); a scripted end-to-end run that saves fonts/splitter size via
one `MainWindow` instance, waits out the real debounce timer, then
constructs a *second, independent* `MainWindow` reading the same
`settings.json` (simulating an actual app restart without needing to
literally relaunch the process) and confirms it picks up the exact
saved font sizes and split proportions; and a rendered screenshot
showing the terminal pane at a visibly larger font size than the input
box, not just asserted via `.pointSize()`. Added a new "Fonts" Help
topic and updated the Dual Input topic to mention the remembered split.

**Phase 9 (GUI-scripting integration) — done.** New
`engine/scripting/line_dispatch.py` (`LineDispatcher`), extended
`engine/scripting/triggers.py`/`aliases.py`/`world.py` (per-trigger
auto-disable, named script load/unload, `dirty`/error reporting),
extended `gui/windows/telnet_bridge.py` (`on_text`/`set_on_text`/
`run_in_background`), rewritten `gui/windows/session_tab.py` (the
actual wiring), extended `gui/windows/main_window.py`/
`address_book_window.py` (periodic autosave, live script reload, the
`scripts_dir` override), extended `gui/dialogs/world_properties_dialog.py`
(new Scripts page), rewritten `gui/help/topics.py`'s Scripting topic.
`engine/scripting`'s 10-function API, sandboxed since Phase 4, reaches
the real GUI for the first time.

Preceded by the most thorough checkpoint of the session, per this
file's own standing rules: five numbered proposals plus one
independent finding, all confirmed or fully specified by Rick before
any code was written. Two of Rick's answers were fully-specified
requirements, not open questions -- the 5-minute dirty-flag autosave
timer and the 5-consecutive-failures trigger auto-disable mechanism
were both implemented exactly as spelled out, with zero remaining
discretion.

**The Phase 9 / Phase 7e naming collision, resolved as approved:**
verified (not assumed) that 14 checked-in files' docstrings/comments
called the tabbed-host-window work "Phase 9" even though SPEC.md's own
roadmap always called it "7e" -- a real, pre-existing inconsistency
between the code and the spec, not a typo in this session's own
writing. Renamed every instance to "Phase 7e" (plus one stray
"Phase 9" found inside this file's own Phase 7e write-up) so "Phase 9"
unambiguously means GUI-scripting integration going forward.

**The threading finding, confirmed true and more far-reaching than
initially scoped.** The checkpoint asked whether Phase 5/6's "the
GUI thread stays free of run_with_timeout's blocking wait" claim still
holds once trigger dispatch runs on every incoming line -- verified it
does *not* hold automatically, and the real fix reaches further than
the original proposal anticipated. `engine/scripting/sandbox.py`'s
`run_with_timeout()` always spawns its own internal worker thread for
the actual script body and blocks the *caller* on `.join()` -- meaning
every single script execution (not just trigger dispatch) hands off to
a different thread than whatever called it, including entry points
that looked GUI-thread-native from the outside (script load at tab
construction, `on_connect`, a fired `timer()`). This was only
discovered by writing and running a real test
(`test_echo_renders_in_real_scrollback`): `echo()`'s effect never
appeared, because its Qt signal emission from inside `on_connect`
turned out to be a genuine cross-thread emission needing the event
loop to actually process it, not the same-thread direct call it looked
like from the call site. `gag()`/`highlight()` are unaffected by this
(their effect is baked into `TriggerTable.dispatch()`'s *return
value*, synchronously observable once the blocking call unwinds) --
only `echo()` (and, transitively, anything relying on its signal)
needed this understood and documented, which `session_tab.py`'s
`_script_echo` docstring now does explicitly, correcting an earlier,
inaccurate draft of that same comment.

**Architecture, following from that finding:**
`engine/scripting/line_dispatch.py`'s `LineDispatcher` is a new,
headless-testable (no Qt) engine-layer class owning line-buffering +
`AnsiParser` + trigger dispatch together -- it buffers raw incoming
text into complete lines (`TriggerTable.dispatch()`/gag/highlight need
a whole line to act on sensibly), and returns a *replaceable* preview
of the still-incomplete trailing line on every `feed()` call rather
than an incremental append, so gag/highlight still correctly cover a
line that happens to arrive split across multiple network reads (the
caller is expected to erase-and-reinsert the previous preview, never
append to it -- `gui/windows/styled_text_qt.py`'s new `replace_tail()`
helper does this). `TelnetBridge` gained one optional hook,
`on_text`/`set_on_text()` -- a plain Python callable (deliberately not
a Qt signal for this one hop, since a signal's auto-marshaling follows
the *receiving* object's thread, which would put the processing back
on the GUI thread and defeat the purpose) invoked synchronously on its
own background thread from inside `_run()`'s read loop, before
`textReceived` is emitted -- and stays fully unaware of ansi/scripting
either way, just invoking whatever callable it's given. `SessionTab`
supplies that callable (`_on_raw_incoming_text`), which calls
`LineDispatcher.feed()` and hands the final, already-processed result
back to the GUI thread via a Qt signal (`_incomingBatchReady` --safe
to emit from any thread by construction). Outbound alias expansion
gets the symmetric fix via a new `TelnetBridge.run_in_background()`
(schedules a blocking callable onto the connection's own asyncio
loop's executor, never the GUI thread or the read-loop's own thread).

**A real bug found and fixed while building `LineDispatcher`, before
any GUI wiring happened:** `_split_on_newlines` deliberately excludes
the line terminator from the plain text used for trigger matching (so
patterns never need to account for a trailing `\n`) -- but the first
draft never added it back to the *rendered* segments, which would have
made every consecutive line run together on screen with no line break
at all. Caught by a dedicated test
(`test_finalized_lines_include_their_trailing_newline`) before it ever
reached the GUI layer, not discovered by eyeballing rendered output.

**Per-tab `ScriptWorld` lifecycle, exactly as checkpointed:** every
`SessionTab` builds a `ScriptWorld` unconditionally in `__init__`
(even a world with zero saved scripts gets an empty one -- one uniform
pipeline for every tab, confirmed by a test that two tabs on the *same*
world have genuinely independent `ScriptWorld`/`TriggerTable`
instances, not just independently-valued ones), loads saved scripts
from `engine/storage/script_store.py` immediately after construction,
and persists variables via `save_script_state()` on
disconnect/shutdown. `ScriptWorld.load_script()` gained an optional
`script_name` parameter (every pre-Phase-9 caller, including existing
tests, omits it and is completely unaffected) and a new
`unload_script()` -- together these let a script be cleanly
edited-and-reloaded (World Properties' Scripts page saving, or a
`reload_scripts()` call on an already-open tab) without old trigger/
alias registrations, and their stale disabled/failure-counter state,
lingering alongside the new version.

**Checkpoint 1's fully-specified autosave, implemented exactly as
given, no discretion exercised:** `ScriptWorld` gained a plain
`dirty` flag, set by `_api_set_var()`, cleared by whatever saves
(periodic or shutdown/disconnect). `MainWindow._script_autosave_timer`
(one shared timer iterating every open tab, matching the existing
`_activity_timer` pattern rather than one timer per tab) fires every 5
minutes and only writes for a tab whose `script_world.dirty` is
actually set -- proven with a test that marks one of two open tabs
dirty and confirms only that one's file gets written. This is
additional to, not a replacement for, `SessionTab.save_script_state()`
on disconnect/shutdown.

**Checkpoint 4's fully-specified auto-disable, also implemented
exactly as given:** `Trigger` gained `consecutive_failures` (reset on
success, incremented on a caught exception) and `source_script`
(tagging which saved script registered it, for the Scripts UI marker).
`TriggerTable.dispatch()` catches `Exception` (not just `ScriptError`
subclasses -- an ordinary bug in a script's own trigger callback, e.g.
a typo'd variable name, must be caught exactly the same way, not left
to crash dispatch for every *other* trigger on the same line) around
each callback, and disables a trigger that hits 5 consecutive failures
-- proven with a test driving exactly 5 matching lines and confirming
`enabled` flips to `False` on the 5th, not the 4th or 6th.
`AliasEngine.expand()` got the same catch-and-report treatment (not
the auto-disable counter, which Rick's checkpoint scoped to triggers
specifically) -- `AliasOutcome` gained an `error` field, and `matched`
stays `True` on a failing alias (falling back to sending the raw text
literally would compound the confusion, not fix it -- proven with a
test that a failing alias never sends anything).

**Error/timeout surfacing reaches every dispatch entrypoint the
checkpoint listed** -- `load_script` (per-script, doesn't stop other
scripts from loading), `triggers.dispatch`, `aliases.expand`,
timer-firing, and `on_connect` (`ScriptWorld.fire_connect_callbacks()`
now returns `(name, message)` pairs instead of letting a broken
callback propagate and block autosends from running afterward --
proven with a test confirming autosends still fire despite a failing
`on_connect`). Every failure prints one clear scrollback line via
`_append_plain`, the same channel connection-level errors already use;
none of them can crash or disconnect the tab.

**Scripts page in World Properties, reusing `_CharactersPage`'s exact
shape** (checked for reuse before building anything new, per this
file's own rule 6) -- a new `_ScriptsPage`: list + name/enabled
checkbox/source-editor fields + Add/Edit/Delete/Save/Cancel. The
"disabled trigger" visual marker (checkpoint 4's explicit requirement)
is deliberately *not* something this dialog computes itself -- it only
ever works with static, on-disk `ScriptRecord`s, with no live
`ScriptWorld` to ask. `AddressBookWindow._open_properties()` supplies
it, via two new `MainWindow` methods (`tabs_for_world()`,
`reload_scripts_for_world()`) that find any tab currently open for
that world and read its *live* `TriggerTable.disabled_source_scripts()`
-- proven end-to-end with a test using a real `MainWindow`/
`AddressBookWindow` pair (not the usual `FakeHostWindow`): a live tab's
trigger gets disabled after 5 failures, Properties shows the marker,
re-saving (even unchanged) resets it on the *already-open* tab, not
just on the next tab opened for that world. Saving Properties preserves
whatever variables are already on disk unconditionally -- this dialog
only ever edits script *source*, never the accumulated in-play state a
session (or a past one) built up.

**A real test-hygiene bug found and fixed mid-phase, not by
inspection but by actually checking the real disk -- and only fully
caught on the *second* sweep, worth being honest about rather than
presenting as clean on the first try:** the first draft of
`SessionTab`'s script loading called
`engine.storage.paths.world_script_path()` directly, with no override
-- meaning any test constructing a `SessionTab`/`MainWindow` with a
real `world=` (several already existed, from Phase 8b) would read *and
write* `~/.local/share/MushTato/scripts/`, the real per-user data
directory, on whatever machine ran the tests. Caught by explicitly
checking `ls ~/.local/share/MushTato/scripts/` before writing more
tests, not assumed safe -- and a real file (`Original.json`) had
already been written by an existing Phase 8b test before the fix,
confirmed empty/harmless and deleted. Fixed with the same dependency-
injection pattern `address_book_storage_path` already established:
`SessionTab` gained `script_store_path`, `MainWindow` gained
`scripts_dir`, `AddressBookWindow` gained `scripts_dir` -- overridable,
defaulting to the real path -- and every *known* affected test file
was updated to pass a `tmp_path`-based override. That first sweep
missed two more call sites (`test_commands_wiring.py`,
`test_chrome.py` -- both reach a real `world=` via `/connect`/
`connect_by_name` rather than a literal `world=` kwarg, which is
exactly why a plain `grep "world="` first pass didn't catch them) --
found only because a second, independent disk check (prompted by a
session interruption, not a scheduled step) turned up a second real
leaked file, `Estrellita.json`. Fixed the same way, then re-swept
*every* test file constructing `MainWindow`/`SessionTab`/
`AddressBookWindow` systematically (not just the two that had just
leaked) checking for any path that reaches `open_tab`/`connect_by_name`
with a real world, rather than assuming the fix was now complete.
Re-verified clean (`ls` reporting "No such file or directory") after
each fix and after the full suite runs that followed -- this two-round
history is recorded here deliberately, since claiming it was caught
cleanly the first time would not have been accurate.

**The accepted TinyFugue-precedent simplification, checkpointed and
now recorded in SPEC.md section 8** (same treatment as the Phase 4
GIL/busy-loop gap, not just mentioned in conversation and forgotten):
an eternally-unterminated trailing partial line (most often an
interactive prompt) renders immediately for a responsive feel, but is
never matched against triggers -- real TinyFugue's more elaborate
`prompt_timeout` mechanism (verified against `~/git/tinyfugue/src/
socket.c`, not assumed) is deliberately not replicated.

Verified at the levels this file's standing rules ask to distinguish:
393 tests, all passing whenever the run completes cleanly (151 engine +
242 gui, up from 385 at the end of the font/splitter work) -- headless
engine fixtures for `LineDispatcher` (including real ANSI-colored,
multi-chunk sample text) and the trigger/alias failure-tracking
mechanism; GUI-level tests exercising the real `QTextEdit` scrollback
(character-format colors read back via `QTextCursor`, not just
asserted at the engine layer) and a real `FakeBridge`/`QTimer`; and one
genuine real-thread confirmation (`test_telnet_bridge_integration.py`'s
new tests, driving an actual background thread, not a fake one, to
prove `on_text`/`run_in_background` really execute off the GUI thread).
**Not** verified against a real MUD server this phase -- unlike several
earlier phases, there was no live-server pass against
`127.0.0.1:4444`; stated plainly rather than implied, per this file's
own rule 8.

**A real, newly-discovered gap, found honestly rather than glossed
over: `pytest tests/` is flaky, not 100% reliable.** Across roughly ten
full-suite runs this phase, most passed cleanly, but a real native
segfault occurred more than once -- always at the identical point,
`engine/scripting/sandbox.py`'s `run_with_timeout()` blocked in
`threading.Thread.join()`, waiting for the worker thread it just
spawned for one `TriggerTable.dispatch()` call. Isolated with real
effort, not just noted and left: a 2000-iteration `dispatch()` stress
test with zero Qt involvement never crashed, ruling out the dispatch
logic or `google-re2` itself in isolation; a specific 3-file GUI subset
(`test_scripting_integration.py`, `test_world_properties_dialog.py`,
`test_address_book_window.py`, run together) reproduced the segfault
reliably. This points at PySide6's offscreen platform plugin
interacting badly with `run_with_timeout`'s design -- a brand-new
real `threading.Thread` spawned for *every single* trigger/alias/
script-load call, unchanged from Phase 4 -- once enough Qt widgets and
threads have both churned through the same process; Phase 9 is the
first phase to exercise that pattern at high enough volume/frequency
(every incoming line, potentially) to expose it. Deliberately **not**
"fixed" here: the checkpoint's own scope explicitly excluded changing
`run_with_timeout`'s design ("no changes to the sandboxing model
itself... this phase is wiring, not redesigning the engine"), and the
real fix for this almost certainly overlaps with SPEC.md section 8's
already-tracked "runaway script execution" hardening item (subprocess
isolation instead of a thread-per-call would sidestep this class of
problem entirely). Recorded there as a second, related known gap
rather than silently worked around. A real running app (one process,
a handful of tabs, dispatch paced by actual network traffic rather
than hundreds of tests' worth of Qt widgets and thread spawns crammed
into one process within seconds) has not been observed to hit this,
but that's an honest "not observed," not a claim it structurally can't
happen.

Still true, called out one more time for the same reason as every
phase since Phase 4b: trusted-mode execution
(`execute_trusted_unrestricted`) is never called from any GUI code
path this phase either -- `ScriptRecord.trusted` remains stored-but-
inert metadata, exactly as Rick's checkpoint 5 confirmed it should stay
until Phase 10's script-sharing ecosystem gives it real purpose.

**Post-Phase-9: connection resilience + clickable URLs — done.** New
`_configure_keepalive()`/`send_nop()` in `engine/net/client.py`, a `NOP`
constant in `engine/net/telnet.py`, `nop_keepalive`/`send_nop_periodically`
in `gui/windows/telnet_bridge.py`, `_auto_reconnect_*` in
`gui/windows/session_tab.py`, `WorldProfile.nop_keepalive` in
`engine/storage/address_book.py`, and URL-anchor rendering in
`gui/windows/styled_text_qt.py`.

Rick reported three issues from real, repeated use, not a planned
phase: several power outages caused an affected tab to just go silent
with no "[Connection lost]" message (unlike a clean server-side close,
which already worked); there was no automatic reconnect after a drop;
and a plain-text URL in the scrollback wasn't clickable. Root-caused
issue 1 by reading the actual code before proposing anything: the
`OSError`-catching/message-display path in `telnet_bridge.py`/
`session_tab.py` was already correct, it simply never got told,
because `TelnetClient` never enabled TCP keepalive -- a silently-dead
socket's `read()` just hangs forever with nothing to catch. Checked
Potato's real source (`~/git/potato/potato.vfs/lib/potato-telnet.tcl`/
`potato-skin.tcl`) for precedent before designing a fix: Potato's own
"keepalive" is an app-level Telnet NOP (`send_keepalive`, `IAC NOP`,
config `world(0,telnet,keepalive)`, default off) whose actual scheduling
call site could not be found in the visible source (flagged explicitly
as unverified, not assumed); its real auto-reconnect is
`world(0,autoreconnect)` (default on) /
`world(0,autoreconnect,time)` (default 330s), and clicking Disconnect
cancels a pending auto-reconnect (this part *was* verified, in
`potato-skin.tcl`).

Two checkpoints before code, per this file's own standing rules.
First, three real forks: retry interval (Rick chose a fixed 30s for
every world over a per-world-configurable one, despite Potato's own
real precedent being configurable); retry limit (Rick chose retry
forever until success or an explicit Disconnect, matching Potato's own
real Disconnect-cancels-pending-retry behavior); keepalive scope (Rick
explicitly chose the larger-scope, non-recommended option -- wire up
the already-present-but-disabled NOP Keepalive checkbox in World
Properties -> Connection too, not just the OS-level TCP fix). Second,
implementation-level forks resolved directly rather than needing
AskUserQuestion: OS-level `SO_KEEPALIVE` (`engine/net/client.py`,
platform-specific -- `TCP_KEEPIDLE`/`INTVL`/`CNT` on Linux,
`TCP_KEEPALIVE` on macOS, `SIO_KEEPALIVE_VALS` on Windows) is always
on for every connection unconditionally, since it's a correctness fix
with no real downside, not a feature needing a per-world toggle;
app-level NOP keepalive is the one that's per-world opt-in, since
sending unsolicited bytes to a server is a more visible behavioral
change Rick specifically wanted gated. Auto-reconnect's timer tick
(`SessionTab._auto_reconnect_tick`) calls the exact same
`reconnect_bridge()` the manual Reconnect action/hotkey/menu entry
already use -- not a parallel implementation, same principle this file
has enforced since Phase 7c. The timer is per-tab, not shared, since
each tab's connection state is genuinely independent (unlike, say, the
tab-activity flash timer, which is intentionally shared because
flashing tabs should blink in sync).

For clickable URLs: kept entirely in `gui/windows/styled_text_qt.py`,
never touching `engine.ansi.Style`/`StyledSegment` (CLAUDE.md rule 2 --
a hyperlink target has no ANSI-SGR equivalent and Style must stay
toolkit/protocol-agnostic). A URL regex (`https?://` only -- bare
`www.` domains deliberately not matched, no reliable way to
distinguish a real domain from an ordinary sentence fragment without
real false-positive risk) splits each segment's text around URL spans
before insertion; a URL span gets `QTextCharFormat.setAnchor(True)`/
`.setAnchorHref(...)` plus a distinct color/underline layered on top of
(not replacing) the segment's own base style, so a URL inside e.g. bold
MUD text still renders bold. Confirmed (not assumed) that plain
`QTextEdit` has no `anchorClicked`/`setOpenExternalLinks` -- those are
`QTextBrowser`-specific -- so `SessionTab.scrollback` and
`SpawnWindow.scrollback` were switched from `QTextEdit` to
`QTextBrowser` (a `QTextEdit` subclass; no other call site needed to
change) with `setOpenExternalLinks(True)`, reusing the exact same
viewport-palette-fix (`apply_scrollback_theme`) already proven correct
for `QTextBrowser` by the Help window since Phase 8.

A real, unrelated pre-existing bug found and fixed along the way, not
introduced by this work: `WorldPropertiesDialog.result_profile()` never
threaded `auto_login` through to the constructed `WorldProfile` at all
-- grepping for "auto_login" in the dialog and its test file returned
zero matches -- meaning saving World Properties for *any* reason (e.g.
just turning on the new Keepalive checkbox) would silently reset that
world's auto-login flag back to off. Fixed alongside adding
`nop_keepalive`, with a dedicated regression test
(`test_result_profile_preserves_auto_login_unchanged`) proving it, not
just describing it.

Tested per this file's own standing rule 7 (a claim needs a test that
would fail if the claim were false), each claim its own test rather
than reusing another: a real socket's actual keepalive options
(`_configure_keepalive`) verified directly against a live socket, not
mocked; a real fake TCP server recording actual bytes received proves
NOP keepalive really reaches the wire, and a second test proves it's
silent when disabled; a real, running `QTimer` (not just calling the
tick handler directly) proves auto-reconnect fires on its own after
the interval elapses; a `/quit`-in-a-secondary-box-style regression
test wasn't needed here since URL handling has no command-parsing
adjacency, but `_split_for_urls` got direct unit tests for its edge
cases (URL mid-sentence, trailing punctuation trimmed, a bare `www.`
correctly *not* matched, a `)`-terminated wiki-style URL's documented
rstrip limitation) plus `QTextCharFormat`-level tests confirming a
rendered URL is really an anchor with the right href and that
non-URL/bold-styled text isn't affected. Full suite: 425 passing (up
from 405 before this round -- 120 engine + a net +20 in GUI).

Verification level, stated plainly per standing rule 8: this round was
verified with real sockets, a real fake TCP server, and a real running
`QTimer` -- one level short of a real dropped connection against an
actual live MUSH server (simulating a genuine network-level silent
drop, as opposed to a clean server-side close, isn't practical to
script against a real remote server) or a real browser actually
opening from a real click, neither of which has been exercised this
round; Rick can confirm both against the real local RhostMUSH and a
packaged build when convenient, same pattern as every other
can't-fully-verify-headless GUI change in this project.

Still NOT wiring `execute_trusted_unrestricted` into any GUI path --
same deferred decision as every phase since Phase 4b, called out again
so it stays visible.

**Post-Phase-9 fix: duplicated scrollback lines on a split network
read — done.** `gui/windows/session_tab.py`'s `_insert_finalized_segments`.

Rick reported real, repeated symptoms: typing e.g. `say some words`
sometimes produced `You say, "some words"` twice in that tab's
scrollback. Initially suspected script involvement (Rick mentioned
he'd been experimenting with the new Scripts page on that world), but
checking the actual on-disk saved scripts
(`~/.local/share/MushTato/scripts/*.json`) found every world's script
list empty — ruled out before proposing anything, not assumed innocent.

Root-caused by reading the actual rendering pipeline, then confirmed by
directly reproducing it (not just reasoned about): a `SessionTab` fed
`'You say, "some'` then `' words"\r\n'` as two separate `simulate_incoming()`
calls (mirroring how a real line arriving split across two TCP reads —
unremarkable on any real network connection, especially one with any
latency — reaches `TelnetBridge.on_text`) rendered
`'You say, "some words"\nYou say, "some'` — the correctly-completed
line followed by a phantom repeat of its own not-yet-terminated tail.
Cause: `_insert_finalized_segments` unconditionally restored whatever
"preview" (`LineDispatcher`'s incomplete-trailing-line mechanism, Phase 9)
was showing *before* an insert, once the new segments were in. That
restore is only correct for `_on_script_echo_requested`'s call path,
where a script's `echo()` genuinely can land in the middle of an
unrelated, still-pending partial line (e.g. a prompt) and must not
swallow it. For `_on_incoming_batch_ready` (ordinary incoming server
text), the "preview" being restored is frequently *the exact same
pending line* `LineDispatcher.feed()` just finished — its not-yet-
terminated tail, now stale, since the full completed line was already
inserted moments earlier in the same call. Restoring it duplicated that
tail. `LineDispatchResult.preview` (the freshly computed, authoritative
current preview) was already being correctly re-applied once, after
every finalized line in a batch — the inner per-insert restore was
always redundant on this path, not merely extra-safe.

Fix: `_insert_finalized_segments` gained a `restore_preview` keyword
(default `True`, unchanged for the echo path); `_on_incoming_batch_ready`
now passes `restore_preview=False` for real incoming text, relying
solely on the batch's own trailing `LineDispatchResult.preview` handling
that already existed. Verified the fix doesn't regress the legitimate
case it might have looked like it was protecting: a single batch with
multiple complete lines *and* a genuine new trailing partial line (e.g.
`"Line1\nLine2\nPartial"`) still renders correctly, preview shown once,
at the true end — proven by a second new test, not just asserted safe
by inspection.

Two new regression tests in `tests/gui/test_main_window_smoke.py`:
`test_line_split_across_two_chunks_is_not_duplicated` (the exact
reproduced failure, using the same `FakeBridge.simulate_incoming()`
two-call pattern used to confirm the bug before writing the fix) and
`test_multiple_finalized_lines_plus_trailing_preview_in_one_batch` (the
non-regression case above). 427 tests passing (up from 425).

**Phase 10 (quick-win polish) — done.** `gui/help/topics.py`
(`_render_about`), `gui/windows/main_window.py` (`_show_about`, the
Edit menu, `_dispatch_focused_edit_action`).

Rick handed over a 10-item, 3-phase external planning document written
without seeing the codebase. Per this file's own standing rules, it was
compiled against the real code before any implementation — corrected
against actual files/classes, checked for existing machinery to reuse,
and had six real forks surfaced via checkpoint (`PHASE10-12_PLAN.md`,
repo root, is the full compiled reference) before writing anything.
Confirmed at that checkpoint: this work becomes Phases 10-12, renumbering
script-sharing from Phase 10 to **Phase 13** in `SPEC.md` section 7 (Rick's
explicit choice, not assumed).

**10a (About box content).** Two existing About surfaces, not the
single "about.py placeholder" the source doc assumed: the bare
`Help -> About` `QMessageBox` in `main_window.py`, and the Help
window's own richer About topic (`gui/help/topics.py`, with a real
Potato/TinyFugue lineage writeup). Per checkpoint, Rick's credit block
(name/aliases/license/repo link) was added to **both**, alongside the
existing lineage content in the Help topic rather than replacing it.
The repo link in the Help topic renders as a real clickable hyperlink
for free, confirmed by directly checking the rendered
`QTextCharFormat` (`isAnchor()`/`anchorHref()`) rather than assuming
the post-Phase-9 URL-anchor work would apply here — it does.

A real, unrelated staleness bug found and fixed while already editing
this exact function: the About topic still claimed Python scripting
"is planned but not wired into the GUI yet" — true before Phase 9,
false since. Fixed in the same pass rather than left for a future
session to rediscover.

**10b (Edit menu expansion).** Current Edit menu had exactly **Copy**
(hardcoded to the active tab's scrollback selection) and a disabled
`Find...` placeholder — not "Copy, Find" as both working, per the
source doc's inaccurate "Current State" (it didn't have the code to
check against). Added Cut/Paste/Undo/Redo/Select All, each with a
platform-appropriate `QKeySequence.StandardKey` shortcut. No "Clear"
item — dropped at checkpoint, Rick's choice, since what it would even
clear was never well-defined by the source doc.

Real design decision made during implementation, not just following
the source doc verbatim: all six actions (including Copy, changing its
existing behavior) now dispatch to `QApplication.focusWidget()` and
call that widget's own `cut()`/`copy()`/`paste()`/`undo()`/`redo()`/
`selectAll()` if it has one, rather than Copy staying hardcoded to the
scrollback while the other five dispatch by focus. Reasoned explicitly
before coding: `SessionTab.scrollback` is read-only (no undo stack,
nothing to cut/paste into), so Cut/Paste/Undo/Redo can only sensibly
target whichever input box has focus regardless; leaving Copy as a
special-cased exception to that same mechanism would have been the
inconsistent choice, not the safe one — and matches actual user intent
better (copying a selection just typed in an input box, not stale
scrollback content). The two input boxes (`HistoryLineEdit`, plain
`QLineEdit`) already got Cut/Copy/Paste/Undo/Redo/Select All for free
from Qt's own built-in key handling before this — the new menu items
add discoverability/mouse-driven access and a `QApplication.
focusWidget()`-based Copy that now also reaches the scrollback, not
new capability where literally none existed before.

**10c (Tools menu population) — no-op by design.** The Tools menu
already exists with three disabled placeholders (`Editor`, `Upload`,
`Mail Window`) found by reading the actual chrome code before writing
the plan doc — Phase 12's text editor and mail window items will
`setEnabled(True)` these directly rather than adding new menu entries.
Nothing to do in Phase 10 itself.

A real test-behavior consequence of the Copy redesign, caught by
running the existing suite rather than assumed compatible: the
pre-existing `test_copy_action_copies_the_active_tab_s_selected_
scrollback_text` implicitly relied on Copy's old hardcoded-to-
scrollback behavior and needed rewriting (split into a scrollback-
focused variant and a new input-box-focused variant proving the actual
behavior change) rather than just extending it. All new focus-dispatch
tests needed the same `host.show()` + `widget.setFocus()` +
`host.activateWindow()` + `QApplication.processEvents()` sequence
`test_hotkeys.py` had already established for `QApplication.
focusWidget()` to resolve correctly headlessly — confirmed by hitting
the exact same failure that pattern exists to avoid, not assumed
needed in advance. 433 tests passing (up from 427).

Not verified against a real desktop this round — the focus-dispatch
mechanism is proven correct at the `QAction.trigger()` level (six new
tests exercise the real dispatch logic against real focused widgets),
but `.trigger()` doesn't reproduce whatever focus-stealing a real
mouse click through an actual open `QMenu` popup might do on a real
window manager; Rick can confirm Cut/Copy/Paste/Undo/Redo/Select All
behave as expected via the menu on a real desktop when convenient,
same pattern as every other can't-fully-verify-headless GUI change in
this project.

**Phase 11 (movable tabs, spawnlog save, error log, find/search) —
done.** New `engine/errorlog.py`, `gui/windows/error_log_window.py`,
`gui/windows/find_bar.py`; extended `engine/storage/paths.py`
(`logs_dir()`), `gui/windows/main_window.py`, `gui/windows/
session_tab.py`, `gui/windows/spawn_window.py`, `gui/app.py`.

Rick handed over a second external planning document mirroring
`PHASE10-12_PLAN.md`'s already-confirmed Phase 11 scope almost
item-for-item, but repeating two things already corrected in that
compiled plan (the guessed `~/.mushtato/...` storage paths, and movable
tabs' acceptance criteria listing persistence-across-restart despite
the Q2 checkpoint already settling on session-only) -- proceeded per
the already-confirmed decisions rather than re-litigating them, noted
inline rather than silently overridden.

**11a (movable tabs).** `MainWindow.tab_widget.setMovable(True)` --
Qt's own native drag-to-reorder, not the custom mouse-event handling
the source doc's pseudocode described (unnecessary once the actual Qt
widget's own capabilities were checked). Session-only per the Phase
10-12 checkpoint: no persistence layer, nothing saved.

**11b (Save Spawnlog).** Added a "Save Spawnlog" button to the
existing `SpawnWindow` (not a new window) -- `QFileDialog.
getSaveFileName()` defaulting to a new `engine/storage/paths.
logs_dir()` (`user_data_dir()/logs`, the real per-OS convention, not
the doc's guessed path) and a timestamped filename, writing UTF-8
plaintext with a header. `logs_dir` threaded through as an explicit
override -- `MainWindow` -> `SessionTab` -> `SpawnWindow` -- the exact
same dependency-injection pattern `scripts_dir`/`script_store_path`
already established, so tests never touch the real per-user logs
directory. Caught before it could leak (not after): the first draft of
`test_save_spawnlog_defaults_to_logs_dir_and_timestamped_filename`
would have called `logs_dir().mkdir(...)` against the real disk path
had the override not been threaded through -- fixed during writing,
verified clean with a real before/after `ls` check on the actual
directory, the same discipline Phase 9's `world_script_path` leak
taught.

**11c (error log), scoped deliberately narrow per checkpoint:**
genuinely *unhandled* exceptions only -- explicitly does **not**
mirror errors this app already shows per-tab (script/trigger/
connection errors stay exactly as they are, untouched by this item).
`engine/errorlog.py` (`ErrorLog`, Qt-free per CLAUDE.md rule 2, a
day-rotated log file + a capped 100-record in-memory ring buffer) is
wired in via `sys.excepthook` **and** `threading.excepthook` --
verified directly, not assumed, that PySide6 *does* route an exception
raised inside a Qt slot through `sys.excepthook` (confirmed with a
real `QApplication` event loop), but that a background thread's
exception (e.g. inside a `TelnetBridge` connection thread) does *not*
reach `sys.excepthook` at all -- Python routes those through the
separate `threading.excepthook` mechanism instead, also confirmed
directly. The source doc's pseudocode only mentioned `sys.excepthook`;
installing both is a real, deliberate extension beyond it, reasoned
through given this app's actual per-connection-background-thread
architecture, not scope creep for its own sake.

Both hooks are installed exactly once, from `gui/app.py`'s real
`main()` only -- never from `MainWindow.__init__`, since they mutate
process-global state and `MainWindow` is constructed repeatedly across
the test suite; installing there would have leaked global state across
unrelated tests. `MainWindow` takes an `error_log=` override (defaults
to a module-level `get_error_log()` singleton, matching how the hooks
themselves are inherently process-global) so tests get an independent,
disk-isolated `ErrorLog` instance instead.

`ErrorLogWindow` (a lazily-constructed singleton, same reuse pattern as
`AddressBookWindow`/`HelpWindow`) uses a small `_ErrorLogSignalBridge`
QObject with one signal for live updates -- the exact same cross-thread
-safe-delivery pattern `telnet_bridge.py`'s own signals already
established, needed here because a record can genuinely originate from
a non-GUI thread (an uncaught background-thread exception). Export
respects the active search filter rather than needing a separate
multi-select mechanism; Clear only empties the in-memory list, never
the on-disk file, proven by a dedicated test rather than described
only.

**11d (find/search), the one item with a real technical correction
to the source doc's own pseudocode, not just its "current state"
claims:** its `cursor.setCharFormat()` approach would have permanently
overwritten -- not overlaid -- a match's real ANSI-derived color/style
directly on the document, with no way back short of manually recording
and restoring every affected character's original format. Verified
`QTextEdit.setExtraSelections()` directly against this PySide6 version
before writing `find_bar.py` around it (a real script confirming match
count, extra-selection count, and that `toPlainText()` is unchanged
after searching) -- the correct, standard Qt idiom for a non-destructive
highlight overlay. New `gui/windows/find_bar.py` (`FindBar`, reusable --
takes any `QTextEdit`/`QTextBrowser`, not hardcoded to `SessionTab`'s
scrollback specifically) is embedded per-tab (`SessionTab.find_bar`,
hidden by default), toggled via `Ctrl+F`/`Edit > Find...`
(`MainWindow._toggle_find_on_current_tab`) -- the real implementation
behind what was a disabled placeholder through Phase 10. Live search
(updates on every keystroke), case-insensitive by default with a
toggle, Prev/Next wrap at either end, Escape closes and clears
highlights, Shift+Return goes to the previous match (needed a small
`_FindLineEdit` subclass -- neither Shift+Return nor Escape has a
dedicated `QLineEdit` signal to hook directly).

A real bug caught by a headless test, not just a style preference:
`SessionTab.toggle_find_bar()`'s first draft checked `find_bar.
isVisible()` to decide open-vs-close -- `isVisible()` depends on the
*entire* ancestor chain actually being on-screen, which is false
whenever a tab isn't the `QTabWidget`'s current page (Qt hides other
tabs' pages itself). That would have made toggling Find on a background
tab always re-open instead of closing an already-open bar. Fixed by
checking `isHidden()` instead (the widget's own explicit shown/hidden
state, independent of any ancestor's visibility) -- caught directly by
a test failing in the exact way the bug predicts, not spotted by
inspection.

Tested per this file's own standing rule 7 throughout: `FindBar` has
13 dedicated tests (match/highlight correctness, non-destructive
document, wrap-around, case sensitivity, Escape/Shift+Return key
handling); `ErrorLog` has 9 engine-level tests including the excepthook
-chaining and background-thread-exception claims each proven with a
real hook install/restore and a real `threading.Thread`, not asserted;
`ErrorLogWindow` has 9 tests including one that raises an exception on
a genuine background `threading.Thread` and confirms it reaches the
window via the signal bridge, not just via a direct same-thread call.
476 tests passing (up from 438 at the end of Phase 10).

Not verified against a real desktop this round -- same honest gap as
Phase 10's Edit-menu work, now compounded by three more GUI-facing
features (movable tabs' real drag feel, the Error Log's tray-adjacent
window chrome, Find's on-screen highlight legibility against a real
scrollback). Rick can confirm all of Phase 11 against a real desktop
build when convenient.

Next: Phase 12 (text editor, tray icon, mail window) -- see
`PHASE10-12_PLAN.md` for the full plan; 12c (mail) still has an open
question (which real mail system Rick's server(s) run) to resolve
before its backend patterns are implemented.

## Standing rules: verification and assumptions

These apply to every session, every phase, not just security-sensitive ones.

1. **Verify before claiming.** For any factual statement about how an
   existing library, format, protocol, or piece of reference material
   (e.g. TinyFugue's or Potato's real source) actually behaves — check it
   against the real source/docs before stating it as fact. If you're
   recalling from training rather than having just checked, say so
   explicitly ("recalling from memory, not verified this session") rather
   than presenting it with the same confidence as something you just read.

2. **Surface every fork in the road, not just the big ones.** If there is
   more than one reasonable way to implement any part of a task — however
   minor it seems — stop and list the options with trade-offs before
   writing code. Do not silently pick one. "This seemed too small to ask
   about" is not a valid reason to skip this.

3. **Name your own uncertainty before starting.** Before beginning
   implementation on anything nontrivial, list anything in the prompt
   that's ambiguous, underspecified, or that you're inferring rather than
   being told directly. Get confirmation before proceeding on those points.

4. **"I'm not sure" is a fully acceptable answer.** If you're not confident
   something is correct, say so rather than guessing. An admitted gap is
   more useful than a confident wrong answer, and never counts against you.

5. **Restate the ask before big work.** Before starting a new phase or any
   substantial chunk of work, summarize your understanding of what's being
   asked, in your own words. Wait for confirmation or correction before
   proceeding. This is cheaper than discovering a misreading after the
   code is written.

6. **Check for existing machinery before building new machinery.** Before
   adding a feature, check whether it needs to reuse or wire into
   something that already exists elsewhere in the codebase (another
   window, an existing handler, an existing data path, an existing
   pattern like the engine/GUI split) rather than assuming a fresh,
   parallel implementation is fine. If two places in the app do "the same
   conceptual thing" (e.g. a button and a command), they should call the
   same underlying code, not reimplement it twice.

7. **Back claims with tests that would fail if the claim were false.** A
   claim like "X works correctly" or "Y is prevented" needs an
   accompanying test exercising that specific claim — not just a
   description of intended behavior, and not just "existing tests still
   pass." (E.g.: don't just say a sandbox blocks dangerous code — write a
   test that tries the dangerous thing and confirms it's blocked.)

8. **Distinguish "I built this" from "I verified this against the real
   thing."** Running code locally, running it against a fake/mock server,
   and running it against a real server (or a real CI pipeline, or a real
   downloaded artifact) are three different levels of verification. State
   plainly which one happened — don't let a local success imply a
   stronger claim than it supports.
