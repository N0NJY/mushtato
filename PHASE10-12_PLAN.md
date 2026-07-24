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

**Nothing in Phases 10-12 has been implemented yet.** Per CLAUDE.md
rule 1 ("one phase at a time"), work proceeds Phase 10 -> 11 -> 12 in
order, each phase done and tested before the next starts.

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

### 12b. Tray icon + logo (doc's Item #6, graphics scope narrowed per Q3)

Technical half: `QSystemTrayIcon` — built into Qt/PySide6, no new
dependency — context menu, click-to-restore, activity-blink timer
reusing the exact pattern `MainWindow`'s existing tab-activity flash
timer already established (shared `QTimer`, tracked-by-object, orange
color choice documented as a fixed non-theme-aware pick, same as
`ACTIVITY_COLOR`).

Graphics half, per Q3: **simple programmatically-generated placeholder
icons** (basic shapes/text via PIL or Qt's own `QPainter`, not real
brand design) for the resting/activity states, clearly documented as
placeholders pending real artwork — no multi-resolution asset pipeline
or animation-frame set beyond what the activity-blink actually needs
(reusing the tab-flash approach — a color/state toggle — rather than
true multi-frame animation, unless that turns out insufficient).

### 12c. Programmable mail window (doc's Item #8)

Enables the Tools menu's existing disabled `Mail Window` placeholder
(10c). Most architecturally novel item in the plan. Per Q6 (still
open): backend command/regex patterns (BrandyMail, MUSH @mail, custom)
need verification against Rick's own real server(s) before
implementation — same standing rule this project has followed all
session (verify before claiming), same approach Phase 8b took reading
real Potato source before designing Characters/auto-sends. Revisit Q6
when this item actually starts.

---

### Phase 12 summary
Items: 12a (editor), 12b (tray icon, placeholder graphics), 12c (mail
— backend patterns pending Q6).

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
