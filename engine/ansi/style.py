"""Style and StyledSegment data structures for parsed ANSI text.

These types are toolkit-agnostic: a renderer for Qt, curses, or plain
terminal output all consume the same structures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Optional, Tuple

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Style:
    """Rendering attributes in effect for a run of text.

    ``fg``/``bg`` are resolved to concrete RGB triples (or ``None`` for
    "terminal default") so that every color source ANSI supports -- the
    8 basic colors, the 8 bright colors, the 256-color palette, and
    24-bit truecolor -- collapses to one representation before it ever
    reaches a renderer.
    """

    fg: Optional[RGB] = None
    bg: Optional[RGB] = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    blink: bool = False
    reverse: bool = False
    strikethrough: bool = False


DEFAULT_STYLE = Style()


class StyledSegment(NamedTuple):
    """A run of text sharing a single :class:`Style`."""

    text: str
    style: Style
