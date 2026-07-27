"""Help content: what each section says, and the one canonical list of
built-in commands that both the real command dispatch (SessionTab) and
this documentation are generated from.

Static sections are plain Markdown string constants -- deliberately
*not* loose .md files on disk: packaging/mushtato.spec's ``datas=[]``
is currently empty, and bundling loose data files into a PyInstaller
build would need real spec-file changes plus frozen-vs-source path
resolution that could only be trusted once verified against an actual
packaged build -- exactly the kind of "works locally, breaks in the
real build" gap that already bit this project twice (the
libxcb-cursor0 packaging bug, and the theme-not-reaching-the-scrollback
bug). A plain .py module needs none of that; it's bundled automatically
as part of the normal import graph.

The command list and hotkey list are generated from live data
(``COMMAND_HELP`` below, and the ``hotkeys``/``theme`` passed into
``HelpContext``) rather than hand-copied prose, so they can't drift out
of sync the way the Phase 7c ``/help`` placeholder already avoided by
generating its text from the live ``CommandTable``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from ..dialogs.settings_dialog import ACTION_LABELS
from ..version import mushtato_version

# Single source of truth for every built-in command's name and help
# text -- SessionTab._register_commands() iterates this same list to
# actually register the commands, so this documentation and the real
# dispatch table cannot diverge by construction.
#
# Placeholders use square brackets ("[name]"), not angle brackets --
# verified empirically (not assumed) that Qt's QTextBrowser.setMarkdown()
# parses "<name>"/"<dark|light>" as (invalid) inline HTML tags, which
# silently corrupted all the rendered content that followed one in the
# same document. Square brackets alone (not immediately followed by
# "(...)", which would make them real Markdown link syntax) render as
# plain literal text, confirmed the same way.
COMMAND_HELP: List[Tuple[str, str]] = [
    ("help", "List available commands/topics, or show help for one: /help [topic|command|topics]"),
    ("quit", "Close this tab"),
    ("spawnlog", "Open a log-mirror spawn window"),
    ("connect", "Connect to a saved world by name, or a blank tab to a raw host/port: /connect [name] | [host] [port]"),
    ("settings", "Open the settings dialog"),
    ("version", "Show the MushTato version"),
    ("theme", "Switch theme: /theme [dark|light]"),
    ("disconnect", "Disconnect from the server"),
    ("reconnect", "Reconnect to the server"),
    ("editor", "Open a new Text Editor window"),
    ("mail", "Open this tab's Mail Window (compose/send)"),
    ("upload", "Upload a file to this tab, line by line"),
    ("ssh", "Connect this (blank) tab via SSH: /ssh [-p port] user@host"),
    ("ssh-forget", "Forget a saved SSH host key: /ssh-forget [host[:port]]"),
]


@dataclass(frozen=True)
class HelpContext:
    """Live data a topic's content may need to render accurately."""

    hotkeys: Dict[str, str]
    theme: str


@dataclass(frozen=True)
class HelpTopic:
    slug: str
    title: str
    render: Callable[[HelpContext], str]


def _render_about(ctx: HelpContext) -> str:
    del ctx
    return f"""# About MushTato

**MushTato** (version {mushtato_version()}) is a free, open-source,
cross-platform GUI client for MUD/MUSH/MOO-style text games (MU*).

The name is a nod to its lineage:

- **Potato** wing bar (a Tcl/Tk MUSH client by Mike Griffiths) --
  MushTato's address book, tabbed sessions, dual input, spawn windows,
  and configurable hotkeys are all modeled on Potato's real GUI
  behavior.
- **TinyFugue** (a classic Unix MUD client) -- MushTato's built-in
  client command system (the `/` and `//` convention) follows
  TinyFugue's own real command-prefix rules.

MushTato is aimed at two kinds of users at once: newcomers who want a
point-and-click client with zero setup, and power users who want
TinyFugue-level control. Every built-in feature that has both a menu/
button *and* a typed command uses the exact same underlying code for
both -- there's no "easy mode" and "real mode," just two ways to reach
the same thing.

Full Python scripting (triggers, macros, gags, highlights, aliases,
timers) is wired into every tab -- see the Scripting topic for the API.

## Author

Written by Rick Donaldson, 2026 (aka Thoran Yo, aka Fletcher, aka
N0NJY). Licensed under the MIT License. Latest copy:
https://github.com/N0NJY/mushtato
"""


