"""A QLineEdit with its own independent up/down-arrow command history.

Each instance keeps its own history list -- used to give the dual
input boxes (Phase 6) separate recall, since they're semantically
different kinds of input (commands vs. poses/says).
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit


class HistoryLineEdit(QLineEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._history: List[str] = []
        self._history_index: int = 0
        self.returnPressed.connect(self._remember_current_text)

    def _remember_current_text(self) -> None:
        text = self.text()
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_index = len(self._history)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 -- Qt override
        if event.key() == Qt.Key.Key_Up:
            if self._history_index > 0:
                self._history_index -= 1
                self.setText(self._history[self._history_index])
            return
        if event.key() == Qt.Key.Key_Down:
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.setText(self._history[self._history_index])
            else:
                self._history_index = len(self._history)
                self.clear()
            return
        super().keyPressEvent(event)
