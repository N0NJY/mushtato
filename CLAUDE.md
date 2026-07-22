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
servers (see below).** Telnet IAC negotiation is hand-rolled on raw
asyncio streams (not telnetlib3)
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

Next: Phase 6, layering in Potato's multi-window features — address
book, multi-connection, spawn windows, dual input.
