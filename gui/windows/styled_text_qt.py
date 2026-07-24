"""Render engine.ansi StyledSegments into a Qt QTextEdit/QTextBrowser.

Kept separate from MainWindow so this conversion -- the one piece of
Phase 5 that's meaningfully testable headless -- doesn't require a
live window or event loop to verify. engine/ansi does all the actual
ANSI parsing; this module only maps its toolkit-agnostic Style output
onto Qt's QTextCharFormat, exactly as CLAUDE.md rule 2 requires (the
engine never imports Qt; this is the GUI-side consumer of its output).

Post-Phase-9 addition: clickable URLs. Deliberately a GUI-only, always-
on rendering concern, not a scripting-API feature -- engine.ansi.Style
has no concept of a hyperlink target (it's fg/bg/bold/italic/underline/
blink/reverse/strikethrough, matching real ANSI SGR attributes only),
and requiring every user to write a trigger script just to get clickable
links in their scrollback would be a poor default. URL detection and
QTextCharFormat anchor-setting both happen entirely in this module,
after a line's gag/highlight processing is already done (see
gui/windows/session_tab.py's rendering pipeline) -- engine/scripting
never knows a URL was even present.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from engine.ansi import Style, StyledSegment

# http(s) only -- bare "www." domains are deliberately not matched (no
# reliable way to tell "www.example.com" the domain from "www. Example
# missed a period" the sentence without real false-positive risk).
# Trailing sentence punctuation is trimmed off the match rather than
# taught to the regex, since "()." vs ")." vs "." context-dependent
# trimming is simpler as a post-processing step than as part of the
# pattern itself.
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_TRAILING_PUNCTUATION = ".,;:!?)"

# A single fixed color for both themes (not theme-aware) -- same
# simplification gui/windows/main_window.py's ACTIVITY_COLOR already
# makes for tab-bar chrome, extended here to scrollback content for the
# same reason: threading theme info through every rendering call site
# is more scope than a first pass needs. Chosen to read reasonably
# against both a black and a white background; revisit if it reads
# poorly on one in practice, same as ACTIVITY_COLOR's own note.
LINK_COLOR = QColor(90, 170, 255)


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


def _split_for_urls(text: str) -> List[Tuple[str, Optional[str]]]:
    """Split ``text`` into ``(chunk, url_or_None)`` pieces -- ``url``
    is set (to the chunk's own text) for a piece that's itself a
    clickable URL.
    """
    pieces: List[Tuple[str, Optional[str]]] = []
    pos = 0
    for match in _URL_RE.finditer(text):
        if match.start() > pos:
            pieces.append((text[pos : match.start()], None))
        url = match.group(0)
        trimmed = url.rstrip(_TRAILING_PUNCTUATION)
        trailing = url[len(trimmed) :]
        if trimmed:
            pieces.append((trimmed, trimmed))
        if trailing:
            pieces.append((trailing, None))
        pos = match.end()
    if pos < len(text):
        pieces.append((text[pos:], None))
    return pieces or [(text, None)]


def _insert_segments(cursor: QTextCursor, segments: Iterable[StyledSegment]) -> None:
    for text, style in segments:
        base_format = style_to_qt_format(style)
        for chunk, url in _split_for_urls(text.replace("\r", "")):
            if url is None:
                cursor.insertText(chunk, base_format)
                continue
            link_format = QTextCharFormat(base_format)
            link_format.setAnchor(True)
            link_format.setAnchorHref(url)
            link_format.setForeground(LINK_COLOR)
            link_format.setFontUnderline(True)
            cursor.insertText(chunk, link_format)


def append_styled_segments(text_edit: QTextEdit, segments: Iterable[StyledSegment]) -> None:
    """Append parsed segments to ``text_edit``'s scrollback, styled.

    Strips ``\\r`` at the display layer only -- engine/ansi's own
    output is untouched; a bare carriage return has no useful rendering
    in a QTextEdit and would otherwise show as a stray character. A URL
    within the text is rendered as a clickable hyperlink (see this
    module's docstring) -- ``text_edit`` needs to be a ``QTextBrowser``
    (or have equivalent anchor-click handling) for that to actually be
    clickable, not just colored; a plain ``QTextEdit`` still renders the
    link's distinct styling correctly, it just won't respond to clicks.
    """
    cursor = QTextCursor(text_edit.document())
    cursor.movePosition(QTextCursor.End)
    _insert_segments(cursor, segments)
    text_edit.setTextCursor(cursor)
    text_edit.ensureCursorVisible()


def replace_tail(text_edit: QTextEdit, start_position: int, segments: Iterable[StyledSegment]) -> None:
    """Erase everything in ``text_edit`` from ``start_position`` to the
    end of the document, then insert ``segments`` in its place.

    Used by Phase 9's LineDispatcher-driven rendering to replace a
    previously-shown "preview" of a still-incomplete line with its
    updated content (or with the finalized, trigger/gag/highlight-
    resolved version once the line completes) without needing to
    re-render anything before ``start_position``. Passing an empty
    ``segments`` just erases the tail (used to clear a preview that
    turned out to belong to a gagged line).
    """
    cursor = QTextCursor(text_edit.document())
    cursor.setPosition(start_position)
    cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
    cursor.removeSelectedText()
    _insert_segments(cursor, segments)
    text_edit.setTextCursor(cursor)
    text_edit.ensureCursorVisible()
