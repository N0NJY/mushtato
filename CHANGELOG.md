# Changelog

Entries before 2026-07-26 predate real version tracking and are
organized by development phase (this project's actual unit of work,
per `CLAUDE.md`/`SPEC.md`'s roadmap), reconstructed from `CLAUDE.md`'s
phase-by-phase notes and git history. All dates below are from the
actual commit history.

Starting 2026-07-26, MushTato tracks real version numbers (starting at
1.0.0, in `pyproject.toml`'s `version` field, which feeds `/version`
and the About box) — bumped after each completed item on the working
todo/bugs list, not per-commit: a patch bump (1.0.x) for a bug fix, a
minor bump (1.x.0) for a new feature/behavior change.

## 1.0.1 — Fix: World Properties silently reset Mail Window settings (2026-07-26)

- Saving World Properties for *any* reason (even something unrelated,
  like a Character edit or renaming the world) silently reset a
  world's Mail Window settings (Format, Custom template, Convert
  Returns, Convert-To string) back to their defaults — this dialog has
  no UI for those fields (they're only ever set from the Mail Window
  itself, on Send), and never threaded them through when rebuilding
  the saved profile, unlike `auto_login`/`connect_count`, which
  already were. Found while adding SSH support; fixed by preserving
  them from the original profile the same way.

## Post-Phase-13 fix — stray terminal escape sequences over SSH (2026-07-26)

- A real bash session over the new SSH feature sends two kinds of
  escape sequence a MU* server never does: bracketed-paste-mode
  toggling (`ESC[?2004h`/`l`) and window-title-setting (`ESC]0;...`).
  Neither matched `engine/ansi`'s parser (which only recognized plain
  numeric CSI sequences), so both leaked through as literal garbled
  text in the scrollback -- found by Rick in real testing. Fixed by
  recognizing and silently discarding both sequence families, the same
  treatment any other non-color CSI sequence already got; this doesn't
  implement their actual behavior (no real title-bar or paste-mode
  logic), it just stops them from rendering as visible garbage. Full
  terminal emulation (cursor movement, screen redraws -- needed for
  `vim`/`top`/`less`) remains a known, separate, much larger gap.

## Post-Phase-13 — SSH connections (2026-07-26)

- MushTato can now open a real SSH session -- a genuine login shell on
  a remote Unix-like machine, not a MU* connection. Two ways to start
  one: File → New Tab (`Ctrl+T`) opens a blank tab where you can type
  `/ssh [-p port] user@host`, or save a world in the Address Book with
  Protocol set to SSH. The password is always prompted fresh at
  connect time and is never saved to disk.
- Host-key verification is trust-on-first-use, like real `ssh`: the
  first connection to a host:port is trusted and remembered; a later
  connection with a *different* key is refused, not silently allowed.
  `/ssh-forget host[:port]` clears a saved key if a change is expected
  (e.g. the server was reinstalled).
- Blank tabs also support a raw `/connect <host> <port>` (no saved
  world needed) alongside the existing `/connect <world-name>` form.
- Input is sent line-by-line, like MU* commands -- ordinary shell
  commands work, but tab-completion, Ctrl+C, and full-screen programs
  (vim, top, less) don't yet; a known, documented limitation, not a bug.
- New dependency: `asyncssh`.
- Phase 13 (originally planned as a script-sharing ecosystem) was
  deprecated in a separate discussion the day before this shipped —
  see `SPEC.md` section 7 and `CLAUDE.md`'s Phase 13 note for why.

## Post-Phase-12c — Upload (2026-07-25)

- New Upload feature (Tools → Upload, or `/upload`): send a file from
  disk to the active tab, one line at a time, modeled closely on
  Potato's own real Upload feature. Options: Ignore Empty Lines (on by
  default), Add to History, MPP Formatted (Potato's `>`-continuation/
  escaping/comment convention), a Delay (seconds) between sends, and a
  Prefix applied to every line sent. A progress window shows bytes
  processed with Hide/Cancel (confirmed) buttons. Only one upload runs
  per tab at a time — reopening it while one's in flight just shows
  its progress window. Disconnecting, an unexpected connection drop, or
  closing the tab all cancel any upload still running on it, so it
  can't silently keep "sending" into a dead connection.
- This completes the last of Potato's toolbar/menu features that had
  been shown as a placeholder pending a real implementation.

## Phase 12c — System tray icon (2026-07-25)

- MushTato now shows a system tray icon (where the OS supports one):
  left/double-click restores the main window, right-click opens a
  Restore/Exit menu. Blinks whenever new text arrives on a background
  tab, or on any tab while the whole MushTato window itself isn't
  focused — clears on switching tabs or refocusing the app. Icon
  graphics are simple placeholders pending real branding.
- This completes the Phase 10-12 plan.

