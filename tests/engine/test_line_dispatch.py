"""Headless tests for LineDispatcher: line-buffering + ANSI parsing +
trigger dispatch (gag/highlight) working together against realistic
chunked MUD output, including ANSI-colored fixtures. Also covers the
per-trigger auto-disable mechanism (engine/scripting/triggers.py).
"""

from engine.ansi import Style
from engine.scripting import ScriptWorld
from engine.scripting.line_dispatch import LineDispatcher
from engine.scripting.triggers import MAX_CONSECUTIVE_TRIGGER_FAILURES


def make_dispatcher(**world_kwargs):
    sent = []
    echoed = []
    world = ScriptWorld(
        send=lambda text: sent.append(text),
        echo=lambda text, style=None: echoed.append((text, style)),
        **world_kwargs,
    )
    dispatcher = LineDispatcher(world.triggers)
    return dispatcher, world, sent, echoed


def plain_text(segments):
    # Finalized (non-gagged) segments include their trailing "\n" back
    # (see LineDispatcher._finalize_pending_line's docstring) -- most
    # assertions care about content, not that terminator, so strip it
    # here; test_finalized_lines_include_their_trailing_newline below
    # explicitly proves the terminator is actually there.
    return "".join(seg.text for seg in segments).rstrip("\n")


# -- Basic line buffering -------------------------------------------------


def test_a_single_complete_line_is_finalized_immediately():
    dispatcher, _, _, _ = make_dispatcher()

    result = dispatcher.feed("You see a sword here.\n")

    assert len(result.finalized) == 1
    assert plain_text(result.finalized[0].segments) == "You see a sword here."
    assert result.preview is None


def test_a_line_split_across_two_chunks_only_finalizes_once_complete():
    dispatcher, _, _, _ = make_dispatcher()

    result1 = dispatcher.feed("You see a sw")
    assert result1.finalized == []
    assert plain_text(result1.preview) == "You see a sw"

    result2 = dispatcher.feed("ord here.\n")
    assert len(result2.finalized) == 1
    assert plain_text(result2.finalized[0].segments) == "You see a sword here."
    assert result2.preview is None


def test_multiple_complete_lines_in_one_chunk_all_finalize():
    dispatcher, _, _, _ = make_dispatcher()

    result = dispatcher.feed("first line\nsecond line\nthird line\n")

    assert [plain_text(f.segments) for f in result.finalized] == [
        "first line",
        "second line",
        "third line",
    ]
    assert result.preview is None


def test_trailing_incomplete_line_is_previewed_but_not_dispatched():
    from engine.scripting.triggers import Trigger

    dispatcher, world, _, _ = make_dispatcher()
    fired = []
    world.triggers.add(Trigger(name="hp", pattern="HP:", callback=lambda m: fired.append(True)))

    result = dispatcher.feed("HP: 100 MP: 50 > ")

    assert result.finalized == []
    assert plain_text(result.preview) == "HP: 100 MP: 50 > "
    assert fired == []  # never dispatched -- the line hasn't "arrived" yet


def test_finalized_lines_include_their_trailing_newline():
    # Real bug found and fixed while building this: _split_on_newlines
    # consumes "\n" as a pure delimiter (deliberately excluded from the
    # plain text used for trigger matching), but the *rendered*
    # segments need it back -- otherwise consecutive lines would run
    # together with no line break once inserted into a scrollback.
    dispatcher, _, _, _ = make_dispatcher()

    result = dispatcher.feed("first\nsecond\n")

    raw_texts = ["".join(seg.text for seg in f.segments) for f in result.finalized]
    assert raw_texts == ["first\n", "second\n"]


def test_a_gagged_line_has_no_newline_and_leaves_no_trace():
    dispatcher, world, _, _ = make_dispatcher()
    world.load_script("on_trigger('spam', lambda m: None, gag=True)", script_name="s1")

    result = dispatcher.feed("this is spam\n")

    assert result.finalized[0].segments == []


