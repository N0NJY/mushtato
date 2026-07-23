# Credits

MushTato exists because of two real, older projects it draws on for
design — not code, but the ideas and conventions that shaped it. Neither
project is affiliated with MushTato; this is simply an acknowledgment of
where its design lineage comes from.

## Potato

MushTato's GUI conventions — the address book, tabbed/multi-window
sessions, dual input boxes, spawn windows, configurable hotkeys, and
overall menu/toolbar layout — are modeled on **Potato**, a Tcl/Tk MUSH
client.

Potato is Copyright (c) 2009 Mike Griffiths, licensed under the MIT
License.

## TinyFugue

MushTato's built-in client command system — the `/` command prefix and
`//` literal-text escape convention, and the general idea of a real,
documented set of client-side commands — follows the real, actual
conventions of **TinyFugue**, a classic Unix MUD client.

TinyFugue is Copyright (c) 1993–2007 Ken Keys, licensed under the GNU
General Public License. <http://tinyfugue.sourceforge.net/>

## A note on how these were used

Per this project's own development guidelines, both Potato's and
TinyFugue's source code were used strictly as *reference material* to
clarify exact behavior when this project's own design was ambiguous —
never as code copied or transliterated into MushTato. MushTato is an
independent implementation in Python, sharing design lineage and
conventions with both projects, not code.

## Built with

MushTato itself is built with [PySide6](https://doc.qt.io/qtforpython/)
(Qt for Python), [RestrictedPython](https://restrictedpython.readthedocs.io/),
[google-re2](https://github.com/google/re2), and
[platformdirs](https://github.com/tox-dev/platformdirs) — see
`pyproject.toml` for the full dependency list.
