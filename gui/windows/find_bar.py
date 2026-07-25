"""Find/Search bar (Phase 11): highlights every match of a search term
in a QTextEdit-like widget (e.g. SessionTab.scrollback), with Prev/Next
navigation and a live match counter. Reusable -- takes any QTextEdit
(or QTextBrowser) rather than being hardcoded to one widget.

Highlights are applied via ``QTextEdit.setExtraSelections()`` --
verified directly against this PySide6 version before writing this
module, not assumed from memory: a non-destructive overlay Qt renders
on top of the real character formatting without altering the document
at all, trivially cleared by passing an empty list. An earlier external
planning doc's pseudocode called ``cursor.setCharFormat()`` directly,
which would have permanently overwritten -- not overlaid -- a match's
real ANSI-derived color/style, with no way back short of manually
recording and restoring every affected character's original format.
``setExtraSelections()`` is the correct, standard Qt idiom for exactly
this and was used instead.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

# All matches vs. the current match get distinct colors -- a single
# fixed, non-theme-aware choice, same simplification this codebase's
# other chrome-level color choices already make (e.g. MainWindow's
# ACTIVITY_COLOR) rather than threading theme info into this widget.
MATCH_COLOR = QColor(255, 235, 80)
CURRENT_MATCH_COLOR = QColor(255, 165, 0)


class _FindLineEdit(QLineEdit):
    """A plain QLineEdit that also reports Shift+Return and Escape --
    neither has a dedicated Qt signal of its own: ``returnPressed``
    fires for a bare Return regardless of modifiers (no way to tell
    Shift+Return apart from it), and QLineEdit has no ``escapePressed``
    signal at all.
    """

    shiftReturnPressed = Signal()
    escapePressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 -- Qt override
        if event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.shiftReturnPressed.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.escapePressed.emit()
            return
        super().keyPressEvent(event)


class FindBar(QWidget):
    """Hidden by default; ``open_bar()``/``close_bar()`` show/hide it.
    Search is live (updates on every keystroke), case-insensitive by
    default with a toggle, and wraps around at either end of the match
    list.
    """

    def __init__(self, text_widget: QTextEdit, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text_widget = text_widget
        self._matches: List[QTextCursor] = []
        self._current_index = -1

        self.search_field = _FindLineEdit(self)
        self.search_field.setPlaceholderText("Find...")
        self.search_field.textChanged.connect(self._search)
        self.search_field.returnPressed.connect(self.next_match)
        self.search_field.shiftReturnPressed.connect(self.prev_match)
        self.search_field.escapePressed.connect(self.close_bar)

        self.prev_button = QPushButton("<", self)
        self.prev_button.setToolTip("Previous match")
        self.prev_button.clicked.connect(self.prev_match)
        self.next_button = QPushButton(">", self)
        self.next_button.setToolTip("Next match")
        self.next_button.clicked.connect(self.next_match)
        self.close_button = QPushButton("×", self)
        self.close_button.setToolTip("Close")
        self.close_button.clicked.connect(self.close_bar)

        self.case_checkbox = QCheckBox("Aa", self)
        self.case_checkbox.setToolTip("Case-sensitive")
        self.case_checkbox.toggled.connect(self._search)

        self.match_label = QLabel("", self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(QLabel("Find:"))
        layout.addWidget(self.search_field)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.case_checkbox)
        layout.addWidget(self.match_label)
        layout.addWidget(self.close_button)

        self.hide()

    def open_bar(self) -> None:
        self.show()
        self.search_field.setFocus()
        self.search_field.selectAll()
        if self.search_field.text():
            self._search()

    def close_bar(self) -> None:
        self.hide()
        self._clear_highlights()

    def _search(self) -> None:
        term = self.search_field.text()
        self._matches = []
        self._current_index = -1
        if not term:
            self._clear_highlights()
            self._update_counter()
            return

        flags = QTextDocument.FindFlag(0)
        if self.case_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively

        document = self._text_widget.document()
        cursor = QTextCursor(document)
        while True:
            cursor = document.find(term, cursor, flags)
            if cursor.isNull():
                break
            self._matches.append(QTextCursor(cursor))

        if self._matches:
            self._current_index = 0
        self._highlight_all()
        self._update_counter()
        self._scroll_to_current()

    def next_match(self) -> None:
        if not self._matches:
            return
        self._current_index = (self._current_index + 1) % len(self._matches)
        self._highlight_all()
        self._update_counter()
        self._scroll_to_current()

    def prev_match(self) -> None:
        if not self._matches:
            return
        self._current_index = (self._current_index - 1) % len(self._matches)
        self._highlight_all()
        self._update_counter()
        self._scroll_to_current()

    def _scroll_to_current(self) -> None:
        if not self._matches or self._current_index < 0:
            return
        self._text_widget.setTextCursor(self._matches[self._current_index])
        self._text_widget.ensureCursorVisible()

    def _highlight_all(self) -> None:
        selections = []
        for i, cursor in enumerate(self._matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            fmt = selection.format
            fmt.setBackground(CURRENT_MATCH_COLOR if i == self._current_index else MATCH_COLOR)
            selection.format = fmt
            selections.append(selection)
        self._text_widget.setExtraSelections(selections)

    def _clear_highlights(self) -> None:
        self._text_widget.setExtraSelections([])

    def _update_counter(self) -> None:
        if not self._matches:
            self.match_label.setText("No matches" if self.search_field.text() else "")
        else:
            self.match_label.setText(f"Match {self._current_index + 1} of {len(self._matches)}")