def _render_address_book(ctx: HelpContext) -> str:
    del ctx
    return """# Address Book

The Address Book is a separate window for saving, editing, and
connecting to MUD/MUSH worlds. It doesn't hold a connection itself --
it's a picker that adds a tab to the main window when you connect.

**Opening it:** File menu -> Address Book..., or the Address Book
toolbar button.

**Saved worlds (quick edit):**
- **Add** -- create a new saved world (name, host, port, notes).
- **Edit** -- quickly change a selected world's name/host/port/notes.
- **Delete** -- remove a selected world from the list.
- **Connect** -- open (or switch to) a tab for the selected world,
  using its stored default Character (if any). Double-clicking a world
  in the list does the same thing.
- **Properties...** -- open the full World Properties window (below)
  for a selected world's deeper settings.

If you Connect to a world that's already open in a tab, MushTato
switches to that existing tab instead of opening a second connection
to the same place.

**Command-line equivalent:** `/connect [name]` looks up a saved world
by name and connects to it (or switches to its tab if already open),
from any tab's input line -- exactly the same underlying action as
clicking Connect in the Address Book.

**Logging in as a specific Character:** selecting a world also lists
its saved Characters in a second list next to it. Pick one and click
**Log In** to connect using that Character specifically -- this is a
one-time choice for that connection only; it never changes the world's
stored default Character. Unlike plain Connect, Log In always opens a
**new** tab, even if that world already has one open elsewhere --
logging in as a different Character is treated as a genuinely
different session (e.g. running a main character and an alt on the
same MUD at once), not a duplicate of an existing connection.

## World Properties

Properties... opens a separate window with six sections (a category
list on the left, that section's fields on the right):

- **Basic** -- world name, Protocol (Telnet for a MU*, or SSH for a
  real shell account -- see the SSH Connections topic; SSH Username
  only applies when Protocol is SSH, and the SSH password is never
  saved here or anywhere else, always prompted fresh at connect), host,
  port, and which saved Character (if any) connects automatically by
  default.
- **Characters** -- a world can have multiple saved Characters, each
  just a name and password. Two different worlds can each have a
  Character with the same name and a different password -- Characters
  are scoped to their own world's list, never shared globally. Add/
  Edit/Delete a Character, then Save or Cancel that one change.
- **Connection** -- the *Login Format* (e.g. `connect {name}
  {password}`, sent with the default Character's name/password
  substituted in), *Login Delay* (how long to wait after connecting
  before sending it, giving the server time to show its own banner
  first), and *Keepalive* (send a Telnet no-op every 60 seconds to keep
  idle firewalls/NAT from silently dropping this connection) are real
  and functional. The rest of this section (SSL, a 2nd address/port,
  proxy, and several other Telnet-specific options) mirrors real
  settings from Potato but is shown **disabled** -- MushTato's
  connection engine doesn't support them yet. Visible on purpose, so
  it's clear what's planned versus what's broken. (Note: this "SSL"
  checkbox is about *encrypting a Telnet/MU* connection* specifically,
  a different, still-unbuilt feature -- if you want to connect to a
  real Unix shell account, that's the Protocol: SSH option on the
  Basic page instead, which is real and functional; see the SSH
  Connections topic.)
- **Auto-Sends** -- three optional blocks of text (one line each) sent
  automatically on connect, in this order: *first connect ever*
  (tracked per world -- only ever fires once, the very first time you
  successfully connect to this world), *every connect, before login*,
  the Character login line itself (if a default Character is set), then
  *every connect, after login*. Auto-sent lines always go to the server
  literally -- never reinterpreted as a `/` client command, the same
  principle the Pose/says... box already follows.
- **Notes** -- one free-text block for anything you want to remember
  about this world.
- **Scripts** -- triggers, aliases, gags, highlights, and timers for
  this world, written in sandboxed Python. See the Scripting topic for
  the full API and how errors/auto-disabled triggers are surfaced.

## Auto-Login on startup

Back in the Address Book's own Worlds list (not inside Properties): each
world's row shows a checkbox once that world has a default Character set
(Properties -> Basic, or just add its first Character on the Characters
page, which auto-selects it as the default). Check it to have MushTato
automatically open and log into that world every time the app starts,
with no confirmation prompt. A world with no default Character shows no
checkbox at all on its row, since there'd be nothing to log in as yet --
set one in Properties first and the checkbox appears. Flagged worlds are
opened one at a time, in the order they appear in this list, the same
way clicking Connect on each in turn would -- a world that's down
doesn't hold up the rest, since nothing waits for a login to actually
succeed before opening the next.

## Sorting and reordering

- **Sort A-Z** / **Sort Z-A** -- re-sort the whole list alphabetically
  by world name, right now. This is a one-time action, not a mode --
  adding a new world afterward just appends it to the end until you
  click Sort again.
- **Drag and drop** a world up or down in the list to put it in
  whatever custom order you want. The saved order is what both the
  list itself and Auto-Login's connect-in-sequence use.
"""


