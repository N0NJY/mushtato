"""Alias table: RE2 pattern matching against the user's own typed
input, dispatched to sandboxed script callbacks (TinyFugue/Potato-style
command aliases -- SPEC.md section 6).

This reuses the same execution machinery as triggers (same
RestrictedPython sandbox, same run_with_timeout watchdog, same
script-ownership check on callbacks) -- an alias callback is code of
uncertain origin exactly like a trigger callback is (both can come from
a shared/downloaded script pack), so nothing about *that* changes.

What's different from triggers, deliberately:

- Patterns match via ``fullmatch`` against the whole (stripped) typed
  line, not ``search`` for a substring anywhere in it. A pattern like
  "n" (for "north") would incorrectly also match "nonsense" or "next"
  under substring search; fullmatch closes that off. A script that
  wants to capture a free-form argument tail writes it explicitly
  (e.g. ``r"gt (?P<rest>.*)"``) rather than the engine implicitly
  splitting "first word vs. rest" the way classic TinyFugue does.
- First match wins (highest priority, then registration order), not
  "fire every match" -- multiple aliases both trying to replace the
  same typed line doesn't have a clean compositional meaning the way
  multiple triggers reacting to one incoming server line does.
- No gag/highlight -- those are trigger-specific display concerns that
  don't apply to outbound expansion.
- The callback is entirely responsible for what gets sent (zero, one,
  or many send() calls). Critically, send() is never re-run through
  alias expansion -- that's not a recursion-depth guard bolted on, it's
  true by construction, because expand() is only ever meant to be
  called by a future integration layer on raw user keystrokes, never
  on the output of send() itself. An alias's callback calling send()
  cannot recursively re-trigger itself or another alias.

Patterns compile against RE2 for the same reason triggers do -- see
engine/scripting/triggers.py's module docstring -- plus, for aliases
specifically, so shared alias packs and shared trigger packs live
under one consistent regex dialect rather than two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import re2

from .errors import ScriptAPIError
from .sandbox import DEFAULT_TIMEOUT_SECONDS, run_with_timeout


@dataclass
class AliasOutcome:
    """Result of trying to expand one line of typed user input.

    If ``matched`` is False, nothing here handled the input at all --
    a future integration layer is responsible for sending the raw text
    verbatim in that case, same as an unmatched trigger just displays
    its line as-is.

    ``error`` (Phase 9) is set if the matched alias's own callback
    raised (a ``ScriptError`` subclass, or any ordinary bug in the
    script's code) -- ``matched`` stays True in that case (the pattern
    *did* match; falling back to sending the raw text as a literal
    command would compound the confusion, not fix it), and the caller
    is expected to surface ``error`` rather than send anything.
    """

    matched: bool = False
    alias_name: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Alias:
    name: str
    pattern: str
    callback: Callable[[Any], None]
    priority: int = 0
    enabled: bool = True
    # Which saved script (ScriptRecord.name) registered this alias --
    # mirrors Trigger.source_script (engine/scripting/triggers.py),
    # used to cleanly remove an old version's registrations when a
    # script is edited and re-saved.
    source_script: str = ""
    compiled: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            self.compiled = re2.compile(self.pattern)
        except re2.error as exc:
            raise ScriptAPIError(f"invalid alias pattern {self.pattern!r}: {exc}") from exc


class AliasEngine:
    """Holds a world's registered aliases and expands typed input."""

    def __init__(self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._aliases: List[Alias] = []
        self._timeout_seconds = timeout_seconds

    def add(self, alias: Alias) -> None:
        self._aliases.append(alias)

    def remove_by_source_script(self, script_name: str) -> None:
        """Drop every alias registered by ``script_name`` -- used when
        that script is unloaded/reloaded (e.g. edited and re-saved) so
        the old version's registrations don't linger alongside the new
        one.
        """
        self._aliases = [a for a in self._aliases if a.source_script != script_name]

    def expand(self, text: str) -> AliasOutcome:
        """Try to expand ``text`` (the user's literal typed line).

        Stops at the first matching, enabled alias (highest priority
        first); that callback runs under the same timeout guard as
        trigger callbacks. Returns ``AliasOutcome(matched=False)`` if
        nothing matched. A callback that raises is caught here (see
        ``AliasOutcome.error``'s docstring) rather than propagated --
        same reasoning as ``TriggerTable.dispatch()``.
        """
        stripped = text.strip()
        enabled = [a for a in self._aliases if a.enabled]
        for alias in sorted(enabled, key=lambda a: -a.priority):
            match = alias.compiled.fullmatch(stripped)
            if match is None:
                continue
            try:
                run_with_timeout(
                    lambda a=alias, m=match: a.callback(m), self._timeout_seconds
                )
            except Exception as exc:  # noqa: BLE001 - a script's own bug must not raise here
                return AliasOutcome(
                    matched=True, alias_name=alias.name, error=f"{type(exc).__name__}: {exc}"
                )
            return AliasOutcome(matched=True, alias_name=alias.name)
        return AliasOutcome(matched=False)
