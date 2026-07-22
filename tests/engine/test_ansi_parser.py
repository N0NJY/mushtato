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