def _render_tabs(ctx: HelpContext) -> str:
    del ctx
    return """# Sessions & Tabs

The main MushTato window is the app's persistent home base -- it opens
when you launch MushTato, before you've connected to anything, and it
stays open even after every connection is closed. Each connection you
open lives in its own **tab** inside this one window, rather than in a
separate window per connection.

- Opening a new world (via the Address Book, or `/connect [name]`)
  adds a new tab and switches to it.
- File -> New Tab (or `Ctrl+T` by default) opens a **blank** tab with
  no connection at all -- type `/connect [host] [port]` or
  `/ssh [-p port] user@host` into it to connect (see the SSH
  Connections topic for the latter). Useful for a one-off connection
  you don't want to save to the Address Book.
- Closing a tab (File menu -> Close, the Close toolbar button, `Ctrl+W`
  by default, or typing `/quit`) closes *only that tab* -- the main
  window itself stays open, even with zero tabs left, ready for a new
  connection.
- To actually exit MushTato, close the main window itself (its window-
  manager close button) or use File -> Exit.
- The status bar always reflects whichever tab is currently active:
  world name, host:port, connection state, how long you've been
  connected, and the clock.

This replaced an earlier design (one separate top-level window per
connection) -- if you're used to an older MushTato build, this is the
intentional current model, not a bug.

## Which tab am I on?

The currently active tab's label is shown in a distinct cyan color, so
it's obvious at a glance which connection you're looking at -- this is
deliberately a different color from the orange used for unseen
activity on a background tab (see below), since a steady "you are
here" cue and a blinking "something happened elsewhere" cue need to
stay visually distinguishable from each other.

## Reordering tabs

Drag a tab to a different position in the tab bar to reorder it. This
is a live, in-session arrangement only -- it isn't saved, and doesn't
affect what order tabs open in on a future launch (including
auto-login's own connect order, which follows the address book's
saved world order instead).

## Finding text

`Ctrl+F` or Edit -> Find... opens a find bar for the active tab's
scrollback -- type to search (live, case-insensitive by default; the
"Aa" checkbox makes it case-sensitive). Every match is highlighted;
Enter or the Next button jumps to the next one, Shift+Enter or the
Previous button jumps back, wrapping around at either end. Escape
closes the bar and clears the highlights. Each tab has its own
independent find bar, searching only that tab's own content.

## Tab activity

If text arrives on a tab you're *not* currently looking at, its label
blinks orange -- so you notice something happened on another world
while your attention was elsewhere. It keeps blinking indefinitely
(not just a few times) until you actually switch to that tab, at which
point it clears immediately. The tab you're currently viewing never
flashes for its own incoming text -- only tabs in the background do.

## System tray icon

If your OS supports one, MushTato shows a system tray icon -- always
shown, no separate setting to turn it off. Left-click (or double-
click) it to bring the main window to the front; right-click for a
small menu (Restore, Exit). It blinks the same way a background tab
does: whenever new text arrives on a tab you're not looking at, *or*
on any tab at all while the whole MushTato window itself isn't
focused (e.g. you've alt-tabbed away or minimized it) -- switching
tabs, or just bringing MushTato back into focus, clears it. The icon
itself is a simple placeholder (not final artwork) until real branding
exists.

## Clickable links

Any `http://` or `https://` URL appearing in a tab's scrollback
(including a spawned log window mirroring it) is shown underlined in a
distinct color and is clickable -- clicking one opens it in your
system's default web browser. This is purely a display-layer feature;
it doesn't change what the server actually sent or what triggers see.

## Detecting a dropped connection

MushTato keeps the underlying TCP connection's OS-level keepalive
turned on for every tab, always -- if the network genuinely goes away
(your own connection drops, a router loses power, etc.) without either
side sending a clean close, the OS itself notices within about 15-20
seconds and MushTato reports "[Connection lost]" in that tab's
scrollback and updates its status bar, the same as a clean server-side
disconnect always did. If a particular world also needs an
application-level nudge to stop an idle firewall/NAT from dropping it
in the first place, turn on that world's *Keepalive* option in World
Properties -> Connection (see the Address Book topic).

## Automatic reconnection

Once a tab's connection drops, that tab automatically retries
connecting again every 30 seconds, on its own, with no confirmation
prompt, and keeps retrying indefinitely until either a retry succeeds
or you click Disconnect (File menu, toolbar, or `/disconnect`) to give
up on it. Each retry is the exact same action as manually clicking
Reconnect. This runs independently per tab -- one tab retrying doesn't
affect any other tab's connection.

One exception: an SSH tab that fails to connect because of a login/
authentication problem (wrong username or password) does **not**
auto-reconnect -- retrying with the same bad credentials could never
succeed, unlike a genuine dropped network connection. Reconnect
manually (or `/ssh` again with the right password) once that's sorted.
See the SSH Connections topic.
"""


