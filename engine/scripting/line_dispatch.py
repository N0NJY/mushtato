"""Per-line trigger dispatch: buffers incoming raw text into complete
lines, ANSI-parses each one, matches the result against a world's
triggers, and applies gag/highlight before handing back render-ready
segments.

Headless and Qt-free (CLAUDE.md rule 2) -- this class doesn't know or
care which thread it's called from. Phase 9's own threading fix is
about *where the caller invokes it from* (the connection's background
thread, never the GUI thread, so a slow/hung trigger's
run_with_timeout wait never blocks the UI) -- see
gui/windows/telnet_bridge.py's ``on_text`` callback for that wiring.

Line-buffering exists specifically because neither engine/net nor
engine/ansi buffer by line: AnsiParser.feed() only buffers a *partial
escape sequence* across calls, never partial text, and MUD triggers
need a complete line to match sensibly (a pattern like
``r"^Bob says"`` can't be evaluated reliably against a still-arriving
fragment). A trailing, never-terminated partial line (most often an
interactive prompt with no trailing "\\n") is still rendered
immediately for a responsive feel, but is never matched against
triggers -- a deliberate, documented simplification versus real
TinyFugue's more elaborate prompt-timeout mechanism (SPEC.md section
8), not an oversight.

The "preview" mechanism is designed so gag/highlight still work
correctly even when a line happens to arrive split across multiple
network reads: the incomplete trailing line's segments are returned
*in full* on every call (not incrementally), and the caller is
expected to replace (erase + reinsert) whatever it rendered as the
previous preview, never append to it. Nothing is ever "permanently"
rendered until the line actually completes, so a gag/highlight that
resolves once the line finishes correctly covers the *entire* line,
not just whatever fragment arrived last.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..ansi import DEFAULT_STYLE, AnsiParser, Style, StyledSegment
from .triggers import DispatchOutcome, TriggerTable


@dataclass
class FinalizedLine:
    """One complete, trigger-processed line ready to render -- or to
    skip entirely, if ``gagged`` (in which case ``segments`` is empty
    and nothing, not even a blank line, should be inserted).
    """

    segments: List[StyledSegment]
    gagged: bool
    outcome: DispatchOutcome


@dataclass
class LineDispatchResult:
    """Result of one :meth:`LineDispatcher.feed` call.

    ``finalized`` is zero or more complete lines that just finished,
    in arrival order. ``preview`` is the *full* current state of the
    still-incomplete trailing line's segments (not an increment) --
    ``None`` if there's currently no pending partial line at all. The
    caller must replace whatever it previously rendered as a preview
    with this one, never append to it (see module docstring).
    """

    finalized: List[FinalizedLine] = field(default_factory=list)
    preview: Optional[List[StyledSegment]] = None


def _split_on_newlines(text: str) -> List[Tuple[str, bool]]:
    """Split ``text`` into ``(piece, ends_a_line)`` pairs.

    Every piece except the last ended in a "\\n" in ``text``; the last
    piece (possibly empty) didn't. E.g. ``"a\\n\\nb"`` ->
    ``[("a", True), ("", True), ("b", False)]``.
    """
    parts = text.split("\n")
    pieces = [(part, True) for part in parts[:-1]]
    pieces.append((parts[-1], False))
    return pieces


def _apply_highlights(
    segments: List[StyledSegment], highlights: List[Tuple[Tuple[int, int], Style]]
) -> List[StyledSegment]:
    """Return ``segments`` with any ``highlights`` spans' style applied.

    ``highlights`` entries are ``((start, end), style)`` character
    offsets into the concatenation of ``segments``' text, in the same
    highest-priority-first order ``TriggerTable.dispatch`` builds them
    in (see engine/scripting/triggers.py). Applied in *reverse* of that
    order (lowest priority first) so a higher-priority trigger's
    highlight visibly wins over a lower-priority one for any
    overlapping characters, matching what "priority" already means
    everywhere else in the trigger system.
    """
    if not highlights:
        return list(segments)

    total_length = sum(len(seg.text) for seg in segments)
    if total_length == 0:
        return list(segments)

    char_styles: List[Style] = []
    for seg in segments:
        char_styles.extend([seg.style] * len(seg.text))

    for (start, end), style in reversed(highlights):
        for i in range(max(0, start), min(total_length, end)):
            char_styles[i] = style

    plain_text = "".join(seg.text for seg in segments)
    result: List[StyledSegment] = []
    run_start = 0
    for i in range(1, total_length + 1):
        if i == total_length or char_styles[i] != char_styles[run_start]:
            result.append(StyledSegment(plain_text[run_start:i], char_styles[run_start]))
            run_start = i
    return result


class LineDispatcher:
    """Wraps an :class:`~engine.ansi.AnsiParser` and a world's
    :class:`TriggerTable` to turn a raw incoming text stream into
    trigger-processed, render-ready lines.
    """

    def __init__(self, triggers: TriggerTable) -> None:
        self._triggers = triggers
        self._parser = AnsiParser()
        self._pending: List[StyledSegment] = []  # current incomplete line's segments so far

    def feed(self, raw_text: str) -> LineDispatchResult:
        result = LineDispatchResult()
        new_segments = self._parser.feed(raw_text)
        for segment in new_segments:
            for piece_text, ends_line in _split_on_newlines(segment.text):
                if piece_text:
                    self._pending.append(StyledSegment(piece_text, segment.style))
                if ends_line:
                    result.finalized.append(self._finalize_pending_line())
        result.preview = list(self._pending) if self._pending else None
        return result

    def _finalize_pending_line(self) -> FinalizedLine:
        segments = self._pending
        self._pending = []
        # The "\n" itself was consumed as a delimiter by
        # _split_on_newlines, deliberately excluded from `plain_text`
        # so trigger patterns never need to account for a trailing
        # newline -- but it has to be added back to the *rendered*
        # segments below, or consecutive lines would run together with
        # no line break once inserted into the scrollback.
        plain_text = "".join(seg.text for seg in segments)
        outcome = self._triggers.dispatch(plain_text)
        if outcome.gagged:
            # A gagged line vanishes entirely -- no blank-line
            # placeholder left behind, matching real gag() semantics.
            return FinalizedLine(segments=[], gagged=True, outcome=outcome)
        final_segments = _apply_highlights(segments, outcome.highlights)
        if final_segments:
            last = final_segments[-1]
            final_segments = final_segments[:-1] + [StyledSegment(last.text + "\n", last.style)]
        else:
            final_segments = [StyledSegment("\n", DEFAULT_STYLE)]
        return FinalizedLine(segments=final_segments, gagged=False, outcome=outcome)
