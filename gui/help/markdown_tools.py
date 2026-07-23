"""Light Markdown-to-plain-text conversion for scrollback display.

Not a full Markdown-to-text engine -- just enough to make the same
Markdown source (also rendered richly in the Help window via
QTextBrowser.setMarkdown()) readable as plain lines in a monospace
scrollback, where "#"/"**" characters would otherwise show up
literally. Deliberately simple: this project has exactly one content
source (gui/help/topics.py) rendered two ways, not two copies of the
content to keep in sync.
"""

from __future__ import annotations

import re

_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BOLD_ALT_RE = re.compile(r"__(.+?)__")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def strip_markdown(text: str) -> str:
    """Strip header markers and emphasis markers, line by line.

    List bullets ("- ") and backtick-quoted code spans are left as-is
    -- both already read fine as plain text in a monospace font.
    """
    text = _HEADER_RE.sub("", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _BOLD_ALT_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    return text