def _render_chrome(ctx: HelpContext) -> str:
    del ctx
    return """# Menus & Toolbar

The main window has a menu bar (File, Edit, View, Logging, Options,
Tools, Help) and a toolbar underneath it with the same actions as
buttons, plus a status bar at the bottom.

**Functional today:**
- **File** -- New Tab (opens a blank, unconnected tab; see the Sessions
  & Tabs and SSH Connections topics), Address Book..., Reconnect,
  Disconnect, Close (closes the active tab), Exit (quits MushTato).
- **Edit** -- Cut, Copy, Paste, Undo, Redo, Select All (all act on
  whichever widget currently has keyboard focus -- an input box, or
  the active tab's scrollback for Copy/Select All), and Find...
  (`Ctrl+F`, see the Sessions & Tabs topic).
- **View** -- Theme submenu (Dark/Light).
- **Logging** -- Spawn Log Window (opens a log-mirror window for the
  active tab).
- **Options** -- Settings... (hotkeys and theme).
- **Tools** -- Editor (opens a new Text Editor window; see below),
  Upload (send a file to the active tab, line by line; see below),
  Mail Window (compose/send mail for the active tab's world; see
  below), Error Log (unhandled-exception history; see below).
- **Help** -- Help (this window) and About. This Help window's own
  View menu also has Show Splash Screen, which re-displays the startup
  splash screen on demand.

**Not implemented yet -- shown disabled/grayed out on purpose, not
missing by accident:** the Tools menu's Events. Modeled on a real
feature from Potato that MushTato doesn't have a working equivalent
for yet. A grayed-out item means "planned, not yet built," not
"broken."

Reconnect, Disconnect, Close, Spawn Log Window, Upload, Mail Window,
and the Edit menu's six focus-dispatched actions plus Find are disabled
whenever there's no tab open at all, since there's nothing for them to
act on. Editor, Error Log, Address Book, Settings, Help, and About stay
available with zero tabs open, since none of them are tied to any one
connection.

## Text Editor

Tools -> Editor (or `Ctrl+Shift+E`, or `/editor`) opens a new,
independent Text Editor window -- unlike every other satellite window
in this app (Address Book, Help, Error Log), you can have as many Text
Editor windows open at once as you want; each is its own separate
document.

It's a plain-text editor for composing and saving macros, triggers, or
drafts -- File menu has New/Open/Save/Save As (prompting to save
unsaved changes before discarding them), and its own independent Edit
menu (Cut/Copy/Paste/Undo/Redo/Select All) and Find bar (`Ctrl+F`) --
separate from the main window's own versions of those, since a Text
Editor is its own top-level window. The status bar shows live word/
line/character counts and cursor position. View menu toggles line
numbers and word wrap. Font, line-number, and word-wrap preferences
are shared across newly-opened editor windows (set via Options ->
Settings..., or by toggling them in an open editor) but don't
retroactively change a *different* already-open editor window.

Files default to save under MushTato's own per-OS data directory (see
`INSTALL.md`'s "Removing your data" section for the exact path) --
Save/Save As remembers whatever directory you last used.

## Upload

Tools -> Upload (or `/upload`) sends a file from disk to the active
tab, one line at a time -- modeled closely on Potato's own real Upload
feature. Only **one** upload runs per tab at a time -- using the
action again while one's already running just brings its progress
window back to the front instead of starting a second.

Picking Upload opens an options + file-picker dialog:

- **Ignore empty lines?** (on by default) -- skips blank lines in the
  file rather than sending them as empty commands.
- **Add to History?** -- sent lines join the Command box's recall
  history, as if you'd typed them yourself.
- **MPP Formatted?** -- a MU*-specific line-continuation convention:
  lines starting with `>` join into a single send (with special
  characters escaped), a line starting with a space or tab is an
  unformatted continuation of the previous send, and lines starting
  with `@@` (or blank/whitespace-only lines) are treated as comments
  and skipped. Leave this off for an ordinary plain-text file of
  commands.
- **Delay (seconds)** -- how long to pace between each line actually
  sent (0 means as fast as possible) -- useful for a large file, to
  avoid flooding the server's command queue.
- **Prefix** -- a string prepended to every line sent (e.g. a command
  name before a batch of arguments).

Clicking Upload validates the file (selected, exists, readable) and
starts sending -- a progress window shows bytes processed of the
file's total, with Hide (dismiss the window without stopping the
upload) and Cancel (confirms first) buttons. Sends go straight to the
server, bypassing alias/slash-command processing entirely, the same
reasoning the Pose/says... box and auto-sends already use. Closing the
tab, or disconnecting, cancels any upload still running on it.

## Mail Window

Tools -> Mail Window (or `/mail`) opens a compose/send window for the
active tab's world -- modeled closely on Potato's own real Mail
Window. Unlike the Text Editor, only **one** Mail Window is open per
tab at a time -- using the action again while one's already open just
brings the existing one to the front instead of opening a second.

Fields: Recipient, CC, BCC, Subject, a Format dropdown, and (only when
Format is set to Custom) a Custom command template. Which of
Recipient/CC/BCC/Subject are actually enabled depends on the selected
format -- a format that doesn't reference a given field (e.g. MUSE
+mail has no Subject at all) grays that field out, since it wouldn't
be sent anyway. The six formats (MUSH @mail, MUX @mail, Multi-Command
+mail, MUSE +mail, Myrddin's BB, and Custom) match Potato's own real
built-in mail systems exactly.

"Convert returns?" (on by default) replaces line breaks in the message
body with the "Convert To:" text (`%r` by default) before sending --
necessary because the underlying command is a single line sent to the
server. File -> Escape Special Characters backslash-escapes softcode-
special characters in the body on demand (not automatic -- only when
you click it).

Format/Custom template/Convert Returns are saved per-world the moment
you click Send -- there's no separate settings page for these, matching
Potato's own real design; just open the Mail Window again to see (or
change) what's currently saved for a world.

Send goes straight to the server, bypassing alias/slash-command
processing entirely -- the same reasoning the Pose/says... box and
auto-sends already use. Cancel (or the window's close button) discards
without sending, and without any "unsaved changes?" prompt.

## Error Log

Tools -> Error Log shows a history of *unhandled* exceptions only --
genuine bugs that would otherwise have nowhere to go. It does **not**
duplicate errors this app already shows you directly (script/trigger
errors, connection failures, and similar all still appear in the
relevant tab's scrollback exactly as before). Search narrows the list;
Export saves whatever's currently listed (respecting an active search)
to a text file; Clear empties the in-memory list but never touches the
on-disk log file, which is written per-day under the same directory
spawnlogs default to. Updates live, even for an error from a
background connection thread.
"""


