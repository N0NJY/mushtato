"""Built-in client command parser/dispatcher (Phase 7c).

Mirrors engine/scripting/aliases.py's split: this module owns parsing
and dispatch only -- the "/" + "//" escape convention and command-name
lookup -- while the GUI registers handler closures binding command
names to real actions (MainWindow.close, spawn_log_window, etc.), the
same pattern ScriptWorld already uses for injected send()/echo().
Nothing here imports Qt/gui, so it's testable headless with fake
handlers.

Prefix convention, verified against the real TinyFugue source
(src/expand.c's statement(), not assumed from memory) rather than
invented: a line with no leading "/" is plain text (send as-is); a
line starting with exactly one "/" is a command -- the slash is
stripped, the rest is "name args"; a line starting with "//" is the
escape hatch -- one slash is stripped and the remainder (still
starting with a "/") is sent as literal text. This is TF's actual,
decades-old answer to "the MUD server also uses this prefix."

Command lookup is exact, case-insensitive name matching (also verified
against TF's find_builtin_cmd/cstrstructcmp, a bsearch with a
case-insensitive comparator) -- no abbreviation support. An
unrecognized "/word" is reported as an error, never silently sent to
the server as a fallback -- same as TF's own behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

# A handler receives the raw argument text (already stripped of the
# command name and leading space) and optionally returns a string to
# display locally -- None means "nothing to show".
CommandHandler = Callable[[str], Optional[str]]


@dataclass
class CommandOutcome:
    """Result of processing one line of typed input.

    ``action`` is one of:
      "send"    -- text should be sent to the server as-is (either it
                   never looked like a command, or it was the "//"
                   escape hatch for a literal server-bound line).
      "handled" -- a registered command ran; ``text`` (if any) is
                   local-only output to display, never sent anywhere.
      "error"   -- the line looked like a command but named one that
                   isn't registered; ``text`` is the error message.
    """

    action: str
    text: Optional[str] = None


@dataclass
class _Command:
    name: str
    handler: CommandHandler
    help_text: str = ""


class CommandTable:
    """Holds a world's registered built-in commands and processes
    typed input against them.

    ``/help`` is always registered automatically -- it only needs to
    introspect this table's own registrations, so there's no reason to
    make every caller register it separately.
    """

    def __init__(self) -> None:
        self._commands: Dict[str, _Command] = {}
        self.register(
            "help",
            self._handle_help,
            "List available commands, or show help for one: /help [command]",
        )

    def register(self, name: str, handler: CommandHandler, help_text: str = "") -> None:
        self._commands[name.lower()] = _Command(
            name=name.lower(), handler=handler, help_text=help_text
        )

    def command_help_text(self, name: str) -> Optional[str]:
        """The registered help text for ``name``, or ``None`` if it
        isn't a registered command. For a caller (e.g. a GUI Help
        system, Phase 8) that wants to look up one command's help text
        directly, without going through the "/name args" text-parsing
        path in :meth:`process`.
        """
        command = self._commands.get(name.lower())
        return command.help_text if command is not None else None

    def process(self, text: str) -> CommandOutcome:
        if text.startswith("//"):
            return CommandOutcome(action="send", text=text[1:])
        if text.startswith("/"):
            name, _, rest = text[1:].partition(" ")
            command = self._commands.get(name.lower())
            if command is None:
                return CommandOutcome(action="error", text=f"No such command: /{name}")
            output = command.handler(rest.strip())
            return CommandOutcome(action="handled", text=output)
        return CommandOutcome(action="send", text=text)

    def _handle_help(self, args: str) -> str:
        if args:
            command = self._commands.get(args.lower())
            if command is None:
                return f"No such command: /{args}"
            if command.help_text:
                return f"/{command.name} - {command.help_text}"
            return f"/{command.name}"
        names = sorted(self._commands.keys())
        return "Available commands: " + ", ".join(f"/{n}" for n in names)
