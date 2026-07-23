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
see below.** Telnet IAC negotiation is
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
"one connection" and "the window chrome" in the same class. Phase 9
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

Next: Rick has his own phase document for what comes after Phase 8b --
not yet assigned a phase number here.

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