def _render_dual_input(ctx: HelpContext) -> str:
    del ctx
    return """# Dual Input

Each tab has two input boxes, both visible at once, both sending to
the same connection:

- **Command...** (the primary box) -- ordinary MUD commands. This is
  the only box that checks for built-in `/` client commands (see the
  Built-in Commands topic). A line starting with a single `/` is
  treated as a client command, not sent to the server; start a line
  with `//` if you actually need to send a literal `/` to the server
  (e.g. a server command that itself uses `/`).
- **Pose/says...** (the secondary box) -- longer free-form text (poses,
  says, anything conversational). This box **always bypasses command
  processing entirely** -- even a line starting with `/` is sent to the
  server exactly as typed. This is deliberate: a pose that happens to
  start with a word like "north" or a `/`-prefixed action must never be
  silently reinterpreted as a client command.

Both boxes keep their own independent recall history (Up/Down arrows
step through what *that* box has sent, not the other one's).

The boundary between the scrollback and the input boxes can be dragged
to resize how much space each gets. For a tab connected to a saved
world, MushTato remembers that world's last-dragged size and uses it
as the starting size the next time you open a tab for that same world
-- this session or a future launch. A tab with no saved world (a blank
tab, or a raw `/connect host port`) instead remembers one shared size
across every such tab. See the Fonts topic for changing the size/
typeface of the text in either area.
"""


def _render_spawn_windows(ctx: HelpContext) -> str:
    del ctx
    return """# Spawn Windows

A spawn window is a separate popup that live-mirrors a connection's
incoming text from the moment it's created onward -- it doesn't parse
or filter anything, it just mirrors.

**Opening one:** Logging menu -> Spawn Log Window, the toolbar button,
`Ctrl+L` by default, or typing `/spawnlog`.

A spawn window is bound to whichever tab was active when you opened
it, for as long as it stays open -- it keeps mirroring that one
connection even if you switch to a different tab afterward. To log a
different connection, switch to that connection's tab first, then open
a new spawn window from there.

**Saving to disk:** the "Save Spawnlog" button writes the window's full
text so far as plaintext, with a timestamp header, defaulting to a
`spawnlog_YYYYMMDD_HHMMSS.txt` filename in MushTato's own per-OS data
directory (see `INSTALL.md`'s "Removing your data" section for the
exact path) -- the save dialog lets you pick a different name or
location instead.
"""


def _render_hotkeys(ctx: HelpContext) -> str:
    lines = ["# Hotkeys", "", "Current bindings (Options -> Settings... to change any of these):", ""]
    for action, label in ACTION_LABELS.items():
        binding = ctx.hotkeys.get(action, "(unbound)")
        lines.append(f"- **{label}**: `{binding}`")
    lines.append("")
    lines.append(
        "Changing a hotkey in Settings takes effect immediately in the "
        "same running session -- you don't need to restart MushTato."
    )
    return "\n".join(lines)


