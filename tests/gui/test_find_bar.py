"""Headless tests for the Find/Search bar (Phase 11).

Highlights are asserted via QTextEdit.extraSelections() (a
non-destructive overlay -- see find_bar.py's module docstring for why
this, not cursor.setCharFormat(), is used), and via toPlainText() to
confirm the underlying document is never altered by searching.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QTextEdit

from gui.windows.find_bar import CURRENT_MATCH_COLOR, MATCH_COLOR, FindBar


def make_bar(text: str) -> tuple[FindBar, QTextEdit]:
    widget = QTextEdit()
    widget.setPlainText(text)
    bar = FindBar(widget)
    return bar, widget


def test_bar_is_hidden_until_opened(qapp):
    bar, _ = make_bar("hello world")
    assert bar.isVisible() is False
    bar.open_bar()
    assert bar.isVisible() is True


def test_search_finds_all_matches_and_highlights_them(qapp):
    bar, widget = make_bar("the cat sat on the mat, the cat ran")
    bar.search_field.setText("cat")

    assert len(bar._matches) == 2
    assert len(widget.extraSelections()) == 2
    assert bar.match_label.text() == "Match 1 of 2"


def test_search_does_not_alter_the_underlying_document(qapp):
    bar, widget = make_bar("the cat sat")
    original = widget.toPlainText()
    bar.search_field.setText("cat")
    assert widget.toPlainText() == original


def test_current_match_is_colored_differently_from_other_matches(qapp):
    bar, widget = make_bar("cat cat cat")
    bar.search_field.setText("cat")

    selections = widget.extraSelections()
    colors = [sel.format.background().color() for sel in selections]
    assert colors.count(CURRENT_MATCH_COLOR) == 1
    assert colors.count(MATCH_COLOR) == 2


def test_next_and_prev_wrap_around(qapp):
    bar, _ = make_bar("cat cat cat")
    bar.search_field.setText("cat")
    assert bar._current_index == 0

    bar.next_match()
    assert bar._current_index == 1
    bar.next_match()
    assert bar._current_index == 2
    bar.next_match()  # wraps to first
    assert bar._current_index == 0

    bar.prev_match()  # wraps to last
    assert bar._current_index == 2


def test_match_counter_updates_on_navigation(qapp):
    bar, _ = make_bar("cat cat cat")
    bar.search_field.setText("cat")
    assert bar.match_label.text() == "Match 1 of 3"
    bar.next_match()
    assert bar.match_label.text() == "Match 2 of 3"


def test_no_matches_shows_no_matches_label(qapp):
    bar, _ = make_bar("hello world")
    bar.search_field.setText("xyz")
    assert bar._matches == []
    assert bar.match_label.text() == "No matches"


def test_empty_search_clears_highlights_and_label(qapp):
    bar, widget = make_bar("cat cat")
    bar.search_field.setText("cat")
    assert widget.extraSelections() != []

    bar.search_field.setText("")
    assert widget.extraSelections() == []
    assert bar.match_label.text() == ""


def test_case_insensitive_by_default(qapp):
    bar, _ = make_bar("Cat cat CAT")
    bar.search_field.setText("cat")
    assert len(bar._matches) == 3


def test_case_sensitive_toggle_narrows_matches(qapp):
    bar, _ = make_bar("Cat cat CAT")
    bar.search_field.setText("cat")
    bar.case_checkbox.setChecked(True)
    assert len(bar._matches) == 1


def test_close_bar_hides_and_clears_highlights(qapp):
    bar, widget = make_bar("cat cat")
    bar.open_bar()
    bar.search_field.setText("cat")
    assert widget.extraSelections() != []

    bar.close_bar()

    assert bar.isVisible() is False
    assert widget.extraSelections() == []


def test_escape_key_closes_the_bar(qapp):
    bar, _ = make_bar("cat cat")
    bar.open_bar()
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    bar.search_field.keyPressEvent(event)
    assert bar.isVisible() is False


def test_shift_return_goes_to_previous_match(qapp):
    bar, _ = make_bar("cat cat cat")
    bar.search_field.setText("cat")
    assert bar._current_index == 0

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    bar.search_field.keyPressEvent(event)

    assert bar._current_index == 2  # wrapped to last, same as prev_match()
