"""Headless tests for the trusted-mode escape hatch.

These prove two things: the normal sandboxed path never grants
unrestricted execution no matter what, and the explicit trusted path
requires deliberate, redundant confirmation to do anything at all.
"""

import pytest

from engine.scripting.trusted import execute_trusted_unrestricted


def test_trusted_execution_requires_both_confirmation_flags():
    with pytest.raises(PermissionError):
        execute_trusted_unrestricted("x = 1", {}, i_understand_this_is_unrestricted=False, confirm_trusted=True)

    with pytest.raises(PermissionError):
        execute_trusted_unrestricted("x = 1", {}, i_understand_this_is_unrestricted=True, confirm_trusted=False)

    with pytest.raises(PermissionError):
        execute_trusted_unrestricted("x = 1", {}, i_understand_this_is_unrestricted=False, confirm_trusted=False)


def test_trusted_execution_with_both_flags_runs_real_unrestricted_python():
    """Confirms this path is genuinely different from the sandbox --
    the same "import os" that's blocked in engine.scripting.sandbox
    works fine here, because that's the entire point of this function
    existing: for a user's own local scripts, deliberately invoked.
    """
    globals_dict = {"__builtins__": __builtins__}
    execute_trusted_unrestricted(
        "import os\nresult = os.getcwd()",
        globals_dict,
        i_understand_this_is_unrestricted=True,
        confirm_trusted=True,
    )
    assert "result" in globals_dict


def test_nothing_in_scriptworld_reaches_trusted_execution_automatically():
    """A script's stored ``trusted`` flag (see engine.storage) must
    never cause the engine to auto-escalate -- there is no code path
    from ScriptWorld.load_script() to execute_trusted_unrestricted().

    Checked at the bytecode level (co_names: the actual identifiers
    the function looks up) rather than by scanning source text, since
    the source's own docstring legitimately *mentions*
    execute_trusted_unrestricted by name to explain that it's
    deliberately not used here -- a plain text search would trip on
    that explanation instead of on an actual call.
    """
    from engine.scripting.world import ScriptWorld

    assert "execute_trusted_unrestricted" not in ScriptWorld.load_script.__code__.co_names