def _render_themes(ctx: HelpContext) -> str:
    return f"""# Themes

MushTato has two themes: **Dark** (the default) and **Light**. Current
theme: **{ctx.theme}**.

**Changing it:** View menu -> Theme -> Dark/Light, Options ->
Settings..., or typing `/theme dark` / `/theme light` from any tab's
input line -- all three go through the exact same code path.

Switching theme applies immediately, including to already-open tabs'
scrollback panes, not just newly-opened ones.

The dark theme's scrollback and input colors match Potato's own real
shipped defaults (black background, dimmed output text, brighter input
text). The light theme has no equivalent in Potato (Potato's own
defaults are always black-background) -- it's MushTato's own design.
"""


def _render_fonts(ctx: HelpContext) -> str:
    del ctx
    return """# Fonts

Options -> Settings... has two independent font pickers:

- **Terminal Font** -- the scrollback/display pane where the MUD's own
  text appears. Only monospaced (fixed-width) fonts are offered here,
  since MUD output (ASCII-art borders, banners, tables) is authored
  assuming every character is the same width -- a proportional font
  would break that alignment.
- **Input Font** -- both input boxes (Command... and Pose/says...)
  share this one setting; any installed font can be used here, since
  the input boxes don't have the terminal's alignment requirement.

Changing either font applies immediately to every already-open tab,
the same live-reload treatment Theme already gets -- you don't need to
reconnect or restart. Both are saved and restored on your next launch.
"""


def _render_commands(ctx: HelpContext) -> str:
    del ctx
    lines = [
        "# Built-in Commands",
        "",
        "Typed into the **Command...** box (the primary input, never the "
        "Pose/says... box -- see Dual Input).",
        "",
        "**The `/` and `//` convention** (matches TinyFugue's own real "
        "rule): a line with no leading `/` is sent to the server as-is. "
        "A line starting with exactly one `/` is a client command -- the "
        "slash is stripped and the rest is treated as `name args`. A line "
        "starting with `//` is the escape hatch: one slash is stripped and "
        "the remainder (still starting with `/`) is sent to the server "
        "literally -- use this if you need to send a server command that "
        "itself begins with `/`.",
        "",
        "Command names are matched exactly (case-insensitive) -- no "
        "abbreviations. An unrecognized `/word` is reported as an error, "
        "never silently sent to the server.",
        "",
        "**Full command list:**",
        "",
    ]
    for name, help_text in COMMAND_HELP:
        lines.append(f"- `/{name}` -- {help_text}")
    lines.append("")
    lines.append(
        "`/help topics` lists every Help topic slug; `/help [topic]` "
        "prints that topic's content; `/help [command]` prints that "
        "command's one-line description."
    )
    return "\n".join(lines)


