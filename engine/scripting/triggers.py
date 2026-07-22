"""Trigger table: RE2 pattern matching against incoming text, dispatched
to sandboxed script callbacks. Gag and highlight are first-class
trigger actions (SPEC.md section 6), settable either declaratively
(``on_trigger(..., gag=True, highlight_style=...)``) or imperatively
(calling ``gag()``/``highlight()`` from within the callback body).

Trigger patterns compile against RE2 rather than stdlib ``re``: RE2
guarantees linear-time matching by construction (no catastrophic
backtracking is possible), which matters specifically here because
this is the one place in the codebase where a pattern of uncertain
origin (a user- or community-authored trigger) is matched against text
of uncertain origin (whatever the remote server sends). See SPEC.md
section 5/8 for the fuller trade-off discussion (RE2 doesn't support
backreferences or lookaround; both are rare for MUD trigger patterns
and can be replicated in the callback body when needed).
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

import re2

from ..ansi.style import Style
from .errors import ScriptAPIError
from .sandbox import DEFAULT_TIMEOUT_SECONDS, run_with_timeout


@dataclass
class DispatchOutcome:
    """Result of running all matching triggers against one line of text.

    A GUI/console renderer (a later phase) uses this to decide whether
    to display the line at all, and with what style overrides -- this
    module only produces the structured outcome, same as engine/ansi
    only produces StyledSegments without deciding how they're drawn.
    """

    gagged: bool = False
    highlights: List[Tuple[Tuple[int, int], Style]] = field(default_factory=list)
    matched_triggers: List[str] = field(default_factory=list)


@dataclass
class _TriggerContext:
    """What gag()/highlight() need to know about "the trigger callback
    currently running": the shared outcome to mutate, and the specific
    match that triggered *this* callback (needed to resolve
    highlight()'s default "whole match" span).
    """

    outcome: DispatchOutcome
    match: Any


# Async-safe (contextvars survive across `await` correctly, unlike a
# plain module-level variable) so concurrent worlds' dispatches never
# see each other's in-flight context, and scoped per-callback (not per
# whole dispatch() call) so each trigger's own match is visible to
# gag()/highlight() even when several triggers match the same line.
_current_context: "contextvars.ContextVar[Optional[_TriggerContext]]" = contextvars.ContextVar(
    "_current_context", default=None
)


def gag_api() -> None:
    """Suppress the currently-matched line from display.

    Only valid inside a trigger callback (i.e. while
    :meth:`TriggerTable.dispatch` is running one) -- raises
    :class:`ScriptAPIError` otherwise, rather than silently doing
    nothing or gagging something unintended.
    """
    ctx = _current_context.get()
    if ctx is None:
        raise ScriptAPIError("gag() can only be called from within a trigger callback")
    ctx.outcome.gagged = True


def highlight_api(style: Style, span: Optional[Tuple[int, int]] = None) -> None:
    """Restyle (a span of) the currently-matched line for display.

    ``span`` defaults to the whole match that fired the currently-
    running trigger callback. Only valid inside a trigger callback,
    same as :func:`gag_api`. ``style`` must be an
    :class:`engine.ansi.Style` instance -- not a raw ANSI escape
    string, which would let a script inject arbitrary terminal escape
    sequences into the rendered output.
    """
    if not isinstance(style, Style):
        raise ScriptAPIError("highlight() requires an engine.ansi.Style instance")
    ctx = _current_context.get()
    if ctx is None:
        raise ScriptAPIError("highlight() can only be called from within a trigger callback")
    if span is None:
        span = (ctx.match.start(), ctx.match.end())
    ctx.outcome.highlights.append((span, style))


@dataclass
class Trigger:
    name: str
    pattern: str
    callback: Callable[[Any], None]
    gag: bool = False
    highlight_style: Optional[Style] = None
    priority: int = 0
    enabled: bool = True
    compiled: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            self.compiled = re2.compile(self.pattern)
        except re2.error as exc:
            raise ScriptAPIError(f"invalid trigger pattern {self.pattern!r}: {exc}") from exc


class TriggerTable:
    """Holds a world's registered triggers and dispatches incoming text."""

    def __init__(self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._triggers: List[Trigger] = []
        self._timeout_seconds = timeout_seconds

    def add(self, trigger: Trigger) -> None:
        self._triggers.append(trigger)

    def dispatch(self, text: str) -> DispatchOutcome:
        """Match ``text`` against every enabled trigger, highest
        priority first, running each match's callback under the
        sandbox's execution-time guard.
        """
        outcome = DispatchOutcome()
        enabled = [t for t in self._triggers if t.enabled]
        for trigger in sorted(enabled, key=lambda t: -t.priority):
            match = trigger.compiled.search(text)
            if match is None:
                continue
            outcome.matched_triggers.append(trigger.name)
            if trigger.gag:
                outcome.gagged = True
            if trigger.highlight_style is not None:
                outcome.highlights.append(
                    ((match.start(), match.end()), trigger.highlight_style)
                )
            token = _current_context.set(_TriggerContext(outcome=outcome, match=match))
            try:
                run_with_timeout(lambda t=trigger, m=match: t.callback(m), self._timeout_seconds)
            finally:
                _current_context.reset(token)
        return outcome
