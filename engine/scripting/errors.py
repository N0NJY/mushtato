"""Exceptions raised by the scripting engine."""

from __future__ import annotations


class ScriptError(Exception):
    """Base class for all engine.scripting errors."""


class ScriptCompileError(ScriptError):
    """Raised when a script fails RestrictedPython compilation."""


class ScriptAPIError(ScriptError):
    """Raised when the scripting API is misused.

    E.g. gag()/highlight() called outside a trigger callback, timer()
    given an out-of-range delay or a callback that isn't a function
    defined in the caller's own script, set_var() given a value that
    isn't JSON-serializable.
    """


class ScriptTimeoutError(ScriptError):
    """Raised when script/callback execution exceeds its time budget.

    See engine.scripting.sandbox.run_with_timeout for the known
    limitation: this cannot interrupt a genuine CPU-bound busy loop.
    """
