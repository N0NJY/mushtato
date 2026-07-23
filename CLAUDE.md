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
chrome) — done, see below.** Telnet IAC negotiation is
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

Next: Phase 8, documentation.