def test_an_empty_line_completes_correctly():
    dispatcher, _, _, _ = make_dispatcher()

    result = dispatcher.feed("one\n\ntwo\n")

    assert [plain_text(f.segments) for f in result.finalized] == ["one", "", "two"]


# -- ANSI styling survives line-splitting ---------------------------------


def test_ansi_colored_text_split_across_chunks_keeps_correct_style():
    dispatcher, _, _, _ = make_dispatcher()
    # Bold-red "Bob" then plain " says hello", split mid-escape-free text.
    dispatcher.feed("\x1b[1;31mBob\x1b[0m say")
    result = dispatcher.feed("s hello\n")

    segments = result.finalized[0].segments
    assert plain_text(segments) == "Bob says hello"
    bob_segment = segments[0]
    assert bob_segment.text == "Bob"
    assert bob_segment.style.bold is True
    assert bob_segment.style.fg == (205, 0, 0)  # basic_color(1), verified via engine.ansi.palette


# -- Gag ---------------------------------------------------------------


def test_gag_suppresses_the_line_entirely():
    dispatcher, world, _, _ = make_dispatcher()
    world.load_script("on_trigger('spam', lambda m: None, gag=True)", script_name="s1")

    result = dispatcher.feed("this is spam\n")

    assert len(result.finalized) == 1
    assert result.finalized[0].gagged is True
    assert result.finalized[0].segments == []


def test_non_matching_line_is_not_gagged():
    dispatcher, world, _, _ = make_dispatcher()
    world.load_script("on_trigger('spam', lambda m: None, gag=True)", script_name="s1")

    result = dispatcher.feed("this is fine\n")

    assert result.finalized[0].gagged is False
    assert plain_text(result.finalized[0].segments) == "this is fine"


# -- Highlight (the concrete motivating use case: speaker-name highlighting) --


def test_highlight_overrides_style_for_the_matched_span_only():
    from engine.scripting.triggers import Trigger

    dispatcher, world, _, _ = make_dispatcher()
    red = Style(fg=(255, 0, 0))
    world.triggers.add(
        Trigger(
            # RE2 doesn't support lookaround (engine/scripting/aliases.py's
            # module docstring notes this trade-off) -- a plain "^\w+"
            # already matches just the leading speaker name here, no
            # lookahead needed.
            name="speaker-highlight",
            pattern=r"^\w+",
            callback=lambda m: None,
            highlight_style=red,
        )
    )

    result = dispatcher.feed("Bob says hello\n")

    segments = result.finalized[0].segments
    assert plain_text(segments) == "Bob says hello"
    # "Bob" should be styled red; the rest should keep the default style.
    bob_part = next(s for s in segments if s.text == "Bob")
    rest_part = next(s for s in segments if "says hello" in s.text)
    assert bob_part.style == red
    assert rest_part.style != red


def test_highlight_on_ansi_colored_text_only_overrides_the_matched_characters():
    dispatcher, world, _, _ = make_dispatcher()
    highlight_style = Style(fg=(0, 255, 0), bold=True)
    from engine.scripting.triggers import Trigger

    world.triggers.add(
        Trigger(
            name="name-highlight",
            pattern="Bob",
            callback=lambda m: None,
            highlight_style=highlight_style,
        )
    )

    result = dispatcher.feed("\x1b[34msomething Bob said\x1b[0m\n")

    segments = result.finalized[0].segments
    assert plain_text(segments) == "something Bob said"
    bob_seg = next(s for s in segments if s.text == "Bob")
    assert bob_seg.style == highlight_style
    other_seg = next(s for s in segments if s.text != "Bob")
    assert other_seg.style.fg == (0, 0, 238)  # basic_color(4), verified via engine.ansi.palette


