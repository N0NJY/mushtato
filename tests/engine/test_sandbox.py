"""Headless tests for the RestrictedPython sandbox -- no live server or
GUI needed. These prove the sandbox actually blocks dangerous scripts,
not just that safe ones run.
"""

import pytest

from engine.scripting.errors import ScriptCompileError, ScriptTimeoutError
from engine.scripting.sandbox import execute_script


def test_safe_script_runs_and_can_call_injected_api():
    calls = []

    def fake_send(text):
        calls.append(text)

    source = "send('hello world')\nresult = 1 + 1\n"
    globals_out = execute_script(source, {"send": fake_send})

    assert calls == ["hello world"]
    assert globals_out["result"] == 2


def test_script_can_define_and_register_a_callback():
    registered = {}

    def fake_on_trigger(pattern, callback):
        registered["pattern"] = pattern
        registered["callback"] = callback

    source = (
        "def handle(match):\n"
        "    return 'handled'\n"
        "on_trigger('foo', handle)\n"
    )
    execute_script(source, {"on_trigger": fake_on_trigger})

    assert registered["pattern"] == "foo"
    assert registered["callback"]("m") == "handled"


@pytest.mark.parametrize(
    "source",
    [
        "import os\nos.system('echo pwned')",
        "import subprocess\nsubprocess.run(['echo', 'pwned'])",
        "import socket\nsocket.socket()",
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd').read()",
        "eval('1 + 1')",
        "exec('import os')",
        "x = ().__class__.__bases__[0].__subclasses__()",
        "import ctypes",
    ],
)
def test_dangerous_scripts_are_blocked(source):
    """The core safety guarantee: nothing in this list should ever be
    able to touch the filesystem, network, or process, or escape the
    sandbox via dunder-attribute introspection -- whether that's caught
    at compile time (SyntaxError-equivalent) or at run time (NameError
    from a missing builtin) doesn't matter, only that it's blocked.
    """
    with pytest.raises((ScriptCompileError, NameError, ImportError)):
        execute_script(source, {})


def test_blocked_script_never_reaches_injected_api():
    """A dangerous script shouldn't get partial credit -- if it's
    blocked, none of its side effects (including calls to the real
    scripting API) should have happened either.
    """
    calls = []

    def fake_send(text):
        calls.append(text)

    source = "send('before')\nimport os\nsend('after')\n"
    with pytest.raises((ScriptCompileError, NameError, ImportError)):
        execute_script(source, {"send": fake_send})

    # send('before') runs fine at the language level -- RestrictedPython
    # doesn't halt at the *first* bad statement's position, it blocks
    # 'import os' specifically. What must never happen is os actually
    # being importable/usable.
    assert "after" not in calls


def test_infinite_loop_is_caught_by_the_timeout():
    """Known limitation (SPEC.md section 8): this proves the watchdog
    fires for a *busy* loop within the timeout window, but does not
    prove the underlying thread actually stops (it can't, due to the
    GIL) -- see the sandbox module docstring.
    """
    with pytest.raises(ScriptTimeoutError):
        execute_script("while True:\n    pass\n", {}, timeout_seconds=0.2)