## Post-Phase-12b — Active-tab highlight (2026-07-25)

- The currently active tab's label is now shown in a distinct cyan
  color, so it's obvious at a glance which connection you're looking
  at — especially in dark mode, where this wasn't obvious before
  without looking closely. Deliberately a different color from the
  orange used for unseen-activity flashing on background tabs, so the
  two aren't confusable.

## Phase 12b — Mail Window (2026-07-25)

- New compose/send Mail Window (Tools → Mail Window, or `/mail`),
  modeled closely on Potato's own real Mail Window: Recipient/CC/BCC/
  Subject fields (enabled or disabled depending on the selected
  format), a Format dropdown with all six of Potato's real built-in
  mail systems (MUSH @mail, MUX @mail, Multi-Command +mail, MUSE
  +mail, Myrddin's BB) plus a Custom command template, "Convert
  Returns" for embedding line breaks in a single-line command, and a
  File → Escape Special Characters action.
- Unlike the Text Editor, only one Mail Window is open per tab at a
  time, matching Potato's real behavior — opening it again just
  brings the existing one to the front.
- Format/Custom template/Convert Returns are saved per world the
  moment you click Send.

## Phase 12a — Text Editor (2026-07-25)

- New Text Editor (Tools → Editor, `Ctrl+Shift+E`, or `/editor`):
  New/Open/Save/Save As with an unsaved-changes prompt, its own
  independent Edit menu and Find bar, live word/line/character counts,
  toggleable line numbers and word wrap, and a configurable font
  (Options → Settings... → Editor Font). Unlike every other satellite
  window in the app, you can open as many Text Editor windows at once
  as you want.
- Files default to a new per-OS `drafts/` data directory; Save/Save As
  remembers the last directory used.
- Fixed a real deadlock found while verifying this phase: the new
  Error Log (Phase 11) briefly used Python's stdlib `logging` module
  internally, whose process-wide lock could deadlock against other
  background threads under heavy test load. Rewritten on plain file
  I/O with an instance-scoped lock instead (same public behavior).

## Phase 11 — Movable tabs, spawnlog save, error log, find/search (2026-07-24)

- Session tabs can now be dragged to reorder (live-session-only, no
  persistence across restarts).
- Spawn (log-mirror) windows gained a "Save Spawnlog" button, saving
  UTF-8 plaintext with a timestamp header to the real per-OS data
  directory by default.
- New Error Log (Tools menu): a crash guard for genuinely unhandled
  exceptions (both on the GUI thread and background connection
  threads) -- does not duplicate errors already shown per-tab. Export/
  Clear/search, with live updates.
- New Find/Search bar in every tab's scrollback (`Ctrl+F` / `Edit ->
  Find...`): live, case-insensitive by default, highlights every match
  without altering the underlying text, Prev/Next with wraparound.

## Phase 10 — Quick-win polish (2026-07-24)

- About box: added Rick's credit block (name/aliases/license/repo
  link) to both the `Help -> About` popup and the Help window's About
  topic, alongside its existing Potato/TinyFugue lineage content.
  Fixed a stale claim in that same topic that scripting "isn't wired
  into the GUI yet" (true before Phase 9, false since).
- Edit menu: added Cut, Paste, Undo, Redo, and Select All (standard
  platform shortcuts). All six Edit actions, including Copy, now
  dispatch to whichever widget currently has keyboard focus rather
  than Copy staying hardcoded to the scrollback.
- Kicked off a new 3-phase plan (10-12) compiled from an external
  planning document and corrected against the real codebase; script-
  sharing (previously Phase 10) is renumbered to Phase 13. See
  `PHASE10-12_PLAN.md` for the full plan.

## Post-Phase-9 — Fix duplicated scrollback lines on a split network read (2026-07-24)

- Fixed a real bug where a line arriving split across two network reads
  (unremarkable on any real connection with latency) could render
  twice — the completed line followed by a phantom repeat of its own
  tail, e.g. `You say, "some words"` then `You say, "some`. Caused by
  `SessionTab._insert_finalized_segments` unconditionally re-showing a
  stale "preview" (the incomplete-trailing-line mechanism from Phase 9)
  that was often the very line that had just been completed. Two new
  regression tests cover the exact reproduced failure and the
  legitimate multi-line-plus-trailing-preview case it could have
  regressed.

## Post-Phase-9 — Connection resilience + clickable URLs (2026-07-24)

- **Dropped connections are now detected.** OS-level TCP keepalive is
  always on for every connection, so a silently-dead network (e.g. the
  user's own connection dropping) now reliably produces the same
  "[Connection lost]" message a clean server-side close already showed
  — previously it just hung with no indication anything was wrong.
- **Automatic reconnection.** Once a tab's connection drops, it retries
  connecting again every 30 seconds — indefinitely, with no
  confirmation prompt — until a retry succeeds or the user clicks
  Disconnect. Runs independently per tab; each retry calls the exact
  same code the manual Reconnect action already uses.
- **Telnet NOP keepalive**, opt-in per world (World Properties →
  Connection → Keepalive checkbox, now functional rather than a
  disabled placeholder): sends an application-level `IAC NOP` every 60
  seconds, for worlds behind a firewall/NAT that drops idle connections
  before OS-level TCP keepalive would ever notice.
- **Clickable URLs.** Any `http://`/`https://` URL in a tab's scrollback
  (or a spawned log window mirroring it) is now underlined, colored,
  and clickable — opens in the system's default browser. Display-layer
  only; doesn't change what triggers see.
- Along the way: fixed a real pre-existing bug where saving World
  Properties for any reason could silently reset a world's `auto_login`
  flag back to off, since it was never threaded through
  `result_profile()`.

## Phase 9 — GUI-scripting integration (2026-07-24)

- `engine/scripting` (sandboxed triggers/aliases/gags/highlights/timers/
  variables, built in Phase 4) is wired into the real GUI for the first
  time. Every tab gets its own independent script runtime; incoming
  text is matched against triggers (which can gag/highlight/echo/send/
  set variables), typed input against aliases.
- A new **Scripts** page in World Properties (Address Book → select a
  world → Properties... → Scripts) for writing/saving scripts per
  world, alongside the existing Basic/Characters/Connection/Auto-Sends/
  Notes sections.
- Script errors and timeouts surface as scrollback lines instead of
  crashing the tab; a trigger that fails 5 times in a row auto-disables
  itself (visibly marked in the Scripts page) rather than flooding the
  scrollback with the same error forever.
- Trigger/alias dispatch runs on the connection's own background
  thread, not the GUI thread, so a slow or hung script can't freeze the
  app.
- Script variables autosave periodically and on disconnect.

## Post-8b — Remembered input-pane size + configurable fonts (2026-07-24)

- The dual-input pane's dragged height is now remembered (one global
  preference, not per-world) and used as the starting split for every
  newly-opened tab, this session or a future launch.
- Two independent font pickers in Options → Settings...: a **Terminal
  Font** (monospaced fonts only, to preserve MUD banner/table
  alignment) for the scrollback pane, and an **Input Font** shared by
  both input boxes. Both apply immediately to already-open tabs and
  persist across restarts.

## Post-8b — Tab-activity flashing (2026-07-24)

- A background tab (one you're not currently viewing) blinks orange when
  it receives new incoming text, and keeps blinking indefinitely until
  you switch to it — the tab you're already looking at never flashes for
  its own traffic.

## Post-8b — Address book auto-login and sorting (2026-07-24)

- A per-world "auto-login" checkbox, shown on that world's row in the
  Address Book's Worlds list once it has a default Character set (no
  checkbox at all otherwise, since there'd be nothing to log in as).
  Checked worlds are opened and logged into automatically, one at a
  time, when MushTato starts — no confirmation prompt.
- Sort A-Z / Sort Z-A buttons (one-shot re-sorts, not a persistent mode)
  and drag-and-drop reordering of the Worlds list.

## Post-8b — Character picker + Log In (2026-07-23)

- A second list next to the Address Book's Worlds list shows the
  selected world's saved Characters. Picking one and clicking **Log In**
  connects as that Character specifically — a one-time choice that never
  changes the world's stored default Character, and always opens a new
  tab (logging in as a different Character is a genuinely different
  session, not a duplicate connection). Confirmed via Potato's real
  source that no equivalent exists there — this is a MushTato original,
  not a ported feature.

## Post-8b — Two real fixes found testing the actual build (2026-07-23)

- Address book buttons (Edit/Delete/Connect/Properties...) silently did
  nothing when clicked with no world selected — now disabled until a
  world is actually selected.
- The first Character added to a world with no default set yet is now
  auto-selected as that world's default, closing a real discoverability
  gap (the Default Character field lives on a different Properties page
  than where Characters are added).

## Phase 8b — Address book / World Properties overhaul (2026-07-23)

- Per-world saved Characters (name + password), auto-sends (first-
  connect-ever / every-connect / after-login), login format/delay, and
  notes — verified against Potato's real source for exact dispatch order
  and data shape, not guessed at.
- A new World Properties window (category list + pages: Basic,
  Characters, Connection, Auto-Sends, Notes) alongside the existing
  quick Edit dialog.
- A real data-loss bug fixed along the way: the quick Edit dialog used
  to silently wipe out a world's Characters/auto-sends if you edited it
  after setting them up via Properties.

## Phase 8 — Documentation & onboarding (2026-07-23)

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