def _render_scripting(ctx: HelpContext) -> str:
    del ctx
    return """# Scripting

MushTato has full Python scripting -- triggers, gags, highlights,
aliases, timers, and persistent per-world variables, running against a
sandboxed scripting API. Every tab gets its own independent runtime, so
two tabs connected to the same world (e.g. a main character and an alt
at once) never share triggers, aliases, or variables with each other.

**Where scripts live:** World Properties' Scripts page (Address Book ->
select a world -> Properties... -> Scripts). Each saved script has a
name, an Enabled checkbox, and a source-code box. Add/Edit/Delete/Save/
Cancel works the same way the Characters page already does. Saving
takes effect immediately on any tab currently open for that world --
you don't need to reconnect.

## The scripting API

Ten functions, available to every script:

- `send(text)` -- send a line to the server, as if typed.
- `echo(text, style=None)` -- print a line locally only, never sent to
  the server. `style` is an optional `Style(...)` (see below).
- `gag()` -- suppress the line currently being matched by a trigger
  from ever appearing in the scrollback. Only valid inside a trigger
  callback.
- `highlight(style, span=None)` -- restyle (part of) the line currently
  being matched. `span` defaults to the whole match. Only valid inside
  a trigger callback.
- `set_var(name, value)` / `get_var(name, default=None)` -- persistent,
  per-world variables (must be JSON-serializable). Saved automatically
  a few minutes after you last changed one, and again whenever you
  disconnect -- you don't need to save manually.
- `timer(delay_seconds, callback)` -- run `callback` once, after a
  delay.
- `on_trigger(pattern, callback, *, gag=False, highlight_style=None,
  priority=0, name=None)` -- run `callback` whenever incoming text
  matches `pattern` (a regular expression). `gag`/`highlight_style` are
  a shorthand for calling `gag()`/`highlight()` unconditionally instead
  of from inside the callback.
- `on_alias(pattern, callback, *, priority=0, name=None)` -- run
  `callback` instead of sending a typed line verbatim, when it exactly
  matches `pattern`. Only the primary Command... box checks aliases --
  Pose/says... always bypasses them, same as it bypasses `/` commands.
- `on_connect(callback)` -- run `callback` once, each time this tab
  connects.
- `Style(...)` -- the class `highlight()`/`echo()` take, e.g.
  `Style(fg=(255, 0, 0), bold=True)`.

A concrete example -- highlighting speaker names in a different color
(trigger patterns compile against RE2, not Python's own `re` -- no
lookaround or backreferences, but linear-time matching guaranteed; a
plain `^\\w+` already matches just the leading word here, no lookahead
needed):

```
def handle(match):
    highlight(Style(fg=(255, 200, 0)))
on_trigger(r'^\\w+', handle, name='speaker-highlight')
```

## Sandboxing

Scripts run under a restricted Python interpreter -- no `import`,
`open`, `exec`/`eval`, or file/network access beyond the API above.
This is always on; there is no way to disable it from the app. A
script that runs too long is stopped with a timeout error (a genuine
infinite loop is a known, documented limitation -- see
TROUBLESHOOTING.md).

## Errors don't crash your session

If a script fails to load, or a trigger/alias/timer/on_connect callback
raises an error, you'll see a line like:

```
[Script error in trigger 'speaker-highlight': ValueError: ...]
```

printed to that tab's scrollback -- the tab keeps working normally,
and nothing else in the script is affected. A trigger that keeps
failing on **5 consecutive lines** is automatically disabled (to stop
flooding the scrollback with the same error and wasting time on
something guaranteed to keep failing), with a line explaining why:

```
[Trigger 'speaker-highlight' disabled after 5 consecutive errors - fix and re-save to re-enable]
```

The Scripts page also shows a visible marker on any script with a
currently-disabled trigger. Fixing the bug and clicking Save (even
without changing anything else) resets it.

## A known, deliberate limitation

An incomplete line -- most often an interactive prompt with no
trailing newline yet, like `HP: 100 >` -- is still shown right away for
a responsive feel, but triggers never match against it until it's
actually a complete line. Real TinyFugue has a more elaborate mechanism
for eventually treating a long-unfinished line as a prompt; MushTato
doesn't replicate that (see SPEC.md section 8).
"""


def _render_ssh(ctx: HelpContext) -> str:
    del ctx
    return """# SSH Connections

Alongside MU*/MUSH connections (Telnet), MushTato can open a real SSH
session -- a genuine login shell on a remote Unix-like machine, not a
MUD connection. This is a different protocol from everything else in
this app: it's encrypted, it authenticates you to the remote machine
itself, and once connected you're typing real shell commands, not MU*
commands.

## Connecting

Two ways, both available:

- **Type it**: File -> New Tab (or `Ctrl+T`) opens a blank tab, then
  type `/ssh [-p port] user@host` into it -- for example
  `/ssh -p 505 rickn0njy@silvren.com`. Port defaults to 22 (the
  standard SSH port) if you leave off `-p`.
- **Save it**: in the Address Book, set a saved world's Protocol to
  SSH (World Properties or the quick Add/Edit dialog) and fill in the
  SSH Username field, then Connect as usual.

Either way, you're prompted for the password every time you connect --
**it is never saved to disk**, unlike a MU* Character's password. This
is a deliberate choice: a real shell account's password is a higher-
stakes secret than a game character's.

Only password authentication is supported currently (no private-key
files yet).

## What actually works

Typed input is sent line-by-line (type a command, press Enter, it's
sent) -- exactly like MU* commands. This means ordinary commands
(`ls`, `cat somefile`, a one-off admin script) work fine. It does
**not** yet behave like a full interactive terminal: tab-completion,
Ctrl+C to interrupt, and full-screen programs (`vim`, `top`, `less`)
won't work correctly, since those need every keystroke sent immediately
rather than a whole line at a time. This is a known, accepted limit of
the current implementation, not a bug -- revisit if it turns out to
matter enough in practice.

A real shell also sends two kinds of escape sequence a MU* server
never does -- bracketed-paste-mode toggling and window-title-setting
-- both are recognized and silently discarded rather than shown as
garbled text (fixed after Rick found them leaking through in real
testing). Sequences a full terminal emulator would need to actually
*act on* (cursor movement, screen redraws -- what the programs listed
above rely on) are still just dropped, not implemented; only these two
specific, harmless-to-ignore kinds get this treatment.

## Host key verification (trust-on-first-use)

The first time you connect to a given host:port, MushTato remembers
the server's host key. Every later connection to that same host:port
checks the key still matches -- if a server's key ever changes, the
connection is **refused**, not silently allowed, exactly like a real
`ssh` client's own "REMOTE HOST IDENTIFICATION HAS CHANGED" warning.
The rejection message tells you the old and new key fingerprints and
names the exact command to run if the change is actually expected
(e.g. the server was reinstalled):

```
/ssh-forget host:port
```

This forgets the saved key for that one host:port so the *next*
connection attempt is treated as first-use again (trusting whatever
key the server offers, and saving it). If you connected on the default
port 22, `/ssh-forget host` alone works too.

Saved host keys live in their own file, separate from anything on your
real system: `ssh_known_hosts.json` in the same per-OS MushTato data
directory as your address book and settings (see `INSTALL.md`'s
"Removing your data" section for the exact path). MushTato never
reads or writes your actual `~/.ssh/known_hosts`. You can also delete
that JSON file directly (or a single entry inside it) if you'd rather
edit it by hand than use `/ssh-forget`.

## What auto-sends/Character login don't do here

A saved world's Auto-Sends and Character/login settings are MU*-
specific (raw softcode "connect name password"-style lines) --
they're skipped entirely for an SSH-protocol world, since sending them
into a real shell prompt would be meaningless. `/mail` and `/upload`
still work the same way they do on a Telnet tab (sending file/mail
content is protocol-agnostic).
"""


