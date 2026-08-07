"""Headless tests for the Text Editor (Phase 12).

Every test passes drafts_dir_override (a tmp_path) -- the real
per-user drafts directory must never be touched by tests, the exact
leak class already caught once with world_script_path (Phase 9) and
again with logs_dir (Phase 11).
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPlainTextEdit

from gui.windows.text_editor_window import TextEditor


def make_editor(tmp_path: Path, **kwargs) -> TextEditor:
    return TextEditor(None, drafts_dir_override=tmp_path / "drafts", **kwargs)


# -- construction / basic state -------------------------------------------


def test_constructs_with_untitled_title(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    assert editor.windowTitle() == "Text Editor — Untitled"
    assert editor.is_modified is False
    assert editor.current_file is None


def test_typing_marks_modified_and_updates_title(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello")
    assert editor.is_modified is True
    assert editor.windowTitle() == "Text Editor — Untitled*"


def test_status_bar_counts_update_live(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello world\nsecond line")

    assert editor.word_count_label.text() == "Words: 4"
    assert editor.line_count_label.text() == "Lines: 2"
    assert editor.char_count_label.text() == "Chars: 23"


def test_cursor_position_label_updates(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello\nworld")
    cursor = editor.text_edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.text_edit.setTextCursor(cursor)

    assert editor.cursor_pos_label.text() == "Ln 2, Col 6"


# -- file operations: New Tab ------------------------------------------------
#
# New Tab never prompts to discard anything -- unlike the old single-tab
# design's New (which cleared the one-and-only text_edit in place), it
# can't lose any other tab's content, since it only ever adds a new tab
# alongside whatever's already open. See test_tabs.py-style coverage
# further down for the actual multi-tab behavior.


def test_new_tab_starts_blank_and_switches_to_it(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("existing content")

    editor.new_tab()

    assert editor.text_edit.toPlainText() == ""


def test_new_tab_never_prompts_and_preserves_other_tabs(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("draft content")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not prompt"))),
    )

    editor.new_tab()

    assert editor.tab_widget.count() == 2
    editor.tab_widget.setCurrentIndex(0)
    assert editor.text_edit.toPlainText() == "draft content"


# -- file operations: Open/Save/Save As ------------------------------------


def test_save_file_with_no_current_file_delegates_to_save_as(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello")
    target = tmp_path / "drafts" / "new.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )

    result = editor.save_file()

    assert result is True
    assert target.read_text(encoding="utf-8") == "hello"
    assert editor.current_file == target
    assert editor.is_modified is False
    assert editor.windowTitle() == "Text Editor — new.txt"


def test_save_file_as_cancelled_dialog_does_not_save(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    result = editor.save_file_as()

    assert result is False
    assert editor.current_file is None
    assert editor.is_modified is True


def test_save_file_creates_the_target_directory_if_missing(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello")
    editor.current_file = tmp_path / "nested" / "does" / "not" / "exist.txt"

    result = editor.save_file()

    assert result is True
    assert editor.current_file.read_text(encoding="utf-8") == "hello"


def test_save_file_dialog_defaults_to_drafts_dir(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello")
    captured = {}

    def fake_get_save_file_name(parent, caption, start, filter_):
        captured["start"] = start
        return "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_get_save_file_name))
    editor.save_file_as()

    assert captured["start"] == str(tmp_path / "drafts")
    assert (tmp_path / "drafts").is_dir()  # created up front


def test_open_file_loads_content_and_updates_title(qapp, tmp_path: Path, monkeypatch):
    source = tmp_path / "macro.txt"
    source.write_text("alias check=score", encoding="utf-8")
    editor = make_editor(tmp_path)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), ""))
    )

    editor.open_file()

    assert editor.text_edit.toPlainText() == "alias check=score"
    assert editor.current_file == source
    assert editor.is_modified is False
    assert editor.windowTitle() == "Text Editor — macro.txt"


def test_open_file_cancelled_dialog_does_nothing(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("existing")
    editor.is_modified = False  # simulate already-saved content, isolating just the dialog-cancel path
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))

    editor.open_file()

    assert editor.text_edit.toPlainText() == "existing"


def test_open_file_with_unsaved_current_tab_opens_a_new_tab_instead(qapp, tmp_path: Path, monkeypatch):
    # Never prompts: the current tab's unsaved content is left completely
    # untouched in its own tab rather than discarded, and the opened file
    # lands in a fresh tab alongside it.
    source = tmp_path / "macro.txt"
    source.write_text("new content", encoding="utf-8")
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("unsaved draft")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not prompt"))),
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), ""))
    )

    editor.open_file()

    assert editor.tab_widget.count() == 2
    assert editor.text_edit.toPlainText() == "new content"  # the new, now-active tab
    editor.tab_widget.setCurrentIndex(0)
    assert editor.text_edit.toPlainText() == "unsaved draft"  # untouched


def test_open_file_reuses_a_blank_untitled_current_tab(qapp, tmp_path: Path, monkeypatch):
    source = tmp_path / "macro.txt"
    source.write_text("new content", encoding="utf-8")
    editor = make_editor(tmp_path)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), ""))
    )

    editor.open_file()

    assert editor.tab_widget.count() == 1  # reused, not a second tab
    assert editor.text_edit.toPlainText() == "new content"


def test_remember_dir_updates_last_dir_and_notifies_host(qapp, tmp_path: Path, monkeypatch):
    calls = []

    class FakeHost:
        def record_editor_last_dir(self, directory):
            calls.append(directory)

        def record_editor_geometry(self, geometry):
            pass

    host = FakeHost()
    editor = TextEditor(host, drafts_dir_override=tmp_path / "drafts")
    editor.text_edit.setPlainText("hello")
    target = tmp_path / "customdir" / "file.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )

    editor.save_file_as()

    assert calls == [str(target.parent)]
    assert editor._last_dir == str(target.parent)


# -- close / unsaved-changes prompt on close -------------------------------


def test_close_with_unsaved_changes_prompts_and_cancel_ignores(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("unsaved")
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel)
    )

    closed = []
    editor.closed.connect(lambda: closed.append(1))
    editor.close()

    assert closed == []
    assert editor.isVisible() is False or editor.isHidden() is False  # window wasn't force-closed


def test_close_with_no_unsaved_changes_closes_cleanly(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    closed = []
    editor.closed.connect(lambda: closed.append(1))

    editor.close()

    assert closed == [1]


# -- multiple tabs in one window --------------------------------------------


def test_starts_with_exactly_one_tab(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    assert editor.tab_widget.count() == 1


def test_new_tab_adds_a_second_tab_labeled_untitled(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.new_tab()
    assert editor.tab_widget.count() == 2
    assert editor.tab_widget.tabText(1) == "Untitled"


def test_tabs_hold_independent_content(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("first file")
    editor.new_tab()
    editor.text_edit.setPlainText("second file")

    editor.tab_widget.setCurrentIndex(0)
    assert editor.text_edit.toPlainText() == "first file"
    editor.tab_widget.setCurrentIndex(1)
    assert editor.text_edit.toPlainText() == "second file"


def test_tab_label_shows_filename_and_modified_marker(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    assert editor.tab_widget.tabText(0) == "Untitled"

    editor.text_edit.setPlainText("hello")
    assert editor.tab_widget.tabText(0) == "Untitled*"

    editor.current_file = tmp_path / "notes.txt"
    editor.is_modified = False
    assert editor.tab_widget.tabText(0) == "notes.txt"


def test_window_title_and_status_bar_follow_the_active_tab(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("one two three")
    editor.new_tab()
    editor.text_edit.setPlainText("four five")

    assert editor.windowTitle() == "Text Editor — Untitled*"
    assert editor.word_count_label.text() == "Words: 2"

    editor.tab_widget.setCurrentIndex(0)
    assert editor.windowTitle() == "Text Editor — Untitled*"
    assert editor.word_count_label.text() == "Words: 3"


def test_undo_redo_cut_copy_paste_dispatch_to_the_active_tab_only(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("tab one")
    editor.new_tab()
    editor.text_edit.insertPlainText("tab two")  # setPlainText clears the undo stack, unlike insert

    editor.undo_action.trigger()  # should only affect the active (second) tab

    assert editor.text_edit.toPlainText() == ""
    editor.tab_widget.setCurrentIndex(0)
    assert editor.text_edit.toPlainText() == "tab one"


def test_find_bar_is_independent_per_tab(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.find_action.trigger()
    assert editor.find_bar.isHidden() is False

    editor.new_tab()
    assert editor.find_bar.isHidden() is True  # the new tab's own, untouched find bar

    editor.tab_widget.setCurrentIndex(0)
    assert editor.find_bar.isHidden() is False  # the first tab's find bar is still open


def test_line_numbers_and_word_wrap_toggles_apply_to_every_open_tab(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.new_tab()

    editor.line_numbers_action.setChecked(False)
    editor.word_wrap_action.setChecked(False)

    for i in range(editor.tab_widget.count()):
        tab = editor.tab_widget.widget(i)
        assert tab.text_edit.line_number_area_width() == 0
        assert tab.text_edit.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


def test_apply_font_changes_every_open_tab(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.new_tab()

    editor.apply_font("Courier New", 18)

    for i in range(editor.tab_widget.count()):
        tab = editor.tab_widget.widget(i)
        assert tab.text_edit.font().family() == "Courier New"
        assert tab.text_edit.font().pointSize() == 18


def test_closing_a_tab_with_no_unsaved_changes_removes_it(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.new_tab()
    assert editor.tab_widget.count() == 2

    editor.close_tab_at(1)

    assert editor.tab_widget.count() == 1


def test_closing_a_modified_tab_prompts_and_cancel_keeps_it_open(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.new_tab()
    editor.text_edit.setPlainText("unsaved")
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel)
    )

    editor.close_tab_at(1)

    assert editor.tab_widget.count() == 2


def test_closing_a_tab_never_affects_other_tabs_content(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("keep me")
    editor.new_tab()
    editor.text_edit.setPlainText("throwaway")
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )

    editor.close_tab_at(1)

    assert editor.tab_widget.count() == 1
    assert editor.text_edit.toPlainText() == "keep me"


def test_closing_the_last_tab_closes_the_whole_window(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    closed = []
    editor.closed.connect(lambda: closed.append(1))

    editor.close_tab_at(0)

    assert closed == [1]


def test_closing_window_with_one_unsaved_tab_among_several_prompts_only_for_that_one(
    qapp, tmp_path: Path, monkeypatch
):
    editor = make_editor(tmp_path)
    editor.new_tab()
    editor.text_edit.setPlainText("unsaved")
    prompted = []

    def fake_question(*a, **k):
        prompted.append(1)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    closed = []
    editor.closed.connect(lambda: closed.append(1))
    editor.close()

    assert prompted == [1]  # only the one modified tab, not the clean one
    assert closed == [1]


def test_closing_window_cancel_on_any_tab_aborts_the_whole_close(qapp, tmp_path: Path, monkeypatch):
    editor = make_editor(tmp_path)
    editor.new_tab()
    editor.text_edit.setPlainText("unsaved")
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel)
    )

    closed = []
    editor.closed.connect(lambda: closed.append(1))
    editor.close()

    assert closed == []
    assert editor.tab_widget.count() == 2  # nothing was torn down


# -- line numbers / word wrap -----------------------------------------------


def test_line_numbers_default_enabled(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    assert editor.line_numbers_action.isChecked() is True
    assert editor.text_edit.line_number_area_width() > 0


def test_toggling_line_numbers_off_zeroes_the_gutter_width(qapp, tmp_path: Path):
    editor = make_editor(tmp_path, line_numbers=True)
    editor.line_numbers_action.setChecked(False)
    assert editor.text_edit.line_number_area_width() == 0


def test_toggling_line_numbers_notifies_host(qapp, tmp_path: Path):
    calls = []

    class FakeHost:
        def record_editor_line_numbers(self, enabled):
            calls.append(enabled)

        def record_editor_geometry(self, geometry):
            pass

    editor = TextEditor(FakeHost(), drafts_dir_override=tmp_path / "drafts")
    editor.line_numbers_action.setChecked(False)

    assert calls == [False]


def test_word_wrap_default_enabled(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    assert editor.word_wrap_action.isChecked() is True
    assert editor.text_edit.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth


def test_toggling_word_wrap_off_changes_wrap_mode(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.word_wrap_action.setChecked(False)
    assert editor.text_edit.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


def test_toggling_word_wrap_notifies_host(qapp, tmp_path: Path):
    calls = []

    class FakeHost:
        def record_editor_word_wrap(self, enabled):
            calls.append(enabled)

        def record_editor_geometry(self, geometry):
            pass

    editor = TextEditor(FakeHost(), drafts_dir_override=tmp_path / "drafts")
    editor.word_wrap_action.setChecked(False)

    assert calls == [False]


def test_constructed_with_saved_line_numbers_and_word_wrap_preferences(qapp, tmp_path: Path):
    editor = make_editor(tmp_path, line_numbers=False, word_wrap=False)
    assert editor.line_numbers_action.isChecked() is False
    assert editor.text_edit.line_number_area_width() == 0
    assert editor.word_wrap_action.isChecked() is False
    assert editor.text_edit.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


# -- geometry persistence ---------------------------------------------------


def test_constructed_with_saved_geometry(qapp, tmp_path: Path):
    editor = make_editor(tmp_path, geometry=[50, 60, 700, 500])
    geo = editor.geometry()
    assert (geo.x(), geo.y(), geo.width(), geo.height()) == (50, 60, 700, 500)


def test_resizing_notifies_host_of_new_geometry(qapp, tmp_path: Path):
    # Confirmed directly (not assumed): the offscreen QPA platform only
    # delivers a resizeEvent for a top-level window's very *first*
    # resize while it's never been shown -- subsequent resizes are
    # silently dropped until show() is called. A real, visible window
    # resizes/fires normally; show() here just reproduces that in this
    # headless environment.
    calls = []

    class FakeHost:
        def record_editor_geometry(self, geometry):
            calls.append(geometry)

    editor = TextEditor(FakeHost(), drafts_dir_override=tmp_path / "drafts")
    editor.show()
    editor.resize(900, 650)

    assert calls  # at least one geometry update was recorded
    assert calls[-1][2] == 900
    assert calls[-1][3] == 650


# -- Edit menu (independent of MainWindow's, see module docstring) --------


def test_edit_menu_actions_operate_directly_on_this_editor_s_own_text(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello world")
    editor.select_all_action.trigger()
    editor.copy_action.trigger()

    assert qapp.clipboard().text() == "hello world"


def test_cut_action_removes_selected_text(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("hello world")
    editor.select_all_action.trigger()
    editor.cut_action.trigger()

    assert editor.text_edit.toPlainText() == ""
    assert qapp.clipboard().text() == "hello world"


def test_paste_action_inserts_clipboard_text(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    qapp.clipboard().setText("pasted text")
    editor.paste_action.trigger()

    assert editor.text_edit.toPlainText() == "pasted text"


def test_undo_action_reverts_the_last_change(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.insertPlainText("hello")
    editor.undo_action.trigger()

    assert editor.text_edit.toPlainText() == ""


# -- Find bar (independent of MainWindow's, see module docstring) ---------


def test_find_action_toggles_this_editor_s_own_find_bar(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    assert editor.find_bar.isHidden() is True

    editor.find_action.trigger()
    assert editor.find_bar.isHidden() is False

    editor.find_action.trigger()
    assert editor.find_bar.isHidden() is True


def test_find_bar_searches_this_editor_s_own_text(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.text_edit.setPlainText("the cat sat on the mat")
    editor.find_action.trigger()
    editor.find_bar.search_field.setText("cat")

    assert len(editor.find_bar._matches) == 1


# -- font live-reload --------------------------------------------------------


def test_apply_font_changes_the_text_edit_font(qapp, tmp_path: Path):
    editor = make_editor(tmp_path)
    editor.apply_font("Courier New", 18)

    assert editor.text_edit.font().family() == "Courier New"
    assert editor.text_edit.font().pointSize() == 18


# -- multiple independent windows (Rick's checkpoint choice) ---------------


def test_multiple_editor_windows_are_fully_independent(qapp, tmp_path: Path):
    editor_a = make_editor(tmp_path)
    editor_b = make_editor(tmp_path)

    editor_a.text_edit.setPlainText("window A content")
    editor_b.text_edit.setPlainText("window B content")

    assert editor_a.text_edit.toPlainText() == "window A content"
    assert editor_b.text_edit.toPlainText() == "window B content"
    assert editor_a is not editor_b


def test_closing_one_editor_window_does_not_affect_another(qapp, tmp_path: Path):
    editor_a = make_editor(tmp_path)
    editor_b = make_editor(tmp_path)

    editor_a.close()

    assert editor_b.text_edit is not None
    editor_b.text_edit.setPlainText("still works")
    assert editor_b.text_edit.toPlainText() == "still works"
