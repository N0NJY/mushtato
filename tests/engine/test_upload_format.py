"""Headless tests for engine/upload_format.py -- the pure per-line
Upload logic (Ignore Empty Lines, Prefix, and the MPP-Formatted
continuation/escaping convention), modeled on Potato's real
uploadBegin. Traces below are worked by hand against the verified
Tcl source, not just asserted against whatever the implementation
happens to produce.
"""

from engine.upload_format import UploadOptions, UploadStepper, delay_ms, escape_mpp


def test_delay_ms_matches_potatos_rounding():
    assert delay_ms(0.0) == 0
    assert delay_ms(0.5) == 500
    assert delay_ms(1.25) == 1250


def test_escape_mpp_maps_every_special_character():
    assert escape_mpp("a b") == "a%bb"
    assert escape_mpp("a\tb") == "a%tb"
    assert escape_mpp("100%") == "100\\%"
    assert escape_mpp("a;b") == "a\\;b"
    assert escape_mpp("[x]") == "\\[x\\]"
    assert escape_mpp("(x)") == "\\(x\\)"
    assert escape_mpp("a,b") == "a\\,b"
    assert escape_mpp("a^b") == "a\\^b"
    assert escape_mpp("a$b") == "a\\$b"
    assert escape_mpp("{x}") == "\\{x\\}"
    assert escape_mpp("a\\b") == "a\\\\b"


def test_escape_mpp_does_not_double_escape_inserted_backslashes():
    # A naive sequence of .replace() calls (escape backslash last) would
    # re-escape the backslash this function itself just inserted for
    # "%". Single left-to-right pass over the ORIGINAL text avoids that.
    assert escape_mpp("%") == "\\%"


def test_plain_mode_ignores_empty_lines_by_default():
    options = UploadOptions()
    stepper = UploadStepper(["one", "", "two"], options)

    assert stepper.step().send_text == "one"
    assert stepper.step().send_text is None  # blank line skipped
    step = stepper.step()
    assert step.send_text == "two"
    assert step.done is False  # last real line consumed, EOF not detected until the next step
    final = stepper.step()
    assert final.send_text is None
    assert final.done is True


def test_plain_mode_sends_empty_lines_when_ignore_empty_is_off():
    options = UploadOptions(ignore_empty=False)
    stepper = UploadStepper(["one", "", "two"], options)

    assert stepper.step().send_text == "one"
    assert stepper.step().send_text == ""
    assert stepper.step().send_text == "two"


def test_prefix_applied_to_every_sent_line():
    options = UploadOptions(prefix="say ")
    stepper = UploadStepper(["hello", "world"], options)

    assert stepper.step().send_text == "say hello"
    assert stepper.step().send_text == "say world"


def test_after_eof_further_steps_return_done_with_no_send():
    # Mirrors Potato's own tick-based uploadBegin: the tick that
    # consumes the last real line doesn't yet know it was the last one
    # (done stays False); the *next* tick is what detects EOF.
    stepper = UploadStepper(["only"], UploadOptions())
    first = stepper.step()
    assert first.send_text == "only"
    assert first.done is False
    second = stepper.step()
    assert second.send_text is None
    assert second.done is True
    third = stepper.step()  # already done -- stays done, doesn't crash or re-send
    assert third.send_text is None
    assert third.done is True


def test_total_lines_and_byte_progress_tracking():
    stepper = UploadStepper(["ab", "cde"], UploadOptions())
    assert stepper.total_lines == 2
    assert stepper.total_bytes == len(b"ab") + 1 + len(b"cde") + 1
    assert stepper.bytes_consumed == 0
    stepper.step()
    assert stepper.bytes_consumed == len(b"ab") + 1
    stepper.step()
    assert stepper.bytes_consumed == stepper.total_bytes


def test_mpp_comment_and_blank_lines_are_skipped():
    lines = ["@@ a comment", "   ", "next"]
    stepper = UploadStepper(lines, UploadOptions(mpp_formatted=True))

    assert stepper.step().send_text is None  # "@@..." comment
    assert stepper.step().send_text is None  # whitespace-only
    step = stepper.step()
    assert step.send_text is None  # "next" just starts a fresh buffer
    final = stepper.step()  # EOF -- flush the buffered "next"
    assert final.send_text == "next"
    assert final.done is True


def test_mpp_formatted_continuation_joins_and_escapes():
    # Worked by hand against potato.tcl's uploadBegin:
    # "first" starts a buffer (gt=1); the first ">" line right after it
    # gets no "%r" separator (gt consumed), its content IS escaped;
    # subsequent ">" lines DO get "%r" first; a space/tab-prefixed line
    # is an unformatted continuation appended raw with NO separator;
    # the next plain line flushes everything accumulated so far.
    lines = [
        "first",
        ">line one",
        ">line two",
        " continued unformatted",
        "another",
    ]
    stepper = UploadStepper(lines, UploadOptions(mpp_formatted=True))

    assert stepper.step().send_text is None  # "first" -- starts the buffer
    assert stepper.step().send_text is None  # ">line one" -- buffered, no separator (gt consumed)
    assert stepper.step().send_text is None  # ">line two" -- buffered with "%r" separator
    assert stepper.step().send_text is None  # unformatted continuation -- appended raw
    step = stepper.step()  # "another" -- flushes everything buffered so far
    assert step.send_text == "firstline%bone%rline%btwocontinued unformatted"

    final = stepper.step()  # EOF -- flush the new buffer started by "another"
    assert final.send_text == "another"
    assert final.done is True


def test_mpp_eof_flush_applies_prefix_a_deliberate_fix_over_potato():
    # Potato's own uploadBegin does NOT apply the configured prefix to
    # the final EOF-triggered buffer flush (every other send in the
    # same proc does) -- almost certainly an oversight there. This
    # module applies it uniformly instead; see the module docstring.
    #
    # Also exercises a genuine Potato quirk, verified directly rather
    # than assumed away: mpp,gt starts at 0 (false), so a file whose
    # very first line is already ">"-prefixed still gets a leading
    # "%r" prepended (the "else prepend %r" branch fires even though
    # the buffer is empty) -- not something worth "fixing" since it's
    # a faithful, verified reproduction of the real behavior.
    stepper = UploadStepper([">only"], UploadOptions(mpp_formatted=True, prefix=">> "))
    stepper.step()  # buffers "%r" + escaped "only"
    final = stepper.step()  # EOF flush
    assert final.send_text == ">> %ronly"
    assert final.done is True


def test_mpp_mode_ignores_ignore_empty_flag_for_its_own_blank_handling():
    # MPP mode's blank/comment skipping is unconditional -- ignore_empty
    # only affects the plain (non-MPP) branch.
    stepper = UploadStepper(["", "data"], UploadOptions(mpp_formatted=True, ignore_empty=False))
    assert stepper.step().send_text is None
    step = stepper.step()
    assert step.send_text is None  # "data" just starts a buffer
    final = stepper.step()
    assert final.send_text == "data"
