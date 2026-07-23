"""Headless tests for the built-in command parser/dispatcher."""

from engine.commands import CommandTable


def test_plain_text_is_sent_unchanged():
    table = CommandTable()
    outcome = table.process("look")
    assert outcome.action == "send"
    assert outcome.text == "look"


def test_double_slash_escape_hatch_strips_one_slash_and_sends():
    """The core TinyFugue-verified convention: "//foo" sends "/foo"
    literally, for MUD servers that use "/" for their own commands.
    """
    table = CommandTable()
    outcome = table.process("//pose waves")
    assert outcome.action == "send"
    assert outcome.text == "/pose waves"


def test_registered_command_is_dispatched_with_its_arguments():
    calls = []
    table = CommandTable()
    table.register("quit", lambda args: calls.append(args) or "done")

    outcome = table.process("/quit now please")

    assert calls == ["now please"]
    assert outcome.action == "handled"
    assert outcome.text == "done"


def test_registered_command_with_no_arguments():
    calls = []
    table = CommandTable()
    table.register("quit", lambda args: calls.append(args))

    table.process("/quit")

    assert calls == [""]


def test_command_lookup_is_case_insensitive():
    calls = []
    table = CommandTable()
    table.register("Quit", lambda args: calls.append("fired"))

    table.process("/QUIT")

    assert calls == ["fired"]


def test_unrecognized_command_is_an_error_not_sent_to_server():
    """Matches TF's own behavior: an unknown "/word" is reported as an
    error, never silently forwarded as if it were plain text.
    """
    table = CommandTable()
    outcome = table.process("/nonsense")
    assert outcome.action == "error"
    assert "nonsense" in outcome.text


def test_handler_returning_none_produces_no_display_text():
    table = CommandTable()
    table.register("quit", lambda args: None)

    outcome = table.process("/quit")

    assert outcome.action == "handled"
    assert outcome.text is None


def test_help_with_no_arguments_lists_all_registered_commands():
    table = CommandTable()
    table.register("quit", lambda args: None, "Close the window")
    table.register("spawnlog", lambda args: None, "Open a log window")

    outcome = table.process("/help")

    assert outcome.action == "handled"
    assert "/help" in outcome.text
    assert "/quit" in outcome.text
    assert "/spawnlog" in outcome.text


def test_help_for_a_specific_command_shows_its_help_text():
    table = CommandTable()
    table.register("quit", lambda args: None, "Close the window")

    outcome = table.process("/help quit")

    assert outcome.text == "/quit - Close the window"


def test_help_for_an_unknown_command_is_not_an_error_action():
    """Distinct from an unrecognized top-level command: /help itself
    matched fine, it's the *subtopic* that's unknown -- still
    "handled", just with an explanatory message as the output.
    """
    table = CommandTable()
    outcome = table.process("/help nonsense")
    assert outcome.action == "handled"
    assert "No such command" in outcome.text


def test_re_registering_the_same_name_replaces_the_handler():
    calls = []
    table = CommandTable()
    table.register("quit", lambda args: calls.append("first"))
    table.register("quit", lambda args: calls.append("second"))

    table.process("/quit")

    assert calls == ["second"]


def test_empty_string_is_sent_unchanged():
    table = CommandTable()
    outcome = table.process("")
    assert outcome.action == "send"
    assert outcome.text == ""