def test_higher_priority_highlight_wins_over_lower_priority_overlap():
    from engine.scripting.triggers import Trigger

    dispatcher, world, _, _ = make_dispatcher()
    low_style = Style(fg=(1, 1, 1))
    high_style = Style(fg=(2, 2, 2))
    world.triggers.add(
        Trigger(name="low", pattern="Bob says", callback=lambda m: None,
                highlight_style=low_style, priority=0)
    )
    world.triggers.add(
        Trigger(name="high", pattern="says hello", callback=lambda m: None,
                highlight_style=high_style, priority=10)
    )

    result = dispatcher.feed("Bob says hello\n")

    segments = result.finalized[0].segments
    # "low" covers "Bob says" (0,8), "high" covers "says hello" (4,14)
    # -- they overlap on "says" (4,8). Applying high last (see
    # _apply_highlights' reversed-order docstring) means that overlap,
    # plus everything else "high" covers, ends up styled high_style;
    # only the non-overlapping "Bob " prefix keeps low_style.
    assert plain_text(segments) == "Bob says hello"
    bob_seg = next(s for s in segments if s.text == "Bob ")
    # The trailing "\n" (re-attached to the last segment when the line
    # finalizes) makes this "says hello\n", not "says hello".
    says_hello_seg = next(s for s in segments if s.text == "says hello\n")
    assert bob_seg.style == low_style
    assert says_hello_seg.style == high_style


# -- Per-trigger auto-disable after repeated failures ---------------------


def test_trigger_disabled_after_max_consecutive_failures():
    from engine.scripting.triggers import Trigger

    dispatcher, world, _, _ = make_dispatcher()

    def boom(m):
        raise ValueError("boom")

    trigger = Trigger(name="broken", pattern="fail", callback=boom)
    world.triggers.add(trigger)

    last_result = None
    for _ in range(MAX_CONSECUTIVE_TRIGGER_FAILURES):
        last_result = dispatcher.feed("fail\n")

    assert trigger.enabled is False
    assert trigger.consecutive_failures == MAX_CONSECUTIVE_TRIGGER_FAILURES
    assert "broken" in last_result.finalized[-1].outcome.disabled_triggers


def test_trigger_error_is_reported_but_does_not_raise():
    from engine.scripting.triggers import Trigger

    dispatcher, world, _, _ = make_dispatcher()

    def boom(m):
        raise ValueError("boom")

    world.triggers.add(Trigger(name="broken", pattern="fail", callback=boom))

    result = dispatcher.feed("fail\n")

    assert result.finalized[0].outcome.errors == [("broken", "ValueError: boom")]


def test_success_resets_the_consecutive_failure_counter():
    from engine.scripting.triggers import Trigger

    dispatcher, world, _, _ = make_dispatcher()
    calls = {"n": 0}

    def sometimes_fails(m):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ValueError("boom")

    trigger = Trigger(name="flaky", pattern="fail", callback=sometimes_fails)
    world.triggers.add(trigger)

    dispatcher.feed("fail\n")
    dispatcher.feed("fail\n")
    assert trigger.consecutive_failures == 2

    dispatcher.feed("fail\n")  # third call succeeds (calls["n"] == 3)
    assert trigger.consecutive_failures == 0
    assert trigger.enabled is True


def test_other_triggers_in_the_same_script_are_unaffected_by_one_disabling():
    from engine.scripting.triggers import Trigger

    dispatcher, world, _, _ = make_dispatcher()

    def boom(m):
        raise ValueError("boom")

    broken = Trigger(name="broken", pattern="fail", callback=boom, source_script="s1")
    healthy = Trigger(name="healthy", pattern="ok", callback=lambda m: None, source_script="s1")
    world.triggers.add(broken)
    world.triggers.add(healthy)

    for _ in range(MAX_CONSECUTIVE_TRIGGER_FAILURES):
        dispatcher.feed("fail\n")

    assert broken.enabled is False
    assert healthy.enabled is True
    result = dispatcher.feed("ok\n")
    assert result.finalized[0].outcome.matched_triggers == ["healthy"]
