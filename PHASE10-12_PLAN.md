# MushTato — Phases 10-12 Plan (confirmed, ready to implement)

Source: Rick's "MushTato Client - Complete Feature Implementation Plan"
(10 items, external doc). Folded into MushTato's real phase-numbering
convention and corrected against the actual codebase — the original
doc was written without seeing the code, so several of its "Current
State" descriptions and implementation notes didn't match reality.
Corrections and open questions were resolved via checkpoint on
2026-07-24 (see "Confirmed decisions" below); `SPEC.md` section 7's
roadmap has been updated to match this numbering. This file is the
detailed implementation reference for Phases 10-12; the phase write-ups
that land in `CLAUDE.md` as each phase actually completes are the
canonical record going forward, same pattern as every prior phase —
this file can be deleted once Phase 12 is done and its content has been
absorbed there.

**Phase 10, Phase 11, Phase 12a (Text Editor), and Phase 12b (Mail
Window) are done** (see CLAUDE.md for the full write-up of each).
**12c (tray icon) has not started.** Per CLAUDE.md rule 1 ("one phase
at a time"), work proceeds in order, each item done and tested before
the next starts. Mail (originally 12c) was reordered ahead of the tray
icon per Rick's explicit request; Q6 was resolved by reading Potato's
real source rather than asking Rick (see the 12b section below).

---

## Confirmed decisions (2026-07-24 checkpoint)

- **Q1 (phase numbering):** this plan becomes Phases 10-12. Script-
  sharing (previously Phase 10) is renumbered to **Phase 13** in
  `SPEC.md`.
- **Q2 (tab persistence):** movable tabs (11a) are **live-session-only**
  — dragging reorders open tabs while running; nothing is saved or
  restored across restarts.
- **Q3 (tray icon graphics):** no real logo/icon artwork exists and I
  have no image-generation tool. Ship **simple programmatically-
  generated placeholder icons** (basic shapes/text) for 12b, swappable
  later once real branding exists.
- **Q4 (About box scope):** Rick's credit text (name/aliases/license/
  repo link) is **added alongside** the Help window's existing About
  topic content — the Potato/TinyFugue lineage writeup stays, it's not
  replaced.
- **Q5 (error log scope + Clear):** the Error Log (11c) covers
  **genuinely unhandled exceptions only** (a `sys.excepthook`-style
  crash guard) — it does not mirror errors already shown per-tab
  (script/trigger/connection errors stay exactly as they are today).
  The Edit menu's **"Clear" item is dropped entirely** — not worth the
  ambiguity; the other five (Cut/Copy/Paste/Undo/Redo/Select All)
  ship without it.
- **Q6 (mail backend reference) — still open, not blocking Phase 10/11:**
  which real mail system(s) Rick's own server(s) actually run needs a
  real answer (with an ideal real transcript) before 12c's backend
  patterns are implemented from anything more than the doc's guessed
  syntax. Revisit when Phase 12 starts, not before.

---

## Phase 10 — Quick wins

### 10a. About box content (doc's Item #1)

Two existing About surfaces, not the single "about.py placeholder" the
doc assumed:
1. `Help menu -> About` — a bare `QMessageBox.information()` in
   `gui/windows/main_window.py:_show_about()`, currently just
   `"MushTato {version}"`.
2. The Help window's own **About MushTato** topic
   (`gui/help/topics.py:_render_about()`) — already has real content:
   version, a Potato/TinyFugue lineage writeup, the project's dual-
   audience goal. Rendered through `QTextBrowser`, so a bare
   `https://github.com/...` link in it renders clickable for free,
   using the URL-anchor work already shipped (post-Phase-9).

Per Q4: add Rick's credit block (name/aliases/license/repo link) to
topic #2, alongside the existing lineage writeup — not replacing it.
Leave surface #1's bare popup as a minimal version pointer, or extend
it too with a short one-line credit — small enough to decide inline
during implementation rather than needing its own checkpoint.

### 10b. Edit menu expansion (doc's Item #9)

