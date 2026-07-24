"""ScriptWorld: the runtime a world's scripts execute against.

Ties together the per-world variable store, trigger table, alias
table, and timer/on_connect registrations behind the ten scripting API
functions (send, echo, gag, highlight, set_var, get_var, timer,
on_trigger, on_connect, on_alias -- SPEC.md section 4, on_alias added
in Phase 4b). Each world gets its own ScriptWorld so multiple
simultaneous connections (a later-phase Potato-style feature) never
share state.

``send``/``echo`` are injected callables rather than a live
TelnetClient/GUI reference -- this keeps engine/scripting decoupled
from engine/net and any UI, exactly like engine/net and engine/ansi
don't import each other. Real wiring (a live socket, a live display)
happens in a later phase; tests here use plain fakes.
"""

from __future__ import annotations

import json
import types
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..ansi.style import Style
from .errors import ScriptAPIError
from .sandbox import (
    DEFAULT_TIMEOUT_SECONDS,
    build_restricted_globals,
    compile_script,
    execute_compiled,
    run_with_timeout,
)
from .aliases import Alias, AliasEngine
from .triggers import Trigger, TriggerTable, gag_api, highlight_api

MAX_TIMER_DELAY_SECONDS = 86400.0  # 24h
MAX_OUTSTANDING_TIMERS = 100


class TimerRequest:
    """A pending timer(), not yet scheduled on any event loop.

    Actually scheduling this (e.g. via ``loop.call_later``) and calling
    :meth:`ScriptWorld.run_callback` when it fires is the job of a
    later phase's live integration code -- this phase only validates
    and records the request, keeping it testable without a running
    event loop.
    """

    def __init__(self, delay_seconds: float, callback: Callable[[], None]) -> None:
        self.delay_seconds = delay_seconds
        self.callback = callback


