"""Headless tests for AliasEngine: outbound user-input expansion
(TinyFugue/Potato-style command aliases).
"""

import time

import pytest

from engine.scripting.aliases import Alias, AliasEngine
from engine.scripting.errors import ScriptAPIError
from engine.scripting.world import ScriptWorld


def make_world():
    sent = []
    world = ScriptWorld(
        send=lambda text: sent.append(text),
        echo=lambda text, style=None: None,
    )
    return world, sent


def test_exact_alias_expands_to_a_different_command():
    world, sent = make_world()
    world.load_script("on_alias('n', lambda m: send('north'), name='n')")
    outcome = world.aliases.expand("n")
    assert outcome.matched is True
    assert outcome.alias_name == "n"
    assert sent == ["north"]


def test_fullmatch_does_not_fire_on_substring():
    """The core correctness property of using fullmatch: a pattern for
    "n" must not fire on "nonsense" or "next" the way a substring
    search would.
    """
    world, sent = make_world()
    world.load_script("on_alias('n', lambda m: send('north'))")

    outcome = world.aliases.expand("nonsense")

    assert outcome.matched is False
    assert sent == []


def test_no_match_falls_back_signal():
    world, _ = make_world()
    world.load_script("on_alias('n', lambda m: send('north'))")
    outcome = world.aliases.expand("look")
    assert outcome.matched is False
    assert outcome.alias_name is None


def test_leading_and_trailing_whitespace_is_stripped_before_matching():
    world, sent = make_world()
    world.load_script("on_alias('n', lambda m: send('north'))")
    outcome = world.aliases.expand("  n  ")
    assert outcome.matched is True
    assert sent == ["north"]


def test_capture_groups_support_argument_substitution():
    world, sent = make_world()
    source = (
        "def give(match):\n"
        "    send('give ' + match.group('item') + ' to ' + match.group('target'))\n"
        "on_alias(r'gt (?P<item>\\S+) (?P<target>\\S+)', give)\n"
    )
    world.load_script(source)
    outcome = world.aliases.expand("gt sword bob")
    assert outcome.matched is True
    assert sent == ["give sword to bob"]


def test_callback_can_send_multiple_commands():
    world, sent = make_world()
    source = (
        "def combo(match):\n"
        "    send('wield sword')\n"
        "    send('wear shield')\n"
        "on_alias('combo', combo)\n"
    )
    world.load_script(source)
    world.aliases.expand("combo")
    assert sent == ["wield sword", "wear shield"]


def test_first_match_wins_by_priority():
    world, sent = make_world()
    source = (
        "def specific(match):\n"
        "    send('specific handled it')\n"
        "def broad(match):\n"
        "    send('broad handled it')\n"
        "on_alias('.*', broad, priority=0)\n"
        "on_alias('go', specific, priority=10)\n"
    )
    world.load_script(source)
    outcome = world.aliases.expand("go")
    assert outcome.alias_name == "specific"
    assert sent == ["specific handled it"]


def test_send_is_never_reprocessed_through_alias_expansion():
    """An alias's callback calling send() must not recursively trigger
    another (or the same) alias -- this is true by construction (send()
    and expand() are different layers), proven here by registering a
    second alias whose pattern would match what the first callback
    sends, and confirming it never fires as a side effect.
    """
    world, sent = make_world()
    source = (
        "def first(match):\n"
        "    send('second')\n"
        "def second(match):\n"
        "    send('should not run')\n"
        "on_alias('first', first)\n"
        "on_alias('second', second)\n"
    )
    world.load_script(source)
    world.aliases.expand("first")
    assert sent == ["second"]


def test_disabled_alias_is_skipped():
    calls = []
    engine = AliasEngine()
    engine.add(Alias(name="n", pattern="n", callback=lambda m: calls.append(m), enabled=False))
    outcome = engine.expand("n")
    assert outcome.matched is False
    assert calls == []


def test_on_alias_rejects_non_script_owned_callback():
    world, _ = make_world()
    with pytest.raises(ScriptAPIError):
        world.load_script("on_alias('x', len)")


def test_invalid_alias_pattern_raises_script_api_error():
    with pytest.raises(ScriptAPIError):
        Alias(name="bad", pattern="(unclosed", callback=lambda m: None)


def test_lookahead_pattern_is_rejected_at_registration_time():
    with pytest.raises(ScriptAPIError):
        Alias(name="bad", pattern="foo(?=bar)", callback=lambda m: None)


def test_catastrophic_backtracking_alias_pattern_does_not_hang():
    engine = AliasEngine()
    engine.add(Alias(name="redos", pattern=r"(a+)+$", callback=lambda m: None))

    pathological_text = "a" * 40 + "!"  # deliberately doesn't match

    start = time.monotonic()
    engine.expand(pathological_text)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"alias expansion took {elapsed}s -- RE2 should be near-instant"
