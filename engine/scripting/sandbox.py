"""RestrictedPython-based sandbox for user scripts.

This module contains the only two calls to real ``exec()`` on
RestrictedPython-compiled bytecode in the whole codebase (see
:func:`execute_script`). Both run against a globals dict built by
:func:`build_restricted_globals`, which starts from RestrictedPython's
own maintained ``safe_globals``/guarded-attribute-access baseline and
adds nothing beyond the scripting API functions a caller explicitly
passes in -- never real builtins, never ``__import__``, ``open``,
``eval``, ``exec``, or unrestricted attribute access. See CLAUDE.md
rule 3. (The *other* place ``exec()`` appears in this codebase is
engine/scripting/trusted.py's explicit, separately-gated escape hatch,
which is not sandboxed at all -- that is the point of it.)
"""

from __future__ import annotations

import contextvars
import operator
import threading
from typing import Any, Callable, Dict

from RestrictedPython import compile_restricted_exec, safe_globals
from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter
from RestrictedPython.Guards import safer_getattr

from .errors import ScriptCompileError, ScriptTimeoutError

DEFAULT_TIMEOUT_SECONDS = 2.0

_INPLACE_OPERATORS: Dict[str, Callable[[Any, Any], Any]] = {
    "+=": operator.iadd,
    "-=": operator.isub,
    "*=": operator.imul,
    "/=": operator.itruediv,
    "//=": operator.ifloordiv,
    "%=": operator.imod,
    "**=": operator.ipow,
    "<<=": operator.ilshift,
    ">>=": operator.irshift,
    "&=": operator.iand,
    "^=": operator.ixor,
    "|=": operator.ior,
}


def _inplacevar(op: str, value: Any, other: Any) -> Any:
    """RestrictedPython rewrites ``n += 1`` to ``n = _inplacevar_('+=', n, 1)``."""
    return _INPLACE_OPERATORS[op](value, other)


def _guarded_write(value: Any) -> Any:
    """RestrictedPython's ``_write_`` hook for plain-name assignment.

    Attribute/subscript writes go through different guards
    (``_getattr_``'s companion setattr guard isn't needed here since
    RestrictedPython itself forbids attribute assignment on anything
    whose name starts with an underscore at compile time); this hook
    only needs to exist and return its argument unchanged.
    """
    return value


def compile_script(source: str, *, filename: str = "<script>") -> Any:
    """Compile ``source`` under RestrictedPython.

    Raises :class:`ScriptCompileError` on any disallowed syntax --
    imports, ``exec``/``eval`` calls, leading-underscore attribute
    access, etc. -- rather than returning a partially-unsafe result.
    """
    result = compile_restricted_exec(source, filename=filename)
    if result.errors:
        raise ScriptCompileError("; ".join(result.errors))
    return result.code


def build_restricted_globals(api: Dict[str, Any]) -> Dict[str, Any]:
    """Build the globals dict a compiled script runs against.

    ``api`` is exactly the set of scripting-API functions/names
    (``send``, ``echo``, ``gag``, ...) exposed to this particular
    script. Nothing else is reachable beyond RestrictedPython's own
    vetted safe builtins and guards.
    """
    restricted_globals = dict(safe_globals)
    restricted_globals["_getattr_"] = safer_getattr
    restricted_globals["_getitem_"] = default_guarded_getitem
    restricted_globals["_getiter_"] = default_guarded_getiter
    restricted_globals["_write_"] = _guarded_write
    restricted_globals["_inplacevar_"] = _inplacevar
    restricted_globals.update(api)
    return restricted_globals


def run_with_timeout(
    func: Callable[[], Any], timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> Any:
    """Run ``func`` (no args) on a worker thread with a wall-clock timeout.

    KNOWN LIMITATION (also recorded in SPEC.md section 8): this cannot
    actually interrupt a pure-Python CPU-bound busy loop (e.g. ``while
    True: pass``) -- the GIL means a thread running such code can't be
    preempted from outside it, so on timeout the worker thread is
    abandoned still running in the background rather than stopped. This
    guards against I/O-style stalls, not a genuine infinite loop. The
    real fix is subprocess isolation with a hard kill; that's a bigger
    change than this phase and is tracked as an open item in SPEC.md.

    Runs ``func`` inside a copy of the *calling* thread's contextvars
    context (via ``contextvars.copy_context()``) rather than a fresh
    one -- a plain ``threading.Thread`` does not inherit the caller's
    context on its own, which would otherwise silently break
    gag()/highlight()'s use of a ContextVar to scope themselves to "the
    trigger currently being dispatched" (see engine.scripting.triggers).
    """
    outcome: Dict[str, Any] = {}
    failure: Dict[str, BaseException] = {}
    ctx = contextvars.copy_context()

    def _target() -> None:
        try:
            outcome["value"] = ctx.run(func)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            failure["value"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise ScriptTimeoutError(f"execution exceeded {timeout_seconds}s timeout")
    if "value" in failure:
        raise failure["value"]
    return outcome.get("value")


def execute_compiled(
    code: Any,
    restricted_globals: Dict[str, Any],
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Run already-compiled ``code`` against ``restricted_globals``.

    Split out from :func:`execute_script` so a caller (see
    engine.scripting.world.ScriptWorld) can register
    ``restricted_globals`` as "belonging to this script" *before*
    execution starts -- API functions like ``on_trigger()`` are called
    mid-script, so that registration has to already be in place by
    then, not applied only after the whole script finishes running.
    """

    def _run() -> Dict[str, Any]:
        exec(code, restricted_globals)  # noqa: S102 -- sandboxed, see module docstring
        return restricted_globals

    return run_with_timeout(_run, timeout_seconds)


def execute_script(
    source: str,
    api: Dict[str, Any],
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    filename: str = "<script>",
) -> Dict[str, Any]:
    """Compile and run ``source`` under the sandbox in one step.

    Returns the resulting globals dict. Convenience wrapper for
    standalone use (e.g. tests); ScriptWorld uses
    :func:`compile_script` / :func:`build_restricted_globals` /
    :func:`execute_compiled` directly instead, for the ordering reason
    described on :func:`execute_compiled`.
    """
    code = compile_script(source, filename=filename)
    restricted_globals = build_restricted_globals(api)
    return execute_compiled(code, restricted_globals, timeout_seconds=timeout_seconds)
