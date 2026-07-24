"""Font resolution for the scrollback/terminal pane and the dual input
boxes -- a small, focused, testable helper, same reasoning as
gui/theme.py's own split from the windows that use it.

engine/storage/settings.py stores an empty family string / a 0 size as
"no override" sentinels (it can't compute a real default itself --
that needs QFontDatabase, i.e. PySide6, which /engine never imports).
Resolving those sentinels into a real QFont is this module's one job.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


def default_scrollback_font() -> QFont:
    """MUD output (banners, tables, ASCII-art borders) is authored
    assuming a fixed-width terminal -- this has been the scrollback's
    default since Phase 5, unchanged here.
    """
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


def resolve_scrollback_font(family: str, size: int) -> QFont:
    font = QFont(family) if family else default_scrollback_font()
    if size > 0:
        font.setPointSize(size)
    return font


def resolve_input_font(family: str, size: int) -> QFont:
    # No fixed-width requirement here -- the input boxes are for typing,
    # not for aligning server-sent content, so an unset family just
    # falls back to Qt's own default widget font.
    font = QFont(family) if family else QFont()
    if size > 0:
        font.setPointSize(size)
    return font
