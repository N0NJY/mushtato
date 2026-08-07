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
independent Edit menu, dispatching to whichever tab is currently active
-- not a parallel implementation of the same *mechanism* in the sense
CLAUDE.md rule 6 warns against, since a window's own tab_widget already
knows exactly which tab is showing, unlike MainWindow's need to poll
QApplication-wide focus across three different widgets. Same reasoning
for Find: each tab gets its own real ``FindBar`` instance (verified
compatible with ``QPlainTextEdit`` directly -- ``FindBar`` only relies
on ``document()``/``setTextCursor()``/``ensureCursorVisible()``/
``setExtraSelections()``, all of which QPlainTextEdit implements with
the same signatures QTextEdit does, confirmed with a real script before
writing this module).

Multiple *tabs* per window (added later, on top of the above -- Rick's
own follow-up request): each open file is an independent ``_EditorFileTab``
(its own text widget, current_file, is_modified, and its own FindBar --
the same "per-tab, not shared" precedent SessionTab already established
for FindBar in Phase 11) held in a ``QTabWidget``. ``TextEditor`` keeps
``text_edit``/``current_file``/``is_modified``/``find_bar`` as properties
delegating to whichever tab is currently active, rather than renaming
them everywhere -- this is deliberate, not laziness: every pre-existing
caller/test that only ever dealt with one tab per window keeps working
unchanged, since "the current tab" is a strict superset of "the only
tab." New/Open no longer need an unsaved-changes prompt at all (a real,
deliberate simplification over the old single-tab design, not an
oversight) -- neither one can destroy another tab's content anymore,
since each file gets its own tab; the discard-confirmation prompt is
still very much used, just relocated to where content can actually be
lost: closing a single tab, or closing the whole window with any tab
still unsaved.

MainWindow's own multi-*window* behavior (Tools > Editor / the hotkey /
`/editor` always opening a brand-new independent TextEditor window) is
deliberately left untouched by this -- adding tabs to what's already an
open window is the literal, minimal-risk reading of "the ability to
open multiple tabs if I have more than one file," and doesn't relitigate
Rick's earlier, explicit multiple-windows checkpoint choice. Worth a
second look together once this is reviewed, in case the intent was
actually for a second file to land in an *already-open* editor window
rather than a new one -- flagging this assumption explicitly rather
than silently deciding it.
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from engine.storage import drafts_dir

from ..fonts import resolve_editor_font
from .find_bar import FindBar

_FILE_DIALOG_FILTER = "Text files (*.txt);;Macro files (*.macro);;All files (*)"


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