def _render_faq(ctx: HelpContext) -> str:
    del ctx
    return """# FAQ / Troubleshooting

The full version of this section lives in `TROUBLESHOOTING.md` (next to
the app, or in the source repo) -- this is the same content.

**"Connection failed" / "Connection refused"** -- check the host and
port for typos (most MU*s use a non-standard port); the server may be
down; a firewall or VPN may be blocking that port.

**Connection hangs and never says Connected or failed** -- usually a
firewall silently dropping the connection attempt itself (before a TCP
connection is even established, so keepalive doesn't help here). Try
`/reconnect` or File -> Reconnect once you suspect this.

**A tab went quiet and I never saw "[Connection lost]"** -- MushTato
relies on the operating system's TCP keepalive to notice a silently-
dead connection (no clean close from either side), which normally
takes 15-20 seconds; a very restrictive firewall/NAT can still swallow
those keepalive probes on some networks. Turning on that world's
Keepalive option (World Properties -> Connection) sends an
application-level nudge too, which can help in that case. Once a drop
is detected, MushTato retries reconnecting automatically every 30
seconds -- see the Sessions & Tabs topic.

**Can't resolve the hostname** -- check for typos, or try a numeric IP
if the world's listing provides one.

**Windows SmartScreen / macOS Gatekeeper warnings on first launch** --
expected: MushTato isn't signed with a paid code-signing certificate.
See `INSTALL.md` for the exact click-through steps for your OS.

**Linux: "could not load the Qt platform plugin xcb"** -- the packaged
build already bundles the libraries it needs; on an unusually minimal
system, install `libxcb-cursor0` and its usual companions yourself (see
`INSTALL.md` for the exact package list).

**A toolbar/menu item does nothing when clicked** -- Events is shown
disabled on purpose; see the Menus & Toolbar topic.

**I checked "auto-login" on a world but nothing happens at startup** --
auto-login also needs that world to have a default Character set (a
checked box with no default Character is inert); see the Address Book
topic.

**Where are my saved worlds/settings stored?** -- see `INSTALL.md`'s
"Removing your data" section for the exact per-OS path.

**An SSH connection says the host key doesn't match / has changed** --
this is intentional, not a bug: MushTato refuses to silently trust a
different key than the one it saw on your first connection to that
host:port. If you're sure the change is expected (server reinstalled,
etc.), run `/ssh-forget host:port` then reconnect. See the SSH
Connections topic.
"""


TOPICS: List[HelpTopic] = [
    HelpTopic("about", "About MushTato", _render_about),
    HelpTopic("address-book", "Address Book", _render_address_book),
    HelpTopic("tabs", "Sessions & Tabs", _render_tabs),
    HelpTopic("ssh-connections", "SSH Connections", _render_ssh),
    HelpTopic("chrome", "Menus & Toolbar", _render_chrome),
    HelpTopic("dual-input", "Dual Input", _render_dual_input),
    HelpTopic("spawn-windows", "Spawn Windows", _render_spawn_windows),
    HelpTopic("hotkeys", "Hotkeys", _render_hotkeys),
    HelpTopic("themes", "Themes", _render_themes),
    HelpTopic("fonts", "Fonts", _render_fonts),
    HelpTopic("commands", "Built-in Commands", _render_commands),
    HelpTopic("faq", "FAQ / Troubleshooting", _render_faq),
    HelpTopic("scripting", "Scripting", _render_scripting),
]

_TOPICS_BY_SLUG: Dict[str, HelpTopic] = {topic.slug: topic for topic in TOPICS}


def get_topic(slug: str) -> "HelpTopic | None":
    return _TOPICS_BY_SLUG.get(slug.lower())
