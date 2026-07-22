"""xterm 256-color and basic 16-color palette -> RGB conversion."""

from __future__ import annotations

from typing import Tuple

from .style import RGB

# Standard xterm 16-color palette (indices 0-7 normal, 8-15 bright).
_BASIC_16: Tuple[RGB, ...] = (
    (0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
    (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229),
    (127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
)


def basic_color(index: int) -> RGB:
    """Resolve a basic palette index 0-15 (0-7 normal, 8-15 bright)."""
    return _BASIC_16[index]


def xterm_256_to_rgb(index: int) -> RGB:
    """Convert an xterm 256-color palette index (0-255) to RGB."""
    if index < 16:
        return _BASIC_16[index]
    if index < 232:
        # 6x6x6 color cube.
        index -= 16
        r, g, b = index // 36, (index // 6) % 6, index % 6
        levels = (0, 95, 135, 175, 215, 255)
        return (levels[r], levels[g], levels[b])
    # Grayscale ramp, 24 steps.
    gray = 8 + (index - 232) * 10
    return (gray, gray, gray)