class _EditorFileTab(QWidget):
    """One open file's editing state within a tabbed TextEditor window:
    its own text widget, current file path, modified flag, and its own
    FindBar. Deliberately dumb -- it tracks its own text/modified state
    but has no idea it's inside a tab widget at all; TextEditor (the
    thing that actually owns the QTabWidget) is what reacts to changes
    here and updates tab labels/window title/status bar accordingly.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        font_family: str = "",
        font_size: int = 0,
        line_numbers: bool = True,
        word_wrap: bool = True,
    ) -> None:
        super().__init__(parent)
        self.current_file: Optional[Path] = None
        self.is_modified: bool = False

        self.text_edit = _EditorTextEdit(self)
        self.text_edit.setFont(resolve_editor_font(font_family, font_size))
        self.text_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if word_wrap else QPlainTextEdit.LineWrapMode.NoWrap
        )
        self.text_edit.set_line_numbers_enabled(line_numbers)
        self.text_edit.textChanged.connect(self._on_text_changed)

        # A real, independent FindBar per tab -- same "per-tab, not
        # shared" precedent as SessionTab.find_bar (Phase 11), so
        # searching in one open file never touches another's highlight
        # state.
        self.find_bar = FindBar(self.text_edit, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.find_bar)
        layout.addWidget(self.text_edit)

    def _on_text_changed(self) -> None:
        self.is_modified = True

    def display_name(self) -> str:
        name = self.current_file.name if self.current_file else "Untitled"
        marker = "*" if self.is_modified else ""
        return f"{name}{marker}"


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
        self._last_dir = last_dir
        self._drafts_dir_override = drafts_dir_override
        # Shared starting point for every tab in *this* window -- View
        # menu toggles and Settings-driven font changes apply to every
        # currently-open tab uniformly (see _on_line_numbers_toggled/
        # _on_word_wrap_toggled/apply_font), and to any tab opened
        # afterward, matching how there's only one View menu for the
        # whole window, not one per tab.
        self._font_family = font_family
        self._font_size = font_size
        self._line_numbers_enabled = line_numbers
        self._word_wrap_enabled = word_wrap

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab_at)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self.tab_widget)

        self._build_menu(line_numbers, word_wrap)
        self._build_status_bar()

        # Every window starts with exactly one blank tab -- there's
        # always something to edit/type into the moment the window
        # opens, same as the pre-tabs design's single always-present
        # text_edit.
        self.new_tab()

        if geometry and len(geometry) == 4:
            self.setGeometry(*geometry)
        else:
            self.resize(800, 600)

        self._update_title()
        self._update_status()

    # -- current-tab convenience properties -------------------------------
    #
    # Every pre-tabs caller (this module's own file-operation methods,
    # MainWindow, and most of the existing test suite) only ever dealt
    # with one tab per window and addressed it as editor.text_edit /
    # .current_file / .is_modified / .find_bar directly. Rather than
    # rename all of that to go through "the current tab" explicitly,
    # these delegate to whichever tab is active -- "the current tab" is
    # a strict superset of "the only tab," so every such caller keeps
    # working unchanged.

    def _current_tab(self) -> Optional[_EditorFileTab]:
        return self.tab_widget.currentWidget()

    @property
    def text_edit(self) -> _EditorTextEdit:
        tab = self._current_tab()
        assert tab is not None, "TextEditor always has at least one tab"
        return tab.text_edit

    @property
    def find_bar(self) -> FindBar:
        tab = self._current_tab()
        assert tab is not None, "TextEditor always has at least one tab"
        return tab.find_bar

    @property
    def current_file(self) -> Optional[Path]:
        tab = self._current_tab()
        return tab.current_file if tab is not None else None

    @current_file.setter
    def current_file(self, value: Optional[Path]) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.current_file = value
            self._refresh_tab_label(tab)

    @property
    def is_modified(self) -> bool:
        tab = self._current_tab()
        return tab.is_modified if tab is not None else False

    @is_modified.setter
    def is_modified(self, value: bool) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.is_modified = value
            self._refresh_tab_label(tab)

    # -- menu ---------------------------------------------------------

    def _build_menu(self, line_numbers: bool, word_wrap: bool) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        self.new_action = file_menu.addAction("New Tab", self.new_tab)
        self.new_action.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
        self.open_action = file_menu.addAction("Open...", self.open_file)
        self.open_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        self.save_action = file_menu.addAction("Save", self.save_file)
        self.save_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Save))
        self.save_as_action = file_menu.addAction("Save As...", self.save_file_as)
        self.save_as_action.setShortcut(QKeySequence(QKeySequence.StandardKey.SaveAs))
        file_menu.addSeparator()
        self.close_action = file_menu.addAction("Close Tab", self.close_current_tab)
        self.close_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Close))
        self.close_window_action = file_menu.addAction("Close Window", self.close)
        self.close_window_action.setShortcut(QKeySequence("Ctrl+Shift+W"))

        edit_menu = menu_bar.addMenu("&Edit")
        self.undo_action = edit_menu.addAction("Undo", self._dispatch_undo)
        self.undo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        self.redo_action = edit_menu.addAction("Redo", self._dispatch_redo)
        self.redo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Redo))
        edit_menu.addSeparator()
        self.cut_action = edit_menu.addAction("Cut", self._dispatch_cut)
        self.cut_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Cut))
        self.copy_action = edit_menu.addAction("Copy", self._dispatch_copy)
        self.copy_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Copy))
        self.paste_action = edit_menu.addAction("Paste", self._dispatch_paste)
        self.paste_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Paste))
        edit_menu.addSeparator()
        self.select_all_action = edit_menu.addAction("Select All", self._dispatch_select_all)
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
        tab = self._current_tab()
        if tab is None:
            return
        # isHidden(), not isVisible() -- the exact same real bug already
        # found and fixed in SessionTab.toggle_find_bar() (Phase 11):
        # isVisible() depends on the whole ancestor chain actually being
        # on-screen, which headless tests (and, in principle, a
        # minimized window) would make false even when the bar is
        # logically "open."
        if tab.find_bar.isHidden():
            tab.find_bar.open_bar()
        else:
            tab.find_bar.close_bar()

    # -- Edit menu dispatch: whichever tab is currently showing -----------
    #
    # Unlike MainWindow (three different widgets, needs real
    # QApplication-wide focus tracking to know which one to act on),
    # this window always knows exactly which tab is active via its own
    # tab_widget -- no focus polling needed.

    def _dispatch_undo(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.text_edit.undo()

    def _dispatch_redo(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.text_edit.redo()

    def _dispatch_cut(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.text_edit.cut()

    def _dispatch_copy(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.text_edit.copy()

    def _dispatch_paste(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.text_edit.paste()

    def _dispatch_select_all(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.text_edit.selectAll()

    # -- tabs -----------------------------------------------------------

    def _add_tab(self) -> _EditorFileTab:
        tab = _EditorFileTab(
            self.tab_widget,
            font_family=self._font_family,
            font_size=self._font_size,
            line_numbers=self._line_numbers_enabled,
            word_wrap=self._word_wrap_enabled,
        )
        tab.text_edit.textChanged.connect(lambda t=tab: self._on_tab_text_changed(t))
        tab.text_edit.cursorPositionChanged.connect(lambda t=tab: self._on_tab_cursor_changed(t))
        self.tab_widget.addTab(tab, tab.display_name())
        return tab

    def new_tab(self) -> _EditorFileTab:
        """Add a blank tab and switch to it.

        Deliberately never prompts to discard anything -- unlike the
        old single-tab design's New (which cleared the one-and-only
        text_edit in place), this can't lose any other tab's content,
        since it only ever adds a new one alongside whatever's already
        open.
        """
        tab = self._add_tab()
        self.tab_widget.setCurrentWidget(tab)
        return tab

    def close_current_tab(self) -> None:
        index = self.tab_widget.currentIndex()
        if index != -1:
            self.close_tab_at(index)

    def close_tab_at(self, index: int) -> None:
        """Close one tab (e.g. its own [x] button, or Close Tab),
        prompting to save first if it has unsaved changes. Closing the
        last remaining tab closes the whole window -- an editor window
        with zero tabs open isn't a useful state to leave sitting
        around, unlike MainWindow's own host window, which deliberately
        stays open at zero session tabs as the persistent root of the
        app; this window isn't that, it's a satellite document window.
        """
        tab = self.tab_widget.widget(index)
        if tab is None:
            return
        if not self._confirm_discard_if_modified(tab, "closing this tab"):
            return
        self.tab_widget.removeTab(index)
        tab.deleteLater()
        if self.tab_widget.count() == 0:
            self.close()

    def _on_current_tab_changed(self, _index: int) -> None:
        self._update_title()
        self._update_status()

    def _on_tab_text_changed(self, tab: _EditorFileTab) -> None:
        self._refresh_tab_label(tab)
        if tab is self._current_tab():
            self._update_status()

    def _on_tab_cursor_changed(self, tab: _EditorFileTab) -> None:
        if tab is self._current_tab():
            self._update_status()

    def _refresh_tab_label(self, tab: _EditorFileTab) -> None:
        index = self.tab_widget.indexOf(tab)
        if index != -1:
            self.tab_widget.setTabText(index, tab.display_name())
        if tab is self._current_tab():
            self._update_title()

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

    def _confirm_discard_if_modified(self, tab: _EditorFileTab, action_description: str) -> bool:
        """True if it's OK to proceed (nothing unsaved on this tab, or
        the user chose Save/Discard); False if the caller should abort
        (Cancel).
        """
        if not tab.is_modified:
            return True
        self.tab_widget.setCurrentWidget(tab)  # bring it into view so the prompt is contextual
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"Save changes before {action_description}?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            return self._save_tab(tab)
        return reply == QMessageBox.StandardButton.No

    def open_file(self) -> None:
        """Open a file into a tab.

        Reuses the current tab if it's still blank/untitled/unmodified
        (the common "just opened this window, haven't typed anything
        yet" case) rather than always adding a new tab -- otherwise
        every window would accumulate a permanently-empty leftover
        "Untitled" tab the first time you use Open. Never prompts to
        discard anything: an already-in-use current tab is left
        completely untouched, and the file opens into a fresh tab
        instead.
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open File", self._default_dialog_dir(), _FILE_DIALOG_FILTER
        )
        if not filepath:
            return
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Failed to open file: {exc}")
            return
        current = self._current_tab()
        if current is not None and current.current_file is None and not current.is_modified:
            tab = current
        else:
            tab = self._add_tab()
        tab.text_edit.setPlainText(content)
        tab.current_file = Path(filepath)
        tab.is_modified = False
        self.tab_widget.setCurrentWidget(tab)
        self._refresh_tab_label(tab)
        self._remember_dir(filepath)

    def save_file(self) -> bool:
        """Returns True if the save actually happened (or there was
        nothing to do), False if a Save As prompt was cancelled --
        callers needing to know whether it's safe to proceed (e.g.
        ``_confirm_discard_if_modified``) check this.
        """
        tab = self._current_tab()
        if tab is None:
            return True
        return self._save_tab(tab)

    def save_file_as(self) -> bool:
        tab = self._current_tab()
        if tab is None:
            return False
        return self._save_tab_as(tab)

    def _save_tab(self, tab: _EditorFileTab) -> bool:
        if tab.current_file is None:
            return self._save_tab_as(tab)
        try:
            tab.current_file.parent.mkdir(parents=True, exist_ok=True)
            tab.current_file.write_text(tab.text_edit.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Failed to save file: {exc}")
            return False
        tab.is_modified = False
        self._refresh_tab_label(tab)
        self.statusBar().showMessage(f"Saved: {tab.current_file}", 2000)
        return True

    def _save_tab_as(self, tab: _EditorFileTab) -> bool:
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save As", self._default_dialog_dir(), _FILE_DIALOG_FILTER
        )
        if not filepath:
            return False
        tab.current_file = Path(filepath)
        saved = self._save_tab(tab)
        if saved:
            self._remember_dir(filepath)
        return saved

    # -- status / title --------------------------------------------------

    def _update_title(self) -> None:
        tab = self._current_tab()
        if tab is None:
            self.setWindowTitle("Text Editor")
            return
        self.setWindowTitle(f"Text Editor — {tab.display_name()}")

    def _update_status(self) -> None:
        tab = self._current_tab()
        if tab is None:
            self.word_count_label.setText("Words: 0")
            self.line_count_label.setText("Lines: 1")
            self.char_count_label.setText("Chars: 0")
            self.cursor_pos_label.setText("Ln 1, Col 1")
            return
        text = tab.text_edit.toPlainText()
        words = len(text.split())
        lines = text.count("\n") + 1 if text else 1
        chars = len(text)
        self.word_count_label.setText(f"Words: {words}")
        self.line_count_label.setText(f"Lines: {lines}")
        self.char_count_label.setText(f"Chars: {chars}")
        cursor = tab.text_edit.textCursor()
        self.cursor_pos_label.setText(f"Ln {cursor.blockNumber() + 1}, Col {cursor.columnNumber() + 1}")

    # -- view toggles / live settings ------------------------------------

    def _on_line_numbers_toggled(self, checked: bool) -> None:
        self._line_numbers_enabled = checked
        for i in range(self.tab_widget.count()):
            self.tab_widget.widget(i).text_edit.set_line_numbers_enabled(checked)
        if self.host_window is not None:
            self.host_window.record_editor_line_numbers(checked)

    def _on_word_wrap_toggled(self, checked: bool) -> None:
        self._word_wrap_enabled = checked
        mode = QPlainTextEdit.LineWrapMode.WidgetWidth if checked else QPlainTextEdit.LineWrapMode.NoWrap
        for i in range(self.tab_widget.count()):
            self.tab_widget.widget(i).text_edit.setLineWrapMode(mode)
        if self.host_window is not None:
            self.host_window.record_editor_word_wrap(checked)

    def apply_font(self, family: str, size: int) -> None:
        """Live-reload hook, same pattern as SessionTab.apply_fonts --
        called by MainWindow when Settings' Editor Font changes while
        this window is already open. Applies to every currently-open
        tab in this window, and becomes the starting font for any tab
        opened afterward.
        """
        self._font_family = family
        self._font_size = size
        font = resolve_editor_font(family, size)
        for i in range(self.tab_widget.count()):
            self.tab_widget.widget(i).text_edit.setFont(font)

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
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if not self._confirm_discard_if_modified(tab, "closing"):
                event.ignore()
                return
        self.closed.emit()
        super().closeEvent(event)
