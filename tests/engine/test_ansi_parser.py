"""Headless tests for the ANSI/xterm-256 SGR parser -- no live server or
GUI needed, per CLAUDE.md's testing philosophy.
"""

from engine.ansi import AnsiParser, DEFAULT_STYLE, Style


def test_plain_text_has_default_style():
    parser = AnsiParser()
    segments = parser.feed("hello world")
    assert segments == [("hello world", DEFAULT_STYLE)]


def test_bold_and_reset():
    parser = AnsiParser()
    segments = parser.feed("\x1b[1mBOLD\x1b[0mnormal")
    assert segments[0] == ("BOLD", Style(bold=True))
    assert segments[1] == ("normal", DEFAULT_STYLE)


def test_basic_foreground_color():
    parser = AnsiParser()
    segments = parser.feed("\x1b[31mred text\x1b[0m")
    assert segments[0].text == "red text"
    assert segments[0].style.fg == (205, 0, 0)


def test_bright_background_color():
    parser = AnsiParser()
    segments = parser.feed("\x1b[100mbg\x1b[0m")
    assert segments[0].style.bg == (127, 127, 127)


def test_xterm_256_color():
    parser = AnsiParser()
    segments = parser.feed("\x1b[38;5;196mfire\x1b[0m")
    assert segments[0].style.fg == (255, 0, 0)


def test_truecolor():
    parser = AnsiParser()
    segments = parser.feed("\x1b[38;2;10;20;30mtruecolor\x1b[0m")
    assert segments[0].style.fg == (10, 20, 30)


def test_combined_attributes_persist_until_changed():
    parser = AnsiParser()
    first = parser.feed("\x1b[1;31mBoldRed")
    assert first[0].style == Style(bold=True, fg=(205, 0, 0))

    more = parser.feed(" still bold red")
    assert more[0].style == Style(bold=True, fg=(205, 0, 0))


def test_escape_sequence_split_across_feed_calls():
    parser = AnsiParser()
    first = parser.feed("plain \x1b[3")
    assert first == [("plain ", DEFAULT_STYLE)]

    second = parser.feed("1mred\x1b[0m")
    assert second[0].text == "red"
    assert second[0].style.fg == (205, 0, 0)


def test_unknown_csi_sequence_is_dropped_not_rendered():
    parser = AnsiParser()
    # Cursor-position / clear-screen sequence; should vanish, not print.
    segments = parser.feed("before\x1b[2Jafter")
    assert segments == [("before", DEFAULT_STYLE), ("after", DEFAULT_STYLE)]


def test_malformed_escape_does_not_crash_or_hang():
    parser = AnsiParser()
    segments = parser.feed("weird\x1b\x07text")
    joined = "".join(segment.text for segment in segments)
    assert "weird" in joined
    assert "text" in joined


# -- DEC private-mode CSI + OSC sequences (post-SSH-feature fix) --------
# A real bash session over SSH sends these constantly (bracketed-paste-
# mode toggling, window-title-setting); a MU* server never does. Found
# by Rick testing real SSH output, not theoretical -- these used to
# leak through as literal visible text.


def test_dec_private_mode_sequence_is_dropped_not_rendered():
    # Bracketed paste mode on/off, exactly as bash sends it.
    segments = AnsiParser().feed("before\x1b[?2004hafter")
    assert segments == [("before", DEFAULT_STYLE), ("after", DEFAULT_STYLE)]

    segments = AnsiParser().feed("before\x1b[?2004lafter")
    assert segments == [("before", DEFAULT_STYLE), ("after", DEFAULT_STYLE)]


def test_dec_private_mode_sequence_split_across_feed_calls():
    parser = AnsiParser()
    first = parser.feed("plain \x1b[?20")
    assert first == [("plain ", DEFAULT_STYLE)]

    second = parser.feed("04hmore")
    assert second == [("more", DEFAULT_STYLE)]


def test_osc_window_title_bel_terminated_is_dropped():
    # Real bash window-title sequence: ESC ] 0 ; text BEL.
    segments = AnsiParser().feed("before\x1b]0;rick@n0njy: ~\x07after")
    assert segments == [("before", DEFAULT_STYLE), ("after", DEFAULT_STYLE)]


def test_osc_sequence_st_terminated_is_dropped():
    # The formal String Terminator form (ESC \) instead of BEL.
    segments = AnsiParser().feed("before\x1b]0;title\x1b\\after")
    assert segments == [("before", DEFAULT_STYLE), ("after", DEFAULT_STYLE)]


def test_osc_sequence_st_terminated_split_right_at_the_terminator():
    # The ESC of the ST terminator arrives in one chunk, the closing
    # backslash (and more text) in the next -- must not be misdetected
    # as a complete, differently-shaped sequence nor left stuck pending.
    parser = AnsiParser()
    first = parser.feed("plain \x1b]0;title\x1b")
    assert first == [("plain ", DEFAULT_STYLE)]

    second = parser.feed("\\after")
    assert second == [("after", DEFAULT_STYLE)]


def test_osc_sequence_split_across_feed_calls():
    parser = AnsiParser()
    first = parser.feed("plain \x1b]0;rick@n0")
    assert first == [("plain ", DEFAULT_STYLE)]

    second = parser.feed("njy: ~\x07more")
    assert second == [("more", DEFAULT_STYLE)]


def test_real_bash_ssh_output_renders_only_the_actual_prompt_text():
    # The exact real-world sequence Rick reported seeing leak through
    # over a real SSH connection -- bracketed-paste-mode on, a window-
    # title OSC sequence, then the actual bash prompt text.
    raw = "\x1b[?2004h\x1b]0;rick@n0njy: ~\x07rick@n0njy:~$ "
    segments = AnsiParser().feed(raw)
    joined = "".join(segment.text for segment in segments)
    assert joined == "rick@n0njy:~$ "


def test_dec_private_mode_does_not_affect_sgr_style_state():
    # A private-mode sequence must not disturb SGR style tracking --
    # bold-then-private-mode-then-more-text should still be bold.
    parser = AnsiParser()
    segments = parser.feed("\x1b[1mbold\x1b[?25lstill bold")
    assert segments[0].style == Style(bold=True)
    assert segments[1].style == Style(bold=True)
    assert "".join(s.text for s in segments) == "boldstill bold"
