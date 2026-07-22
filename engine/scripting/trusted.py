"""The explicit, opt-in unrestricted execution escape hatch.

CLAUDE.md rule 3: unrestricted execution must be genuinely hard to
reach by accident. Nothing in engine/scripting ever calls this
automatically based on a script's stored ``trusted`` flag -- that flag
(see engine/storage) is inert metadata a future GUI could read to
decide whether to *offer* this path to the user; the engine itself
never branches on it. Every caller must import this module by name and
explicitly pass both required confirmation keywords, every time.

This is the only place in the codebase other than
engine/scripting/sandbox.py that calls real ``exec()`` -- and unlike
that module, nothing here is sandboxed at all. That is the point of
it: it exists for a user's own local, personally-authored scripts
only.
"""

from __future__ import annotations

from typing import Any, Dict


def execute_trusted_unrestricted(
    source: str,
    globals_dict: Dict[str, Any],
    *,
    i_understand_this_is_unrestricted: bool,
    confirm_trusted: bool,
    filename: str = "<trusted script>",
) -> None:
    """Run ``source`` as ordinary, unrestricted Python. No sandbox.

    DANGER: this can do anything any other Python code on this machine
    can do -- read/write arbitrary files, open sockets, import
    anything, run subprocesses. Only ever call this for a user's own
    local scripts that they personally wrote or explicitly reviewed.
    NEVER for a script downloaded, imported, or shared from anyone
    else, even if that script's own saved metadata claims to be
    "trusted" -- a shared script setting its own trusted flag must
    never be honored. Any future script-import/sharing feature
    (SPEC.md section 7, phase 8) MUST force ``trusted=False`` on
    anything not authored locally, regardless of what the imported
    file says about itself.

    Both keyword-only confirmation arguments are required, with no
    default, specifically so this can't be reached by one accidental
    flag left on somewhere -- a caller has to spell out, at the call
    site, every single time, that it means to do this.
    """
    if not (i_understand_this_is_unrestricted and confirm_trusted):
        raise PermissionError(
            "execute_trusted_unrestricted() requires both "
            "i_understand_this_is_unrestricted=True and confirm_trusted=True "
            "-- this is deliberate friction, not a bug"
        )
    code = compile(source, filename, "exec")
    exec(code, globals_dict)  # noqa: S102 -- intentional, see module docstring
