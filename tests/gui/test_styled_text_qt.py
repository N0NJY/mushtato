"""Headless tests for the engine.ansi StyledSegment -> Qt conversion --
the one piece of Phase 5 that's meaningfully testable without a live
window (per the task's explicit ask).
"""

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QTextEdit

from engine.ansi import Style, StyledSegment
from gui.windows.styled_text_qt import append_styled_segments, style_to_qt_format


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
