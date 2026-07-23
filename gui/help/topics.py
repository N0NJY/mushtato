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
    ("connect", "Connect to a saved world by name: /connect [name]"),
    ("settings", "Open the settings dialog"),
    ("version", "Show the MushTato version"),
    ("theme", "Switch theme: /theme [dark|light]"),
    ("disconnect", "Disconnect from the server"),
    ("reconnect", "Reconnect to the server"),
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

Full Python scripting (triggers, macros, gags, highlights) is planned
but **not wired into the GUI yet** -- see the Scripting topic.
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

Properties... opens a separate window with five sections (a category
list on the left, that section's fields on the right):

- **Basic** -- world name, host, port, and which saved Character (if
  any) connects automatically by default.
- **Characters** -- a world can have multiple saved Characters, each
  just a name and password. Two different worlds can each have a
  Character with the same name and a different password -- Characters
  are scoped to their own world's list, never shared globally. Add/
  Edit/Delete a Character, then Save or Cancel that one change.
- **Connection** -- the *Login Format* (e.g. `connect {name}
  {password}`, sent with the default Character's name/password
  substituted in) and *Login Delay* (how long to wait after connecting
  before sending it, giving the server time to show its own banner
  first) are real and functional. The rest of this section (SSL, a 2nd
  address/port, proxy, and several Telnet-specific options) mirrors
  real settings from Potato but is shown **disabled** -- MushTato's
  connection engine doesn't support them yet. Visible on purpose, so
  it's clear what's planned versus what's broken.
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
"""


def _render_chrome(ctx: HelpContext) -> str:
    del ctx
    return """# Menus & Toolbar

The main window has a menu bar (File, Edit, View, Logging, Options,
Tools, Help) and a toolbar underneath it with the same actions as
buttons, plus a status bar at the bottom.

**Functional today:**
- **File** -- Address Book..., Reconnect, Disconnect, Close (closes
  the active tab), Exit (quits MushTato).
- **Edit** -- Copy (copies the active tab's selected scrollback text).
- **View** -- Theme submenu (Dark/Light).
- **Logging** -- Spawn Log Window (opens a log-mirror window for the
  active tab).
- **Options** -- Settings... (hotkeys and theme).
- **Help** -- Help (this window) and About.

**Not implemented yet -- shown disabled/grayed out on purpose, not
missing by accident:** Edit -> Find..., and the Tools menu's Editor,
Upload, and Mail Window. These are modeled on real features from
Potato that MushTato doesn't have working equivalents for yet. A
grayed-out item means "planned, not yet built," not "broken."

Reconnect, Disconnect, Close, Spawn Log Window, and Copy are disabled
whenever there's no tab open at all, since there's nothing for them to
act on.
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
to resize how much space each gets.
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
    return """# Scripting (Not Yet Available)

MushTato's design includes full Python scripting -- triggers, macros,
gags, highlights, and more, running against a sandboxed scripting API
(`send`, `echo`, `gag`, `highlight`, `set_var`, `get_var`, `timer`,
`on_trigger`, `on_connect`, `on_alias`). That engine layer exists and
is tested, but **it is not wired into the GUI yet** -- there is
currently no way to attach a script to a connection from the app
itself. This is a deliberate, tracked deferral, not a missing feature
that was forgotten.
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
firewall silently dropping the connection. Try `/reconnect` or File ->
Reconnect once you suspect this.

**Can't resolve the hostname** -- check for typos, or try a numeric IP
if the world's listing provides one.

**Windows SmartScreen / macOS Gatekeeper warnings on first launch** --
expected: MushTato isn't signed with a paid code-signing certificate.
See `INSTALL.md` for the exact click-through steps for your OS.

**Linux: "could not load the Qt platform plugin xcb"** -- the packaged
build already bundles the libraries it needs; on an unusually minimal
system, install `libxcb-cursor0` and its usual companions yourself (see
`INSTALL.md` for the exact package list).

**A toolbar/menu item does nothing when clicked** -- some items (Editor,
Upload, Mail Window, Find) are shown disabled on purpose; see the Menus
& Toolbar topic.

**Where are my saved worlds/settings stored?** -- see `INSTALL.md`'s
"Removing your data" section for the exact per-OS path.
"""


TOPICS: List[HelpTopic] = [
    HelpTopic("about", "About MushTato", _render_about),
    HelpTopic("address-book", "Address Book", _render_address_book),
    HelpTopic("tabs", "Sessions & Tabs", _render_tabs),
    HelpTopic("chrome", "Menus & Toolbar", _render_chrome),
    HelpTopic("dual-input", "Dual Input", _render_dual_input),
    HelpTopic("spawn-windows", "Spawn Windows", _render_spawn_windows),
    HelpTopic("hotkeys", "Hotkeys", _render_hotkeys),
    HelpTopic("themes", "Themes", _render_themes),
    HelpTopic("commands", "Built-in Commands", _render_commands),
    HelpTopic("faq", "FAQ / Troubleshooting", _render_faq),
    HelpTopic("scripting", "Scripting", _render_scripting),
]

_TOPICS_BY_SLUG: Dict[str, HelpTopic] = {topic.slug: topic for topic in TOPICS}


def get_topic(slug: str) -> "HelpTopic | None":
    return _TOPICS_BY_SLUG.get(slug.lower())
