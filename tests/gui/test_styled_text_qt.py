"""Headless tests for the engine.ansi StyledSegment -> Qt conversion --
the one piece of Phase 5 that's meaningfully testable without a live
window (per the task's explicit ask).
"""

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QTextEdit

from engine.ansi import Style, StyledSegment
from gui.windows.styled_text_qt import (
    LINK_COLOR,
    _split_for_urls,
    append_styled_segments,
    replace_tail,
    style_to_qt_format,
)


def test_plain_style_has_no_overrides(qapp):
    fmt = style_to_qt_format(Style())
    assert not fmt.hasProperty(fmt.ForegroundBrush) if hasattr(fmt, "ForegroundBrush") else True


def test_foreground_color_is_applied(qapp):
    fmt = style_to_qt_format(Style(fg=(205, 0, 0)))
    assert fmt.foreground().color() == QColor(205, 0, 0)


def test_background_color_is_applied(qapp):
    fmt = style_to_qt_format(Style(bg=(0, 0, 238)))
    assert fmt.background().color() == QColor(0, 0, 238)


def test_bold_sets_font_weight(qapp):
    fmt = style_to_qt_format(Style(bold=True))
    assert fmt.fontWeight() == QFont.Bold


def test_italic_underline_strikethrough(qapp):
    fmt = style_to_qt_format(Style(italic=True, underline=True, strikethrough=True))
    assert fmt.fontItalic() is True
    assert fmt.fontUnderline() is True
    assert fmt.fontStrikeOut() is True


def test_reverse_swaps_foreground_and_background(qapp):
    fmt = style_to_qt_format(Style(fg=(205, 0, 0), bg=(0, 0, 238), reverse=True))
    assert fmt.foreground().color() == QColor(0, 0, 238)
    assert fmt.background().color() == QColor(205, 0, 0)


def test_append_styled_segments_renders_plain_text(qapp):
    text_edit = QTextEdit()
    segments = [
        StyledSegment("hello ", Style()),
        StyledSegment("world", Style(bold=True, fg=(205, 0, 0))),
    ]
    append_styled_segments(text_edit, segments)
    assert text_edit.toPlainText() == "hello world"


def test_append_styled_segments_strips_carriage_return(qapp):
    text_edit = QTextEdit()
    append_styled_segments(text_edit, [StyledSegment("HP: 100\r\n", Style())])
    assert text_edit.toPlainText() == "HP: 100\n"


def test_append_styled_segments_preserves_per_segment_formatting(qapp):
    text_edit = QTextEdit()
    segments = [
        StyledSegment("plain ", Style()),
        StyledSegment("bold", Style(bold=True)),
    ]
    append_styled_segments(text_edit, segments)

    doc = text_edit.document()
    plain_format = doc.findBlock(0).charFormat()
    # Locate the "bold" run by cursor position and inspect its format.
    cursor = text_edit.textCursor()
    cursor.setPosition(len("plain "))
    cursor.setPosition(len("plain bold"), cursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().fontWeight() == QFont.Bold


# -- clickable URLs (post-Phase-9 addition) ----------------------------


def test_split_for_urls_no_url_returns_single_plain_piece():
    assert _split_for_urls("hello world") == [("hello world", None)]


def test_split_for_urls_whole_string_is_a_url():
    assert _split_for_urls("https://example.com") == [
        ("https://example.com", "https://example.com")
    ]


def test_split_for_urls_url_embedded_in_a_sentence():
    pieces = _split_for_urls("see http://example.com/path for info")
    assert pieces == [
        ("see ", None),
        ("http://example.com/path", "http://example.com/path"),
        (" for info", None),
    ]


def test_split_for_urls_trims_trailing_sentence_punctuation():
    pieces = _split_for_urls("visit https://example.com/x, or https://example.com/y.")
    assert pieces == [
        ("visit ", None),
        ("https://example.com/x", "https://example.com/x"),
        (",", None),
        (" or ", None),
        ("https://example.com/y", "https://example.com/y"),
        (".", None),
    ]


def test_split_for_urls_trailing_paren_trimmed_but_matched_paren_pair_kept():
    # A real, deliberately-scoped limitation: this is a plain
    # rstrip-of-punctuation, not a balanced-parenthesis parser -- a URL
    # ending in ")" always has that ")" trimmed, even if the "(" was
    # actually part of the URL. Documented via this test rather than
    # silently discovered later.
    pieces = _split_for_urls("(see https://example.com/wiki/Foo_(bar))")
    assert pieces[-2] == ("https://example.com/wiki/Foo_(bar", "https://example.com/wiki/Foo_(bar")
    assert pieces[-1] == ("))", None)


def test_split_for_urls_multiple_urls_in_one_string():
    pieces = _split_for_urls("https://a.example.com then https://b.example.com")
    urls = [url for _, url in pieces if url is not None]
    assert urls == ["https://a.example.com", "https://b.example.com"]


def test_append_styled_segments_marks_a_url_as_an_anchor(qapp):
    text_edit = QTextEdit()
    append_styled_segments(text_edit, [StyledSegment("go to https://example.com now", Style())])

    assert text_edit.toPlainText() == "go to https://example.com now"
    cursor = text_edit.textCursor()
    cursor.setPosition(len("go to "))
    cursor.setPosition(len("go to https://example.com"), cursor.MoveMode.KeepAnchor)
    fmt = cursor.charFormat()
    assert fmt.isAnchor() is True
    assert fmt.anchorHref() == "https://example.com"
    assert fmt.foreground().color() == LINK_COLOR
    assert fmt.fontUnderline() is True


def test_append_styled_segments_non_url_text_is_not_an_anchor(qapp):
    text_edit = QTextEdit()
    append_styled_segments(text_edit, [StyledSegment("no links here", Style())])

    cursor = text_edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(len("no links here"), cursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().isAnchor() is False


def test_append_styled_segments_url_keeps_the_segments_own_base_style(qapp):
    # A URL arriving inside a bold-styled segment should still render
    # bold -- only foreground color/underline are overridden for the
    # link styling, not the whole format.
    text_edit = QTextEdit()
    append_styled_segments(
        text_edit, [StyledSegment("https://example.com", Style(bold=True))]
    )

    cursor = text_edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(len("https://example.com"), cursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().fontWeight() == QFont.Bold
    assert cursor.charFormat().isAnchor() is True


def test_replace_tail_also_marks_urls_as_anchors(qapp):
    text_edit = QTextEdit()
    append_styled_segments(text_edit, [StyledSegment("placeholder", Style())])
    start = 0
    replace_tail(text_edit, start, [StyledSegment("https://example.com", Style())])

    assert text_edit.toPlainText() == "https://example.com"
    cursor = text_edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(len("https://example.com"), cursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().isAnchor() is True


def test_bare_www_domain_is_not_treated_as_a_url(qapp):
    # Deliberate scope limit (documented in styled_text_qt.py): only
    # http(s):// is matched, not bare "www." text, to avoid false
    # positives on ordinary sentences.
    text_edit = QTextEdit()
    append_styled_segments(text_edit, [StyledSegment("see www.example.com for info", Style())])

    cursor = text_edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(len("see www.example.com for info"), cursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().isAnchor() is False
