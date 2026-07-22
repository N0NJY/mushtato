"""Reconstruct terminal-displayable ANSI escapes from StyledSegments.

This is the inverse of :class:`~engine.ansi.parser.AnsiParser`: given
parsed styled segments, produce a string a real terminal can display
with equivalent colors/attributes. Used by the dev console client
(``scripts/console_client.py``); a GUI renderer wouldn't need this and
would instead read ``Style`` fields directly.
"""

from __future__ import annotations

from typing import Iterable, List

from .style import Style, StyledSegment

RESET = "\x1b[0m"


def _sgr_for(style: Style) -> str:
    codes: List[str] = []
    if style.bold:
        codes.append("1")
    if style.italic:
        codes.append("3")
    if style.underline:
        codes.append("4")
    if style.blink:
        codes.append("5")
    if style.reverse:
        codes.append("7")
    if style.strikethrough:
        codes.append("9")
    if style.fg is not None:
        codes += ["38", "2", *map(str, style.fg)]
    if style.bg is not None:
        codes += ["48", "2", *map(str, style.bg)]
    return f"\x1b[{';'.join(codes)}m" if codes else ""


def styled_text_to_ansi(segments: Iterable[StyledSegment]) -> str:
    """Render segments back to a string with ANSI truecolor escapes."""
    out = []
    for text, style in segments:
        out.append(RESET + _sgr_for(style) + text)
    out.append(RESET)
    return "".join(out)
