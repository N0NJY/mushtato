"""Text Editor (Phase 12): a standalone window for composing/saving
plain-text content (macros, triggers, drafts) -- independent of any one
connection. Supports multiple simultaneous windows (Rick's explicit
checkpoint choice, over the single-reused-window pattern every other
satellite window in this app -- Help/Address Book/Error Log -- uses),
matching the existing SpawnWindow precedent instead (MainWindow already
tracks a *list* of those, not a single slot).

Confirmed empirically before designing around it, not assumed: a real
script driving two separate QMainWindows showed
``QApplication.focusWidget()`` returns ``None`` the instant a
*different* top-level window (MainWindow) is activated -- which merely
opening MainWindow's own menu bar requires. So MainWindow's existing
Cut/Copy/Paste/Undo/Redo/Select-All focus-dispatch mechanism
(main_window.py's ``_dispatch_focused_edit_action``) cannot reach this
window's own text widget in real use, despite an external planning
doc's "existing implementation already handles focus, so should work
automatically" claim -- that claim does not hold, confirmed directly
rather than assumed either way. This window therefore owns its own
independent Edit menu, hardcoded directly to its own QPlainTextEdit's
methods -- not a parallel implementation of the same *mechanism* in the
sense CLAUDE.md rule 6 warns against, since there's only ever one
editable widget in this whole window (no focus-dispatch is even needed
the way MainWindow needs it across three different widgets). Same
reasoning for Find: a real, separate ``FindBar`` instance (verified
compatible with ``QPlainTextEdit`` directly -- ``FindBar`` only relies
on ``document()``/``setTextCursor()``/``ensureCursorVisible()``/
``setExtraSelections()``, all of which QPlainTextEdit implements with
the same signatures QTextEdit does, confirmed with a real script before
writing this module).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from engine.storage import drafts_dir

from ..fonts import resolve_editor_font
from .find_bar import FindBar


class _LineNumberArea(QWidget):
    def __init__(self, editor: "_EditorTextEdit") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        self._editor.paint_line_numbers(event)


class _EditorTextEdit(QPlainTextEdit):
    """QPlainTextEdit plus an optional line-number gutter -- the
    standard Qt "Code Editor" example pattern (a paintEvent-based side
    widget kept to this one file rather than split out further, since
    it's only ever used here).
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._line_number_area = _LineNumberArea(self)
        self._line_numbers_enabled = True
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)

    def set_line_numbers_enabled(self, enabled: bool) -> None:
        self._line_numbers_enabled = enabled
        self._line_number_area.setVisible(enabled)
        self._update_line_number_area_width(0)

    def line_number_area_width(self) -> int:
        if not self._line_numbers_enabled:
            return 0
        digits = len(str(max(1, self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(230, 230, 230))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(120, 120, 120))
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


class TextEditor(QMainWindow):
    closed = Signal()

    def __init__(
        self,
        host_window=None,  # MainWindow; None only in standalone tests -- see record_* methods
        *,
        font_family: str = "",
        font_size: int = 0,
        line_numbers: bool = True,
        word_wrap: bool = True,
        geometry: Optional[List[int]] = None,
        last_dir: str = "",
        drafts_dir_override: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.host_window = host_window
        self.current_file: Optional[Path] = None
        self.is_modified = False
        self._last_dir = last_dir
        self._drafts_dir_override = drafts_dir_override

        self.text_edit = _EditorTextEdit(self)
        self.text_edit.setFont(resolve_editor_font(font_family, font_size))
        self.text_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if word_wrap else QPlainTextEdit.LineWrapMode.NoWrap
        )
        self.text_edit.set_line_numbers_enabled(line_numbers)
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.text_edit.cursorPositionChanged.connect(self._update_status)

        # A real, independent FindBar (see this module's docstring for
        # why MainWindow's own tab-scoped find_action can't reach here).
        self.find_bar = FindBar(self.text_edit, self)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.find_bar)
        layout.addWidget(self.text_edit)
        self.setCentralWidget(central)

        self._build_menu(line_numbers, word_wrap)
        self._build_status_bar()

        if geometry and len(geometry) == 4:
            self.setGeometry(*geometry)
        else:
            self.resize(800, 600)

        self._update_title()
        self._update_status()

    # -- menu ---------------------------------------------------------

    def _build_menu(self, line_numbers: bool, word_wrap: bool) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        self.new_action = file_menu.addAction("New", self.new_file)
        self.new_action.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
        self.open_action = file_menu.addAction("Open...", self.open_file)
        self.open_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        self.save_action = file_menu.addAction("Save", self.save_file)
        self.save_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Save))
        self.save_as_action = file_menu.addAction("Save As...", self.save_file_as)
        self.save_as_action.setShortcut(QKeySequence(QKeySequence.StandardKey.SaveAs))
        file_menu.addSeparator()
        self.close_action = file_menu.addAction("Close", self.close)
        self.close_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Close))

        edit_menu = menu_bar.addMenu("&Edit")
        self.undo_action = edit_menu.addAction("Undo", self.text_edit.undo)
        self.undo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        self.redo_action = edit_menu.addAction("Redo", self.text_edit.redo)
        self.redo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Redo))
        edit_menu.addSeparator()
        self.cut_action = edit_menu.addAction("Cut", self.text_edit.cut)
        self.cut_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Cut))
        self.copy_action = edit_menu.addAction("Copy", self.text_edit.copy)
        self.copy_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Copy))
        self.paste_action = edit_menu.addAction("Paste", self.text_edit.paste)
        self.paste_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Paste))
        edit_menu.addSeparator()
        self.select_all_action = edit_menu.addAction("Select All", self.text_edit.selectAll)
        self.select_all_action.setShortcut(QKeySequence(QKeySequence.StandardKey.SelectAll))
        edit_menu.addSeparator()
        self.find_action = edit_menu.addAction("Find...", self._toggle_find)
        self.find_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Find))

        view_menu = menu_bar.addMenu("&View")
        self.line_numbers_action = view_menu.addAction("Line Numbers")
        self.line_numbers_action.setCheckable(True)
        self.line_numbers_action.setChecked(line_numbers)
        self.line_numbers_action.toggled.connect(self._on_line_numbers_toggled)
        self.word_wrap_action = view_menu.addAction("Word Wrap")
        self.word_wrap_action.setCheckable(True)
        self.word_wrap_action.setChecked(word_wrap)
        self.word_wrap_action.toggled.connect(self._on_word_wrap_toggled)

    def _build_status_bar(self) -> None:
        self.word_count_label = QLabel("Words: 0")
        self.line_count_label = QLabel("Lines: 1")
        self.char_count_label = QLabel("Chars: 0")
        self.cursor_pos_label = QLabel("Ln 1, Col 1")
        bar = self.statusBar()
        bar.addWidget(self.word_count_label)
        bar.addWidget(self.line_count_label)
        bar.addWidget(self.char_count_label)
        bar.addPermanentWidget(self.cursor_pos_label)

    def _toggle_find(self) -> None:
        # isHidden(), not isVisible() -- the exact same real bug already
        # found and fixed in SessionTab.toggle_find_bar() (Phase 11):
        # isVisible() depends on the whole ancestor chain actually being
        # on-screen, which headless tests (and, in principle, a
        # minimized window) would make false even when the bar is
        # logically "open."
        if self.find_bar.isHidden():
            self.find_bar.open_bar()
        else:
            self.find_bar.close_bar()

    # -- file operations ------------------------------------------------

    def _drafts_dir(self) -> Path:
        return self._drafts_dir_override if self._drafts_dir_override is not None else drafts_dir()

    def _default_dialog_dir(self) -> str:
        if self._last_dir:
            return self._last_dir
        # Created up front, matching SpawnWindow.save_spawnlog's same
        # precedent -- so the Open/Save dialog actually starts in the
        # real drafts directory instead of silently falling back
        # elsewhere because it doesn't exist yet.
        path = self._drafts_dir()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _remember_dir(self, filepath: str) -> None:
        directory = str(Path(filepath).parent)
        self._last_dir = directory
        if self.host_window is not None:
            self.host_window.record_editor_last_dir(directory)

    def _confirm_discard_if_modified(self, action_description: str) -> bool:
        """True if it's OK to proceed (nothing unsaved, or the user
        chose Save/Discard); False if the caller should abort (Cancel).
        """
        if not self.is_modified:
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"Save changes before {action_description}?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            return self.save_file()
        return reply == QMessageBox.StandardButton.No

    def new_file(self) -> None:
        if not self._confirm_discard_if_modified("creating a new file"):
            return
        self.text_edit.clear()
        self.current_file = None
        self.is_modified = False
        self._update_title()

    def open_file(self) -> None:
        if not self._confirm_discard_if_modified("opening another file"):
            return
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            self._default_dialog_dir(),
            "Text files (*.txt);;Macro files (*.macro);;All files (*)",
        )
        if not filepath:
            return
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Failed to open file: {exc}")
            return
        self.text_edit.setPlainText(content)
        self.current_file = Path(filepath)
        self.is_modified = False
        self._update_title()
        self._remember_dir(filepath)

    def save_file(self) -> bool:
        """Returns True if the save actually happened (or there was
        nothing to do), False if a Save As prompt was cancelled --
        callers needing to know whether it's safe to proceed (e.g.
        ``_confirm_discard_if_modified``) check this.
        """
        if self.current_file is None:
            return self.save_file_as()
        try:
            self.current_file.parent.mkdir(parents=True, exist_ok=True)
            self.current_file.write_text(self.text_edit.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Failed to save file: {exc}")
            return False
        self.is_modified = False
        self._update_title()
        self.statusBar().showMessage(f"Saved: {self.current_file}", 2000)
        return True

    def save_file_as(self) -> bool:
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            self._default_dialog_dir(),
            "Text files (*.txt);;Macro files (*.macro);;All files (*)",
        )
        if not filepath:
            return False
        self.current_file = Path(filepath)
        saved = self.save_file()
        if saved:
            self._remember_dir(filepath)
        return saved

    # -- status / title --------------------------------------------------

    def _update_title(self) -> None:
        name = self.current_file.name if self.current_file else "Untitled"
        marker = "*" if self.is_modified else ""
        self.setWindowTitle(f"Text Editor — {name}{marker}")

    def _on_text_changed(self) -> None:
        self.is_modified = True
        self._update_title()
        self._update_status()

    def _update_status(self) -> None:
        text = self.text_edit.toPlainText()
        words = len(text.split())
        lines = text.count("\n") + 1 if text else 1
        chars = len(text)
        self.word_count_label.setText(f"Words: {words}")
        self.line_count_label.setText(f"Lines: {lines}")
        self.char_count_label.setText(f"Chars: {chars}")
        cursor = self.text_edit.textCursor()
        self.cursor_pos_label.setText(f"Ln {cursor.blockNumber() + 1}, Col {cursor.columnNumber() + 1}")

    # -- view toggles / live settings ------------------------------------

    def _on_line_numbers_toggled(self, checked: bool) -> None:
        self.text_edit.set_line_numbers_enabled(checked)
        if self.host_window is not None:
            self.host_window.record_editor_line_numbers(checked)

    def _on_word_wrap_toggled(self, checked: bool) -> None:
        self.text_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if checked else QPlainTextEdit.LineWrapMode.NoWrap
        )
        if self.host_window is not None:
            self.host_window.record_editor_word_wrap(checked)

    def apply_font(self, family: str, size: int) -> None:
        """Live-reload hook, same pattern as SessionTab.apply_fonts --
        called by MainWindow when Settings' Editor Font changes while
        this window is already open.
        """
        self.text_edit.setFont(resolve_editor_font(family, size))

    # -- geometry persistence --------------------------------------------

    def moveEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().moveEvent(event)
        self._record_geometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self._record_geometry()

    def _record_geometry(self) -> None:
        if self.host_window is not None:
            g = self.geometry()
            self.host_window.record_editor_geometry([g.x(), g.y(), g.width(), g.height()])

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if not self._confirm_discard_if_modified("closing"):
            event.ignore()
            return
        self.closed.emit()
        super().closeEvent(event)