Current Edit menu (`main_window.py` `_build_chrome`) has exactly
**Copy** (wired to the active tab's scrollback selection) and a
**disabled** `Find...` placeholder.

The two input boxes (`HistoryLineEdit`, a plain `QLineEdit` subclass)
already get Cut/Copy/Paste/Undo/Redo/Select All for free from Qt — no
custom wiring needed for those individually. `SessionTab.scrollback`
is a **read-only** `QTextBrowser` — no undo stack, nothing to cut or
paste into, so Cut/Paste/Undo/Redo only make sense against whichever
input box currently has focus; Select All and Copy can reasonably act
on whichever widget has focus, including the scrollback.

Implementation: menu handlers dispatch to `QApplication.focusWidget()`
and call that widget's own `cut()`/`copy()`/`paste()`/`undo()`/
`redo()`/`selectAll()` if it has one, doing nothing when the focused
widget doesn't support that operation. Per Q5, **no "Clear" item** —
final Edit menu list: Cut, Copy, Paste, Undo, Redo, Select All, Find...
(existing, wired for real in 11d).

The disabled `Find...` action becomes the real wiring target for
Phase 11's Find/Search item (11d) rather than a separate thing — one
feature, two entry points.

### 10c. Tools menu population (doc's Item #10)

The Tools menu already exists (`main_window.py:_build_chrome`) with
three **disabled placeholders**: `Editor`, `Upload`, `Mail Window`.
Phase 12's Text Editor (12a) and Mail Window (12c) items have their
real menu homes already built — just `setEnabled(True)` + wiring once
each feature exists in 12a/12c. `Upload` has no corresponding item in
this plan and stays disabled. No standalone Phase 10 work item here.

---

### Phase 10 summary
Items: 10a (About credits), 10b (Edit menu: Cut/Copy/Paste/Undo/Redo/
Select All, dispatched by focus), 10c (no-op — Tools menu wiring folds
into 12a/12c).

---

## Phase 11 — Medium complexity

### 11a. Movable tabs (doc's Item #2, persistence dropped per Q2)

`QTabWidget` (`MainWindow.tab_widget`) has a built-in
`setMovable(True)` giving real drag-to-reorder with native visual
feedback — currently not set. Per Q2, this is the entire scope: enable
it, add a test confirming it's enabled. No persistence work — tabs are
live connections, not documents; nothing to save or restore.

### 11b. Save Spawnlog to disk (doc's Item #3)

`SpawnWindow` (`gui/windows/spawn_window.py`) already exists as the
log-mirror window this item adds a Save button to — this is "add one
button + one method to the existing class," not a new window.

Storage: the doc's proposed paths (`~/.mushtato/logs/`,
`%APPDATA%/MushTato/logs/`) don't match this project's real,
already-established convention (`engine/storage/paths.py`,
`platformdirs.user_data_dir` — `~/.local/share/MushTato/` on Linux,
`%LOCALAPPDATA%\MushTato\` on Windows, `~/Library/Application
Support/MushTato/` on macOS). Add a `logs_dir()` to
`engine/storage/paths.py` alongside the existing
`address_book_path()`/`settings_path()`/`world_script_path()`.

Default filename (`spawnlog_YYYYMMDD_HHMMSS.txt`) and plaintext-with-
timestamp-header format from the doc are fine as-is.

### 11c. Error logging system (doc's Item #4, scope narrowed per Q5)

Per Q5: **unhandled exceptions only** — a `sys.excepthook` install
that logs to file + an in-memory ring buffer, viewable from a new
Tools-menu-accessible window (doc's list/detail/export/clear UI is
reasonable as designed). Does **not** duplicate script/trigger/
connection errors already shown per-tab — those stay exactly as they
are today, untouched by this item.

Storage: same correction as 11b — `user_data_dir()/logs/
error_YYYYMMDD.log`, not `~/.mushtato/logs/`.

### 11d. Find/Search in scrollback (doc's Item #7)

Genuinely new. `QTextEdit`/`QTextBrowser` has a built-in single-match
`find()`, but "highlight *every* match at once + Prev/Next between
them" needs `setExtraSelections()` — custom work, not free from Qt the
way movable tabs is. This is the real implementation behind the Edit
menu's `Find...` placeholder (10b) — `Ctrl+F` and the menu item both
open the same find bar.

---

### Phase 11 summary
Items: 11a (movable tabs, session-only), 11b (spawnlog save), 11c
(error log, unhandled-exceptions-only), 11d (find/search).

---

## Phase 12 — Large/complex

### 12a. Built-in text editor (doc's Item #5)

Enables the Tools menu's existing disabled `Editor` placeholder (10c).
Default draft directory: same platformdirs-based fix as 11b/11c —
`user_data_dir()/drafts/`, added to `engine/storage/paths.py`.

### 12b. Programmable mail window — Q6 resolved, plan confirmed 2026-07-25

Enables the Tools menu's existing disabled `Mail Window` placeholder
(10c). Reordered ahead of the tray icon per Rick's explicit request
(now 12c). Q6 ("which real mail system does Rick's server run") is
**resolved, not by asking Rick, but by reading Potato's actual real
source** (`~/git/potato/potato.vfs/lib/potato.tcl` — `::potato::
mailWindow`/`mailWindowFormatChange`/`mailWindowSend` — and
`potato-config.tcl`'s `gameMail` array) rather than the earlier
external planning doc's guessed "BrandyMail"/"MUSH @mail" backends,
which don't match Potato's real format list at all.

**Confirmed real format templates** (`potato-config.tcl`'s `gameMail`
array), replicated verbatim as MushTato's own format list:

| Format | Template |
|---|---|
| MUSH @mail | `@mail %to%=%subject%/%body%` |
| MUX @mail | `@mail %to%=%subject% ;; -%body% ;; --` |
| Multi-Command +mail | `+mail %to%=%subject% ;; -%body% ;; --` |
| MUSE +mail | `+mail %to%=%body%` (no subject placeholder at all) |
| Myrddin's BB | `+bbpost %to%/%subject%=%body%` |
| Custom | `writeto %to% %cc% %bcc% about %subject% ;; write %body% ;; send` |

**Real mechanics, confirmed from the actual proc bodies, not
paraphrased from memory:**
- `;;` in a template (bare or surrounded by spaces) means "send this
  as separate lines" — the fully-substituted command string is split
  on `;;` and each piece sent to the server as its own line (this is
  how the 3-line MUX/Multi-Command sequence works: recipient/subject
  line, body line, terminator line).
- Each of To/CC/BCC/Subject is enabled in the UI only if the
  *currently active* template (the selected built-in one, or the
  Custom text) actually contains that placeholder — e.g. MUSE grays
  out CC, BCC, *and* Subject, since its template references none of
  them.
- "Convert Returns" (default on) replaces literal newlines in the body
  with a configurable string (default `%r`) before any placeholder
  substitution — needed since these are single-line softcode commands
  over telnet.
- Mail is sent straight to the raw connection, bypassing alias/
  slash-command processing entirely — matches the exact reasoning
  MushTato's existing autosends already established (`_send_to_bridge
  (..., apply_aliases=False)`), not a new principle.
- A File-menu "Escape Special Characters" action backslash-escapes
  softcode-special characters (`% ; [ ] ( ) , ^ $ { } \` plus tab->`%t`)
  in the body on demand — a real, useful, self-contained feature.

**Real, deliberate deviations from Potato, confirmed via checkpoint
(2026-07-25), all matching the recommended/Potato-parity option:**
- **Scope: compose-only**, matching what Potato's real source actually
  does — there is no list/read/search/auto-refresh anywhere in
  `potato.tcl`'s mail code; the earlier external planning doc's fuller
  mail-client mockup (List/Compose/Read/Search views, unread badges)
  was never real Potato parity to begin with, and is explicitly
  **out of scope** for this item.
- **One compose window per tab** (Potato's real `.mailWindow$c`
  behavior — opening a second re-shows the existing one), not the
  unlimited-simultaneous-windows pattern Phase 12a's Text Editor just
  established. Owned by `SessionTab` (a single `Optional[MailWindow]`
  slot, not a list), the same "per-tab, not global" pattern
  `find_bar` already uses.
- **Format/Custom-template/Convert-Returns are edited only in the
  compose window itself**, matching Potato's real model exactly — no
  new World Properties page. Persisting a change follows the
  established `MainWindow.record_world_connected()` pattern (Phase
  8b): mutate the in-memory `WorldProfile`, reload the address book
  fresh from disk, find the matching entry by name+host+port, copy the
  changed fields over, save, and refresh `AddressBookWindow`'s list if
  open.
- **"Escape Special Characters" is included in v1.**

**New `WorldProfile` fields** (`engine/storage/address_book.py`,
matching existing per-world field conventions like `login_format`/
`nop_keepalive`): `mail_format: str = "MUSH @mail"`,
`mail_format_custom: str = <the Custom template above>`,
`mail_convert_returns: bool = True`, `mail_convert_returns_to: str =
"%r"`.

**Architecture:** the actual template-substitution/`;;`-splitting
logic is pure string manipulation with no Qt dependency — lives in a
new, headlessly-testable `engine/mail_format.py` (a `build_mail_
commands(...)` function returning the list of raw lines to send),
matching this project's standing preference for Qt-free pure logic
(CLAUDE.md rule 2) over embedding it directly in the Qt window class.
`gui/windows/mail_window.py` (`MailWindow`, a `QMainWindow`) owns the
UI only: field widgets, the format-driven enable/disable behavior,
and calling `build_mail_commands()` then `bridge.send_line()` per
resulting line. Own independent Edit menu (Cut/Copy/Paste on the body
`QPlainTextEdit`) for the identical, already-confirmed reason Phase
12a's Text Editor needed one (`QApplication.focusWidget()` cannot
reach a separate top-level window) — using MushTato's own established
simpler always-enabled-no-op-if-nothing-to-do convention rather than
Potato's more elaborate dynamic Copy/Cut/Paste enable-state logic.

---

### Phase 12 summary
Items: 12a (editor, done), 12b (mail — plan confirmed, ready to
implement), 12c (tray icon, placeholder graphics, reordered after
mail per Rick's request).

---

## Session breakdown (adjusted from the doc's 7-session estimate)

Given the corrections above (movable tabs is now a ~15-minute change,
not 1-2 hours; Tools-menu "population" folds into 12a/12c rather than
being separate; Find and Edit-menu-Find are one feature not two; the
Error Log's scope narrowed to unhandled-exceptions-only; Clear dropped
from Edit), the original 17-21 hour / 7-session estimate is high. Rough
revised estimate, to be treated as a guess until each phase is actually
built:

- **Phase 10** (10a About, 10b Edit menu): well under an hour combined.
- **Phase 11** (11a movable tabs, 11b spawnlog save, 11c error log,
  11d find/search): roughly 3-5 hours, dominated by 11c and 11d.
- **Phase 12** (12a editor, 12b tray icon, 12c mail): roughly 6-10
  hours, dominated by 12c (mail) and contingent on Q6's answer.

No fixed session count committed here — CLAUDE.md rule 1 governs actual
pacing (one phase at a time, each tested before the next starts).
