"""A multi-line-capable command input box with its own independent
up/down-arrow command history.

Each instance keeps its own history list -- used to give the dual
input boxes (Phase 6) separate recall, since they're semantically
different kinds of input (commands vs. poses/says).

Originally a plain QLineEdit (single-line only). Rebuilt on
QPlainTextEdit to add real Potato-parity multi-line paste support (a
pasted block of several lines shows as several visible lines, not one
collapsed string) -- confirmed against Potato's own real source
(~/git/potato/potato.vfs/lib/potato.tcl) before designing this, not
assumed: Potato's own input window is a genuine multi-line Tk ``Text``
widget (class ``PotatoInput``); pasting into it is a completely generic
clipboard insert (``textPaste``, no line-splitting logic at all) --
showing multiple lines is just inherent multi-line-widget behavior, not
a special paste feature. The actual "send" mechanism
(``send_mushage``) grabs the *entire* current box content on Return,
clears the box, and sends it via ``process_input``, which splits on
"\\n" and processes/sends each resulting line separately. This class
mirrors that shape exactly; the actual per-line split-and-send lives in
SessionTab (``_split_input_lines``/``_on_primary_send``/
``_on_secondary_send``), since that's also where the existing
alias/command-processing pipeline for a single line already lives --
this class only owns the widget/history mechanics.

Kept as ``HistoryLineEdit`` (not renamed) despite the base class change
-- every external caller only ever needs "a box with history," and a
handful of QLineEdit-shaped compatibility methods below
(``text``/``setText``/``insert``/``selectedText``/``setCursorPosition``,
plus a synthesized ``returnPressed`` signal) mean every pre-existing
single-line caller keeps working completely unchanged; only genuinely
multi-line content (which only ever arrives via paste) exercises the
new behavior at all.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


class HistoryLineEdit(QPlainTextEdit):
    # QPlainTextEdit has no built-in equivalent of QLineEdit's
    # returnPressed -- emitted here on a plain Return/Enter (no
    # modifiers), the exact same "the user wants to send this" meaning
    # every existing caller (SessionTab's returnPressed.connect(...)
    # wiring, and every test that calls returnPressed.emit() directly)
    # already expects.
    returnPressed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._history: List[str] = []
        self._history_index: int = 0
        self.returnPressed.connect(self._remember_current_text)
        # Tab moves focus to the next widget rather than inserting a
        # literal tab character -- matches QLineEdit's own implicit
        # behavior, which this widget replaces.
        self.setTabChangesFocus(True)

    # -- QLineEdit-shaped compatibility surface --------------------------
    #
    # A deliberate, minimal shim, not a general-purpose QLineEdit
    # emulation layer: exactly the methods real callers (SessionTab and
    # the existing test suite) actually use, so single-line usage -- by
    # far the common case -- needs no changes anywhere else.

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, text: str) -> None:
        # Real QLineEdit.setText() moves the cursor to the end of the
        # new text -- QPlainTextEdit.setPlainText() does not (leaves it
        # at position 0), a real behavioral gap caught by a test
        # (typing/inserting after a programmatic setText() would have
        # landed at the *start* instead of continuing after it).
        self.setPlainText(text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def insert(self, text: str) -> None:
        self.insertPlainText(text)

    def selectedText(self) -> str:
        return self.textCursor().selectedText()

    def setCursorPosition(self, position: int) -> None:
        cursor = self.textCursor()
        cursor.setPosition(position)
        self.setTextCursor(cursor)

    # -- history -----------------------------------------------------------

    def _remember_current_text(self) -> None:
        self.remember(self.text())

    def remember(self, text: str) -> None:
        """Add ``text`` to this box's recall history without changing
        its currently displayed text -- used by Upload's "Add to
        History?" option, where lines are sent programmatically and
        never actually typed into this box.
        """
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_index = len(self._history)

    def _recall(self, text: str) -> None:
        self.setPlainText(text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def _on_first_line(self) -> bool:
        return self.textCursor().blockNumber() == 0

    def _on_last_line(self) -> bool:
        return self.textCursor().blockNumber() == self.document().blockCount() - 1

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 -- Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Shift+Return inserts a literal newline -- a deliberate
            # small addition beyond Potato's own real behavior (which
            # has no such escape hatch, confirmed against its source),
            # letting a multi-line block be typed directly rather than
            # only ever arriving via paste. Handled explicitly here
            # (not delegated to super()) -- confirmed directly, not
            # assumed, that plain QPlainTextEdit has no default binding
            # for Shift+Return at all (it inserts nothing); only a bare
            # Return is bound to "insert a newline" by default, which is
            # exactly why plain Return must be intercepted below rather
            # than left to fall through. Plain Return always sends,
            # matching Potato's own send_mushage exactly -- there's no
            # way to "just add a newline" with a bare Return, by design.
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.insertPlainText("\n")
                return
            self.returnPressed.emit()
            return
        # History recall only kicks in when the cursor is already on the
        # first/last line of whatever's currently in the box -- almost
        # always true (the box is normally empty or holds one line), so
        # this reduces to the exact original single-line behavior in the
        # common case. It only steps aside for genuine multi-line content
        # (which only ever arrives via paste, or the Shift+Return escape
        # hatch above), where Up/Down need to move the cursor between
        # those lines normally instead of recalling history.
        if event.key() == Qt.Key.Key_Up and not event.modifiers() and self._on_first_line():
            if self._history_index > 0:
                self._history_index -= 1
                self._recall(self._history[self._history_index])
            return
        if event.key() == Qt.Key.Key_Down and not event.modifiers() and self._on_last_line():
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self._recall(self._history[self._history_index])
            else:
                self._history_index = len(self._history)
                self.clear()
            return
        super().keyPressEvent(event)
