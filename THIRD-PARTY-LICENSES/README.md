# Third-Party Licenses

MushTato's own code is MIT-licensed (see `LICENSE` at the repo root).
This folder holds the license text for third-party components MushTato
bundles in its packaged builds, whose own licenses require the text to
be distributed alongside the software.

## Qt (via PySide6)

MushTato is built with [PySide6](https://doc.qt.io/qtforpython/) (Qt
for Python), used under the **GNU Lesser General Public License,
version 3 (LGPLv3)** — specifically the Qt Core, Qt Gui, Qt Widgets,
Qt Network, and Qt D-Bus modules, each confirmed on Qt's own
documentation as LGPLv3-available (Qt is dual-licensed; LGPLv3 is the
option used here, not GPL or a commercial license).

- `Qt-LGPL-3.0.txt` — the LGPLv3 license text.
- `Qt-GPL-3.0.txt` — the GPLv3 text that LGPLv3 incorporates by
  reference (the FSF distributes LGPLv3 as a short set of additional
  permissions layered on top of GPLv3, not as a fully independent
  document — both files together are the complete LGPLv3 terms,
  matching how the FSF's own template projects bundle it).

Practical notes on how MushTato meets LGPLv3's requirements:

- **Dynamically linked, not statically compiled in.** MushTato's
  packaged build (`packaging/mushtato.spec`, `--onedir`) ships Qt as
  separate shared library files (`.so`/`.dll`/`.dylib`) alongside the
  `MushTato` executable, not linked into a single static binary. This
  is what LGPLv3 requires to keep MushTato's own code independently
  licensed (MIT) rather than falling under LGPL itself.
- **Qt's own complete source code** is publicly available directly
  from The Qt Company / the Qt Project — see
  <https://download.qt.io/> or <https://code.qt.io/> for the exact
  version bundled (check `pyproject.toml`'s `PySide6` dependency pin
  for the version). MushTato doesn't re-host Qt's source itself, since
  it's already freely available from its own upstream.
- **You may replace the bundled Qt libraries** with your own compatible
  build — they're separate files in the installed `MushTato` folder,
  not compiled into the executable.

Qt Virtual Keyboard is explicitly **not** bundled (see
`packaging/mushtato.spec`'s exclusion list, originally trimmed for
download size) — worth noting here too, since that module is
GPLv3-only with no LGPL option, unlike every module MushTato actually
uses.

## Other dependencies

MushTato's other direct dependencies are all permissively licensed and
don't require bundled license text: RestrictedPython (Zope Public
License 2.1), google-re2 (BSD), platformdirs (MIT), asyncssh
(EPL-2.0/GPL-2.0, dual — used here as an unmodified library dependency
under EPL-2.0). See `pyproject.toml` for the full dependency list and
`CREDITS.md` for design-lineage acknowledgments (Potato, TinyFugue).

This is a good-faith technical summary, not legal advice — if you need
certainty about license compliance for your own use of MushTato, have
a lawyer review it.
