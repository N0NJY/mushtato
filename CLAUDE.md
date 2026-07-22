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
headless) — done, including Phase 4b (on_alias, see below).** Telnet
IAC negotiation is hand-rolled on raw asyncio streams (not telnetlib3)
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

Next: Phase 5, the minimal Qt shell — one window, one connection,
scrollback + input, wired to the validated engine.
