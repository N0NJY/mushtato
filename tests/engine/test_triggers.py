"""Headless tests for TriggerTable: RE2-based pattern matching, gag/
highlight outcomes, and priority ordering.
"""

import time

import pytest

from engine.scripting.errors import ScriptAPIError
from engine.scripting.triggers import Trigger, TriggerTable, gag_api


def test_matching_trigger_fires_callback():
    calls = []
    table = TriggerTable()
    table.add(Trigger(name="t1", pattern="gold", callback=lambda m: calls.append(m.group(0))))

    outcome = table.dispatch("You found 42 gold coins.")

    assert calls == ["gold"]
    assert outcome.matched_triggers == ["t1"]


def test_non_matching_trigger_does_not_fire():
    calls = []
    table = TriggerTable()
    table.add(Trigger(name="t1", pattern="silver", callback=lambda m: calls.append(m)))

    outcome = table.dispatch("You found 42 gold coins.")

    assert calls == []
    assert outcome.matched_triggers == []


def test_disabled_trigger_is_skipped():
    calls = []
    table = TriggerTable()
    table.add(Trigger(name="t1", pattern="gold", callback=lambda m: calls.append(m), enabled=False))

    table.dispatch("gold gold gold")

    assert calls == []


def test_priority_controls_dispatch_order():
    order = []
    table = TriggerTable()
    table.add(Trigger(name="low", pattern="gold", callback=lambda m: order.append("low"), priority=0))
    table.add(Trigger(name="high", pattern="gold", callback=lambda m: order.append("high"), priority=10))

    table.dispatch("gold")

    assert order == ["high", "low"]


def test_declarative_gag_flag_gags_without_calling_gag_function():
    table = TriggerTable()
    table.add(Trigger(name="t1", pattern="spam", callback=lambda m: None, gag=True))

    outcome = table.dispatch("this is spam")

    assert outcome.gagged is True


def test_invalid_trigger_pattern_raises_script_api_error():
    with pytest.raises(ScriptAPIError):
        Trigger(name="bad", pattern="(unclosed", callback=lambda m: None)


def test_lookahead_pattern_is_rejected_at_registration_time():
    """RE2 doesn't support lookaround -- confirms it fails loud (at
    Trigger construction) rather than silently misbehaving later.
    """
    with pytest.raises(ScriptAPIError):
        Trigger(name="bad", pattern="foo(?=bar)", callback=lambda m: None)


def test_catastrophic_backtracking_pattern_does_not_hang():
    """The whole point of choosing RE2 for trigger patterns: a
    pattern that would take stdlib re an exponential amount of time
    (or effectively forever) on adversarial input must still resolve
    near-instantly here.
    """
    table = TriggerTable()
    table.add(Trigger(name="redos", pattern=r"(a+)+$", callback=lambda m: None))

    pathological_text = "a" * 40 + "!"  # deliberately doesn't match, worst case for backtracking

    start = time.monotonic()
    table.dispatch(pathological_text)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"trigger dispatch took {elapsed}s -- RE2 should be near-instant"


def test_gag_outside_dispatch_raises():
    with pytest.raises(ScriptAPIError):
        gag_api()
