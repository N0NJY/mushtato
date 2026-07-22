"""Headless tests for ScriptWorld and the scripting API surface:
send/echo/gag/highlight/set_var/get_var/timer/on_trigger/on_connect.
"""

import pytest

from engine.ansi import Style
from engine.scripting import ScriptAPIError, ScriptWorld


def make_world(**kwargs):
    sent = []
    echoed = []
    world = ScriptWorld(
        send=lambda text: sent.append(text),
        echo=lambda text, style=None: echoed.append((text, style)),
        **kwargs,
    )
    return world, sent, echoed


def test_send_forwards_to_injected_callback():
    world, sent, _ = make_world()
    world.load_script("send('north')")
    assert sent == ["north"]


def test_send_rejects_non_string():
    world, _, _ = make_world()
    with pytest.raises(ScriptAPIError):
        world.load_script("send(123)")


def test_echo_forwards_text_and_style():
    world, _, echoed = make_world()
    world.load_script("echo('status line')")
    assert echoed == [("status line", None)]


def test_echo_rejects_raw_string_as_style():
    """Closes the "inject raw ANSI escapes as a style" path -- style
    must be an engine.ansi.Style instance, never a string.
    """
    world, _, _ = make_world()
    source = "echo('x', '\\x1b[31m')"
    with pytest.raises(ScriptAPIError):
        world.load_script(source)


def test_set_var_and_get_var_round_trip():
    world, _, _ = make_world()
    world.load_script("set_var('hp', 42)\nresult = get_var('hp')")
    assert world.variables["hp"] == 42


def test_get_var_default_when_missing():
    world, _, echoed = make_world()
    world.load_script("echo(str(get_var('missing', 'fallback')))")
    assert echoed == [("fallback", None)]


def test_set_var_rejects_non_json_serializable_value():
    """A function object (like the injected get_var itself) isn't
    JSON-serializable -- set_var() must reject it rather than silently
    storing a live reference that could smuggle code through storage.
    """
    world, _, _ = make_world()
    with pytest.raises(ScriptAPIError):
        world.load_script("set_var('x', get_var)")


def test_timer_accepts_valid_delay_and_script_owned_callback():
    world, _, _ = make_world()
    world.load_script("def cb():\n    pass\ntimer(5, cb)\n")
    assert len(world.pending_timers) == 1
    assert world.pending_timers[0].delay_seconds == 5


@pytest.mark.parametrize("bad_delay", [0, -1, 86401, "5", True])
def test_timer_rejects_out_of_range_or_wrong_type_delay(bad_delay):
    world, _, _ = make_world()
    source = f"def cb():\n    pass\ntimer({bad_delay!r}, cb)\n"
    with pytest.raises(ScriptAPIError):
        world.load_script(source)


def test_timer_rejects_non_script_owned_callback():
    """timer() must reject a builtin/external reference -- only a
    function actually defined inside this same script is acceptable.
    """
    world, _, _ = make_world()
    with pytest.raises(ScriptAPIError):
        world.load_script("timer(5, len)")


def test_timer_enforces_outstanding_cap():
    world, _, _ = make_world()
    lines = ["def cb():\n    pass"]
    lines += [f"timer(1, cb)" for _ in range(101)]
    source = "\n".join(lines)
    with pytest.raises(ScriptAPIError):
        world.load_script(source)


def test_on_trigger_registers_and_fires_on_matching_text():
    world, sent, _ = make_world()
    source = (
        "def handle(match):\n"
        "    send('triggered')\n"
        "on_trigger('You found gold', handle)\n"
    )
    world.load_script(source)
    outcome = world.triggers.dispatch("You found gold on the ground.")
    assert sent == ["triggered"]
    assert outcome.matched_triggers


def test_on_trigger_rejects_non_script_owned_callback():
    world, _, _ = make_world()
    with pytest.raises(ScriptAPIError):
        world.load_script("on_trigger('x', len)")


def test_gag_suppresses_matched_line():
    world, _, _ = make_world()
    source = (
        "def handle(match):\n"
        "    gag()\n"
        "on_trigger('spam', handle)\n"
    )
    world.load_script(source)
    outcome = world.triggers.dispatch("this is spam text")
    assert outcome.gagged is True


def test_highlight_records_style_and_span():
    world, _, _ = make_world()
    source = (
        "def handle(match):\n"
        "    highlight(Style(bold=True))\n"
        "on_trigger('gold', handle)\n"
    )
    world.load_script(source)
    outcome = world.triggers.dispatch("you see gold here")
    assert outcome.highlights == [((8, 12), Style(bold=True))]


def test_gag_outside_trigger_context_raises():
    from engine.scripting.triggers import gag_api

    with pytest.raises(ScriptAPIError):
        gag_api()


def test_on_connect_registers_and_fires():
    world, sent, _ = make_world()
    source = (
        "def hello():\n"
        "    send('connected!')\n"
        "on_connect(hello)\n"
    )
    world.load_script(source)
    world.fire_connect_callbacks()
    assert sent == ["connected!"]


def test_callback_from_a_different_world_is_rejected():
    """A function defined in world A's script must not be usable as a
    callback in world B -- identity-based ownership, not name-based.
    """
    world_a, _, _ = make_world()
    world_a.load_script("def cb():\n    pass\n")
    stolen_callback = world_a._script_globals[0]["cb"]

    world_b, _, _ = make_world()  # world_b has no scripts loaded of its own
    with pytest.raises(ScriptAPIError):
        world_b._require_script_owned_callable(stolen_callback, "on_connect()")
