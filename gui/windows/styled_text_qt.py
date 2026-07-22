"""Render engine.ansi StyledSegments into a Qt QTextEdit.

Kept separate from MainWindow so this conversion -- the one piece of
Phase 5 that's meaningfully testable headless -- doesn't require a
live window or event loop to verify. engine/ansi does all the actual
ANSI parsing; this module only maps its toolkit-agnostic Style output
onto Qt's QTextCharFormat, exactly as CLAUDE.md rule 2 requires (the
engine never imports Qt; this is the GUI-side consumer of its output).
"""

from __future__ import annotations

from typing import Iterable

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from engine.ansi import Style, StyledSegment


def style_to_qt_format(style: Style) -> QTextCharFormat:
    """Convert one Style into an equivalent QTextCharFormat.

    ``reverse`` is honored by swapping the resolved fg/bg before
    applying them. ``blink`` has no Qt text-character equivalent (it
    would need a timer-driven repaint, out of scope here) and is
    silently not rendered -- everything else in Style maps directly.
    """
    fmt = QTextCharFormat()
    fg, bg = style.fg, style.bg
    if style.reverse:
        fg, bg = bg, fg
    if fg is not None:
        fmt.setForeground(QColor(*fg))
    if bg is not None:
        fmt.setBackground(QColor(*bg))
    if style.bold:
        fmt.setFontWeight(QFont.Bold)
    if style.italic:
        fmt.setFontItalic(True)
    if style.underline:
        fmt.setFontUnderline(True)
    if style.strikethrough:
        fmt.setFontStrikeOut(True)
    return fmt


def append_styled_segments(text_edit: QTextEdit, segments: Iterable[StyledSegment]) -> None:
    """Append parsed segments to ``text_edit``'s scrollback, styled.

    Strips ``\\r`` at the display layer only -- engine/ansi's own
    output is untouched; a bare carriage return has no useful rendering
    in a QTextEdit and would otherwise show as a stray character.
    """
    cursor = QTextCursor(text_edit.document())
    cursor.movePosition(QTextCursor.End)
    for text, style in segments:
        cursor.insertText(text.replace("\r", ""), style_to_qt_format(style))
    text_edit.setTextCursor(cursor)
    text_edit.ensureCursorVisible()
