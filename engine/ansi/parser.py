"""ANSI/xterm-256 SGR (color/style) parser.

Turns raw text containing ANSI escape sequences into a list of
:class:`StyledSegment` objects -- (text, Style) pairs -- with no
dependency on any GUI toolkit. Only SGR sequences (``ESC [ ... m``,
which carry color and text attributes) affect the returned style;
other CSI sequences (cursor movement, screen clearing, etc.) are
recognized and dropped rather than rendered as literal text, since
this is a color/style extractor, not a full terminal emulator.

The parser is stateful across calls to :meth:`AnsiParser.feed`, for two
reasons: an escape sequence can be split across two reads from the
network, and SGR state (e.g. "bold is on") persists across writes just
like it does in a real terminal, until it's explicitly changed.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import List, Optional, Tuple

from .palette import basic_color, xterm_256_to_rgb
from .style import DEFAULT_STYLE, RGB, Style, StyledSegment

ESC = "\x1b"

# A complete CSI sequence: ESC [ params... final-byte.
_CSI_RE = re.compile(r"\x1b\[([0-9;]*)([@-~])")

# An escape sequence that's well-formed *so far* but cut off by the end
# of the currently available data -- i.e. still waiting on its final
# byte from the next network read.
_PARTIAL_RE = re.compile(r"\x1b(\[[0-9;]*)?\Z")


class AnsiParser:
    """Incremental parser: feed it text chunks, get StyledSegments back."""

    def __init__(self) -> None:
        self._style = DEFAULT_STYLE
        self._pending = ""  # buffered partial escape sequence

    def feed(self, text: str) -> List[StyledSegment]:
        """Parse another chunk of text, returning newly completed segments.

        Any trailing partial escape sequence is buffered internally and
        completed on the next call.
        """
        data = self._pending + text
        self._pending = ""

        segments: List[StyledSegment] = []
        pos = 0
        text_start = 0

        while True:
            esc = data.find(ESC, pos)
            if esc == -1:
                if text_start < len(data):
                    segments.append(StyledSegment(data[text_start:], self._style))
                return segments

            if _PARTIAL_RE.match(data, esc):
                if text_start < esc:
                    segments.append(StyledSegment(data[text_start:esc], self._style))
                self._pending = data[esc:]
                return segments

            match = _CSI_RE.match(data, esc)
            if match is None:
                # An escape we don't understand (or malformed input).
                # Drop just the ESC byte and keep scanning -- never get
                # stuck on it.
                if text_start < esc:
                    segments.append(StyledSegment(data[text_start:esc], self._style))
                pos = esc + 1
                text_start = pos
                continue

            if text_start < esc:
                segments.append(StyledSegment(data[text_start:esc], self._style))

            if match.group(2) == "m":
                self._apply_sgr(match.group(1))
            # Any other CSI final byte (cursor movement, clear screen,
            # etc.) is consumed and dropped, not rendered as text.

            pos = match.end()
            text_start = pos

    def _apply_sgr(self, params: str) -> None:
        codes = [int(p) if p else 0 for p in params.split(";")] if params else [0]
        style = self._style
        i = 0
        while i < len(codes):
            code = codes[i]
            if code == 0:
                style = DEFAULT_STYLE
            elif code == 1:
                style = replace(style, bold=True)
            elif code == 3:
                style = replace(style, italic=True)
            elif code == 4:
                style = replace(style, underline=True)
            elif code == 5:
                style = replace(style, blink=True)
            elif code == 7:
                style = replace(style, reverse=True)
            elif code == 9:
                style = replace(style, strikethrough=True)
            elif code == 22:
                style = replace(style, bold=False)
            elif code == 23:
                style = replace(style, italic=False)
            elif code == 24:
                style = replace(style, underline=False)
            elif code == 25:
                style = replace(style, blink=False)
            elif code == 27:
                style = replace(style, reverse=False)
            elif code == 29:
                style = replace(style, strikethrough=False)
            elif 30 <= code <= 37:
                style = replace(style, fg=basic_color(code - 30))
            elif code == 38:
                rgb, consumed = self._extended_color(codes, i)
                style = replace(style, fg=rgb)
                i += consumed
            elif code == 39:
                style = replace(style, fg=None)
            elif 40 <= code <= 47:
                style = replace(style, bg=basic_color(code - 40))
            elif code == 48:
                rgb, consumed = self._extended_color(codes, i)
                style = replace(style, bg=rgb)
                i += consumed
            elif code == 49:
                style = replace(style, bg=None)
            elif 90 <= code <= 97:
                style = replace(style, fg=basic_color(code - 90 + 8))
            elif 100 <= code <= 107:
                style = replace(style, bg=basic_color(code - 100 + 8))
            # Unrecognized SGR codes are ignored rather than raising, so
            # an unusual/rare sequence never breaks the whole stream.
            i += 1
        self._style = style

    @staticmethod
    def _extended_color(codes: List[int], i: int) -> Tuple[Optional[RGB], int]:
        """Parse the ``5;n`` (256-color) or ``2;r;g;b`` (truecolor) tail
        following an SGR 38/48 code. Returns (rgb, extra codes consumed).
        """
        if i + 1 >= len(codes):
            return None, 0
        mode = codes[i + 1]
        if mode == 5 and i + 2 < len(codes):
            return xterm_256_to_rgb(codes[i + 2]), 2
        if mode == 2 and i + 4 < len(codes):
            return (codes[i + 2], codes[i + 3], codes[i + 4]), 4
        return None, 0