class ScriptWorld:
    def __init__(
        self,
        *,
        send: Callable[[str], None],
        echo: Callable[[str, Optional[Style]], None],
        variables: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._send = send
        self._echo = echo
        self.variables: Dict[str, Any] = dict(variables or {})
        self.triggers = TriggerTable(timeout_seconds=timeout_seconds)
        self.aliases = AliasEngine(timeout_seconds=timeout_seconds)
        self.pending_timers: List[TimerRequest] = []
        self._connect_callbacks: List[Callable[[], None]] = []
        self._timeout_seconds = timeout_seconds
        # Globals dicts of every script loaded into this world, used to
        # verify a callback passed to timer()/on_trigger()/on_connect()
        # really was defined inside one of them (see
        # _require_script_owned_callable). Kept as a plain list (not
        # keyed) for this original purpose -- unrelated to the
        # name-keyed tracking added below for unload_script().
        self._script_globals: List[Dict[str, Any]] = []
        # Phase 9: parallel, *named* tracking so a specific saved script
        # (ScriptRecord.name) can be cleanly unloaded/reloaded (edited +
        # re-saved) without its old registrations lingering alongside
        # the new ones. Additive to self._script_globals above, not a
        # replacement -- load_script() without a script_name (every
        # pre-Phase-9 caller, including existing tests) never touches
        # this and behaves exactly as before.
        self._script_globals_by_name: Dict[str, Dict[str, Any]] = {}
        self._currently_loading_script: Optional[str] = None
        # Phase 9: set whenever set_var() changes `variables`, cleared
        # by whatever saved it (periodic autosave or shutdown/
        # disconnect) -- a plain public attribute rather than a
        # property, since the GUI layer needs to both read and clear
        # it, and there's no invariant here worth guarding with one.
        self.dirty: bool = False

    # -- scripting API functions (bound as closures into a script's globals) --

    def _api_send(self, text: str) -> None:
        if not isinstance(text, str):
            raise ScriptAPIError("send() requires a string")
        self._send(text)

    def _api_echo(self, text: str, style: Optional[Style] = None) -> None:
        if not isinstance(text, str):
            raise ScriptAPIError("echo() requires a string")
        if style is not None and not isinstance(style, Style):
            raise ScriptAPIError("echo() style must be an engine.ansi.Style instance")
        self._echo(text, style)

    def _api_set_var(self, name: str, value: Any) -> None:
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ScriptAPIError(
                f"set_var({name!r}, ...) value must be JSON-serializable: {exc}"
            ) from exc
        self.variables[name] = value
        self.dirty = True

    def _api_get_var(self, name: str, default: Any = None) -> Any:
        return self.variables.get(name, default)

    def _api_timer(self, delay_seconds: float, callback: Callable[[], None]) -> None:
        if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)):
            raise ScriptAPIError("timer() delay_seconds must be a number")
        if not (0 < delay_seconds <= MAX_TIMER_DELAY_SECONDS):
            raise ScriptAPIError(
                f"timer() delay_seconds must be > 0 and <= {MAX_TIMER_DELAY_SECONDS}"
            )
        self._require_script_owned_callable(callback, "timer()")
        if len(self.pending_timers) >= MAX_OUTSTANDING_TIMERS:
            raise ScriptAPIError(
                f"timer() cap of {MAX_OUTSTANDING_TIMERS} outstanding timers reached"
            )
        self.pending_timers.append(TimerRequest(delay_seconds, callback))

    def _api_on_trigger(
        self,
        pattern: str,
        callback: Callable[[Any], None],
        *,
        gag: bool = False,
        highlight_style: Optional[Style] = None,
        priority: int = 0,
        name: Optional[str] = None,
    ) -> None:
        self._require_script_owned_callable(callback, "on_trigger()")
        trigger = Trigger(
            name=name or getattr(callback, "__name__", pattern),
            pattern=pattern,
            callback=callback,
            gag=gag,
            highlight_style=highlight_style,
            priority=priority,
            source_script=self._currently_loading_script or "",
        )
        self.triggers.add(trigger)

    def _api_on_connect(self, callback: Callable[[], None]) -> None:
        self._require_script_owned_callable(callback, "on_connect()")
        self._connect_callbacks.append(callback)

    def _api_on_alias(
        self,
        pattern: str,
        callback: Callable[[Any], None],
        *,
        priority: int = 0,
        name: Optional[str] = None,
    ) -> None:
        self._require_script_owned_callable(callback, "on_alias()")
        alias = Alias(
            name=name or getattr(callback, "__name__", pattern),
            pattern=pattern,
            callback=callback,
            priority=priority,
            source_script=self._currently_loading_script or "",
        )
        self.aliases.add(alias)

    def _require_script_owned_callable(self, callback: Any, api_name: str) -> None:
        """Reject anything that isn't a function defined inside one of
        this world's own sandboxed scripts.

        Checked by identity (``callback.__globals__ is g``), not
        equality -- two different globals dicts can compare equal by
        value at some point in time, which would make an ``in`` check
        against a list of dicts an unreliable, spoofable test. A
        function's ``__globals__`` is set to the exact dict it was
        defined in the moment ``def`` runs, so this can't be satisfied
        by a string, a builtin, a lambda from outside a script, or a
        function belonging to a *different* world's script.
        """
        is_own_script_function = isinstance(callback, types.FunctionType) and any(
            callback.__globals__ is g for g in self._script_globals
        )
        if not is_own_script_function:
            raise ScriptAPIError(
                f"{api_name} requires a function defined in this same script, "
                "not a string, builtin, or external reference"
            )

    def api_namespace(self) -> Dict[str, Any]:
        return {
            "send": self._api_send,
            "echo": self._api_echo,
            "gag": gag_api,
            "highlight": highlight_api,
            "set_var": self._api_set_var,
            "get_var": self._api_get_var,
            "timer": self._api_timer,
            "on_trigger": self._api_on_trigger,
            "on_connect": self._api_on_connect,
            "on_alias": self._api_on_alias,
            # Not itself one of the 9 API functions -- but echo()/
            # highlight() take a Style instance as an argument, so
            # scripts need the class available to construct one. It's
            # a frozen dataclass of bools/tuples with no methods that
            # touch anything sensitive, so exposing the type itself
            # carries no more risk than the two functions that already
            # take it as a parameter.
            "Style": Style,
        }

    def load_script(
        self, source: str, *, script_name: Optional[str] = None, filename: str = "<script>"
    ) -> None:
        """Compile and run ``source`` under the sandbox.

        This is always the sandboxed path -- there is no ``trusted``
        parameter here and never will be; the unrestricted escape
        hatch is a completely separate function a caller must
        explicitly reach for on its own (see
        engine.scripting.trusted.execute_trusted_unrestricted).

        The script's globals dict is registered in
        ``self._script_globals`` *before* execution starts, not after
        it returns: API calls like ``on_trigger(pattern, my_callback)``
        happen mid-script, and ``_require_script_owned_callable`` needs
        the ownership check to already be valid at that point.

        ``script_name`` (Phase 9) is optional and additive -- every
        pre-Phase-9 caller omits it and behaves exactly as before
        (anonymous, un-reloadable script). When given (the GUI always
        passes the owning ``ScriptRecord.name``), triggers/aliases this
        script registers are tagged with it, and the script becomes
        individually unloadable/reloadable via :meth:`unload_script`
        without needing to tear down the whole ``ScriptWorld``.
        """
        code = compile_script(source, filename=filename)
        script_globals = build_restricted_globals(self.api_namespace())
        self._script_globals.append(script_globals)
        if script_name is not None:
            self._script_globals_by_name[script_name] = script_globals
        previous_loading = self._currently_loading_script
        self._currently_loading_script = script_name
        try:
            execute_compiled(code, script_globals, timeout_seconds=self._timeout_seconds)
        finally:
            self._currently_loading_script = previous_loading

    def unload_script(self, script_name: str) -> None:
        """Remove everything ``script_name`` previously registered --
        triggers, aliases, pending timers, on_connect callbacks -- so
        it can be cleanly reloaded (edited + re-saved) without
        duplicate registrations piling up alongside the new version.

        A no-op if ``script_name`` was never loaded with a name (or
        already unloaded) -- safe to call unconditionally before every
        reload.
        """
        script_globals = self._script_globals_by_name.pop(script_name, None)
        self.triggers.remove_by_source_script(script_name)
        self.aliases.remove_by_source_script(script_name)
        if script_globals is None:
            return
        self._script_globals = [g for g in self._script_globals if g is not script_globals]
        self.pending_timers = [
            t for t in self.pending_timers if t.callback.__globals__ is not script_globals
        ]
        self._connect_callbacks = [
            cb for cb in self._connect_callbacks if cb.__globals__ is not script_globals
        ]

    def run_callback(self, callback: Callable[..., None], *args: Any) -> None:
        """Invoke a script-owned callback under the same timeout guard
        used for trigger dispatch. Future live-integration code (timer
        firing, connect firing) should call this rather than the
        callback directly, so every entry point into script code is
        uniformly guarded.
        """
        run_with_timeout(lambda: callback(*args), self._timeout_seconds)

    def fire_connect_callbacks(self) -> List[Tuple[str, str]]:
        """Run every registered on_connect() callback, in registration
        order.

        Returns ``(callback_name, message)`` pairs for any that raised
        -- a broken on_connect callback must not prevent *other*
        on_connect callbacks (or autosends/login, which the GUI fires
        around the same point) from running, so failures are caught
        and reported here rather than propagated.
        """
        errors: List[Tuple[str, str]] = []
        for callback in self._connect_callbacks:
            try:
                self.run_callback(callback)
            except Exception as exc:  # noqa: BLE001 - a script's own bug must not propagate
                name = getattr(callback, "__name__", "on_connect")
                errors.append((name, f"{type(exc).__name__}: {exc}"))
        return errors
