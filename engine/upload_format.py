"""Pure, Qt-free logic for the Upload feature (Tools > Upload / /upload)
-- reading a file and deciding what, if anything, to send for each of
its lines. Modeled on Potato's real ``::potato::uploadBegin`` (potato.tcl
lines ~1197-1287, verified directly against the source, not guessed):
files are processed one original line at a time, with an optional
"MPP Formatted" line-continuation/escaping convention, a Prefix
applied to every sent line, and Ignore Empty Lines filtering. Pacing
(the delay between sends) and the progress-window UI are GUI-layer
concerns built on top of this (see gui/windows/upload_session.py) --
this module only decides, one original line at a time, what (if
anything) should be sent.

Real, deliberate deviations from Potato, called out rather than ported
silently:

- The final MPP-buffer flush at end-of-file applies the configured
  Prefix here; Potato's own uploadBegin does not (``send_to_real $c
  $conn($c,upload,mpp,buffer)``, no ``$prefix``) -- almost certainly an
  oversight in Potato's own source rather than an intentional
  asymmetry, since every *other* send in the same proc does apply the
  prefix. Fixed here rather than reproduced: a MushTato user's
  configured Prefix silently not applying to just the very last line
  would be a confusing surprise, not a feature worth preserving.
- Progress is tracked in bytes-consumed-of-the-original-file terms
  using a simple ``len(line.encode("utf-8")) + 1`` per line, not
  Potato's own ``tell``/``bytelength``-based real newline-length
  auto-detection -- a documented simplification, not exact byte parity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class UploadOptions:
    ignore_empty: bool = True
    mpp_formatted: bool = False
    prefix: str = ""
    delay_seconds: float = 0.0
    add_to_history: bool = False


# Verified directly from potato.tcl's uploadBegin: `string map [list
# " " %b "\t" %t % \\% {;} {\;} \[ \\\[ \] \\\] ( \\( ) \\) , \\, ^ \\^
# $ \\$ \{ \\\{ \} \\\} \\ \\\\]`. All keys are exactly one character,
# so (unlike a naive sequence of .replace() calls) a single
# left-to-right scan over the ORIGINAL text is enough -- Tcl's
# `string map` doesn't rescan substituted output either, so escaping
# order among these entries doesn't matter for correctness.
_MPP_ESCAPE_MAP = {
    " ": "%b",
    "\t": "%t",
    "%": "\\%",
    ";": "\\;",
    "[": "\\[",
    "]": "\\]",
    "(": "\\(",
    ")": "\\)",
    ",": "\\,",
    "^": "\\^",
    "$": "\\$",
    "{": "\\{",
    "}": "\\}",
    "\\": "\\\\",
}


def escape_mpp(text: str) -> str:
    """Escape one line's content for an MPP-formatted continuation
    line (a ``>``-prefixed line in MPP mode).

    A single left-to-right pass over the original text -- naive
    sequential ``.replace()`` calls would double-escape the
    backslashes this function itself inserts, since a later `.replace
    ("\\\\", ...)` pass would also match backslashes an earlier
    replacement just produced.
    """
    return "".join(_MPP_ESCAPE_MAP.get(ch, ch) for ch in text)


def delay_ms(delay_seconds: float) -> int:
    """Matches Potato's own ``round(1000 * $conn($c,upload,delay))``."""
    return round(1000 * delay_seconds)


@dataclass
class UploadStep:
    send_text: Optional[str]
    done: bool


class UploadStepper:
    """Advances through ``lines`` one original line at a time, exactly
    like Potato's ``uploadBegin`` -- one :meth:`step` call per original
    line, returning what (if anything) should be sent this step.
    Pacing between steps (waiting ``delay_ms(options.delay_seconds)``
    after a step that actually sent something, or proceeding
    immediately after a skipped/buffered line) is the caller's job,
    not this class's -- matches Potato's own real behavior, where a
    skipped/buffered line incurs no delay before the next one.
    """

    def __init__(self, lines: List[str], options: UploadOptions) -> None:
        self.lines = lines
        self.options = options
        self.position = 0
        self.bytes_consumed = 0
        self.total_bytes = sum(len(line.encode("utf-8")) + 1 for line in lines)
        self._mpp_buffer = ""
        self._mpp_gt = False
        self._done = False

    @property
    def total_lines(self) -> int:
        return len(self.lines)

    @property
    def done(self) -> bool:
        return self._done

    def step(self) -> UploadStep:
        if self._done:
            return UploadStep(send_text=None, done=True)

        if self.position >= len(self.lines):
            text = None
            if self.options.mpp_formatted and self._mpp_buffer:
                text = self._mpp_buffer
                self._mpp_buffer = ""
            self._done = True
            return UploadStep(send_text=self._apply_prefix(text), done=True)

        line = self.lines[self.position]
        self.position += 1
        self.bytes_consumed = min(
            self.total_bytes, self.bytes_consumed + len(line.encode("utf-8")) + 1
        )

        send_text: Optional[str] = None

        if self.options.mpp_formatted:
            stripped = line.strip(" \t")
            if stripped == "" or line[:2] == "@@":
                pass  # blank/whitespace/comment line -- skipped entirely
            elif line[:1] == ">":
                if self._mpp_gt:
                    # First ">" line right after a fresh buffer start --
                    # no "%r" joiner needed yet.
                    self._mpp_gt = False
                else:
                    self._mpp_buffer += "%r"
                self._mpp_buffer += escape_mpp(line[1:])
            elif line[:1] in (" ", "\t"):
                # Unformatted continuation -- appended raw (trimmed),
                # no escaping, no separator.
                self._mpp_buffer += line.lstrip(" \t")
            else:
                if self._mpp_buffer:
                    send_text = self._mpp_buffer
                self._mpp_gt = True
                self._mpp_buffer = line
        elif line != "" or not self.options.ignore_empty:
            send_text = line

        return UploadStep(send_text=self._apply_prefix(send_text), done=False)

    def _apply_prefix(self, text: Optional[str]) -> Optional[str]:
        if text is None:
            return None
        return f"{self.options.prefix}{text}" if self.options.prefix else text
